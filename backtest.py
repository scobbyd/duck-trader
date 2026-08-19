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


def _step(row, c_plan, d_plan, p, soc, eta, dt):
    """One executor step: the reactive guards + SOC clipping. Shared by the
    plain and re-solving execution paths (the guards stay active under
    re-solving as the sub-check-interval safety net)."""
    s, load = row["sell"], row["load"]
    m_ac, a_ac = row["pv_pot"] * PV_AC, row["aux"] * PV_AC
    c, d = float(c_plan), float(d_plan)
    if s <= 0:
        d = 0.0
        surplus = max(0.0, m_ac + a_ac - load)
        c = max(c, min(p.p_kw, surplus))
    c = max(0.0, min(c, p.p_kw, (p.soc_max - soc) / (eta * dt)))
    d = max(0.0, min(d, p.p_kw, (soc - p.soc_min) * eta / dt))
    u = _pv_use(m_ac, a_ac, load, c, d, s)
    grid = load + c - d - u - a_ac
    soc = soc + (eta * c - d / eta) * dt
    return c, d, u, max(grid, 0.0), max(-grid, 0.0), soc


def execute_hours(mslice, planned, p, soc0, dt=1.0):
    eta = np.sqrt(p.rt)
    soc = soc0
    out = {k: [] for k in ("c", "d", "u", "imp", "exp", "soc")}
    for i, (ts, row) in enumerate(mslice.iterrows()):
        c, d, u, imp, exp_, soc = _step(row, planned["c"][i], planned["d"][i],
                                        p, soc, eta, dt)
        out["c"].append(c), out["d"].append(d), out["u"].append(u)
        out["imp"].append(imp), out["exp"].append(exp_)
        out["soc"].append(soc)
    return {k: np.array(v) for k, v in out.items()} | {"soc_end": soc}


def _check_steps(resolve_check, freq):
    """Check interval -> whole steps of the planning grid (min 1)."""
    if resolve_check is None:
        return None
    if isinstance(resolve_check, (int, np.integer)):
        return max(1, int(resolve_check))
    return max(1, round(pd.Timedelta(resolve_check) / pd.Timedelta(freq)))


def _execute_resolve(msl, plan, p, soc0, lam, dt, check_steps, deadband,
                     sell, buy, lf, pv_main, aux_fc, pv_update, allow=True):
    """Stepwise execution with intraday re-solves. At each check boundary
    the actual SOC is compared with the active plan's expected SOC for the
    step just completed; a drift beyond `deadband` kWh re-solves the MILP
    from the current step to the end of the day's original horizon with
    soc0 = actual SOC, the same stored forecasts and the same published
    prices (strictly causal). With pv_update the remaining PV forecast is
    rescaled by today's realized/forecast cumsum ratio (clamped 0,3..3,0;
    applied only once the forecast cumsum exceeds 2 kWh so night hours
    cannot produce garbage ratios)."""
    eta = np.sqrt(p.rt)
    plan_c = np.asarray(plan["c"], dtype=float).copy()
    plan_d = np.asarray(plan["d"], dtype=float).copy()
    plan_soc = soc0 + np.cumsum((eta * plan_c - plan_d / eta) * dt)
    act_pv = (msl["pv_pot"].values + msl["aux"].values) * PV_AC
    fc_pv_tot = np.asarray(pv_main, dtype=float) + np.asarray(aux_fc,
                                                              dtype=float)
    out = {k: [] for k in ("c", "d", "u", "imp", "exp", "soc")}
    soc = soc0
    n_res = n_res_fail = 0
    for i, (ts, row) in enumerate(msl.iterrows()):
        if (allow and i > 0 and i % check_steps == 0
                and abs(soc - plan_soc[i - 1]) > deadband):
            pv_i, aux_i = pv_main[i:], aux_fc[i:]
            if pv_update:
                cf = float(fc_pv_tot[:i].sum()) * dt
                if cf > 2.0:
                    ratio = min(3.0, max(
                        0.3, float(act_pv[:i].sum()) * dt / cf))
                    pv_i, aux_i = pv_i * ratio, aux_i * ratio
            r2 = opt.plan(sell[i:], buy[i:], lf[i:], pv_i, aux_i,
                          soc, p, lam, dt=dt)
            if r2["ok"]:
                n_res += 1
                plan_c[i:] = r2["c"]
                plan_d[i:] = r2["d"]
                plan_soc[i:] = soc + np.cumsum(
                    (eta * r2["c"] - r2["d"] / eta) * dt)
            else:
                n_res_fail += 1
        c, d, u, imp, exp_, soc = _step(row, plan_c[i], plan_d[i],
                                        p, soc, eta, dt)
        out["c"].append(c), out["d"].append(d), out["u"].append(u)
        out["imp"].append(imp), out["exp"].append(exp_)
        out["soc"].append(soc)
    ex = {k: np.array(v) for k, v in out.items()} | {"soc_end": soc}
    return ex, plan_c[:len(msl)], plan_d[:len(msl)], n_res, n_res_fail


def _frame(mslice, ex):
    return pd.DataFrame({
        "load": mslice["load"].values,
        "aux_ac": mslice["aux"].values * PV_AC,
        "pot_ac": mslice["pv_pot"].values * PV_AC,
        "sell": mslice["sell"].values, "buy": mslice["buy"].values,
        "c": ex["c"], "d": ex["d"], "u": ex["u"],
        "imp": ex["imp"], "exp": ex["exp"], "soc": ex["soc"],
    }, index=mslice.index)


def _totals(h, p, dt=1.0):
    eta = np.sqrt(p.rt)
    cash_gross = float((h.sell * h.exp - h.buy * h.imp).sum()) * dt
    deg = float(h.d.sum()) * dt / eta * p.c_deg
    neg = h.sell <= 0
    # split absorption at non-positive prices: PV-surplus-covered charge
    # (rescued solar) vs deliberate paid grid-charging
    surplus = (h.pot_ac + h.aux_ac - h.load).clip(lower=0.0)
    soak_pv = float(np.minimum(h.c[neg], surplus[neg]).sum()) * dt
    return {
        "cash_gross": cash_gross,
        "deg_cost": deg,
        "cash_net": cash_gross - deg,
        "kwh_imp": float(h.imp.sum()) * dt, "kwh_exp": float(h.exp.sum()) * dt,
        "kwh_curtailed": float((h.pot_ac - h.u).sum()) * dt,
        "kwh_soaked_neg": float(h.c[neg].sum()) * dt,
        "kwh_soak_pv": soak_pv,
        "kwh_gridcharge_neg": float(h.c[neg].sum()) * dt - soak_pv,
        "efc": float(h.d.sum()) * dt / eta / p.cap,
    }


def _exec_window(master, days):
    t0, _, _ = sched.plan_horizon(days[0])
    _, _, end = sched.plan_horizon(days[-1])
    return master.loc[(master.index >= t0) & (master.index < end)]


def run_rule_based(master, p, battery, days=None, dt=1.0):
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
            c = max(0.0, min(p.p_kw, surplus, (p.soc_max - soc) / (eta * dt)))
        elif battery and surplus < 0:
            d = max(0.0, min(p.p_kw, -surplus, (soc - p.soc_min) * eta / dt))
        u = _pv_use(m_ac, a_ac, load, c, d, s)
        grid = load + c - d - u - a_ac
        soc = soc + (eta * c - d / eta) * dt
        ex["c"].append(c), ex["d"].append(d), ex["u"].append(u)
        ex["imp"].append(max(grid, 0.0)), ex["exp"].append(max(-grid, 0.0))
        ex["soc"].append(soc)
    h = _frame(w, {k: np.array(v) for k, v in ex.items()})
    return {"hours": h} | _totals(h, p, dt)


def default_lam_end(master, p, t0):
    eta = np.sqrt(p.rt)
    win = master.loc[t0 - pd.Timedelta(days=7):t0, "sell"].dropna()
    med = float(win.median()) if len(win) else 0.08
    return max(0.0, p.lam_end_frac * eta * med)


def run_planned(master, p, fc_load, fc_pv, days=None, lam_end_fn=None,
                min_profit_eur=0.0, dt=1.0, freq="1h",
                resolve_check=None, resolve_deadband_kwh=1.0,
                resolve_pv_update=False):
    """B2 (causal forecasts) / B3 (actuals as forecasts) rolling backtest.

    min_profit_eur: optional post-hoc gate — if the plan's expected
    improvement over a no-trade plan is below this, execute no-trade.

    Intraday re-solving (default off, behavior then unchanged): with
    resolve_check set (a Timedelta string like "30min" or a step count),
    the day executes stepwise and at each check boundary actual SOC is
    compared with the active plan's expectation; drift beyond
    resolve_deadband_kwh re-solves from the current step to the end of
    the day's original horizon (same information set: published prices,
    stored forecasts, soc0 = actual). resolve_pv_update additionally
    rescales the remaining PV forecast by today's realized/forecast
    ratio. plan_c/plan_d columns reflect the plan ACTIVE at each executed
    step. n_resolves (total) is exposed in the result dict and per day
    in plan_meta. A day gated to no-trade by min_profit_eur is not
    re-solved (the gate decided the day should not trade)."""
    days = list(days) if days is not None else list(sched.plan_days())
    master = _with_fee(master, p)
    lam_end_fn = lam_end_fn or default_lam_end
    check_steps = _check_steps(resolve_check, freq)
    soc = p.soc_min
    parts, plans = [], []
    n_fail = n_resolves = n_resolve_fail = 0
    for day in days:
        t0, hz, exec_end = sched.plan_horizon(day, freq=freq)
        hz = hz[np.isin(hz, master.index)]
        sell = master.loc[hz, "sell"].values
        buy = master.loc[hz, "buy"].values
        lf = fc_load(t0, hz)
        pv_main_ac, aux_ac = fc_pv(t0, hz)   # AC-side, as opt expects
        lam = lam_end_fn(master, p, t0)
        r = opt.plan(sell, buy, lf, pv_main_ac, aux_ac, soc, p, lam, dt=dt)
        gated = False
        if not r["ok"]:
            n_fail += 1
            r = {"c": np.zeros(len(hz)), "d": np.zeros(len(hz))}
        if min_profit_eur > 0.0 and r.get("ok"):
            base = opt.plan(sell, buy, lf, pv_main_ac, aux_ac, soc, p, lam,
                            no_trade=True, dt=dt)
            if r["objective"] - base["objective"] < min_profit_eur:
                r, gated = base, True
        sl = hz[hz < exec_end]
        msl = master.loc[sl]
        day_res = 0
        if check_steps is None:
            ex = execute_hours(msl, {"c": r["c"][:len(sl)],
                                     "d": r["d"][:len(sl)]}, p, soc, dt=dt)
            rec_c, rec_d = r["c"][:len(sl)], r["d"][:len(sl)]
        else:
            ex, rec_c, rec_d, day_res, day_res_fail = _execute_resolve(
                msl, r, p, soc, lam, dt, check_steps, resolve_deadband_kwh,
                sell, buy, lf, pv_main_ac, aux_ac, resolve_pv_update,
                allow=not gated)
            n_resolves += day_res
            n_resolve_fail += day_res_fail
        soc = ex["soc_end"]
        h = _frame(msl, ex)
        h["plan_c"] = rec_c
        h["plan_d"] = rec_d
        parts.append(h)
        plans.append({"day": str(day), "lam_end": lam,
                      "n_resolves": day_res})
    h = pd.concat(parts)
    out = {"hours": h, "n_fail": n_fail, "n_resolves": n_resolves,
           "n_resolve_fail": n_resolve_fail} | _totals(h, p, dt)
    out["plan_meta"] = plans
    return out


def monthly(h, p, dt=1.0):
    eta = np.sqrt(p.rt)
    g = h.assign(cash=(h.sell * h.exp - h.buy * h.imp) * dt,
                 deg=h.d * dt / eta * p.c_deg)
    m = g.groupby(g.index.tz_convert(TZ).strftime("%Y-%m"))
    return pd.DataFrame({
        "cash_gross": m.cash.sum(), "deg": m.deg.sum(),
        "cash_net": m.cash.sum() - m.deg.sum(),
        "imp": m.imp.sum() * dt, "exp": m["exp"].sum() * dt,
        "efc": m.d.sum() * dt / eta / p.cap,
    }).round(2)
