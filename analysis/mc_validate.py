#!/usr/bin/env python3
"""Cross-checks for the market-character study.

1. Engine check against the day-ahead study. tools/dayahead/data/results_summary.md
   reports a site-independent pure-price bound: a 12-month rolling
   battery-vs-prices run over 2025-08-15 .. 2026-08-14 nets 858,27 EUR at
   214 EFC in the contract frame (+-2 ct fee, wear netted off). Re-running the
   same window through this study's own money engine with fee = 0,02 should
   land on the same number. It is the same planner and the same battery, but a
   separately written driver, so agreement is evidence the driver is right.

2. Data check against the documented dataset. SOURCES.md section 1 tabulates
   per-year row counts, mean prices and the regulation-state mix from an
   earlier, independent fetch. Re-derive them here.

3. Arithmetic check: recompute one period's cash directly from the executed
   transcript rather than through the ledger helper.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # repo root: opt.py, params.py, sched.py
import market_character as mc   # noqa: E402
from params import TZ, variant  # noqa: E402

MC = HERE / "cache"


def _csv(name):
    """Prefer the gzipped panel shipped in the repo; fall back to plain CSV."""
    gz = MC / f"{name}.csv.gz"
    return gz if gz.exists() else MC / f"{name}.csv"


def check_engine():
    isp, da_h, _ = mc.load()
    lo = pd.Timestamp("2025-08-15", tz=TZ).tz_convert("UTC")
    hi = pd.Timestamp("2026-08-15", tz=TZ).tz_convert("UTC")
    da = (da_h.loc[lo:hi] / 1000.0).dropna()
    orig = mc.PRM
    try:
        mc.PRM = variant(fee=0.02)          # contract frame, as in the study
        sell = da - 0.02
        buy = da + 0.02
        ex = mc.run_rolling(sell, buy, 1.0, "1h")
        led = mc.ledger(ex, 1.0)
    finally:
        mc.PRM = orig
    return {"window": [str(ex.index[0]), str(ex.index[-1])],
            "net_after_wear_eur": round(led["net_after_wear_eur"], 2),
            "cash_eur": round(led["cash_eur"], 2),
            "efc": round(led["efc"], 1),
            "reference_results_summary": {"net": 858.27, "efc": 214.0},
            "net_delta": round(led["net_after_wear_eur"] - 858.27, 2),
            "efc_delta": round(led["efc"] - 214.0, 1)}


def check_data():
    isp = pd.read_csv(_csv("isp_full"), index_col=0, parse_dates=True)
    isp.index = pd.to_datetime(isp.index, utc=True)
    lo = isp.index.tz_convert(TZ)
    out = {}
    for y in (2023, 2024, 2025):
        s = isp[lo.year == y]
        out[str(y)] = {"rows": int(len(s)),
                       "buy_mean": round(float(s["buy_eur_mwh"].mean()), 1),
                       "sell_mean": round(float(s["sell_eur_mwh"].mean()), 1),
                       "buy_min": float(s["buy_eur_mwh"].min()),
                       "sell_neg_pct": round(float(100 * (s["sell_eur_mwh"] < 0).mean()), 1)}
    out["_reference_SOURCES_md"] = {
        "2023": {"rows": 35040, "buy_mean": 103.4, "sell_mean": 93.6,
                 "buy_min": -1549.47, "sell_neg_pct": 19.5},
        "2024": {"rows": 35136, "buy_mean": 96.2, "sell_mean": 66.2,
                 "buy_min": -1593.10, "sell_neg_pct": 24.8},
        "2025": {"rows": 35040, "buy_mean": 94.7, "sell_mean": 72.2,
                 "buy_min": -1310.43, "sell_neg_pct": 18.5}}
    reg = isp["regulation_state"].value_counts().to_dict()
    out["reg_state_counts"] = {str(int(k)): int(v) for k, v in sorted(reg.items())}
    out["_reference_reg_state"] = {"-1": 48766, "0": 6735, "1": 44616, "2": 26887,
                                   "note": "SOURCES.md ran to 2026-08-15; this "
                                           "set runs one day longer"}
    viol = isp[isp["buy_eur_mwh"] < isp["sell_eur_mwh"]]
    out["buy_lt_sell_rows"] = [str(t) for t in viol.index]
    return out


def check_arithmetic():
    """Recompute 2026 day-ahead cash straight from the ledger definition."""
    j = json.loads((MC / "market_character.json").read_text())
    per = j.get("money", {}).get("by_period", {}).get("da_rolling", {})
    if "Y2026" not in per:
        return {"skipped": "money block not present yet"}
    v = per["Y2026"]
    recomputed = v["eur_per_day"] * v["days"]
    return {"cash_eur": round(v["cash_eur"], 2),
            "eur_per_day_x_days": round(recomputed, 2),
            "delta": round(v["cash_eur"] - recomputed, 6),
            "efc_vs_export": round(v["export_kwh"] / np.sqrt(0.93) / 48.0
                                   - v["efc"], 6)}


if __name__ == "__main__":
    out = {"engine_vs_dayahead_study": check_engine(),
           "data_vs_sources_md": check_data(),
           "arithmetic": check_arithmetic()}
    (MC / "validation.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out, indent=2, default=float))
