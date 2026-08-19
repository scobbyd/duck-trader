"""Backtest engine: executor + rule-based baselines + planned scenarios.

Executor realism rules: the battery follows the plan clipped to SOC
feasibility computed on actuals, with two reactive guards mirroring a
typical inverter-side automation: at sell < 0 residual export is
curtailed (PV downregulation), and at sell <= 0 surplus potential PV is
soaked into free headroom even if the plan did not ask for it.
"""
import numpy as np
import pandas as pd

import opt
import sched
from params import PV_AC, TZ

PORT_KW = opt.PORT_KW


def _with_fee(master, p):
    """Prices derived from da with the variant's fee (master's stored
    sell/buy columns are the 0,02 default; sensitivities need their own)."""
    m = master.copy()
    m["sell"] = m["da_eur_mwh"] / 1000.0 - p.fee
    m["buy"] = m["da_eur_mwh"] / 1000.0 + p.fee
    return m


def _pv_use(m_ac, a_ac, load, c, d, s):
    port = max(0.0, PORT_KW - d + c)
    if s > 0:
        return min(m_ac, port)
    return min(m_ac, max(0.0, load + c - d - a_ac), port)


def execute_hours(mslice, planned, p, soc0):
    eta = np.sqrt(p.rt)
    soc = soc0
    out = {k: [] for k in ("c", "d", "u", "imp", "exp", "soc")}
    for i, (ts, row) in enumerate(mslice.iterrows()):
        s, load = row["sell"], row["load"]
        m_ac, a_ac = row["pv_pot"] * PV_AC, row["aux"] * PV_AC
        c, d = float(planned["c"][i]), float(planned["d"][i])
        if s <= 0:
            d = 0.0
            surplus = max(0.0, m_ac + a_ac - load)
            c = max(c, min(p.p_kw, surplus))
        c = max(0.0, min(c, p.p_kw, (p.soc_max - soc) / eta))
        d = max(0.0, min(d, p.p_kw, (soc - p.soc_min) * eta))
        u = _pv_use(m_ac, a_ac, load, c, d, s)
        grid = load + c - d - u - a_ac
        soc = soc + eta * c - d / eta
        out["c"].append(c), out["d"].append(d), out["u"].append(u)
        out["imp"].append(max(grid, 0.0)), out["exp"].append(max(-grid, 0.0))
        out["soc"].append(soc)
    return {k: np.array(v) for k, v in out.items()} | {"soc_end": soc}


def _frame(mslice, ex):
    return pd.DataFrame({
        "load": mslice["load"].values,
        "aux_ac": mslice["aux"].values * PV_AC,
        "pot_ac": mslice["pv_pot"].values * PV_AC,
        "sell": mslice["sell"].values, "buy": mslice["buy"].values,
        "c": ex["c"], "d": ex["d"], "u": ex["u"],
        "imp": ex["imp"], "exp": ex["exp"], "soc": ex["soc"],
    }, index=mslice.index)


def _totals(h, p):
    eta = np.sqrt(p.rt)
    cash_gross = float((h.sell * h.exp - h.buy * h.imp).sum())
    deg = float(h.d.sum()) / eta * p.c_deg
    neg = h.sell <= 0
    # split absorption at non-positive prices: PV-surplus-covered charge
    # (rescued solar) vs deliberate paid grid-charging
    surplus = (h.pot_ac + h.aux_ac - h.load).clip(lower=0.0)
    soak_pv = float(np.minimum(h.c[neg], surplus[neg]).sum())
    return {
        "cash_gross": cash_gross,
        "deg_cost": deg,
        "cash_net": cash_gross - deg,
        "kwh_imp": float(h.imp.sum()), "kwh_exp": float(h.exp.sum()),
        "kwh_curtailed": float((h.pot_ac - h.u).sum()),
        "kwh_soaked_neg": float(h.c[neg].sum()),
        "kwh_soak_pv": soak_pv,
        "kwh_gridcharge_neg": float(h.c[neg].sum()) - soak_pv,
        "efc": float(h.d.sum()) / eta / p.cap,
    }


def _exec_window(master, days):
    t0, _, _ = sched.plan_horizon(days[0])
    _, _, end = sched.plan_horizon(days[-1])
    return master.loc[(master.index >= t0) & (master.index < end)]


def run_rule_based(master, p, battery, days=None):
    """B0 (battery=False) and B1 greedy self-consumption (battery=True)."""
    days = list(days) if days is not None else list(sched.plan_days())
    master = _with_fee(master, p)
    w = _exec_window(master, days)
    eta = np.sqrt(p.rt)
    soc = p.soc_min
    ex = {k: [] for k in ("c", "d", "u", "imp", "exp", "soc")}
    for ts, row in w.iterrows():
        s, load = row["sell"], row["load"]
        m_ac, a_ac = row["pv_pot"] * PV_AC, row["aux"] * PV_AC
        surplus = m_ac + a_ac - load
        c = d = 0.0
        if battery and surplus > 0:
            c = max(0.0, min(p.p_kw, surplus, (p.soc_max - soc) / eta))
        elif battery and surplus < 0:
            d = max(0.0, min(p.p_kw, -surplus, (soc - p.soc_min) * eta))
        u = _pv_use(m_ac, a_ac, load, c, d, s)
        grid = load + c - d - u - a_ac
        soc = soc + eta * c - d / eta
        ex["c"].append(c), ex["d"].append(d), ex["u"].append(u)
        ex["imp"].append(max(grid, 0.0)), ex["exp"].append(max(-grid, 0.0))
        ex["soc"].append(soc)
    h = _frame(w, {k: np.array(v) for k, v in ex.items()})
    return {"hours": h} | _totals(h, p)


def default_lam_end(master, p, t0):
    eta = np.sqrt(p.rt)
    win = master.loc[t0 - pd.Timedelta(days=7):t0, "sell"].dropna()
    med = float(win.median()) if len(win) else 0.08
    return max(0.0, p.lam_end_frac * eta * med)


def run_planned(master, p, fc_load, fc_pv, days=None, lam_end_fn=None,
                min_profit_eur=0.0):
    """B2 (causal forecasts) / B3 (actuals as forecasts) rolling backtest.

    min_profit_eur: optional post-hoc gate — if the plan's expected
    improvement over a no-trade plan is below this, execute no-trade."""
    days = list(days) if days is not None else list(sched.plan_days())
    master = _with_fee(master, p)
    lam_end_fn = lam_end_fn or default_lam_end
    soc = p.soc_min
    parts, plans = [], []
    n_fail = 0
    for day in days:
        t0, hz, exec_end = sched.plan_horizon(day)
        hz = hz[np.isin(hz, master.index)]
        sell = master.loc[hz, "sell"].values
        buy = master.loc[hz, "buy"].values
        lf = fc_load(t0, hz)
        pv_main_ac, aux_ac = fc_pv(t0, hz)   # AC-side, as opt expects
        lam = lam_end_fn(master, p, t0)
        r = opt.plan(sell, buy, lf, pv_main_ac, aux_ac, soc, p, lam)
        if not r["ok"]:
            n_fail += 1
            r = {"c": np.zeros(len(hz)), "d": np.zeros(len(hz))}
        if min_profit_eur > 0.0 and r.get("ok"):
            base = opt.plan(sell, buy, lf, pv_main_ac, aux_ac, soc, p, lam,
                            no_trade=True)
            if r["objective"] - base["objective"] < min_profit_eur:
                r = base
        sl = hz[hz < exec_end]
        msl = master.loc[sl]
        ex = execute_hours(msl, {"c": r["c"][:len(sl)], "d": r["d"][:len(sl)]},
                           p, soc)
        soc = ex["soc_end"]
        h = _frame(msl, ex)
        h["plan_c"] = r["c"][:len(sl)]
        h["plan_d"] = r["d"][:len(sl)]
        parts.append(h)
        plans.append({"day": str(day), "lam_end": lam})
    h = pd.concat(parts)
    out = {"hours": h, "n_fail": n_fail} | _totals(h, p)
    out["plan_meta"] = plans
    return out


def monthly(h, p):
    eta = np.sqrt(p.rt)
    g = h.assign(cash=h.sell * h.exp - h.buy * h.imp,
                 deg=h.d / eta * p.c_deg)
    m = g.groupby(g.index.tz_convert(TZ).strftime("%Y-%m"))
    return pd.DataFrame({
        "cash_gross": m.cash.sum(), "deg": m.deg.sum(),
        "cash_net": m.cash.sum() - m.deg.sum(),
        "imp": m.imp.sum(), "exp": m["exp"].sum(),
        "efc": m.d.sum() / eta / p.cap,
    }).round(2)
