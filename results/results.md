# Results

Synthetic data as of 2026-07-19: 320 weekly channel cohorts, 375,770 installs. Regenerate with `make all`.

## Backtest: forecast 180-day revenue per install from the first k days

Only cohorts whose real 180-day value is known; each forecast uses only data that existed on its day k.

| Channel | k | Multiplier MAPE | Curve-fit MAPE | Multiplier bias | Cohorts |
|---|---|---|---|---|---|
| paid_social | 7 | 19.0% | 125.2% | -6.1% | 26 |
| paid_social | 14 | 14.2% | 184.3% | -3.2% | 27 |
| paid_social | 30 | 11.2% | 181.2% | -0.6% | 29 |
| paid_video | 7 | 23.0% | 58.5% | +14.6% | 26 |
| paid_video | 14 | 23.2% | 74.1% | +20.9% | 27 |
| paid_video | 30 | 11.3% | 118.9% | +3.5% | 29 |
| rewarded_network | 7 | 3.8% | 184.0% | +1.0% | 26 |
| rewarded_network | 14 | 3.7% | 137.8% | +0.4% | 27 |
| rewarded_network | 30 | 2.3% | 89.2% | +0.1% | 29 |

A power law fitted to a cohort's own first days overshoots badly: revenue climbs fastest in the first days, so the fitted curve keeps climbing long after real players have left. Learning the growth from older cohorts of the same channel is far more accurate, so the recommendation uses the multiplier method.

## Recommendation from day 14

| Channel | Spend | CPI | D7 ROAS | D180 ROAS forecast | 90% range | Actual D180 ROAS | Payback day | Decision |
|---|---|---|---|---|---|---|---|---|
| paid_social | $20,993 | $2.35 | 0.07 | 0.93 | 0.74 to 1.23 | 0.80 | after 180 | **hold** |
| paid_video | $19,655 | $3.15 | 0.04 | 1.00 | 0.61 to 1.08 | 1.12 | after 180 | **hold** |
| rewarded_network | $9,222 | $0.90 | 0.34 | 0.61 | 0.57 to 0.65 | 0.60 | after 180 | **cut** |

## Recommendation from day 30

| Channel | Spend | CPI | D7 ROAS | D180 ROAS forecast | 90% range | Actual D180 ROAS | Payback day | Decision |
|---|---|---|---|---|---|---|---|---|
| paid_social | $21,054 | $2.36 | 0.06 | 0.83 | 0.69 to 1.04 | 0.79 | after 180 | **hold** |
| paid_video | $19,526 | $3.14 | 0.05 | 1.05 | 0.83 to 1.23 | 1.20 | 163 | **hold** |
| rewarded_network | $9,188 | $0.90 | 0.34 | 0.61 | 0.59 to 0.64 | 0.61 | after 180 | **cut** |

## What this shows

- **Day-7 ROAS picks the wrong channel.** rewarded_network has by far the best day-7 ROAS and the worst 180-day ROAS: its players earn quickly from ads and then leave. paid_video is the slowest starter and the only channel that pays back.
- **Day 14 is too early for a slow-burn channel.** From day 14 the paid_video range does not quite reach its actual ROAS; from day 30 every range contains the actual value.
- **Decisions use the low and high ends, not the point forecast.** A channel is scaled only when even the low end pays back, and cut only when even the high end does not.
