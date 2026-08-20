### Money, Full calendar years (EUR/year, raw prices, wear excluded)

| strategy | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance, perfect foresight (ceiling) | 5.676 | 5.283 | 3.641 | 3.263 |
| imbalance, causal reactive rule (fixed params) | 2.059 | 1.617 | 1.032 | 1.297 |
| imbalance, best reactive in hindsight | 2.283 | 1.738 | 1.209 | 1.428 |
| imbalance, reactive with live-price bound | 3.123 | 2.691 | 1.689 | 1.691 |
| day-ahead, rolling 13:00 plan (implementable) | 1.365 | 1.396 | 1.555 | 1.887 |

### Ratios and cycling, Full calendar years

| period | imb ceiling / DA | imb reactive / DA | EFC/yr imb PF | EFC/yr imb reactive | EFC/yr DA |
|---|---:|---:|---:|---:|---:|
| 2023 | 4,16 | 1,51 | 623 | 245 | 457 |
| 2024 | 3,78 | 1,16 | 587 | 221 | 440 |
| 2025 | 2,34 | 0,66 | 580 | 193 | 446 |
| 2026 | 1,73 | 0,69 | 498 | 181 | 410 |

### Money, Mar-Aug only (seasonal control) (EUR/year, raw prices, wear excluded)

| strategy | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance, perfect foresight (ceiling) | 6.058 | 6.017 | 4.190 | 3.576 |
| imbalance, causal reactive rule (fixed params) | 2.361 | 2.205 | 1.354 | 1.514 |
| imbalance, best reactive in hindsight | 2.634 | 2.320 | 1.616 | 1.679 |
| imbalance, reactive with live-price bound | 3.353 | 3.333 | 2.119 | 1.937 |
| day-ahead, rolling 13:00 plan (implementable) | 1.395 | 1.545 | 1.859 | 2.281 |

### Ratios and cycling, Mar-Aug only (seasonal control)

| period | imb ceiling / DA | imb reactive / DA | EFC/yr imb PF | EFC/yr imb reactive | EFC/yr DA |
|---|---:|---:|---:|---:|---:|
| 2023 | 4,34 | 1,69 | 622 | 247 | 464 |
| 2024 | 3,90 | 1,43 | 597 | 239 | 447 |
| 2025 | 2,25 | 0,73 | 593 | 218 | 442 |
| 2026 | 1,57 | 0,66 | 491 | 184 | 420 |

### Imbalance dispersion, Full calendar years (EUR/MWh unless stated)

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean sell price | 93,6 | 66,2 | 72,2 | 84,9 |
| sd of sell price | 195,0 | 225,9 | 166,0 | 188,5 |
| IQR of sell price | 67,0 | 89,2 | 86,6 | 82,6 |
| mean daily max-min | 1.136,1 | 1.247,0 | 799,8 | 758,2 |
| mean best-2h spread | 517,8 | 503,9 | 309,7 | 290,2 |
| median best-2h spread | 426,2 | 363,7 | 198,7 | 194,2 |
| mean abs ISP-to-ISP step | 68,9 | 72,2 | 44,8 | 38,4 |
| % ISPs sell <= 0 | 19,5 | 25,0 | 19,1 | 16,6 |
| % abs(sell) > 200 | 8,37 | 6,07 | 2,73 | 3,23 |
| % abs(sell) > 500 | 2,73 | 3,07 | 1,08 | 0,74 |
| % dual-priced (buy > sell) | 7,5 | 16,5 | 26,3 | 38,1 |
| mean buy-sell wedge | 9,8 | 30,0 | 22,5 | 27,6 |
| mean abs (imb - DA) | 79,5 | 84,1 | 58,7 | 57,2 |
| mean (imb - DA) | -2,2 | -11,1 | -14,6 | -16,0 |
| corr(imb sell, DA) | 0,242 | 0,223 | 0,280 | 0,297 |

### Day-ahead dispersion, Full calendar years (EUR/MWh)

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean DA price | 95,8 | 77,3 | 86,8 | 100,8 |
| sd of DA price | 49,0 | 49,5 | 50,1 | 62,1 |
| mean daily max-min | 107,6 | 113,0 | 129,9 | 177,9 |
| mean best-2h spread | 100,4 | 105,6 | 117,5 | 152,5 |
| % slots DA <= 0 | 4,3 | 6,2 | 7,4 | 7,2 |

### Imbalance dispersion, Mar-Aug only (EUR/MWh unless stated)

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean sell price | 89,2 | 54,8 | 62,3 | 82,5 |
| sd of sell price | 195,5 | 237,8 | 180,9 | 202,2 |
| IQR of sell price | 58,7 | 95,9 | 90,4 | 113,0 |
| mean daily max-min | 1.174,1 | 1.431,6 | 946,9 | 881,4 |
| mean best-2h spread | 559,0 | 581,1 | 362,5 | 322,5 |
| median best-2h spread | 480,2 | 469,8 | 222,0 | 203,9 |
| mean abs ISP-to-ISP step | 70,2 | 83,0 | 50,1 | 42,6 |
| % ISPs sell <= 0 | 19,1 | 28,6 | 23,2 | 20,5 |
| % abs(sell) > 200 | 8,80 | 7,57 | 2,68 | 3,62 |
| % abs(sell) > 500 | 3,29 | 4,07 | 1,45 | 0,84 |
| % dual-priced (buy > sell) | 6,9 | 13,9 | 24,9 | 40,0 |
| mean buy-sell wedge | 8,6 | 28,5 | 22,7 | 31,0 |
| mean abs (imb - DA) | 83,0 | 92,1 | 63,8 | 61,3 |
| mean (imb - DA) | -0,1 | -11,5 | -14,5 | -18,4 |
| corr(imb sell, DA) | 0,236 | 0,212 | 0,262 | 0,310 |

### Day-ahead dispersion, Mar-Aug only (EUR/MWh)

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean DA price | 89,3 | 66,3 | 76,8 | 100,9 |
| sd of DA price | 47,4 | 44,4 | 50,4 | 69,7 |
| mean daily max-min | 107,5 | 122,9 | 146,6 | 211,0 |
| mean best-2h spread | 101,0 | 115,3 | 138,2 | 181,9 |
| % slots DA <= 0 | 5,2 | 10,0 | 12,0 | 9,6 |

### Opportunity normalised by the price level, full years

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance best-2h spread / mean DA level | 5,40 | 6,52 | 3,57 | 2,88 |
| day-ahead best-2h spread / mean DA level | 1,05 | 1,37 | 1,35 | 1,51 |
| mean DA price level (EUR/MWh) | 95,8 | 77,3 | 86,8 | 100,8 |

### Regulation-state mix, % of ISPs, full years

| state | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| state -1 | 43,1 | 42,9 | 35,4 | 28,4 |
| state 0 | 12,0 | 5,5 | 1,3 | 0,6 |
| state 1 | 37,2 | 34,8 | 36,0 | 31,0 |
| state 2 | 7,7 | 16,8 | 27,3 | 40,0 |

### Predictability of the imbalance price, full years

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| ACF lag 15 min | 0,485 | 0,484 | 0,505 | 0,562 |
| ACF lag 30 min | 0,318 | 0,354 | 0,338 | 0,379 |
| ACF lag 60 min | 0,242 | 0,277 | 0,226 | 0,248 |
| ACF lag 2 h | 0,115 | 0,117 | 0,114 | 0,125 |
| AR(1) R2, price level | 0,235 | 0,235 | 0,255 | 0,315 |
| AR(1) R2, deviation from DA | 0,200 | 0,205 | 0,209 | 0,269 |
| persistence skill vs mean | -0,015 | -0,016 | 0,005 | 0,064 |
| P(next ISP also <= 0 | <= 0) | 0,704 | 0,746 | 0,758 | 0,808 |
| mean run length of sell <= 0 (ISPs) | 3,38 | 3,93 | 4,13 | 5,21 |
| P(same price tercile as previous ISP) | 0,713 | 0,716 | 0,719 | 0,752 |

### Quarterly series (EUR/year run-rate; spread and dual share from the same quarter)

| quarter | imb ceiling | imb reactive | DA rolling | imb/DA | best-2h spread | % dual |
|---|---:|---:|---:|---:|---:|---:|
| 2023 Q1 | 6.094 | 1.777 | 1.276 | 4,78 | 502,0 | 7,2 |
| 2023 Q2 | 5.771 | 1.992 | 1.376 | 4,20 | 528,9 | 7,1 |
| 2023 Q3 | 6.053 | 2.825 | 1.601 | 3,78 | 591,2 | 6,6 |
| 2023 Q4 | 4.809 | 1.635 | 1.207 | 3,98 | 448,8 | 9,1 |
| 2024 Q1 | 4.564 | 1.601 | 773 | 5,90 | 469,0 | 11,9 |
| 2024 Q2 | 5.963 | 1.977 | 1.574 | 3,79 | 560,4 | 11,0 |
| 2024 Q3 | 6.075 | 2.251 | 1.821 | 3,34 | 583,3 | 17,6 |
| 2024 Q4 | 4.543 | 641 | 1.410 | 3,22 | 402,9 | 25,4 |
| 2025 Q1 | 3.986 | 816 | 1.487 | 2,68 | 339,3 | 20,6 |
| 2025 Q2 | 4.724 | 1.415 | 2.082 | 2,27 | 422,4 | 26,1 |
| 2025 Q3 | 3.684 | 1.316 | 1.673 | 2,20 | 316,9 | 27,9 |
| 2025 Q4 | 2.190 | 580 | 983 | 2,23 | 162,0 | 30,6 |
| 2026 Q1 | 2.707 | 936 | 1.207 | 2,24 | 233,3 | 35,1 |
| 2026 Q2 | 3.789 | 1.571 | 2.367 | 1,60 | 350,4 | 40,7 |
| 2026 Q3 | 3.312 | 1.454 | 2.264 | 1,46 | 282,6 | 38,6 |

### Reactive-rule parameter sweep (EUR/year, full years)

| quantile band | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| 0.10/0.90 | 1.410 | 1.179 | 735 | 821 |
| 0.20/0.80 | 1.886 | 1.495 | 996 | 1.181 |
| 0.25/0.75 | 2.059 | 1.617 | 1.032 | 1.297 |
| 0.30/0.70 | 2.129 | 1.681 | 1.137 | 1.361 |
| 0.35/0.65 | 2.226 | 1.680 | 1.170 | 1.412 |
| 0.40/0.60 | 2.283 | 1.720 | 1.209 | 1.428 |
| 0.45/0.55 | 2.251 | 1.738 | 1.183 | 1.390 |
| 0.50/0.50 | 2.238 | 1.724 | 1.182 | 1.372 |

### Controls (EUR/year, full years)

| run | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance PF, 15-min, dual pricing | 5.676 | 5.283 | 3.641 | 3.263 |
| imbalance PF, dual-pricing wedge removed | 6.093 | 6.383 | 4.351 | 4.085 |
| imbalance PF, hourly-averaged prices | 4.817 | 4.412 | 2.834 | 2.667 |
| day-ahead rolling, hourly MTU | 1.365 | 1.396 | 1.555 | 1.887 |
| day-ahead rolling, 15-min MTU | 1.861 | 1.976 | 1.695 | 2.024 |

### Intra-hour price structure (EUR/MWh, mean within-hour sd)

| market | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| imbalance, within-hour sd | 60,2 | 62,4 | 38,6 | 33,2 |
| day-ahead, within-hour sd | 0,0 | 0,0 | 2,0 | 9,7 |

Before / after the 2025-10-01 switch to a 15-minute day-ahead MTU: imbalance 56,6 -> 30,2; day-ahead 0,0 -> 9,2.

### The dual-pricing wedge, full years

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| % of ISPs dual-priced | 7,5 | 16,5 | 26,3 | 38,0 |
| mean wedge when dual (EUR/MWh) | 130,8 | 182,3 | 85,5 | 72,7 |
| median wedge when dual (EUR/MWh) | 87,6 | 95,8 | 54,5 | 54,8 |
| mean wedge over all ISPs (EUR/MWh) | 9,8 | 30,0 | 22,5 | 27,6 |
| wedge cost per full cycle (EUR) | 0,471 | 1,442 | 1,080 | 1,327 |
| wedge cost at 300 EFC/yr (EUR) | 141 | 432 | 324 | 398 |

### Body versus tail of the daily imbalance spread (EUR/MWh)

| metric | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| mean best-2h spread | 517,8 | 503,9 | 309,7 | 290,2 |
| median | 426,2 | 363,7 | 198,7 | 194,2 |
| p25 | 277,4 | 199,5 | 153,7 | 143,0 |
| p75 | 669,3 | 667,0 | 306,4 | 246,7 |
| mean, prices clipped to +-200 | 226,2 | 206,9 | 177,4 | 166,2 |
| tail contribution (mean - clipped) | 291,5 | 296,9 | 132,3 | 124,0 |
| tail share of the spread, % | 56,3 | 58,9 | 42,7 | 42,7 |
| % of days with spread < 100 | 0,3 | 3,8 | 5,5 | 9,6 |
