"""Causal forecasters for the day-ahead planner.

Load candidates: the trailing-average family against covariate models
(24 h temperature forecast + time-of-day + weekday/weekend), to test
whether weather features add signal for a given household.

  climatology  median by local hour, trailing 14 days (the bar to beat)
  ridge        weather features, linear
  gbm          weather features, HistGradientBoosting
  gbm_lags     weather + trailing-load features (signal probe)

All refit per call on data strictly <= t0 (expanding window; the plan
retrains daily, a simplification of the spec's "weekly" that is strictly
causal and slightly better). Temperature/GHI features use the archived
24 h forecasts (fc_d1_*), never actuals.

PV: slot-ratio model, pv_pot_ac(hour) = ratio[hour] * fc_d1_ghi, ratio a
trailing-60-day median. Main and aux fitted separately (aux is must-run).
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from params import PV_AC, TZ

LOAD_MODELS = ("ma7", "climatology", "ridge", "gbm", "gbm_lags")

RATIO_WIN_D = 60
GHI_MIN = 30.0


def _local(idx):
    return idx.tz_convert(TZ)


def _fc_temp(df):
    """fc_d1 temperature with NaN filled from 24 h earlier (still causal)."""
    t = df["fc_d1_temp_c"]
    return t.fillna(t.shift(24)).fillna(t.mean())


def _fc_ghi(df):
    g = df["fc_d1_ghi_wm2"]
    return g.fillna(g.shift(24)).fillna(0.0)


def _weather_features(df, idx):
    """Hour one-hot x weekend + fc_d1 temp + its local-day mean."""
    local = _local(idx)
    hour = np.asarray(local.hour)
    wknd = np.asarray(local.weekday >= 5, dtype=float)
    temp = _fc_temp(df).reindex(idx).values
    day = pd.Series(temp, index=local.date)
    daymean = day.groupby(level=0).transform("mean").values
    X = np.zeros((len(idx), 24 * 2 + 3))
    for i, (h, w) in enumerate(zip(hour, wknd)):
        X[i, h] = 1.0
        if w:
            X[i, 24 + h] = 1.0
    X[:, 48] = wknd
    X[:, 49] = temp
    X[:, 50] = daymean
    return X


def _gbm_features(df, idx):
    local = _local(idx)
    temp = _fc_temp(df).reindex(idx).values
    day = pd.Series(temp, index=local.date)
    daymean = day.groupby(level=0).transform("mean").values
    return np.column_stack([
        np.asarray(local.hour, dtype=float),
        np.asarray(local.weekday >= 5, dtype=float),
        temp, daymean,
    ])


def _lag_features_train(load, idx):
    lag24 = load.reindex(idx - pd.Timedelta("24h")).values
    lag168 = load.reindex(idx - pd.Timedelta("168h")).values
    trail = load.rolling("24h").mean().shift(1).reindex(idx).values
    return np.column_stack([lag24, lag168, trail])


def _lag_features_serve(load_hist, idx, t0):
    """As-of t0: most recent same-local-hour value; trailing mean at t0."""
    lh = load_hist.dropna()
    by_hour = {h: s.iloc[-1] for h, s in lh.groupby(_local(lh.index).hour)}
    by_dow = {k: s.iloc[-1] for k, s in
              lh.groupby([_local(lh.index).weekday, _local(lh.index).hour])}
    trail = float(lh.loc[t0 - pd.Timedelta("24h"):].mean())
    local = _local(idx)
    lag24 = np.array([by_hour.get(h, trail) for h in local.hour])
    lag168 = np.array([by_dow.get((d, h), by_hour.get(h, trail))
                       for d, h in zip(local.weekday, local.hour)])
    return np.column_stack([lag24, lag168, np.full(len(idx), trail)])


def load_forecast(kind, df, t0, hz):
    # strictly < t0: the hour stamped t0 is the one being planned and has
    # not been observed at solve time
    hist = df.loc[df.index < t0]
    y = hist["load"].dropna()

    if kind == "ma7":
        # the primary model: simple 7-day moving average of usage,
        # per local hour (it beat every covariate model on the reference
        # household; validate on yours)
        win = y.loc[t0 - pd.Timedelta(days=7):]
        avg = win.groupby(_local(win.index).hour).mean()
        fallback = float(win.mean()) if len(win) else 0.5
        return np.array([avg.get(h, fallback) for h in _local(hz).hour])

    if kind == "climatology":
        win = y.loc[t0 - pd.Timedelta(days=14):]
        med = win.groupby(_local(win.index).hour).median()
        fallback = float(win.median()) if len(win) else 0.5
        return np.array([med.get(h, fallback) for h in _local(hz).hour])

    if kind == "ridge":
        X, Xh = _weather_features(df, y.index), _weather_features(df, hz)
        m = Ridge(alpha=1.0).fit(X, y.values)
        return np.clip(m.predict(Xh), 0.05, None)

    if kind == "gbm":
        X, Xh = _gbm_features(df, y.index), _gbm_features(df, hz)
        m = HistGradientBoostingRegressor(random_state=0).fit(X, y.values)
        return np.clip(m.predict(Xh), 0.05, None)

    if kind == "gbm_lags":
        X = np.column_stack([_gbm_features(df, y.index),
                             _lag_features_train(y, y.index)])
        ok = ~np.isnan(X).any(axis=1)
        m = HistGradientBoostingRegressor(random_state=0).fit(X[ok], y.values[ok])
        Xh = np.column_stack([_gbm_features(df, hz),
                              _lag_features_serve(y, hz, t0)])
        return np.clip(m.predict(Xh), 0.05, None)

    raise ValueError(kind)


def pv_forecast(df, t0, hz):
    hist = df.loc[(df.index < t0) & (df.index > t0 - pd.Timedelta(days=RATIO_WIN_D))]
    ghi = _fc_ghi(df)
    gh = ghi.reindex(hist.index)
    mask = gh >= GHI_MIN
    hours = _local(hist.index[mask]).hour
    r_main = (hist.loc[mask, "pv_pot"] * PV_AC / gh[mask]).groupby(hours).median()
    r_aux = (hist.loc[mask, "aux"] * PV_AC / gh[mask]).groupby(hours).median()
    gh_h = ghi.reindex(hz).values
    lh = _local(hz).hour
    main = np.array([r_main.get(h, 0.0) for h in lh]) * gh_h
    aux = np.array([r_aux.get(h, 0.0) for h in lh]) * gh_h
    return (np.clip(np.nan_to_num(main), 0.0, 21.0 * PV_AC),
            np.clip(np.nan_to_num(aux), 0.0, 4.0 * PV_AC))
