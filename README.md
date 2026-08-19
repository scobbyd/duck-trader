# duck-trader

A day-ahead trading algorithm for a home battery, built around the Dutch
duck curve. Every day at 13:00, right after the EPEX auction publishes
tomorrow's prices, it solves one small optimization over the next 35-36
hours: when to charge, when to discharge, when to curtail the PV array,
and what to leave in the battery for later. Only the first 24 hours are
executed; tomorrow's plan overwrites the rest.

There are no modes and no rules. The optimizer implicitly computes, for
every hour, what a stored kWh is worth given everything the horizon
holds, and every action is an inequality against that value: buy below
it, sell above it, soak free solar whenever it is positive, curtail when
even free energy has nowhere to go. The behaviors people hand-code in
rule-based controllers fall out by themselves, including the two-cycle
duck day: sell the battery empty in the morning at positive prices, soak
the negative-price midday window with solar that would otherwise be
curtailed, discharge again into the evening peak.

## Reference results

Backtested on a real Dutch household (about 4,5 MWh/yr consumption,
roughly 20 kWp PV, 48 kWh LiFePO4 battery behind a 12 kW hybrid
inverter, traded at 10 kW) over 152 days, mid-March through mid-August
2026, at bare EPEX day-ahead prices. Numbers are rounded; ratios are
accurate.

| controller | result, EUR / 152 d |
|---|---:|
| No battery | ~470 |
| Greedy self-consumption battery | ~480 |
| Commercial imbalance-trading EMS (realized, same site and window) | ~980 |
| This algorithm (causal backtest) | ~1.360 |
| Same, with perfect load/solar foresight | ~1.370 |
| Omniscient full-window ceiling | ~1.420 |

Battery wear is tracked as its own ledger (~85 EUR at 0,50 EUR per
equivalent full cycle, ~170 cycles) rather than hidden in the totals.
Three observations carry most of the insight:

1. Self-consumption is nearly worthless at raw prices; all the value is
   in timing. The algorithm triples the site result.
2. Forecast quality barely matters. Perfect knowledge of tomorrow's load
   and solar is worth ~1% more. A 7-day moving average per hour of day
   beat every weather-feature ML model tried, and the five candidate
   load models land within 1 EUR of each other. The prices, which are
   simply published, carry the signal.
3. The cycle write-off inside the objective is the whole "don't cycle
   for pennies" mechanism: thin spreads price themselves out and no
   external filter is needed.

Full results, limitations, and the EV roadmap: `docs/results-and-limitations.md`.
Home Assistant integration and dependencies: `docs/home-assistant.md`.

## What is in here

    params.py       battery/tariff parameters + sensitivity variants
    opt.py          the planner: 36 h MILP (HiGHS via scipy), curtailment
                    slack, hybrid-inverter port constraint, charge/discharge
                    exclusivity, cycle write-off in the objective
    forecasters.py  ma7 usage forecast (primary) + candidate models + a
                    slot-ratio PV forecast from 24 h irradiance forecasts
    sched.py        13:00-local plan times, 36 h horizons, DST-safe
    backtest.py     executor (reactive guards) + baselines + accounting
    tests/          20 unit tests with hand-computed optima

## What you must bring

The repo deliberately ships no data adapters; every site is different.
To backtest or run it you supply, on an hourly UTC grid:

- day-ahead prices (EUR/MWh) through the end of D+1;
- house load (kW) and its history;
- potential PV production (kW), i.e. what the array can produce, not
  what a curtailing inverter reports (see the reconstruction notes in
  `docs/results-and-limitations.md`);
- optionally, archived 24 h-lead irradiance forecasts for the PV model.

## Quick start

    pip install numpy pandas scipy scikit-learn pytest
    python -m pytest tests/ -v

Then wire `opt.plan()` and `backtest.run_planned()` to your data. The
planner call is a single function: prices, load forecast, PV forecast,
current state of charge in; hourly charge/discharge/curtailment plan out.

## License

MIT. No warranty; a battery is a large object that stores real energy,
and an inverter register written wrong is your problem, not this repo's.
