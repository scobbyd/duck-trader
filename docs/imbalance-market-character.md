# Has the imbalance market changed character for battery trading?

Companion study to this repository's day-ahead trading algorithm. The question
it answers: has the Dutch imbalance (onbalans) market changed character over
2023-2026 in a way that makes it less attractive for a small battery traded on
price signals? "This type of trading" is a 48 kWh / 10 kW home battery behind a
hybrid inverter, of the kind this repo's algorithm plans for.

The motivation is practical. Many Dutch home batteries are traded on the
imbalance market by a supplier-side EMS, and this repository exists because a
self-run day-ahead algorithm turned out to beat one. This study asks whether
that is a story about the algorithm or a story about the market.

Everything below is reproducible from the price panels and scripts in
`analysis/`. No number in this document was typed by hand; see
[Reproduction](#reproduction).

## Verdict

Yes, and the change is large, dated and mechanical rather than a matter of
sentiment. Over 2023-2026 the settled Dutch imbalance market lost roughly half
of the dispersion a battery can monetise, while the day-ahead market gained
about half again as much. The two markets crossed. The single cleanest statistic
is the ratio of the two markets' daily best-2h spreads, which is immune to both
the price level and the season:

| | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance spread / day-ahead spread, full year | 5,16 | 4,77 | 2,69 | 2,02 |
| the same, Mar-Aug only | 5,54 | 5,04 | 2,62 | 1,87 |

The imbalance market's excess opportunity over day-ahead has fallen by about
two-thirds.

Priced as money on the owner's own battery, the two markets crossed over during
2025. A causal reactive imbalance rule earned 1,51x what a causal day-ahead plan
earned in 2023; in 2026 it earns 0,69x. The imbalance market is still the richer
market in theory, its perfect-foresight ceiling being 1,73x day-ahead's, but
that ceiling is unreachable, and what a real strategy can actually take out of
it has fallen below what day-ahead hands you for free with the prices published
a day in advance. Section 4 carries the full table.

Two dated structural events explain most of the change, and neither is a market
mood: the go-live of PICASSO cross-border aFRR exchange in the Netherlands in
October 2024, and the switch of the NL day-ahead market to a 15-minute market
time unit on 1 October 2025. A third channel, the growth of the Dutch battery
fleet, is corroborated externally but cannot be identified separately here.

## Data

| Series | Source | Coverage | Resolution |
|---|---|---|---|
| Settled TenneT imbalance prices | `publications.tennet.eu` APEX report, re-parsed from cached raw day fragments, keeping the full report column set | 2023-01-01 .. 2026-08-16 | 15-min ISP |
| NL day-ahead | `api.energy-charts.info` | 2023-01-01 .. 2026-08-16 | hourly to 2025-09-30, 15-min after |

127.100 ISP rows, zero gaps, zero parse failures, all seven DST days carrying
their correct 92 or 100 rows. The `buy >= sell` invariant holds on all but the
four ISPs that are genuine source-data exceptions, and those are exactly the
four this parse finds (2023-01-26 12:45 / 14:00 / 18:15 and 2024-06-08 14:30
UTC).

The parse keeps regulation state and the incident-reserve flags alongside the
two prices. `buy_eur_mwh` is the shortage price (what a battery pays to
charge), `sell_eur_mwh` the surplus price (what it receives to discharge);
timestamps are ISP start in UTC.

**Frame.** Raw market prices, no supplier fee, matching the convention used in
`docs/results-and-limitations.md`. The 0,50 EUR/cycle write-off stays
inside the optimiser objective, where it is what keeps thin cycles out of the
plan, and is reported as a separate wear ledger rather than netted off the cash.
Battery: 48 kWh, 10 kW, 93% round trip, SOC band 10-95%.

## 1. Dispersion: the two markets moved in opposite directions

The metric that matters for a battery is not the sd of the price series but the
spread it can actually capture. `best-2h spread` is, per local day, the mean of
the eight dearest sell slots minus the mean of the eight cheapest buy slots —
two hours in each direction, roughly what a 48 kWh / 10 kW battery moves. For
the imbalance market it is computed on sell for the top and buy for the bottom,
so the dual-pricing wedge is inside it, as it is in reality.

### Imbalance market, full calendar years (EUR/MWh unless stated)

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean best-2h spread | 517,8 | 503,9 | 309,7 | 290,2 |
| median best-2h spread | 426,2 | 363,7 | 198,7 | 194,2 |
| mean daily max-min | 1.136,1 | 1.247,0 | 799,8 | 758,2 |
| mean abs ISP-to-ISP step | 68,9 | 72,2 | 44,8 | 38,4 |
| mean abs (imbalance - day-ahead) | 79,5 | 84,1 | 58,7 | 57,2 |
| mean (imbalance - day-ahead) | -2,2 | -11,1 | -14,6 | -16,0 |
| % of ISPs with sell <= 0 | 19,5 | 25,0 | 19,1 | 16,6 |
| % of ISPs with abs(sell) > 200 | 8,37 | 6,07 | 2,73 | 3,23 |
| % of ISPs with abs(sell) > 500 | 2,73 | 3,07 | 1,08 | 0,74 |
| % dual-priced (buy > sell) | 7,5 | 16,5 | 26,3 | 38,1 |
| mean sell price | 93,6 | 66,2 | 72,2 | 84,9 |

### Day-ahead market, same years and same metric definitions

Computed on the hourly series for all four years. This matters: the
quarter-hourly day-ahead file is the hourly product resampled before October
2025, so measuring day-ahead on a 15-minute grid across the whole window would
manufacture exactly the kind of spurious regime change this study is testing
for. On the consistent hourly basis the genuine 15-minute product adds
8,5 EUR/MWh to the 2026 figure, about 6% — real, but not the story.

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean best-2h spread | 100,4 | 105,6 | 115,2 | 144,0 |
| mean daily max-min | 107,6 | 113,0 | 123,2 | 149,6 |
| sd of price | 49,0 | 49,5 | 49,8 | 60,2 |
| % of slots <= 0 | 4,3 | 6,2 | 7,4 | 7,2 |
| mean price | 95,8 | 77,3 | 86,8 | 100,8 |

Read the two tables together. Between 2024 and 2026 the imbalance market's
capturable spread fell 42% and its median fell 47%, its ISP-to-ISP jumpiness
fell 47%, its extreme tail (abs(sell) > 500) thinned by 76%, and its deviation
from day-ahead shrank 32%. Over the same years the day-ahead market's capturable
spread rose 43% and its daily range rose 39%.

That opposite sign is the study's most important single fact, because it rules
out the whole family of explanations that would apply to both markets at once.
"The system got calmer", "renewables levelled off", "there was less scarcity" —
none of these survive, because day-ahead volatility went up while imbalance
volatility went down.

### The price level does not explain it either

2023 was a post-crisis year with high absolute prices, and one obvious worry is
that the whole comparison is a level effect. It is not, and normalising makes
the finding stronger rather than weaker, because the day-ahead level in 2026
(100,8 EUR/MWh) is the highest of the four years:

| best-2h spread / mean day-ahead price level | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance | 5,40 | 6,52 | 3,57 | 2,88 |
| day-ahead | 1,05 | 1,37 | 1,33 | 1,43 |

Level-normalised, the imbalance market's opportunity fell 56% from its 2024 peak
while day-ahead's rose 36% from 2023.

### Seasonality does not explain it

The owner's own comparison window is spring and summer, so the year-over-year
claim has to survive a like-for-like Mar-Aug slice. It survives with a wider
margin than the full-year comparison:

| Mar-Aug only | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance, mean best-2h spread | 559,0 | 581,1 | 362,5 | 322,5 |
| imbalance, median best-2h spread | 480,2 | 469,8 | 222,0 | 204,0 |
| imbalance, mean abs ISP-to-ISP step | 70,2 | 83,0 | 50,1 | 42,6 |
| imbalance, % dual-priced | 7,0 | 13,9 | 24,9 | 40,0 |
| imbalance, % abs(sell) > 500 | 3,29 | 4,07 | 1,45 | 0,84 |
| day-ahead, mean best-2h spread | 101,0 | 115,3 | 138,2 | 172,4 |
| day-ahead, mean daily max-min | 107,5 | 122,9 | 146,6 | 178,6 |

On the exact months the owner cares about, the imbalance median spread is down
57% from 2023 and 57% from 2024, while day-ahead is up 71% from 2023.

### Body and tail both shrank, the tail harder

A compression that only removed spikes would leave a workable everyday business;
one that narrowed ordinary days too is worse. It did both.

| daily best-2h spread, imbalance | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean | 517,8 | 503,9 | 309,7 | 290,2 |
| median | 426,2 | 363,7 | 198,7 | 194,2 |
| p25 | 277,4 | 199,5 | 153,7 | 143,0 |
| p75 | 669,3 | 667,0 | 306,4 | 246,7 |
| mean with prices clipped to +-200 (the body) | 226,2 | 206,9 | 177,4 | 166,2 |
| tail contribution (mean minus clipped mean) | 291,5 | 296,9 | 132,3 | 124,0 |
| tail share of the spread, % | 56,3 | 58,9 | 42,7 | 42,7 |
| % of days with spread < 100 | 0,3 | 3,8 | 5,5 | 9,6 |

The body lost 27% between 2023 and 2026; the tail lost 58%. The p75 — the good
days, which is where a trading strategy makes its year — collapsed 63%, from
669 to 247. Days too flat to trade at all (spread under 100 EUR/MWh) went from
one in 300 to one in ten.

## 2. Predictability got better, not worse

One candidate explanation for a reactive imbalance strategy earning less is that
the price became harder to anticipate. The data says the opposite, and this is
worth stating plainly because it removes an excuse.

| metric, imbalance sell price | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| autocorrelation at 15 min | 0,485 | 0,484 | 0,505 | 0,562 |
| autocorrelation at 30 min | 0,318 | 0,354 | 0,338 | 0,379 |
| autocorrelation at 60 min | 0,242 | 0,277 | 0,226 | 0,248 |
| AR(1) R2 on the level | 0,235 | 0,235 | 0,255 | 0,315 |
| AR(1) R2 on the deviation from day-ahead | 0,200 | 0,205 | 0,209 | 0,269 |
| P(next ISP also <= 0, given this one is) | 0,704 | 0,746 | 0,758 | 0,808 |
| mean run length of sell <= 0, in ISPs | 3,38 | 3,93 | 4,13 | 5,21 |
| P(same price tercile as the previous ISP) | 0,713 | 0,716 | 0,719 | 0,752 |

Every persistence measure improved. A negative-price episode now lasts 5,2 ISPs
where it lasted 3,4 in 2023; knowing the last ISP tells you more about the next
one than it used to. The Mar-Aug slice shows the same pattern.

The implication is important for reading the money table below. If reactive
imbalance trading earns less now, it is not because the signal got noisier. The
signal got slightly cleaner and the prize got smaller. A better reactive
algorithm would not recover the difference, because the difference is in the
price series, not in the forecast.

(Note that persistence skill against a trivial mean forecast stays near zero
throughout: -0,015 in 2023 to +0,064 in 2026. Persistence is informative about
*direction and regime*, never about magnitude. That has not changed.)

## 3. Mechanisms

### 3.1 Dual pricing went from a curiosity to the normal case

TenneT prices the two directions separately. In regulation states 1, -1 and 0 a
single price applies to both; in state 2, where both upward and downward
regulation were dispatched inside the same ISP, the shortage price a battery
pays to charge exceeds the surplus price it receives to discharge. That wedge is
a pure friction on cycling, structurally identical to a supplier fee, and it has
grown from a rounding error into the dominant cost of the strategy.

| regulation state, % of ISPs | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| -1, downward only | 43,1 | 42,9 | 35,4 | 28,4 |
| 0, no regulation | 12,0 | 5,6 | 1,3 | 0,6 |
| 1, upward only | 37,2 | 34,8 | 36,0 | 31,0 |
| **2, both directions (dual-priced)** | **7,7** | **16,8** | **27,3** | **40,0** |

State 2 has gone from 7,7% of quarters to 40,0%, a fivefold rise. What that
costs a battery:

| the dual-pricing wedge | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| % of ISPs dual-priced | 7,5 | 16,5 | 26,3 | 38,1 |
| mean wedge when dual (EUR/MWh) | 130,8 | 182,3 | 85,5 | 72,7 |
| median wedge when dual (EUR/MWh) | 87,6 | 95,8 | 54,5 | 54,8 |
| mean wedge over all ISPs (EUR/MWh) | 9,8 | 30,0 | 22,5 | 27,6 |
| wedge cost per full cycle (EUR) | 0,471 | 1,442 | 1,080 | 1,327 |
| wedge cost at 300 cycles/year (EUR) | 141 | 433 | 324 | 398 |

The last row is a first-order estimate — it assumes the charge and discharge
quarters are drawn at random from the year, which a good optimiser would avoid —
but the order of magnitude is the point. At 2026 rates the wedge is worth about
2,8 ct/kWh of throughput, more than the 2 ct/kWh supplier fee the owner already
treats as a material cost, and in 2023 it was worth 1,0 ct/kWh. This alone is a
structural worsening of the imbalance business independent of any spread change.

This finding independently reproduces the external record. Dutch trade press in
November 2024 reported regeltoestand 2 rising from 8% in 2023 to over 15% in
2024, "a share not seen since 2008", and TenneT intervening because of it. Our
measurement is 7,7% and 16,8%. The series then continues to 27,3% and 40,0%,
which is past the point any of that commentary anticipated.

### 3.2 October 2025: the 15-minute MTU moved volatility out of imbalance

On 1 October 2025 the NL day-ahead market switched from hourly to quarter-hourly
products. Before that date, every intra-hour mismatch between a flat hourly
day-ahead schedule and a continuously varying load and generation profile had
nowhere to be resolved except the imbalance market. After it, the day-ahead
product itself prices the quarters.

This is directly measurable as the within-hour standard deviation of the four
quarter prices:

| mean within-hour sd (EUR/MWh) | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance | 60,2 | 62,4 | 38,6 | 33,2 |
| day-ahead | 0,0 | 0,0 | 2,0 | 9,7 |

Before / after the switch, using all data either side: imbalance 56,6 -> 30,2,
day-ahead 0,0 -> 9,2. Month by month across the boundary:

| month | imbalance within-hour sd | day-ahead within-hour sd | imbalance best-2h spread |
|---|---:|---:|---:|
| 2025-07 | 36,1 | 0,0 | 320,1 |
| 2025-08 | 34,6 | 0,0 | 223,6 |
| 2025-09 | 50,2 | 0,0 | 410,0 |
| **2025-10** | **29,4** | **11,1** | **194,2** |
| 2025-11 | 20,4 | 7,3 | 145,8 |
| 2025-12 | 18,4 | 5,3 | 145,5 |

The day-ahead figure is exactly zero for every month before October 2025 by
construction, because the hourly price was the only price. It becomes non-zero
the month the 15-minute product went live, and imbalance within-hour dispersion
falls 41% in the same month, with the capturable imbalance spread halving. This
is a transfer, not a disappearance: the volatility a battery used to have to
enter the imbalance market to reach is now in a market where it is published a
day ahead and can be traded with certainty.

That single mechanism explains why this study's two headline series move in
opposite directions, and why a self-run day-ahead algorithm should be expected
to have overtaken an imbalance EMS at roughly this point in time.

### 3.3 October 2024: PICASSO

TenneT NL joined the European PICASSO platform for cross-border aFRR exchange in
the week of 14 October 2024. Cross-border balancing pools deeper reserves against
the same national imbalance, which compresses the marginal price of regulation.
The monthly series shows the break:

| period | imbalance best-2h spread | % dual-priced |
|---|---:|---:|
| 2024-06 .. 2024-09 (mean) | 602,3 | 17,3 |
| 2024-10 .. 2024-12 (mean) | 403,5 | 25,4 |

A 33% drop in capturable spread and an eight-point jump in dual pricing, at the
quarter boundary. Dexter Energy's published estimate of the same effect — the NL
day-ahead-to-imbalance spread falling about 20% post-PICASSO, from roughly 50 to
40 EUR/MWh — is directionally consistent with our measured mean abs(imbalance -
day-ahead) falling from 84,1 (2024) to 58,7 (2025), though our metric is not
theirs and the magnitudes are not directly comparable.

### 3.4 Battery fleet growth: plausible, corroborated externally, not identified here

The owner's hypothesis was fleet-driven cannibalisation. The external record
supports rapid growth: Dutch grid-scale storage went from 229 MW / 343 MWh at
end-2023 to 350 MW / 620 MWh at end-2024 (CBS via Energy Storage NL), with
4,1 GW of battery projects "in realization" by September 2025; registered home
batteries reached 20.596 new units in 2025 and 30.856 in the first half of 2026
alone, and market researcher DNE counted nearly 90.000 actual 2025 installations
against the 20.596 registered, so the official series is a floor. A DNV study
commissioned by RVO found in mid-2025 that imbalance trading was the *only*
profitable home-battery model at about 162 EUR/month across 216 real systems,
while explicitly warning that saturation would undermine it.

This study cannot separate the fleet effect from the two dated regulatory events,
because they overlap in time and we have no counterfactual. What the data does
show is that the fleet story cannot be the whole story: fleet growth is smooth
and monotone, whereas the compression arrives in two steps at October 2024 and
October 2025. Fleet growth is best read as the slow background against which the
two step changes landed, and as the reason the market has not recovered between
them.

## 4. The money metric

The dispersion statistics say the opportunity shrank. This section prices it:
the same 48 kWh / 10 kW battery, no PV and no house load, raw prices, run over
every year under five strategies. Imbalance runs on the native 15-minute ISP
grid; day-ahead runs on its own native market time unit, hourly, which is the
consistent basis across all four years. All figures are EUR per year of cash,
wear excluded and reported separately.

The five runs, and what each one honestly represents:

- **(a) Imbalance, perfect foresight.** Rolling daily 13:00 plan over a 36 h
  horizon with the settled ISP prices revealed in advance. Physically impossible
  (ISP prices settle after the fact) and therefore the ceiling on any imbalance
  strategy whatsoever.
- **(b/c) Day-ahead, rolling 13:00 plan.** The identical horizon structure on
  published day-ahead prices. For day-ahead, perfect foresight and the causal
  strategy are the *same run*: D+1 prices are published at 12:45, so a
  prices-only day-ahead algorithm has no forecast error at all. This is both the
  ceiling and the implementable strategy, and it is the closest analogue to the
  algorithm the owner backtested.
- **(d) Imbalance, causal reactive rule.** Trailing 7-day quantile band
  (0,25 / 0,75), charge below the low band and discharge above the high band,
  every trade gated to clear its own round trip and wear. The decision for ISP t
  uses ISP t-1's settled price, which is strictly causal. Parameters held fixed
  across all four years.
- **(d2) The same rule with a live-price bound.** Identical, but deciding ISP t
  on ISP t's own price, standing in for a perfect intra-ISP live estimate. An
  optimistic bound on reactive play.
- **(d3) The best band in hindsight.** The reactive rule swept over eight
  quantile bands, best per year chosen after the fact. An upper bound on
  parameter tuning, and the check that (d) is not just a badly tuned rule.

### Full calendar years, EUR/year

| strategy | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| (a) imbalance, perfect foresight (ceiling) | 5.676 | 5.283 | 3.641 | 3.263 |
| (d2) imbalance, reactive with live-price bound | 3.123 | 2.691 | 1.689 | 1.691 |
| (d3) imbalance, best reactive band in hindsight | 2.283 | 1.738 | 1.209 | 1.428 |
| (d) imbalance, causal reactive rule (fixed) | 2.059 | 1.617 | 1.032 | 1.297 |
| (b/c) day-ahead, rolling 13:00 plan | 1.365 | 1.396 | 1.555 | 1.887 |

Per kWh of installed battery per year, the two rows that matter: the imbalance
ceiling went 118,25 -> 67,98 EUR/kWh/yr, the implementable day-ahead strategy
went 28,44 -> 39,31.

### Equivalent full cycles per year

| strategy | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| (a) imbalance, perfect foresight | 623 | 587 | 580 | 498 |
| (b/c) day-ahead, rolling 13:00 plan | 457 | 440 | 446 | 410 |
| (d) imbalance, causal reactive rule | 245 | 221 | 193 | 181 |

At 0,50 EUR per cycle the wear ledger is 311 / 294 / 290 / 249 EUR/yr for the
imbalance ceiling and 229 / 220 / 223 / 205 for day-ahead. Note that the
imbalance ceiling earns its money at 1,4-1,7 cycles a day, which is close to
what TenneT's own simulations assumed for battery participants and well above
the day-ahead strategy's pace.

### The crossover, which is the answer to the owner's question

| ratio to the day-ahead strategy | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance ceiling / day-ahead | 4,16 | 3,78 | 2,34 | 1,73 |
| imbalance reactive (d) / day-ahead | 1,51 | 1,16 | 0,66 | 0,69 |
| imbalance reactive live bound (d2) / day-ahead | 2,29 | 1,93 | 1,09 | 0,90 |

In 2023 a causal reactive imbalance rule beat a causal day-ahead plan by 51%.
In 2025 and 2026 it loses to it by 31-34%. Even the optimistic live-price
variant, which assumes a perfect intra-quarter price estimate, has fallen from
2,3x day-ahead to 0,9x. The crossover happens during 2025, between the two
structural events identified in section 3.

This is the quantitative form of the owner's intuition, and it matches his lived
experience: a commercial imbalance-trading EMS realised roughly 980 EUR on this
battery over mid-March to mid-August 2026, while the self-run day-ahead backtest
made roughly 1.360 EUR raw over the same window on the hourly frame used here
(roughly 1.410 on the quarter-hourly frame this repo reports as headline).
Figures are rounded, as in the README. A market where the honest reactive proxy
earns 0,69x what day-ahead earns is a market where that outcome is expected
rather than surprising.

### Mar-Aug like-for-like

The owner's comparison window is spring and summer, so the same table on the
seasonal slice:

| strategy, Mar-Aug only | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| (a) imbalance, perfect foresight | 6.058 | 6.017 | 4.190 | 3.576 |
| (d2) imbalance, reactive live-price bound | 3.353 | 3.333 | 2.119 | 1.937 |
| (d3) imbalance, best reactive in hindsight | 2.634 | 2.320 | 1.616 | 1.679 |
| (d) imbalance, causal reactive rule | 2.361 | 2.205 | 1.354 | 1.514 |
| (b/c) day-ahead, rolling 13:00 plan | 1.395 | 1.545 | 1.859 | 2.281 |
| **reactive (d) / day-ahead** | **1,69** | **1,43** | **0,73** | **0,66** |

Same crossover, slightly sharper, and located between 2024 and 2025. Seasonality
is not doing the work.

### Controls

| control run, EUR/year | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance ceiling, dual-pricing wedge removed | 6.093 | 6.383 | 4.351 | 4.085 |
| cost of the dual-pricing wedge (difference) | 417 | 1.100 | 710 | 822 |
| imbalance ceiling on hourly-averaged prices | 4.817 | 4.412 | 2.834 | 2.667 |
| value of the 15-min ISP grid (difference) | 859 | 871 | 807 | 596 |

Two things worth reading off this. First, **without the dual-pricing wedge 2024
would have been the best year of the four**, at 6.383 EUR/yr against 2023's
6.093. The wedge is not a side effect of the compression, it is a substantial
independent part of it: it cost 417 EUR/yr in 2023 and 822 in 2026, roughly
doubling. Second, the imbalance market's 15-minute granularity is still worth
about 600 EUR/yr, but that advantage is eroding too (859 -> 596) and day-ahead
has now acquired its own 15-minute product, which adds 137 EUR/yr to the
day-ahead result in 2026 (2.024 against 1.887 hourly).

*Caveat on the day-ahead 15-min control:* before October 2025 the quarter-hourly
day-ahead file is the hourly product resampled, so running it at 15-minute
resolution for 2023 and 2024 measures finer dispatch on the same prices, not new
price information. Only the 2026 figure reflects a genuine quarter-hourly
market.

### What is robust here and what is not

The **trajectory** is robust. It appears in the perfect-foresight ceiling, which
contains no strategy at all, and it appears at similar magnitude in every
reactive variant including the best-tuned-in-hindsight one. It survives the
seasonal slice and the price-level normalisation.

The **absolute level** of the reactive rows is proxy-dependent and should be read
as a lower bound. A real EMS trades on a sub-quarter live signal published every
12 seconds since July 2025, nets a portfolio, and earns aFRR capacity income
that never appears in a settled ISP price series. Our (d2) bound partly covers
the first of these; nothing here covers the other two. If a commercial EMS
earns materially more than 1.297 EUR/yr equivalent on a battery this size, that
gap is where it comes from, and it does not contradict anything above.

## 5. External evidence

Collected by web search, kept separate from the measurements above. The rule
applied here is that anything this study measured itself is reported as data,
and anything only asserted elsewhere is reported as a claim with its source.

**Corroborates, and is independently reproduced by our data.** The rise of
regeltoestand 2 from 8% in 2023 to over 15% in 2024, reported by Solar & Storage
Magazine on 16 November 2024 alongside TenneT's decision to intervene by delaying
publication of the imbalance signal from 2 to 5 minutes on 3 December 2024
(<https://solarmagazine.nl/nieuws-zonne-energie/i39044/tennet-grijpt-in-vanwege-regeltoestand-2-partijen-varen-nu-lange-tijd-in-de-mist>).
Our measurement is 7,7% and 16,8%, and the series continues to 40,0% in 2026.
RaboResearch's Sanne de Boer made the same point in September 2024, calling home
battery payback promises "questionable" precisely because of state 2.

**Corroborates the dating.** PICASSO went live for TenneT NL in the week of
14 October 2024 (<https://dexterenergy.ai/news/go-live-of-picasso-in-the-netherlands/>);
we find a 33% spread drop and an eight-point dual-pricing jump at that quarter
boundary. The 15-minute day-ahead MTU went live on the EPEX/Nord Pool day-ahead
auction on 30 September 2025, effective for delivery from 1 October; our
day-ahead series carries a within-hour standard deviation of exactly zero before
that date and non-zero from that month onward, which both dates the event in our
own data and validates the day-ahead feed.

**Corroborates the direction, weaker sourcing.** Dexter Energy (26 February 2026,
<https://dexterenergy.ai/news/balancing-markets-in-2026/>) put the post-PICASSO
NL day-ahead-to-imbalance spread compression at about 20%, roughly 50 to
40 EUR/MWh; Dexter is itself a balancing service provider. A DNV study for RVO
reported in June 2025 that imbalance trading was the only profitable home
battery model (about 162 EUR/month over 216 real systems) while warning that
saturation would erode it
(<https://www.solar365.nl/nieuws/alleen-onbalansmarkt-biedt-volgens-onderzoek-rendabel-verdienmodel-voor-thuisbatterij-66ABB5B4.html>).
A Dutch comparison site claims realised returns fell from 150-200 EUR/month in
2023 and early 2024 to 80-120 in 2025 and lower again in 2026 for a 10-20 kWh
battery; that site sells batteries, the figure is unaudited, and it should be
read as directional only.

**Contradicts, or at least complicates.** No source found argues the
compression did not happen, which is itself a weak signal — an absence of
dissent in commentary is not evidence. More usefully, the independent tracker
Mijnbatterij.nl shows very large month-to-month swings in realised home-battery
imbalance earnings during 2026 (73,87 EUR per 10 kW in February, 178,16 in June,
about 87 in a partial August), which is a real caution: any conclusion drawn
from a short window can be seasonal noise. This study's answer to that is the
Mar-Aug control and the full-year series, both of which show the same thing.

**Price level context, verified against our own data.** NL day-ahead annual
means reported externally are about 95,90 (2023), 77-78 (2024) and 87 (2025)
EUR/MWh. Our independently fetched series gives 95,82, 77,29 and 86,82. That
agreement is a useful check that the day-ahead feed is the right series.
External sources also report negative day-ahead hours rising from 458 (2024) to
584 (2025); the solar-driven cannibalisation of the day-ahead market is a real
and separate phenomenon, and it is part of why day-ahead spreads widened.

**Growth figures, unverifiable here.** Grid-scale storage 229 MW / 343 MWh at
end-2023 to 350 MW / 620 MWh at end-2024 (CBS via Energy Storage NL,
<https://www.energystoragenl.nl/en/2025/07/21/explosieve-groei-batterijopslag-in-nederland/>);
20.596 registered new home batteries in 2025 and 30.856 in H1 2026
(<https://solarmagazine.nl/nieuws-zonne-energie/i42603/netbeheerders-registreerden-vorig-jaar-20-596-nieuwe-batterijen>),
against DNE Research's count of nearly 90.000 actual 2025 installations. No
source gives the fraction of that fleet actively trading imbalance, so the
cannibalisation channel cannot be quantified from public data.

## 6. Adversarial review: what would overturn this

Taking each way the tempting story could be wrong.

**"It is seasonal."** Controlled. The Mar-Aug slices show the effect more
strongly than the full years (imbalance median spread down 57% versus the
full-year 54%; the imbalance-to-day-ahead spread ratio falling 5,54 to 1,87
versus 5,16 to 2,02). Rejected.

**"It is the price level. 2023 was a post-crisis year."** Controlled, and it
cuts the other way. The day-ahead level in 2026 is the highest of the four years
at 100,8 EUR/MWh, so normalising by the level increases the measured
compression, from 42% to 56% off the 2024 peak. Rejected.

**"The whole system just got calmer."** Rejected by the day-ahead control. On
identical metric definitions and a consistent hourly basis, the day-ahead
market's capturable spread rose 43% and its daily range rose 39% over the same
years. Volatility did not leave the
system; it changed venue.

**"Our reactive proxy is just a weak strategy, so this measures our algorithm,
not the market."** This is the strongest objection and it is only partly
answerable. Three things reduce it. First, the perfect-foresight imbalance
ceiling declines by a similar proportion, and that number contains no strategy
at all — it is the most any algorithm could have extracted. Second, the reactive
rule was swept across eight quantile bands per year and the best band in
hindsight declines too, so the result is not an artefact of one parameter choice
frozen at the wrong value. Third, predictability improved, so a smarter reactive
rule has *more* signal to work with in 2026 than in 2023 and still earns less.
What remains genuinely proxy-dependent is the *absolute level* of the reactive
numbers: a real EMS with a live sub-ISP price estimate, aFRR capacity income,
and a portfolio to net against would earn more than our rule does. The
*trajectory* is what this study asserts; the *level* is a lower bound.

**"The data is wrong."** Checked three ways. Per-year row counts, mean prices,
minima and negative-share all reproduce an earlier, independently fetched copy
of the same TenneT series exactly, as do the four `buy < sell` exceptions. The day-ahead annual means reproduce externally
published figures to within 0,1 EUR/MWh. The money engine, re-driven here by a
separately written harness, reproduces the day-ahead study's published 12-month
pure-price bound to 0,45 EUR out of 858,27 (0,05%) at 214,1 versus 214,0
equivalent full cycles.

**What could still overturn it.** Three things, honestly.

1. *A regime change back.* Two of the three mechanisms are one-off structural
   events already absorbed. If the compression is mostly PICASSO plus the 15-min
   MTU rather than fleet saturation, there is no reason to expect further
   decline, and the 2026 quarterly series does show a partial recovery in
   absolute imbalance spread from the 2025Q4 trough (162 to 350 in 2026Q2).
   The imbalance market is smaller, not dying.
2. *Imbalance income we do not model.* This study prices energy arbitrage only.
   A real aggregator also earns aFRR capacity payments and portfolio netting
   value that never appear in the settled ISP price series. If those have grown
   while spreads shrank, an EMS's realised result could hold up better than our
   ceiling suggests. We found no NL time series for this and flag it as the
   largest unpriced term.
3. *The reactive rule's sub-ISP blindness.* Real passive-imbalance play acts on
   TenneT's live intra-ISP estimate, which since July 2025 is published every
   12 seconds rather than once a minute. Our lag-0 variant approximates a
   perfect live estimate and brackets this, but a strategy trading *within* the
   quarter on a 12-second feed is outside what a settled-ISP dataset can
   evaluate at all.

## Reproduction

```
cd analysis
python3 market_character.py all   # cache/market_character.json   (~1 min)
python3 mc_mechanism.py           # cache/mechanism.json
python3 mc_validate.py            # cache/validation.json
python3 mc_report.py              # cache/tables.md, every table in this document
```

The three price panels ship gzipped in `analysis/cache/`
(`isp_full.csv.gz`, `da_hourly.csv.gz`, `da_q15.csv.gz`), so the whole chain
runs offline with no API keys and no network. `mc_build.py` is the step that
built them from raw cached TenneT day fragments; it is included for
completeness but needs a raw fetch cache that is not shipped.

The scripts import `opt.py`, `params.py` and `sched.py` from the repository root
unmodified, so the battery physics and the MILP are exactly the ones the
day-ahead algorithm uses. Each strategy is one continuous pass over the whole
2023-2026 span with SOC carried across, sliced into years, Mar-Aug seasons,
quarters and months afterwards, so period boundaries cost no warm-up.

Validation is in `analysis/cache/validation.json`. The money engine reproduces
this repo's published 12-month pure-price day-ahead bound to 0,45 EUR out of
858,27 (0,05%) at 214,1 versus 214,0 equivalent full cycles, which is
meaningful because it is a separately written driver over the same planner. The
price panel reproduces every per-year statistic from an earlier independent
fetch of the same TenneT series exactly, including the four `buy < sell`
exceptions.

Data sources: TenneT publishes settled imbalance prices as market transparency
information at `publications.tennet.eu`; day-ahead prices come from
`api.energy-charts.info`. Both are public.

**Performance note for anyone reusing this code.** `run_rolling` filters its
horizon with `hz[hz.isin(sell.index)]`, not `np.isin(hz, sell.index)`. A
tz-aware `DatetimeIndex` degrades to an object array under numpy, which makes
`np.isin` about 500x slower here (2,58 s versus 0,005 s per call, measured), and
at 1.300 daily solves that is the difference between a 44-second run and a
53-minute one. `backtest.py` carried the same slow form in `run_planned` and was
fixed in this repo for the same reason.
