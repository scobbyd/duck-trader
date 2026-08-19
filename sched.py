"""Plan-time mechanics: daily 13:00-local solves, 36 h horizons, 24 h
execution slices. DST-safe because everything is built from local
calendar days and converted to the hourly UTC grid."""
import pandas as pd

from params import BT_FIRST_PLAN, BT_LAST_PLAN, TZ


def plan_days():
    return pd.date_range(BT_FIRST_PLAN, BT_LAST_PLAN, freq="1D").date


def plan_horizon(day, plan_hour=13):
    """(t0, horizon_index, exec_end) for the plan issued on local `day`.

    horizon: t0 .. end of day+1 local (the '36 h' price lookahead);
    exec_end: the next day's t0 (only this slice is executed)."""
    d = pd.Timestamp(day)
    t0 = pd.Timestamp(f"{d:%Y-%m-%d} 13:00", tz=TZ).tz_convert("UTC")
    # horizon ends at local midnight after D+1, built from the calendar so a
    # DST day cannot leak an hour of D+2 (whose price is not yet published)
    d2 = d + pd.Timedelta(days=2)
    end = pd.Timestamp(f"{d2:%Y-%m-%d} 00:00", tz=TZ).tz_convert("UTC")
    hz = pd.date_range(t0, end - pd.Timedelta("1h"), freq="1h")
    # 13:00 local next day, expressed via calendar day to stay DST-safe
    nxt = d + pd.Timedelta(days=1)
    exec_end = pd.Timestamp(f"{nxt:%Y-%m-%d} 13:00", tz=TZ).tz_convert("UTC")
    return t0, hz, exec_end


def account_index(master):
    """Hourly UTC stamps of the full accounting window."""
    first, _, _ = plan_horizon(plan_days()[0])
    _, _, last_end = plan_horizon(plan_days()[-1])
    return master.index[(master.index >= first) & (master.index < last_end)]
