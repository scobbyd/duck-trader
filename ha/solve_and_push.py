#!/usr/bin/env python3
"""Solve the day-ahead plan from Home Assistant data and push it back.

Runs OUTSIDE Home Assistant (any box on the network: cron, systemd timer,
a container) because the solver needs scipy, which HA's runtime does not
ship. Two invocation patterns, both stateless:

  daily plan   cron at 13:05 local, after the auction publishes D+1
  re-solve     called by the 30-min deadband automation in
               duck_trader_package.yaml whenever reality drifted from plan

Either way it solves from NOW to the end of the last published price and
overwrites sensor.duck_trader_plan. Config via environment:

  HA_URL        e.g. http://homeassistant.local:8123
  HA_TOKEN      long-lived access token
  PRICE_ENTITY  a Nord Pool-style sensor with raw_today/raw_tomorrow
                attributes (list of {start, value}); value in EUR/kWh
  LOAD_ENTITY   house load power sensor, W
  SOC_ENTITY    battery SOC sensor, %
  PV_FC_ENTITY  optional Solcast-style sensor with a detailedForecast
                attribute (list of {period_start, pv_estimate}); kW
  FEE_CT        supplier fee ct/kWh each direction (default 0)

Requires this repo on PYTHONPATH: pip install numpy pandas scipy requests
"""
import os
import sys

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import opt                # noqa: E402
from params import P, TZ  # noqa: E402

HA = os.environ["HA_URL"].rstrip("/")
HDRS = {"Authorization": f"Bearer {os.environ['HA_TOKEN']}"}
FEE = float(os.environ.get("FEE_CT", "0")) / 100.0


def state(entity):
    r = requests.get(f"{HA}/api/states/{entity}", headers=HDRS, timeout=15)
    r.raise_for_status()
    return r.json()


def price_series():
    """Hourly (or finer) EUR/kWh series from a Nord Pool-style sensor."""
    s = state(os.environ["PRICE_ENTITY"])
    rows = (s["attributes"].get("raw_today") or []) + \
           (s["attributes"].get("raw_tomorrow") or [])
    ser = pd.Series({pd.Timestamp(r["start"]): float(r["value"])
                     for r in rows if r.get("value") is not None}).sort_index()
    ser.index = ser.index.tz_convert("UTC")
    return ser


def load_ma7(grid):
    """7-day moving average of house load per local hour, mapped to grid."""
    end = pd.Timestamp.now(tz="UTC")
    start = (end - pd.Timedelta(days=7)).isoformat()
    r = requests.get(
        f"{HA}/api/history/period/{start}",
        headers=HDRS, timeout=60,
        params={"filter_entity_id": os.environ["LOAD_ENTITY"],
                "minimal_response": "true", "no_attributes": "true"})
    r.raise_for_status()
    rows = r.json()[0] if r.json() else []
    ser = pd.Series({pd.Timestamp(x["last_changed"]): float(x["state"])
                     for x in rows
                     if x.get("state") not in (None, "unknown", "unavailable")})
    kw = (ser.sort_index().resample("1h").mean() / 1000.0).dropna()
    avg = kw.groupby(kw.index.tz_convert(TZ).hour).mean()
    fallback = float(kw.mean()) if len(kw) else 0.4
    return np.array([avg.get(h, fallback) for h in grid.tz_convert(TZ).hour])


def pv_forecast(grid):
    ent = os.environ.get("PV_FC_ENTITY")
    if not ent:
        return np.zeros(len(grid))
    s = state(ent)
    rows = s["attributes"].get("detailedForecast") or []
    ser = pd.Series({pd.Timestamp(r["period_start"]): float(r["pv_estimate"])
                     for r in rows}).sort_index()
    ser.index = ser.index.tz_convert("UTC")
    return ser.resample("15min").mean().reindex(grid, method="ffill") \
              .fillna(0.0).values


def main():
    p = P(fee=FEE)
    prices = price_series()
    now = pd.Timestamp.now(tz="UTC")
    step = prices.index[1] - prices.index[0]          # 1 h or 15 min
    dt = step / pd.Timedelta("1h")
    t0 = now.floor(f"{int(dt * 60)}min")
    grid = prices.loc[t0:].index
    if len(grid) < 4:
        sys.exit("no published prices ahead; is raw_tomorrow filled yet?")
    sell = prices.loc[grid].values - p.fee
    buy = prices.loc[grid].values + p.fee
    load = load_ma7(grid)
    pv = pv_forecast(grid)
    soc_pct = float(state(os.environ["SOC_ENTITY"])["state"])
    soc0 = min(max(soc_pct / 100.0 * p.cap, p.soc_min), p.soc_max)
    lam = max(0.0, p.lam_end_frac * np.sqrt(p.rt) * float(np.median(sell)))
    r = opt.plan(sell, buy, load, pv, np.zeros(len(grid)), soc0, p, lam, dt=dt)
    if not r["ok"]:
        sys.exit(f"solver failed: {r.get('message')}")
    plan = [{"t": ts.isoformat(),
             "c_kw": round(float(c), 2), "d_kw": round(float(d), 2),
             "soc_kwh": round(float(s_), 2),
             "export_ok": bool(sv > 0)}
            for ts, c, d, s_, sv in zip(grid, r["c"], r["d"], r["soc"], sell)]
    requests.post(
        f"{HA}/api/states/sensor.duck_trader_plan", headers=HDRS, timeout=15,
        json={"state": pd.Timestamp.now(tz="UTC").isoformat(),
              "attributes": {"friendly_name": "Duck Trader plan",
                             "horizon_end": grid[-1].isoformat(),
                             "step_minutes": int(dt * 60),
                             "soc0_kwh": round(soc0, 2),
                             "objective_eur": round(float(r["objective"]), 2),
                             "plan": plan}}).raise_for_status()
    print(f"plan pushed: {len(plan)} steps to {grid[-1]}, "
          f"objective {r['objective']:.2f} EUR")


if __name__ == "__main__":
    main()
