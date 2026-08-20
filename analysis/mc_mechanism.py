#!/usr/bin/env python3
"""Mechanism probes for the market-character study.

Three targeted tests that separate the candidate explanations for the
imbalance market's loss of dispersion:

  intrahour  Did the intra-hour price structure move from the imbalance
             market into the day-ahead market when NL day-ahead switched to a
             15-minute MTU on 2025-10-01? Measures the within-hour standard
             deviation of both series, month by month.
  dual       What does the dual-pricing wedge cost a battery that cycles?
             Priced per equivalent full cycle, per year.
  decomp     Is the compression a loss of extreme events or a narrowing of
             ordinary conditions? Splits the daily best-2h spread into a
             winsorised body and a tail contribution.

Reads data/mc/*.csv (built by mc_build.py). Writes data/mc/mechanism.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # repo root: opt.py, params.py, sched.py
from params import TZ   # noqa: E402

MC = HERE / "cache"


def _csv(name):
    """Prefer the gzipped panel shipped in the repo; fall back to plain CSV."""
    gz = MC / f"{name}.csv.gz"
    return gz if gz.exists() else MC / f"{name}.csv"
MTU15 = pd.Timestamp("2025-10-01", tz=TZ).tz_convert("UTC")
YEARS = [2023, 2024, 2025, 2026]


def load():
    isp = pd.read_csv(_csv("isp_full"), index_col=0, parse_dates=True)
    isp.index = pd.to_datetime(isp.index, utc=True)
    da_q = pd.read_csv(_csv("da_q15"), index_col=0, parse_dates=True)["eur_mwh"]
    da_q.index = pd.to_datetime(da_q.index, utc=True)
    return isp.sort_index(), da_q.sort_index()


def intrahour(isp, da_q):
    """Within-hour sd of the four quarter prices, monthly, both markets."""
    out = {}
    for name, s in (("imbalance_sell", isp["sell_eur_mwh"]),
                    ("day_ahead", da_q)):
        g = s.groupby([s.index.tz_convert(TZ).strftime("%Y-%m"),
                       s.index.floor("1h")])
        sd = g.std(ddof=0)
        m = sd.groupby(level=0).mean()
        out[name] = {k: round(float(v), 3) for k, v in m.items()}
    # year and pre/post 15-min-MTU aggregates
    agg = {}
    for name, s in (("imbalance_sell", isp["sell_eur_mwh"]),
                    ("day_ahead", da_q)):
        sd = s.groupby(s.index.floor("1h")).std(ddof=0)
        lo = sd.index.tz_convert(TZ)
        agg[name] = {
            **{str(y): round(float(sd[lo.year == y].mean()), 3)
               for y in YEARS if (lo.year == y).any()},
            "pre_15min_mtu": round(float(sd[sd.index < MTU15].mean()), 3),
            "post_15min_mtu": round(float(sd[sd.index >= MTU15].mean()), 3),
        }
    out["_aggregate"] = agg
    return out


def dual_cost(isp, cap=48.0, rt=0.93):
    """The dual-pricing wedge expressed as a cost per equivalent full cycle.

    A battery that charges in one ISP and discharges in another pays the buy
    (shortage) price and receives the sell (surplus) price. Where the two
    differ the wedge is a pure friction on cycling, structurally identical to a
    supplier fee. One EFC moves `cap` kWh out and cap/rt kWh in, so the wedge
    cost of a cycle is roughly cap x mean_wedge / 1000 EUR."""
    eta = np.sqrt(rt)
    out = {}
    for y in YEARS:
        m = isp.index.tz_convert(TZ).year == y
        if not m.any():
            continue
        sub = isp[m]
        w = (sub["buy_eur_mwh"] - sub["sell_eur_mwh"])
        dual = w > 1e-9
        out[str(y)] = {
            "dual_pct": round(float(100 * dual.mean()), 2),
            "wedge_mean_all_eur_mwh": round(float(w.mean()), 2),
            "wedge_median_when_dual": round(float(w[dual].median()), 2),
            "wedge_mean_when_dual": round(float(w[dual].mean()), 2),
            "wedge_p90_when_dual": round(float(w[dual].quantile(0.90)), 2),
            # cost of one full cycle if charge and discharge ISPs are drawn at
            # random from the year: cap kWh charged at buy, cap x eta^2 sold
            "eur_per_efc_at_mean_wedge": round(
                float(cap * w.mean() / 1000.0), 3),
            "eur_per_year_at_300_efc": round(
                float(300 * cap * w.mean() / 1000.0), 1),
        }
    return out


def decomp(isp):
    """Split the daily best-2h spread into a winsorised body and the tail."""
    out = {}
    df = isp.copy()
    df.index = df.index.tz_convert(TZ)
    for y in YEARS:
        sub = df[df.index.year == y]
        if len(sub) < 96 * 30:
            continue
        raw, win = [], []
        for _, g in sub.groupby(lambda t: t.date()):
            if len(g) < 16:
                continue
            s, b = g["sell_eur_mwh"].values, g["buy_eur_mwh"].values
            raw.append(np.sort(s)[-8:].mean() - np.sort(b)[:8].mean())
            sc = np.clip(s, -200, 200)
            bc = np.clip(b, -200, 200)
            win.append(np.sort(sc)[-8:].mean() - np.sort(bc)[:8].mean())
        raw, win = np.array(raw), np.array(win)
        out[str(y)] = {
            "n_days": int(len(raw)),
            "best2h_mean": round(float(raw.mean()), 1),
            "best2h_mean_winsorised_200": round(float(win.mean()), 1),
            "tail_contribution": round(float(raw.mean() - win.mean()), 1),
            "tail_share_pct": round(float(100 * (1 - win.mean() / raw.mean())), 1),
            "best2h_p25": round(float(np.percentile(raw, 25)), 1),
            "best2h_median": round(float(np.median(raw)), 1),
            "best2h_p75": round(float(np.percentile(raw, 75)), 1),
            "days_below_100": round(float(100 * (raw < 100).mean()), 1),
            "days_below_50": round(float(100 * (raw < 50).mean()), 1),
        }
    return out


def main():
    isp, da_q = load()
    res = {"intrahour": intrahour(isp, da_q),
           "dual_cost": dual_cost(isp),
           "decomp": decomp(isp)}
    (MC / "mechanism.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res["intrahour"]["_aggregate"], indent=2))
    print(json.dumps(res["dual_cost"], indent=2))
    print(json.dumps(res["decomp"], indent=2))


if __name__ == "__main__":
    main()
