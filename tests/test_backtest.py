"""Backtest engine tests: executor guards, greedy invariants,
reconciliation. Synthetic 4-day master frames, hand-computed cash."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backtest  # noqa: E402
from params import P, PV_AC  # noqa: E402


def synth_master(start="2025-08-14", days=4, da=100.0, load=0.5, pv_kw=0.0):
    idx = pd.date_range(start, periods=days * 24, freq="1h", tz="UTC")
    da_s = np.full(len(idx), float(da))
    df = pd.DataFrame({
        "load": load, "aux": 0.0, "pv_pot": 0.0,
        "da_eur_mwh": da_s, "sell": da_s / 1000 - 0.02, "buy": da_s / 1000 + 0.02,
    }, index=idx)
    if pv_kw:
        local = idx.tz_convert("Europe/Amsterdam")
        df.loc[(local.hour >= 10) & (local.hour < 16), "pv_pot"] = pv_kw
    return df


DAYS = [pd.Timestamp("2025-08-15").date(), pd.Timestamp("2025-08-16").date()]


def test_b0_accounting_hand_computed():
    m = synth_master()
    r = backtest.run_rule_based(m, P(), battery=False, days=DAYS)
    h = r["hours"]
    assert np.abs(h.c).max() == 0 and np.abs(h.d).max() == 0
    # flat 0,5 kW load, no pv: import every hour at 0,12
    assert h.imp.round(6).eq(0.5).all()
    assert r["cash_gross"] == pytest.approx(-0.5 * 0.12 * len(h))
    # per-hour balance closes
    resid = h.imp - h.exp - (h.load + h.c - h.d - h.u - h.aux_ac)
    assert np.abs(resid).max() < 1e-9


def test_b1_greedy_never_grid_charges():
    m = synth_master(pv_kw=8.0)
    r = backtest.run_rule_based(m, P(), battery=True, days=DAYS)
    h = r["hours"]
    surplus = (h.pot_ac + h.aux_ac - h.load).clip(lower=0.0)
    assert (h.c <= surplus + 1e-9).all(), "greedy charged from the grid"
    deficit = (h.load - h.pot_ac - h.aux_ac).clip(lower=0.0)
    assert (h.d <= deficit + 1e-9).all(), "greedy discharged beyond deficit"


def test_b1_curtails_at_negative_sell():
    m = synth_master(da=-40.0, pv_kw=8.0)   # sell = -0,06
    r = backtest.run_rule_based(m, P(), battery=True, days=DAYS)
    h = r["hours"]
    assert h.exp.max() < 1e-9, "exported at negative sell"


def test_executor_clips_to_soc():
    m = synth_master()
    p = P()
    hz = m.index[:2]
    planned = {"c": np.array([0.0, 0.0]), "d": np.array([10.0, 10.0])}
    ex = backtest.execute_hours(m.loc[hz], planned, p, soc0=p.soc_min)
    assert ex["d"].max() < 1e-9, "discharged below soc floor"
    planned = {"c": np.array([10.0, 10.0]), "d": np.array([0.0, 0.0])}
    ex = backtest.execute_hours(m.loc[hz], planned, p, soc0=p.soc_max)
    assert ex["c"].max() < 1e-9, "charged above soc ceiling"


def test_executor_free_soak_overrides_plan():
    m = synth_master(da=0.0, pv_kw=9.0)     # sell = -0,02 all day
    p = P()
    hz = m.index[(m.index.hour >= 10) & (m.index.hour < 12)][:2]
    planned = {"c": np.zeros(2), "d": np.zeros(2)}
    ex = backtest.execute_hours(m.loc[hz], planned, p, soc0=p.soc_min)
    assert ex["c"].min() > 7.0, "free surplus not soaked at negative sell"
    assert ex["exp"].max() < 1e-9


def test_planned_scenario_reconciles():
    m = synth_master(pv_kw=6.0)
    # make an arbitrage shape: cheap night, pricey evening
    local = m.index.tz_convert("Europe/Amsterdam")
    da = np.where(local.hour < 7, 20.0, np.where(local.hour >= 18, 250.0, 90.0))
    m["da_eur_mwh"] = da
    m["sell"] = da / 1000 - 0.02
    m["buy"] = da / 1000 + 0.02
    p = P()
    r = backtest.run_planned(
        m, p,
        fc_load=lambda t0, hz: m["load"].reindex(hz).values,
        fc_pv=lambda t0, hz: (m["pv_pot"].reindex(hz).values * PV_AC,
                              m["aux"].reindex(hz).values * PV_AC),
        days=DAYS)
    h = r["hours"]
    resid = h.imp - h.exp - (h.load + h.c - h.d - h.u - h.aux_ac)
    assert np.abs(resid).max() < 1e-9
    cash = float((h.sell * h.exp - h.buy * h.imp).sum())
    assert r["cash_gross"] == pytest.approx(cash)
    eta = np.sqrt(p.rt)
    assert r["deg_cost"] == pytest.approx(float(h.d.sum()) / eta * p.c_deg)
    # soc trajectory consistent with flows
    soc = p.soc_min + np.cumsum(eta * h.c.values - h.d.values / eta)
    assert np.allclose(soc, h.soc.values, atol=1e-6)
    # it actually traded into the evening peak
    assert h.d[local[np.isin(m.index, h.index)].hour >= 18].sum() > 5.0


def test_executor_and_totals_at_quarter_dt():
    m = synth_master()
    # quarter-hourly frame: repeat each hour 4x on a 15-min index
    q = m.reindex(pd.date_range(m.index.min(), m.index.max()
                                + pd.Timedelta("45min"), freq="15min"),
                  method="ffill")
    p = P()
    hz = q.index[:8]
    planned = {"c": np.full(8, 10.0), "d": np.zeros(8)}
    ex = backtest.execute_hours(q.loc[hz], planned, p, soc0=p.soc_min, dt=0.25)
    eta = np.sqrt(p.rt)
    # 8 quarters at 10 kW = 2 h x 10 kW x eta cell-side
    assert ex["soc_end"] == pytest.approx(p.soc_min + 2 * 10 * eta, abs=1e-6)
    h = backtest._frame(q.loc[hz], ex)
    t = backtest._totals(h, p, dt=0.25)
    # flat load 0,5 kW, no pv: import = load + charge, 2 h of energy
    assert t["kwh_imp"] == pytest.approx((0.5 + 10.0) * 2, abs=1e-6)
    assert t["cash_gross"] == pytest.approx(-(0.5 + 10.0) * 2 * 0.12, abs=1e-6)
