# Results, limitations, and the EV extension

## The backtest

152 daily plans, mid-March through mid-August 2026, on a real Dutch
household: about 4,5 MWh/yr consumption, roughly 20 kWp of PV (a main
string array plus a small never-curtailed microinverter array), a 48 kWh
LiFePO4 battery behind a 12 kW hybrid inverter, traded at 10 kW where
the measured round trip is about 93% (standby draw excluded: it runs
whether or not you trade, so it is sunk and does not belong in the
round-trip figure). Wear is charged inside the optimizer at 0,50 EUR per
equivalent full cycle and reported as a separate ledger.

All totals below are at bare EPEX day-ahead prices (no supplier fees),
on the market's native quarter-hour grid, rounded, with ratios
preserved.

| controller | EUR / 152 d | cycles |
|---|---:|---:|
| No battery | ~465 | 0 |
| Greedy self-consumption | ~475 | ~14 |
| Commercial imbalance EMS (realized) | ~980 | n/a |
| This algorithm | ~1.410 | ~190 |
| Perfect load+PV foresight | ~1.430 | ~190 |
| Omniscient full-window ceiling | ~1.480 | ~190 |

## The comparison that matters

The same site, in the same window, was actually operated by a commercial
EMS that trades the battery on the imbalance market; it realized roughly
980 EUR (believed to be before supplier fees). The day-ahead algorithm
backtests about 45% above that, from prices that are simply published
every afternoon, with no real-time trading infrastructure and no
imbalance exposure. Fair caveats in both directions: a backtest is not
realized cash, the realized figure includes whatever co-dispatch the EMS
actually did, and imbalance trading has better months than this window
elsewhere in the year. Still, the gap says the boring market, played
deliberately, is at least competitive with the exciting one.

A related warning from the same data: passively settling day-ahead-
optimal flows at imbalance prices loses about 35% (measured at the
settlement's own quarter-hour resolution). Day-ahead planning
with imbalance settlement is the worst combination; match your dispatch
basis to your settlement basis, or add a genuinely selective
imbalance-aware layer.

## Where the money comes from

Roughly speaking, over the window: pure price arbitrage a bit under
half; harvesting solar that would otherwise be curtailed in
negative-price windows about a third (curtailment loss drops from
~2.300 kWh to ~600 kWh; on ~65 duck days the battery soaks ~30 kWh/day
of surplus that the greedy controller wastes); the rest is timing of
exports and load coverage. Winter, estimated with a prices-only bound
over a full year, contributes maybe a quarter of what the duck months
do; a raw annual figure around 1.800-1.950 EUR at ~430 cycles is a
defensible extrapolation for this class of site.

## Limitations, honestly

- Low household usage. At ~4,5 MWh/yr with no electric heating there is
  little self-consumption value to shift; this site's result leans on
  trading and solar-soak. A high-usage household would shift the mix,
  not necessarily the total.
- No EV, no heat pump. The two biggest flexible loads in a normal home
  are absent from both the site and the model (see below).
- Season coverage. The backtest is duck season (spring/summer). Winter
  is estimated from a prices-only bound, not backtested.
- Grid granularity, measured: the headline table is the quarter-hourly
  run on the market's native 15-minute products; plain hourly planning
  lands about 3,5% lower at ~10% less cycling (the planner supports both
  via its dt parameter). Load and PV are step-held hourly on the quarter
  grid, so the granularity gain is price-side only.
- Settlement basis. The backtest settles at day-ahead. If your supplier
  settles imbalance, see the warning above.
- Potential-PV reconstruction. If your inverter curtails, its reported
  production under-states what the array could do exactly on the hours
  this algorithm exploits. The backtest reconstructed potential from a
  never-curtailed reference array; you will need an equivalent trick
  (a reference string, irradiance-based estimates) or your backtest
  will under-credit the strategy.
- Degradation is a linear 0,50 EUR/cycle. Real aging is kinder to
  shallow cycles and unkinder to heat and high SOC parking; the number
  is a planning price, not a battery model.
- The executor seam. This repo backtests; reference HA wiring (solver
  bridge + package YAML with the re-solve deadband loop) ships in ha/,
  but the inverter-register mapping itself remains yours.

## Why an EV is the natural next addition

An EV is the missing piece this optimizer is shaped for, because
charging is a large deferrable load with a deadline, and that is just
one more set of linear constraints:

- Model the car as a second storage node with an availability window
  (plugged in from arrival to departure), a deadline SOC ("80% by
  07:00"), and charge power limits. The same MILP places the charging
  kWh in the cheapest or negative-priced hours automatically, exactly as
  it places battery charging today.
- The scale is decisive. A 60 kWh pack absorbs an entire duck-day
  curtailment window that the home battery cannot fit, and a commuter
  charging ~2.000 kWh/yr who moves all of it from flat charging into
  the cheapest quartile of hours captures on the order of 150-250 EUR/yr
  from load-shifting alone, before counting free negative-price energy.
- Planning ahead is the point. The 36 h horizon means Friday's plan can
  already see the negative Saturday midday and hold the car's charging
  for it. Without a planner, an EV charges when it happens to be
  plugged in, which is usually the evening peak, the most expensive
  possible choice.
- V2G, where hardware and contract allow it, upgrades the car from a
  deferrable load to a second tradable battery several times the size
  of the home pack. The optimizer needs nothing new conceptually; the
  constraints (departure SOC, cycling limits the owner accepts) are the
  same shape as the ones already in `opt.py`.
