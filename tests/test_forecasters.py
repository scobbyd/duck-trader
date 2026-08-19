"""Forecast layer tests: causality above all, then feature behavior."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import forecasters  # noqa: E402

TZ = "Europe/Amsterdam"


def synth_master(days=90, load_fn=None, temp=10.0, ghi_scale=0.0):
    idx = pd.date_range("2025-01-01", periods=days * 24, freq="1h", tz="UTC")
    local = idx.tz_convert(TZ)
    load = np.ones(len(idx))
    if load_fn is not None:
        load = np.array([load_fn(ts) for ts in local])
    ghi = np.maximum(0.0, np.sin((local.hour - 4) / 14 * np.pi)) * 600.0
    df = pd.DataFrame({
        "load": load,
        "fc_d1_temp_c": temp,
        "fc_d1_ghi_wm2": ghi,
        "pv_pot": ghi_scale * ghi,      # panel-side main
        "aux": 0.0,
    }, index=idx)
    return df


def horizon(t0, hours=35):
    return pd.date_range(t0, periods=hours, freq="1h", tz="UTC")


def test_causality_poisoned_future():
    df = synth_master()
    t0 = df.index[60 * 24]
    hz = horizon(t0)
    clean = {k: forecasters.load_forecast(k, df, t0, hz)
             for k in forecasters.LOAD_MODELS}
    poisoned = df.copy()
    poisoned.loc[poisoned.index > t0, ["load"]] = 1e9
    for k in forecasters.LOAD_MODELS:
        dirty = forecasters.load_forecast(k, poisoned, t0, hz)
        assert np.allclose(clean[k], dirty), f"{k} reads future load"
        assert np.all(np.isfinite(dirty))
        assert np.allclose(dirty, 1.0, atol=0.2), f"{k} far from truth"


def test_weekend_signal_captured():
    def load_fn(ts):
        return 2.0 if ts.weekday() >= 5 else 1.0
    df = synth_master(load_fn=load_fn)
    # first Saturday after day 70
    t0 = df.index[70 * 24]
    while t0.tz_convert(TZ).weekday() != 5:
        t0 += pd.Timedelta("1h")
    # t0 is local Saturday 00:00; forecast local Saturday 10:00-18:00
    hz = horizon(t0 + pd.Timedelta("10h"), hours=8)
    for k in ("ridge", "gbm"):
        fc = forecasters.load_forecast(k, df, t0, hz)
        assert np.allclose(fc, 2.0, atol=0.25), f"{k} missed weekend level: {fc}"


def test_pv_forecast_reproduces_ratio():
    df = synth_master(ghi_scale=0.01)
    t0 = df.index[70 * 24]
    hz = horizon(t0)
    main, aux = forecasters.pv_forecast(df, t0, hz)
    expected = 0.01 * df.loc[hz, "fc_d1_ghi_wm2"].values * forecasters.PV_AC
    assert np.allclose(main, expected, atol=0.05), "ratio model off"
    assert np.allclose(aux, 0.0, atol=1e-6)


def test_horizon_length_and_index():
    df = synth_master()
    t0 = df.index[60 * 24]
    hz = horizon(t0, hours=25)
    fc = forecasters.load_forecast("climatology", df, t0, hz)
    assert len(fc) == 25
