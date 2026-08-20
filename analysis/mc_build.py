#!/usr/bin/env python3
"""Build the multi-year price panel for the market-character study.

Reads the raw TenneT ISP day fragments cached by tools/dayahead/fetch_isp.py
(data/cache/isp_raw.jsonl) and re-parses them keeping ALL report columns, not
just shortage/surplus: regulation state, dispatch prices and the incident
reserve flags. Nothing is fetched here; the cache is read-only input, so this
script is safe to run while the fetcher is still appending and it is fully
offline afterwards.

Also normalises the day-ahead series (hourly and quarter-hourly) into the same
directory so the analysis script has one self-contained input set.

Outputs (tools/imbalance/data/mc/):
  isp_full.csv    ts_utc, buy_eur_mwh, sell_eur_mwh, dispatch_up_eur_mwh,
                  dispatch_down_eur_mwh, regulation_state,
                  incident_reserve_up, incident_reserve_down
  da_hourly.csv   ts_utc, eur_mwh
  da_q15.csv      ts_utc, eur_mwh
  build_report.json
"""
import html as htmllib
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "cache" / "isp_raw.jsonl"   # not shipped: see the note below
OUT = HERE / "cache"
TZ = ZoneInfo("Europe/Amsterdam")

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL_RE = re.compile(r'<td[^>]*headers="([^"]+)"[^>]*>(.*?)</td>', re.S)


def _num(cells, key):
    v = htmllib.unescape(cells.get(key, "")).strip()
    v = re.sub(r"<[^>]+>", "", v).strip()
    if not v:
        return float("nan")
    try:
        return float(v)
    except ValueError:
        return float("nan")


def _flag(cells, key):
    v = htmllib.unescape(cells.get(key, "")).strip()
    v = re.sub(r"<[^>]+>", "", v).strip().upper()
    return v in ("Y", "YES", "TRUE", "1", "J", "JA")


def expected_rows(day):
    lo = pd.Timestamp(day, tz=TZ)
    hi = pd.Timestamp(day + timedelta(days=1), tz=TZ)
    return int((hi - lo) / pd.Timedelta(minutes=15))


def parse_day(day, fragment):
    """-> DataFrame indexed by UTC ISP start, or raise ValueError."""
    recs = []
    for tr in ROW_RE.findall(fragment):
        cells = dict(CELL_RE.findall(tr))
        if "PTU" not in cells:
            continue
        ptu_raw = re.sub(r"<[^>]+>", "", htmllib.unescape(cells["PTU"])).strip()
        recs.append({
            "ptu": int(ptu_raw),
            "buy_eur_mwh": _num(cells, "PRICE_SHORTAGE"),
            "sell_eur_mwh": _num(cells, "PRICE_SURPLUS"),
            "dispatch_up_eur_mwh": _num(cells, "PRICE_DISPATCH_UP"),
            "dispatch_down_eur_mwh": _num(cells, "PRICE_DISPATCH_DOWN"),
            "regulation_state": _num(cells, "REGULATION_STATE"),
            "incident_reserve_up": _flag(cells, "IND_INCIDENT_RESERVE_UP"),
            "incident_reserve_down": _flag(cells, "IND_INCIDENT_RESERVE_DOWN"),
        })
    n_exp = expected_rows(day)
    if len(recs) != n_exp:
        raise ValueError(f"{day}: {len(recs)} rows, expected {n_exp}")
    if [r["ptu"] for r in recs] != list(range(1, n_exp + 1)):
        raise ValueError(f"{day}: PTU sequence not 1..{n_exp}")
    idx = pd.date_range(pd.Timestamp(day, tz=TZ), periods=n_exp,
                        freq="15min").tz_convert("UTC")
    df = pd.DataFrame(recs, index=idx).drop(columns=["ptu"])
    df.index.name = "ts_utc"
    return df


def load_cache():
    """date-string -> html. Tolerates a truncated final line (the fetcher may
    still be appending)."""
    if not RAW.exists():
        sys.exit(f"raw TenneT day-fragment cache not found: {RAW}\n"
             "The built panels ship in analysis/cache/*.csv.gz; this script is\n"
             "only needed to rebuild them from a fresh fetch.")
    out, bad = {}, 0
    with RAW.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            out[rec["date"]] = rec["html"]
    return out, bad


def build_isp():
    cached, bad_lines = load_cache()
    frames, failed = [], []
    for key in sorted(cached):
        day = pd.Timestamp(key).date()
        try:
            frames.append(parse_day(day, cached[key]))
        except (ValueError, KeyError) as exc:
            failed.append(f"{key}: {exc}")
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df, {"cache_days": len(cached), "bad_json_lines": bad_lines,
                "parse_failures": failed}


def load_da():
    """Prefer the multi-year caches; fall back to the shorter ones."""
    d = DAYAHEAD / "data"
    out = {}
    for key, names in (("hourly", ["da_prices_multiyear.csv", "da_prices.csv"]),
                       ("q15", ["da_q15_multiyear.csv", "da_prices_q15.csv"])):
        for n in names:
            p = d / n
            if p.exists():
                s = pd.read_csv(p, index_col=0, parse_dates=True)["eur_mwh"]
                s.index = pd.to_datetime(s.index, utc=True)
                s.index.name = "ts_utc"
                out[key] = (s.sort_index(), n)
                break
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    isp, meta = build_isp()
    isp.to_csv(OUT / "isp_full.csv")
    rep = dict(meta)
    rep["isp_rows"] = len(isp)
    rep["isp_range"] = [isp.index[0].isoformat(), isp.index[-1].isoformat()]
    rep["isp_gaps"] = int((isp.index.to_series().diff().dropna()
                           != pd.Timedelta("15min")).sum())
    rep["buy_ge_sell_pct"] = round(
        100.0 * (isp["buy_eur_mwh"] >= isp["sell_eur_mwh"]).mean(), 4)
    rep["reg_state_counts"] = {str(int(k)): int(v) for k, v in
                               isp["regulation_state"].value_counts().items()}
    rep["per_year_rows"] = {str(k): int(v) for k, v in
                            isp.groupby(isp.index.year).size().items()}

    da = load_da()
    for key, (s, src) in da.items():
        s.to_frame().to_csv(OUT / f"da_{key}.csv")
        rep[f"da_{key}_source"] = src
        rep[f"da_{key}_rows"] = len(s)
        rep[f"da_{key}_range"] = [s.index[0].isoformat(), s.index[-1].isoformat()]

    (OUT / "build_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2)[:4000])


if __name__ == "__main__":
    main()
