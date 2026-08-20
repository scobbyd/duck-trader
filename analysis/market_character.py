#!/usr/bin/env python3
"""Did the Dutch imbalance market change character for battery trading?

Year-by-year (2023 for context, then 2024, 2025, 2026-to-date) comparison of
the settled TenneT imbalance market against the NL day-ahead market, from the
point of view of a 48 kWh / 10 kW home battery traded on price signals only.

Blocks:
  dispersion  distributional / opportunity statistics per market per period
  money       a prices-only battery run under several strategies, one
              continuous pass per strategy over the whole span, sliced
              afterwards into years, Mar-Aug seasons, quarters and months
  predict     autocorrelation and persistence skill of the imbalance price

Inputs are the cached CSVs written by mc_build.py; nothing is fetched, so the
whole thing re-runs offline. Battery physics and the MILP come from
tools/dayahead/ (opt.py, params.py, sched.py) unmodified.

Usage:
  python3 mc_build.py                 # rebuild data/mc/*.csv from the raw cache
  python3 market_character.py all     # -> data/mc/market_character.json
  python3 market_character.py dispersion | money | predict
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # repo root: opt.py, params.py, sched.py

import opt            # noqa: E402
import sched          # noqa: E402
from params import TZ, variant   # noqa: E402

MC = HERE / "cache"


def _csv(name):
    """Prefer the gzipped panel shipped in the repo; fall back to plain CSV."""
    gz = MC / f"{name}.csv.gz"
    return gz if gz.exists() else MC / f"{name}.csv"
OUTJSON = MC / "market_character.json"

# Raw frame per the owner's convention: bare market prices, no supplier fee.
# The cycle write-off stays inside the optimiser objective (it is what keeps
# thin cycles out of the plan) and is reported as a separate wear ledger,
# never netted off the headline cash.
PRM = variant(fee=0.0)
ETA = np.sqrt(PRM.rt)

YEARS = [2023, 2024, 2025, 2026]
SEASON = (3, 8)          # Mar-Aug, the owner's comparison window
TAILS = (200.0, 500.0)   # EUR/MWh

REACT_GRID = [(0.10, 0.90), (0.20, 0.80), (0.25, 0.75), (0.30, 0.70),
              (0.35, 0.65), (0.40, 0.60), (0.45, 0.55), (0.50, 0.50)]
REACT_FIXED = (0.25, 0.75)   # the one parameter set held constant across years


# ---------------------------------------------------------------- data ----

def load():
    isp = pd.read_csv(_csv("isp_full"), index_col=0, parse_dates=True)
    isp.index = pd.to_datetime(isp.index, utc=True)
    isp = isp.sort_index()
    isp = isp[~isp.index.duplicated(keep="first")]
    da_h = pd.read_csv(_csv("da_hourly"), index_col=0, parse_dates=True)["eur_mwh"]
    da_h.index = pd.to_datetime(da_h.index, utc=True)
    da_q = None
    p = _csv("da_q15")
    if p.exists():
        da_q = pd.read_csv(p, index_col=0, parse_dates=True)["eur_mwh"]
        da_q.index = pd.to_datetime(da_q.index, utc=True)
        da_q = da_q.sort_index()
    return isp, da_h.sort_index(), da_q


def local(idx):
    return idx.tz_convert(TZ)


def slices(idx):
    """label -> boolean mask, for every reporting period."""
    lo = local(idx)
    out = {}
    for y in YEARS:
        m = (lo.year == y)
        if m.sum():
            out[f"Y{y}"] = m
            s = m & (lo.month >= SEASON[0]) & (lo.month <= SEASON[1])
            if s.sum():
                out[f"S{y}"] = s          # Mar-Aug, seasonal control
            for q in (1, 2, 3, 4):
                qm = m & (lo.quarter == q)
                if qm.sum():
                    out[f"Q{y}Q{q}"] = qm
    ymk = lo.strftime("%Y-%m")
    for k in pd.unique(ymk):
        out[f"M{k}"] = (ymk == k)
    return out


def da_on_isp_grid(da_h, da_q, idx):
    """Day-ahead price on the ISP grid: native 15-min slots where the market
    had them (NL day-ahead moved to a 15-min MTU on 2025-10-01), hourly price
    step-held across the four quarters before that."""
    base = da_h.reindex(da_h.index.union(idx)).ffill().reindex(idx)
    if da_q is not None and len(da_q):
        base = da_q.reindex(idx).combine_first(base)
    return base


# ---------------------------------------------------- block 1: dispersion --

def _best_n_spread(sell, buy, idx, n_isp=8):
    """Per local day: mean of the n dearest sell slots minus mean of the n
    cheapest buy slots. n_isp = 8 ISPs = 2 h, roughly the energy a
    48 kWh / 10 kW battery moves in one direction. This is the spread a
    battery can actually monetise, unlike the single max-min tick."""
    df = pd.DataFrame({"sell": sell, "buy": buy}, index=local(idx))
    out = {}
    for day, g in df.groupby(lambda t: t.date()):
        if len(g) < 2 * n_isp:
            continue
        out[day] = (np.sort(g["sell"].values)[-n_isp:].mean()
                    - np.sort(g["buy"].values)[:n_isp].mean())
    return pd.Series(out)


def dispersion_one(sell, buy, idx, da=None, reg=None, n_isp=8):
    d = {"n": int(len(sell))}
    for name, v in (("sell", sell), ("buy", buy)):
        d[f"{name}_mean"] = float(np.mean(v))
        d[f"{name}_median"] = float(np.median(v))
        d[f"{name}_sd"] = float(np.std(v, ddof=1))
        d[f"{name}_p05"] = float(np.percentile(v, 5))
        d[f"{name}_p95"] = float(np.percentile(v, 95))
        d[f"{name}_iqr"] = float(np.percentile(v, 75) - np.percentile(v, 25))
        d[f"{name}_neg_pct"] = float(100.0 * np.mean(v <= 0))
        for t in TAILS:
            d[f"{name}_abs_gt{int(t)}_pct"] = float(100.0 * np.mean(np.abs(v) > t))
    s = pd.Series(sell, index=local(idx))
    g = s.groupby(lambda t: t.date())
    rng = g.max() - g.min()
    d["daily_range_sell_mean"] = float(rng.mean())
    d["daily_range_sell_median"] = float(rng.median())
    bn = _best_n_spread(sell, buy, idx, n_isp)
    d["best2h_spread_mean"] = float(bn.mean())
    d["best2h_spread_median"] = float(bn.median())
    d["best2h_spread_p25"] = float(bn.quantile(0.25))
    dd = s.groupby(lambda t: t.date()).diff().dropna()
    d["step_abs_diff_mean"] = float(dd.abs().mean())
    d["step_abs_diff_median"] = float(dd.abs().median())
    dual = buy > sell + 1e-9
    d["dual_priced_pct"] = float(100.0 * np.mean(dual))
    d["dual_spread_mean_when_dual"] = (float(np.mean((buy - sell)[dual]))
                                       if dual.any() else 0.0)
    d["dual_spread_mean_all"] = float(np.mean(buy - sell))
    if reg is not None:
        vc = pd.Series(reg).value_counts(normalize=True) * 100.0
        d["reg_state_pct"] = {str(int(k)): round(float(v), 2)
                              for k, v in sorted(vc.items())}
    if da is not None:
        dev = np.asarray(sell, float) - np.asarray(da, float)
        ok = np.isfinite(dev)
        if ok.sum() > 100:
            dv = dev[ok]
            d["dev_vs_da_n"] = int(ok.sum())
            d["dev_vs_da_mean"] = float(np.mean(dv))
            d["dev_vs_da_median"] = float(np.median(dv))
            d["dev_vs_da_mad"] = float(np.mean(np.abs(dv)))
            d["dev_vs_da_sd"] = float(np.std(dv, ddof=1))
            d["dev_vs_da_p05"] = float(np.percentile(dv, 5))
            d["dev_vs_da_p95"] = float(np.percentile(dv, 95))
            d["dev_vs_da_neg_pct"] = float(100.0 * np.mean(dv < 0))
            daa = np.asarray(da, float)[ok]
            if np.std(daa) > 0:
                d["corr_sell_da"] = float(np.corrcoef(np.asarray(sell, float)[ok],
                                                      daa)[0, 1])
    return d


def block_dispersion(isp, da_h, da_q):
    da_i = da_on_isp_grid(da_h, da_q, isp.index)
    sl = slices(isp.index)
    out = {"imbalance": {}, "day_ahead": {}}
    for label, m in sl.items():
        sub = isp[m]
        if len(sub) < 96 * 20:
            continue
        out["imbalance"][label] = dispersion_one(
            sub["sell_eur_mwh"].values, sub["buy_eur_mwh"].values, sub.index,
            da=da_i[m].values, reg=sub["regulation_state"].values)
        v = da_i[m].dropna()
        if len(v) >= 96 * 20:
            out["day_ahead"][label] = dispersion_one(v.values, v.values, v.index)
    return out


# --------------------------------------------------------- block 2: money --

def _lam_end(sell_ser, t0):
    win = sell_ser.loc[t0 - pd.Timedelta(days=7):t0].dropna()
    med = float(win.median()) if len(win) else 0.08
    return max(0.0, PRM.lam_end_frac * ETA * med)


def run_rolling(sell, buy, dt, freq):
    """Rolling daily 13:00-local MILP, 36 h horizon, 24 h executed, SOC carried
    continuously across the whole span.

    With day-ahead prices this is exactly implementable (D+1 is published at
    12:45, so there is no forecast error on the price side at all). With
    imbalance prices it is a perfect-foresight ceiling, since ISP prices only
    settle after the fact. Identical horizon structure for both markets so the
    two are compared like for like."""
    lo = local(sell.index)
    days = sorted({d for d in lo.date})[:-1]
    soc = PRM.soc_min
    rows, n_fail = [], 0
    for day in days:
        t0, hz, exec_end = sched.plan_horizon(day, freq=freq)
        # Index.isin, not np.isin: a tz-aware DatetimeIndex degrades to an
        # object array under numpy, making np.isin ~500x slower here.
        hz = hz[hz.isin(sell.index)]
        if len(hz) < 4:
            continue
        s_v, b_v = sell.loc[hz].values, buy.loc[hz].values
        if not (np.all(np.isfinite(s_v)) and np.all(np.isfinite(b_v))):
            continue
        r = opt.plan(s_v, b_v, *[np.zeros(len(hz))] * 3, soc, PRM,
                     _lam_end(sell, t0), dt=dt)
        if not r["ok"]:
            n_fail += 1
            continue
        ex = hz < exec_end
        c, d, ts = r["c"][ex], r["d"][ex], hz[ex]
        soc = soc + (ETA * c.sum() * dt) - (d.sum() * dt / ETA)
        rows.append(pd.DataFrame({"c": c, "d": d,
                                  "sell": sell.loc[ts].values,
                                  "buy": buy.loc[ts].values}, index=ts))
    ex = pd.concat(rows)
    ex.attrs["dt"] = dt
    ex.attrs["n_plan_fail"] = n_fail
    return ex


def run_reactive(sell, buy, dt, q_lo, q_hi, win_days=7, lag=1, gate=0.0):
    """Causal trailing-quantile reactive rule — the honest imbalance proxy.

    Imbalance prices are not knowable ahead, so a real passive-imbalance player
    reacts to the price signal it can see. A trailing `win_days` window of
    settled sell prices, ending strictly before the step being decided, gives a
    reference band (q_lo, q_hi). With lag=1 the decision for ISP t uses the
    price of ISP t-1, which is what a settled-price feed supports; lag=0 uses
    the current ISP's own price, standing in for a perfect live intra-ISP
    estimate — an optimistic bound on the same rule.

    Every trade must clear its own round trip and wear: charging needs
    hi*eta - buy/eta - c_deg > gate, discharging sell*eta - lo/eta - c_deg > gate.
    """
    n = len(sell)
    s, b = sell.values, buy.values
    w = max(4, int(win_days * 24 / dt))
    ref = sell.rolling(w, min_periods=w // 4)
    lo_b = np.concatenate([[np.nan], ref.quantile(q_lo).values[:-1]])
    hi_b = np.concatenate([[np.nan], ref.quantile(q_hi).values[:-1]])
    sig_s = np.concatenate([[np.nan] * lag, s[:n - lag]]) if lag else s
    sig_b = np.concatenate([[np.nan] * lag, b[:n - lag]]) if lag else b

    soc = PRM.soc_min
    c = np.zeros(n)
    d = np.zeros(n)
    cdeg = PRM.c_deg
    for t in range(n):
        lo, hi, ps, pb = lo_b[t], hi_b[t], sig_s[t], sig_b[t]
        if not (np.isfinite(lo) and np.isfinite(hi)
                and np.isfinite(ps) and np.isfinite(pb)):
            continue
        if pb <= lo and hi * ETA - pb / ETA - cdeg > gate:
            c[t] = max(0.0, min(PRM.p_kw, (PRM.soc_max - soc) / (ETA * dt)))
            soc += ETA * c[t] * dt
        elif ps >= hi and ps * ETA - lo / ETA - cdeg > gate:
            d[t] = max(0.0, min(PRM.p_kw, (soc - PRM.soc_min) * ETA / dt))
            soc -= d[t] * dt / ETA
    ex = pd.DataFrame({"c": c, "d": d, "sell": s, "buy": b}, index=sell.index)
    ex.attrs["dt"] = dt
    return ex


def ledger(ex, dt):
    cash = float((ex["sell"] * ex["d"] * dt - ex["buy"] * ex["c"] * dt).sum())
    dch_cell = float((ex["d"] * dt / ETA).sum())
    efc = dch_cell / PRM.cap
    days = len(ex) * dt / 24.0
    out = {"cash_eur": cash, "wear_eur": efc * PRM.cycle_eur,
           "net_after_wear_eur": cash - efc * PRM.cycle_eur, "efc": efc,
           "import_kwh": float((ex["c"] * dt).sum()),
           "export_kwh": float((ex["d"] * dt).sum()),
           "n_steps": int(len(ex)), "days": days}
    if days > 0:
        out["eur_per_day"] = cash / days
        out["eur_per_year"] = cash / days * 365.25
        out["eur_per_kwh_batt_per_year"] = out["eur_per_year"] / PRM.cap
        out["efc_per_year"] = efc / days * 365.25
    return out


def _job(spec):
    """One strategy, run continuously over its whole span (worker process)."""
    kind, name, payload = spec
    t = time.time()
    if kind == "rolling":
        sell, buy, dt, freq = payload
        ex = run_rolling(sell, buy, dt, freq)
    else:
        sell, buy, dt, kw = payload
        ex = run_reactive(sell, buy, dt, **kw)
    return name, ex["c"].values, ex["d"].values, ex["sell"].values, \
        ex["buy"].values, ex.index, ex.attrs.get("dt", 1.0), round(time.time() - t, 1)


def block_money(isp, da_h, da_q, workers=8):
    i_sell = isp["sell_eur_mwh"] / 1000.0
    i_buy = isp["buy_eur_mwh"] / 1000.0
    # granularity control: the same imbalance prices averaged to hourly, so
    # the 15-min advantage of the ISP grid can be separated from the market
    hh = isp[["sell_eur_mwh", "buy_eur_mwh"]].resample("1h").mean().dropna()
    i_h, i_hb = hh["sell_eur_mwh"] / 1000.0, hh["buy_eur_mwh"] / 1000.0
    d_h = (da_h / 1000.0).dropna()

    jobs = [
        ("rolling", "imb_perfect", (i_sell, i_buy, 0.25, "15min")),
        ("rolling", "imb_perfect_singleprice", (i_sell, i_sell, 0.25, "15min")),
        ("rolling", "imb_perfect_hourly_ctrl", (i_h, i_hb, 1.0, "1h")),
        ("rolling", "da_rolling", (d_h, d_h, 1.0, "1h")),
    ]
    if da_q is not None and len(da_q) > 96 * 30:
        d_q = (da_q / 1000.0).dropna()
        jobs.append(("rolling", "da_rolling_q15", (d_q, d_q, 0.25, "15min")))
    for a, b in REACT_GRID:
        jobs.append(("react", f"imb_react_{a:.2f}_{b:.2f}",
                     (i_sell, i_buy, 0.25, {"q_lo": a, "q_hi": b, "lag": 1})))
    jobs.append(("react", "imb_react_live_bound",
                 (i_sell, i_buy, 0.25,
                  {"q_lo": REACT_FIXED[0], "q_hi": REACT_FIXED[1], "lag": 0})))

    execs = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for name, c, d, s, b, idx, dt, el in pool.map(_job, jobs):
            execs[name] = (pd.DataFrame({"c": c, "d": d, "sell": s, "buy": b},
                                        index=idx), dt)
            print(f"  {name}: {el}s", flush=True)

    sl = slices(isp.index)
    out = {"totals": {}, "by_period": {}}
    for name, (ex, dt) in execs.items():
        out["totals"][name] = ledger(ex, dt)
        per = {}
        exsl = slices(ex.index)
        for label, m in exsl.items():
            sub = ex[m]
            if len(sub) * dt / 24.0 < 20:
                continue
            per[label] = ledger(sub, dt)
        out["by_period"][name] = per
    out["_fixed_reactive"] = f"imb_react_{REACT_FIXED[0]:.2f}_{REACT_FIXED[1]:.2f}"
    return out


# ----------------------------------------------------- block 3: predict ----

def _mean_run(flags):
    runs, cur = [], 0
    for f in flags:
        if f:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return float(np.mean(runs)) if runs else 0.0


def block_predict(isp, da_h, da_q):
    da_i = da_on_isp_grid(da_h, da_q, isp.index)
    out = {}
    for label, m in slices(isp.index).items():
        if not label.startswith(("Y", "S", "Q")):
            continue
        sub = isp[m]
        if len(sub) < 96 * 20:
            continue
        s = sub["sell_eur_mwh"]
        d = {"n": int(len(s))}
        for lag, nm in ((1, "15min"), (2, "30min"), (4, "60min"),
                        (8, "120min"), (96, "24h")):
            d[f"acf_sell_{nm}"] = float(s.autocorr(lag))
        for tag, series in (("level", s), ("dev_vs_da", s - da_i[m])):
            v = series.dropna()
            if len(v) < 200:
                continue
            x, y = v.values[:-1], v.values[1:]
            r = float(np.corrcoef(x, y)[0, 1])
            d[f"ar1_rho_{tag}"] = r
            d[f"ar1_r2_{tag}"] = r * r
            rp = float(np.sqrt(np.mean((y - x) ** 2)))
            rm = float(np.sqrt(np.mean((y - y.mean()) ** 2)))
            d[f"rmse_persistence_{tag}"] = rp
            d[f"rmse_mean_{tag}"] = rm
            d[f"persistence_skill_{tag}"] = 1.0 - rp / rm
        neg = (s <= 0).values
        d["p_neg_uncond"] = float(neg.mean())
        if neg[:-1].sum() > 20:
            d["p_neg_stays_neg"] = float(neg[1:][neg[:-1]].mean())
        d["mean_neg_run_isps"] = _mean_run(neg)
        # tercile persistence: does the previous ISP tell you the current one's
        # position in the day's price distribution?
        q1, q2 = s.quantile([1 / 3, 2 / 3])
        terc = np.digitize(s.values, [q1, q2])
        d["p_same_tercile"] = float(np.mean(terc[1:] == terc[:-1]))
        out[label] = d
    return out


# ----------------------------------------------------------------- main ----

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    isp, da_h, da_q = load()
    print(f"ISP  {isp.index[0]} .. {isp.index[-1]} ({len(isp)} rows)")
    print(f"DAh  {da_h.index[0]} .. {da_h.index[-1]} ({len(da_h)})")
    if da_q is not None:
        print(f"DAq  {da_q.index[0]} .. {da_q.index[-1]} ({len(da_q)})")

    res = json.loads(OUTJSON.read_text()) if OUTJSON.exists() else {}
    res["_meta"] = {
        "generated_by": "tools/imbalance/market_character.py",
        "isp_range": [isp.index[0].isoformat(), isp.index[-1].isoformat()],
        "isp_rows": int(len(isp)),
        "da_hourly_range": [da_h.index[0].isoformat(), da_h.index[-1].isoformat()],
        "da_q15_range": ([da_q.index[0].isoformat(), da_q.index[-1].isoformat()]
                         if da_q is not None else None),
        "battery": {"cap_kwh": PRM.cap, "p_kw": PRM.p_kw, "rt": PRM.rt,
                    "soc_band": [PRM.soc_lo, PRM.soc_hi],
                    "cycle_eur": PRM.cycle_eur, "fee_eur_kwh": PRM.fee},
        "season_months": list(SEASON),
        "reactive_fixed": list(REACT_FIXED),
        "reactive_grid": [list(g) for g in REACT_GRID],
    }
    if what in ("all", "dispersion"):
        print("dispersion...", flush=True)
        res["dispersion"] = block_dispersion(isp, da_h, da_q)
    if what in ("all", "predict"):
        print("predictability...", flush=True)
        res["predict"] = block_predict(isp, da_h, da_q)
    if what in ("all", "money"):
        print("money...", flush=True)
        res["money"] = block_money(isp, da_h, da_q)
    OUTJSON.write_text(json.dumps(res, indent=2, default=float))
    print(f"wrote {OUTJSON}")


if __name__ == "__main__":
    main()
