"""Optimizer unit tests: toy horizons with hand-computed optima.

Conventions under test (spec 'System model'):
  - plan(sell, buy, load, pv_main, aux, soc0, p, lam_end) -> dict
  - all power AC-side kW on an hourly grid; soc in kWh (cell-side)
  - eta_c = eta_d = sqrt(p.rt); degradation p.c_deg EUR per CELL kWh
    discharged (= d_ac / eta_d)
  - Deye port: -12 <= pv_used + d - c <= 12; aux bypasses it
  - charge/discharge exclusivity per hour (binaries)
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from params import P  # noqa: E402
import opt  # noqa: E402

TOL = 1e-6


def run(sell, buy, load=None, pv=None, aux=None, soc0=None, p=None, lam_end=0.0):
    p = p or P()
    T = len(sell)
    z = np.zeros(T)
    r = opt.plan(np.asarray(sell, float), np.asarray(buy, float),
                 z if load is None else np.asarray(load, float),
                 z if pv is None else np.asarray(pv, float),
                 z if aux is None else np.asarray(aux, float),
                 p.soc_min if soc0 is None else soc0, p, lam_end)
    assert r["ok"], r.get("message")
    return r, p


def assert_exclusive(r):
    overlap = np.minimum(r["c"], r["d"])
    assert overlap.max() < 1e-5, f"simultaneous charge+discharge: {overlap.max()}"


def test_flat_prices_do_nothing():
    sell, buy = [0.08] * 6, [0.12] * 6
    lam = 0.9 * 0.08 * np.sqrt(0.93)
    r, p = run(sell, buy, soc0=20.0, lam_end=lam)
    assert np.abs(r["c"]).max() < 1e-5
    assert np.abs(r["d"]).max() < 1e-5
    assert r["soc"][-1] == pytest.approx(20.0, abs=1e-4)
    assert r["objective"] == pytest.approx(lam * 20.0, abs=1e-4)


def test_two_price_day_full_cycle():
    sell = [0.03] * 12 + [0.28] * 12
    buy = [0.07] * 12 + [0.32] * 12
    r, p = run(sell, buy)
    eta = np.sqrt(p.rt)
    usable = p.soc_max - p.soc_min
    expected = usable * eta * 0.28 - (usable / eta) * 0.07 - usable * p.c_deg
    assert r["objective"] == pytest.approx(expected, abs=1e-3)
    assert r["soc"].max() == pytest.approx(p.soc_max, abs=1e-3)
    assert r["soc"][-1] == pytest.approx(p.soc_min, abs=1e-3)
    assert_exclusive(r)


def test_break_even_spread_blocks_marginal_trade():
    p = P()
    eta = np.sqrt(p.rt)
    be_sell = (0.10 + p.c_deg * eta) / p.rt
    r_no, _ = run([0.0, be_sell - 0.002], [0.10, be_sell + 0.04])
    assert np.abs(r_no["c"]).max() < 1e-5, "traded below break-even"
    r_yes, _ = run([0.0, be_sell + 0.006], [0.10, be_sell + 0.05])
    assert r_yes["c"][0] > 1.0, "did not trade above break-even"


def test_negative_sell_full_battery_curtails():
    # t1 sell 0,005: eta*0,005 < c_deg so exporting does not pay, but
    # covering the 0,12 import does -> discharge exactly the load
    p = P()
    r, _ = run(sell=[-0.03, 0.005], buy=[0.01, 0.12],
               load=[0.5, 0.5], pv=[15.0, 0.0], soc0=p.soc_max)
    assert r["exp"][0] < TOL, "exported at negative sell price"
    assert r["imp"][0] < TOL
    assert r["pv_used"][0] == pytest.approx(0.5, abs=1e-4)
    assert r["d"][1] == pytest.approx(0.5, abs=1e-4)
    assert_exclusive(r)


def test_negative_sell_with_headroom_soaks():
    p = P()
    r, _ = run(sell=[-0.03, 0.30], buy=[0.01, 0.34],
               load=[0.5, 0.5], pv=[15.0, 0.0], soc0=p.soc_min)
    eta = np.sqrt(p.rt)
    assert r["c"][0] == pytest.approx(p.p_kw, abs=1e-3), "did not soak free PV"
    assert r["exp"][0] < TOL
    soc1 = p.soc_min + eta * p.p_kw
    assert r["soc"][0] == pytest.approx(soc1, abs=1e-3)
    d1 = (soc1 - p.soc_min) * eta
    assert r["d"][1] == pytest.approx(min(p.p_kw, d1), abs=1e-3)


def test_deye_port_cap_limits_export():
    p = P()
    r, _ = run(sell=[0.10], buy=[0.14], load=[0.0], pv=[15.0],
               soc0=p.soc_max)
    assert r["pv_used"][0] == pytest.approx(12.0, abs=1e-3)
    assert r["exp"][0] == pytest.approx(12.0, abs=1e-3)


def test_lam_end_drives_terminal_soc():
    sell, buy = [0.03] * 6, [0.07] * 6
    p = P()
    r_hi, _ = run(sell, buy, lam_end=0.10)
    assert r_hi["soc"][-1] == pytest.approx(p.soc_max, abs=1e-3)
    r_lo, _ = run(sell, buy, lam_end=0.0, soc0=20.0)
    assert r_lo["soc"][-1] == pytest.approx(p.soc_min, abs=1e-3)


def test_duck_day_emergent_behavior():
    """The duck-day target pattern: sell down to the floor while export
    still earns, soak the free midday window, discharge into the evening
    peak."""
    p = P()
    # 36 h from 13:00 D: 11 h of D (sell 0,12), D+1 morning 8 h (0,08),
    # D+1 free window 5 h (sell -0,02), D+1 evening 12 h (peak 0,25)
    sell = np.array([0.12] * 11 + [0.08] * 8 + [-0.02] * 5 + [0.25] * 12)
    buy = sell + 0.04
    pv = np.zeros(36)
    pv[19:24] = 13.0          # the free window, 65 kWh potential
    load = np.full(36, 0.4)
    r, _ = run(sell, buy, load=load, pv=pv, soc0=20.0)
    assert r["soc"][18] == pytest.approx(p.soc_min, abs=0.5), \
        "battery not emptied before the free window"
    assert r["soc"][23] >= 0.95 * p.soc_max, "free window not soaked"
    assert r["exp"][19:24].max() < TOL, "exported during negative-sell window"
    assert r["d"][24:].sum() * np.sqrt(p.rt) > 25.0, "evening peak not served"
    assert_exclusive(r)


def test_no_trade_reference_plan():
    sell = [0.03] * 12 + [0.28] * 12
    buy = [0.07] * 12 + [0.32] * 12
    p = P()
    z = np.zeros(24)
    r = opt.plan(np.array(sell), np.array(buy), z, z, z, p.soc_min, p, 0.0,
                 no_trade=True)
    assert r["ok"]
    assert np.abs(r["c"]).max() < 1e-9 and np.abs(r["d"]).max() < 1e-9
    r_free, _ = run(sell, buy)
    assert r_free["objective"] > r["objective"] + 5.0


def test_relax_matches_milp_on_clean_day():
    sell = [0.03] * 12 + [0.28] * 12
    buy = [0.07] * 12 + [0.32] * 12
    p = P()
    z = np.zeros(24)
    r_lp = opt.plan(np.array(sell), np.array(buy), z, z, z, p.soc_min, p,
                    0.0, relax=True)
    r_mi, _ = run(sell, buy)
    assert r_lp["objective"] == pytest.approx(r_mi["objective"], abs=1e-4)
    assert np.minimum(r_lp["c"], r_lp["d"]).max() < 1e-6


def test_dt_quarter_matches_hourly_on_flat_slots():
    # each hourly price repeated 4x at dt=0,25 must reproduce the hourly solve
    sell_h = [0.03] * 12 + [0.28] * 12
    buy_h = [0.07] * 12 + [0.32] * 12
    p = P()
    r_h, _ = run(sell_h, buy_h)
    sell_q = np.repeat(sell_h, 4)
    buy_q = np.repeat(buy_h, 4)
    z = np.zeros(96)
    r_q = opt.plan(sell_q, buy_q, z, z, z, p.soc_min, p, 0.0, dt=0.25)
    assert r_q["ok"]
    assert r_q["objective"] == pytest.approx(r_h["objective"], abs=1e-3)
    assert (r_q["d"].sum() * 0.25) == pytest.approx(r_h["d"].sum(), abs=1e-3)


def test_dt_exploits_intra_hour_spike():
    # one spike quarter inside an otherwise flat expensive hour: with just
    # enough charge for one quarter's discharge, all of it goes to the spike
    p = P()
    sell = np.array([0.0] * 4 + [0.30, 0.10, 0.10, 0.10])
    buy = np.array([0.50] * 4 + [0.34, 0.14, 0.14, 0.14])  # charging never pays
    z = np.zeros(8)
    eta = np.sqrt(p.rt)
    soc0 = p.soc_min + 2.5 / eta   # exactly one quarter of 10 kW discharge
    r = opt.plan(sell, buy, z, z, z, soc0, p, 0.0, dt=0.25)
    assert r["ok"]
    assert r["d"][4] == pytest.approx(10.0, abs=1e-3), "spike quarter not used"
    assert r["d"][5:].max() < 1e-6, "discharged into flat quarters instead"
