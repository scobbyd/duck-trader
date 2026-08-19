# Running it against Home Assistant

The backtest in this repo is pure Python. Turning it into a live
controller means wiring three flows through Home Assistant: data in,
a daily solve, and a plan out to the inverter. This document describes
the reference wiring; adjust to your hardware.

## Dependencies

| Need | Reference choice | Notes |
|---|---|---|
| Day-ahead prices | ENTSO-E or Nord Pool HA integration, or energy-charts.info (tokenless API, CC BY 4.0) | Must expose tomorrow's hourly prices after the ~12:45 CET auction publication. 15-min products also work; this repo plans hourly. |
| Inverter data + control | Solarman integration (Deye-family hybrids) or native Modbus | You need: battery SOC, PV power, load power, and a way to command charge/discharge (see "Plan out"). |
| Usage history | HA long-term statistics on a house-load sensor | The primary forecast is a 7-day moving average per hour of day; a `statistics`/SQL sensor or a small script over LTS is enough. A dedicated energy meter beats inverter-reported load (inverters over- or double-count more often than you would think; validate against a second meter). |
| PV forecast | Solcast integration, or Open-Meteo (free) | Anything that gives tomorrow's hourly production estimate. The backtest used archived 24 h-lead irradiance forecasts times a trailing per-hour ratio; Solcast effectively is that, done for you. |
| Runtime | pyscript, AppDaemon, or a standalone container on the same network | The solve itself is one scipy MILP over 36 hourly steps: well under a second. Do not run heavy loops inside HA's event loop; schedule one solve per day plus a re-solve on demand. |

## Data in

Build one hourly frame per solve: prices for the horizon (today 13:00
through tomorrow midnight), the ma7 load forecast per hour, the PV
forecast per hour, and the measured SOC now. Everything the planner
consumes is strictly causal; nothing needs history beyond seven days of
load and roughly sixty days of PV-versus-forecast ratios.

## The daily solve

Trigger at 13:00 local (after publication), call `opt.plan()`, store the
resulting hourly charge/discharge/curtailment schedule in HA (e.g. as an
attribute-rich sensor or input_text JSON). Solve again on demand if SOC
diverges badly from plan (a big unplanned load, an outage).

## Plan out (the hard 20%)

Executing an hourly schedule on a hybrid inverter is hardware-specific:

- Deye-family inverters expose time-of-use segments and a
  grid-charging toggle over Modbus (writable through Solarman): map each
  planned hour onto TOU slots with target SOC and charge/discharge
  enablement. Rate-limit writes and make them idempotent.
- Export limiting (the curtailment decision) is a separate register or
  automation; the plan tells you when export earns nothing.
- Add the two executor guards from `backtest.py` as automations: never
  export at negative sell prices, and opportunistically soak PV surplus
  whenever prices are at or below zero and headroom exists. These two
  rules rescue most forecast misses.
- If a supplier-side EMS also writes to the inverter, decide ownership
  explicitly. Two controllers fighting over one battery is worse than
  either alone.

## Safety rails

Keep a master enable switch in HA that halts all inverter writes; clamp
every commanded value against the battery vendor's limits regardless of
what the plan says; treat the BMS as the last word. Log the plan and the
realized flows per hour from day one: the plan-versus-actual divergence
is your main debugging signal, and after a season it is also your own
backtest.


## HA code

Reference wiring ships in `ha/`. Two files, three moving parts:

`ha/solve_and_push.py` is the solver bridge. It runs outside Home
Assistant (cron, a container, any box that can `pip install scipy`),
pulls everything it needs over the REST API (prices from a Nord
Pool-style sensor's `raw_today`/`raw_tomorrow`, a 7-day per-hour load
average from history, SOC, optionally a Solcast `detailedForecast`),
solves from now to the last published price, and posts the plan back as
`sensor.duck_trader_plan` with one attribute row per step
(`t, c_kw, d_kw, soc_kwh, export_ok`). It is stateless: every invocation
is a fresh solve from current state, so the same script serves both the
13:05 daily plan and every intraday re-solve.

`ha/duck_trader_package.yaml` is the HA side:

- a master `input_boolean` gating every automation (kill switch first);
- template sensors exposing the current step's charge/discharge
  setpoints, the planned SOC, and an `export_ok` flag;
- the daily-solve automation at 13:05;
- the re-solve loop: every 30 minutes, compare actual SOC against the
  plan's expected SOC and call the solver again only when the gap
  exceeds an `input_number` deadband. Manage expectations here: on the
  reference site this loop was backtested (`run_planned` supports it
  via `resolve_check`/`resolve_deadband_kwh`) and added almost nothing,
  because the daily plan plus the guards already absorb divergence, and
  aggressive re-solving on a fine grid can even churn slightly. Treat
  it as insurance against large unforecast events (an unplanned 10 kWh
  load, a storm day), not as a profit source: a wide deadband of about
  4 kWh and no PV rescaling measured best;
- the executor skeleton (per-step setpoints to your inverter: this part
  is hardware-specific and deliberately ships writing nothing but a
  notification until you map it) and the negative-price export guard.

The division of labor is intentional: the planner is stateless and
lives where scipy lives; HA owns state, triggers, deadbands, and the
actual inverter writes; and the guards run even if the solver box dies,
so the failure mode of the whole stack is "battery follows yesterday's
plan with safe reflexes", never "battery does something new and wrong".
