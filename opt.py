"""The planner: one MILP over the 36 h horizon (HiGHS via scipy).

Single AC-node model per the spec. Hourly steps, kW == kWh. Variables per
step: c (charge), d (discharge), u (main PV used), imp, exp, soc, z
(charge/discharge exclusivity binary — without it the LP burns energy
through the battery at negative prices, a known LP artifact).

The Deye hybrid's DC<->AC bridge carries main PV and battery flows but not
the aux microinverter: -12 <= u + d - c <= 12. DC-coupled PV above 12 kW
can therefore still charge the battery, matching the hardware.

Degradation: p.c_deg EUR per cell-side kWh discharged (= d / eta_d), so a
full 48 kWh cycle costs exactly p.cycle_eur.
"""
import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

PORT_KW = 12.0

COLS = ["c", "d", "u", "imp", "exp", "soc", "z"]
NV = len(COLS)
I = {name: i for i, name in enumerate(COLS)}


def plan(sell, buy, load, pv_main, aux, soc0, p, lam_end, no_trade=False,
         relax=False, dt=1.0):
    """relax=True is the standard LP relaxation of the binaries (z becomes
    continuous, which still implies c + d <= p_kw) — used only for the
    long-window B4 ceiling. Simultaneous charge+discharge can then appear
    at negative prices (counted and reported); the feasible set is a
    superset of the MILP's, so B4 remains a valid ceiling."""
    for arr in (sell, buy, load, pv_main, aux):
        if not np.all(np.isfinite(arr)):
            return {"ok": False, "message": "non-finite input"}
    T = len(sell)
    n = T * NV
    eta = np.sqrt(p.rt)

    def col(t, name):
        return t * NV + I[name]

    obj = np.zeros(n)
    for t in range(T):
        obj[col(t, "exp")] = -sell[t] * dt
        obj[col(t, "imp")] = buy[t] * dt
        obj[col(t, "d")] = p.c_deg / eta * dt
    obj[col(T - 1, "soc")] -= lam_end

    rows, cols, vals = [], [], []
    lb, ub = [], []
    r = 0

    def add(t, name, v):
        rows.append(r), cols.append(col(t, name)), vals.append(v)

    for t in range(T):
        # AC balance: imp - exp = load + c - d - u - aux
        add(t, "imp", 1.0), add(t, "exp", -1.0)
        add(t, "c", -1.0), add(t, "d", 1.0), add(t, "u", 1.0)
        lb.append(load[t] - aux[t]), ub.append(load[t] - aux[t]); r += 1
        # SOC continuity (energy per step = power x dt)
        add(t, "soc", 1.0), add(t, "c", -eta * dt), add(t, "d", dt / eta)
        if t > 0:
            add(t - 1, "soc", -1.0)
        rhs = soc0 if t == 0 else 0.0
        lb.append(rhs), ub.append(rhs); r += 1
        # Deye port
        add(t, "u", 1.0), add(t, "d", 1.0), add(t, "c", -1.0)
        lb.append(-PORT_KW), ub.append(PORT_KW); r += 1
        # exclusivity: c <= p_kw*z ; d <= p_kw*(1-z)
        add(t, "c", 1.0), add(t, "z", -p.p_kw)
        lb.append(-np.inf), ub.append(0.0); r += 1
        add(t, "d", 1.0), add(t, "z", p.p_kw)
        lb.append(-np.inf), ub.append(p.p_kw); r += 1

    A = sparse.coo_matrix((vals, (rows, cols)), shape=(r, n))

    x_lo, x_hi = np.zeros(n), np.full(n, np.inf)
    integrality = np.zeros(n)
    for t in range(T):
        x_hi[col(t, "c")] = 0.0 if no_trade else p.p_kw
        x_hi[col(t, "d")] = 0.0 if no_trade else p.p_kw
        x_hi[col(t, "u")] = max(0.0, pv_main[t])
        x_lo[col(t, "soc")] = p.soc_min
        x_hi[col(t, "soc")] = p.soc_max
        x_hi[col(t, "z")] = 1.0
        integrality[col(t, "z")] = 0 if relax else 1

    res = milp(obj, constraints=LinearConstraint(A, lb, ub),
               bounds=Bounds(x_lo, x_hi), integrality=integrality)
    if res.status != 0:
        return {"ok": False, "message": res.message}

    def grid(name):
        return np.array([res.x[col(t, name)] for t in range(T)])

    return {
        "ok": True,
        "objective": -res.fun,
        "c": grid("c"), "d": grid("d"), "pv_used": grid("u"),
        "imp": grid("imp"), "exp": grid("exp"), "soc": grid("soc"),
    }
