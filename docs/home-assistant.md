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
