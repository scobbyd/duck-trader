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
2026, at bare EPEX day-ahead prices on the market's native quarter-hour
grid. Numbers are rounded; ratios are accurate.

| controller | result, EUR / 152 d |
|---|---:|
| No battery | ~465 |
| Greedy self-consumption battery | ~475 |
| Commercial imbalance-trading EMS (realized, same site and window) | ~980 |
| This algorithm (causal backtest) | ~1.410 |
| Same, with perfect load/solar foresight | ~1.430 |
| Omniscient full-window ceiling | ~1.480 |

Battery wear is tracked as its own ledger (~95 EUR at 0,50 EUR per
equivalent full cycle, ~190 cycles) rather than hidden in the totals.
Three observations carry most of the insight:

1. Self-consumption is nearly worthless at raw prices; all the value is
   in timing. The algorithm triples the site result.
2. Forecast quality barely matters. Perfect knowledge of tomorrow's load
   and solar is worth ~1,5% more, and perfect load knowledge alone is
   worth nothing at all. A 7-day moving average per hour of day
   beat every weather-feature ML model tried, and the five candidate
   load models land within 1 EUR of each other. The prices, which are
   simply published, carry the signal.
3. The cycle write-off inside the objective is the whole "don't cycle
   for pennies" mechanism: thin spreads price themselves out and no
   external filter is needed.

Full results, limitations, and the EV roadmap: `docs/results-and-limitations.md`.
Home Assistant integration and dependencies: `docs/home-assistant.md`.
Why day-ahead beat the imbalance market: `docs/imbalance-market-character.md`.

## Why not trade the imbalance market instead?

Most Dutch home batteries that are traded at all are traded on the imbalance
(onbalans) market by a supplier-side EMS, so the obvious question is why this
algorithm targets day-ahead. `docs/imbalance-market-character.md` answers it
with four years of settled TenneT imbalance prices against NL day-ahead,
2023-2026.

The short version: the two markets crossed over during 2025. A causal reactive
imbalance rule earned 1,51x what a causal day-ahead plan earned in 2023 and
0,69x in 2026, on the same battery. The imbalance market's capturable spread
fell about 42% from its 2024 peak while day-ahead's rose about 43%, and the
imbalance-to-day-ahead spread ratio went 5,16 -> 2,02. Two dated structural
events carry most of it: PICASSO cross-border aFRR exchange going live in
October 2024, and the NL day-ahead market switching to a 15-minute market time
unit on 1 October 2025, which moved intra-hour volatility out of imbalance and
into a market where it is published a day ahead. Meanwhile dual-priced
settlement quarters went from 7,7% to 40,0%, taxing every cycle.

The analysis lives in `analysis/`, reuses this repo's planner unmodified, and
re-runs offline in about a minute from the gzipped price panels in
`analysis/cache/`.

## What is in here

    params.py       battery/tariff parameters + sensitivity variants
    opt.py          the planner: 36 h MILP (HiGHS via scipy), curtailment
                    slack, hybrid-inverter port constraint, charge/discharge
                    exclusivity, cycle write-off in the objective
    forecasters.py  ma7 usage forecast (primary) + candidate models + a
                    slot-ratio PV forecast from 24 h irradiance forecasts
    sched.py        13:00-local plan times, 36 h horizons, DST-safe
    backtest.py     executor (reactive guards) + baselines + accounting
    ha/             Home Assistant reference wiring: solver bridge script
                    + package YAML (daily solve, 30-min re-solve deadband
                    loop, executor skeleton, guards)
    tests/          23 unit tests with hand-computed optima

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
