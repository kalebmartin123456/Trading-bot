# Relative strength + breadth candidate V1 — 2026-08-30

## Verdict

**Rejected. Do not add this candidate to paper execution.**

The filter reduced trades, costs, losses, and validation drawdown, especially in the falling market. It did not produce positive return, profit factor above 1, or positive expectancy for BTC or ETH. The final 20% holdout remains sealed and unscored.

## Design fixed before validation

- Candidate: baseline entries allowed only when BTC is above its 168-hour EMA with positive 168-hour return, at least 60% of a ten-asset crypto universe is above its 168-hour EMA, and the traded asset has positive 72-hour absolute and cross-sectional relative strength.
- Universe: BTC, ETH, SOL, LTC, BCH, LINK, UNI, AAVE, DOGE, AVAX against USD.
- Candidate changes entry selectivity only; exits, stops, sizing, costs, and risk are unchanged.
- Evaluation: 730 days ending 2026-08-30 16:00 UTC.
- Development: first 60%; validation: next 20%; sealed holdout: final 20%.
- Universe selection uses currently available assets and therefore carries survivorship bias.

## Chronological results

| Period | Asset | Baseline return | Candidate return | Lift | Baseline / candidate DD | Baseline / candidate PF | Baseline / candidate expectancy | Candidate trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Development | BTC | -7.65% | -3.99% | +3.66% | 8.04% / 5.53% | 0.742 / 0.756 | -$3.24 / -$3.30 | 121 |
| Development | ETH | -8.04% | -7.32% | +0.73% | 8.04% / 8.14% | 0.625 / 0.569 | -$5.66 / -$6.97 | 105 |
| Validation | BTC | -7.25% | -3.28% | +3.97% | 7.67% / 4.33% | 0.304 / 0.288 | -$10.33 / -$15.58 | 23 |
| Validation | ETH | -8.01% | -2.19% | +5.83% | 8.01% / 3.39% | 0.459 / 0.600 | -$8.62 / -$6.51 | 38 |

## Gate result

The forward candidate gate requires each execution asset to have positive candidate return, return above baseline, profit factor above 1, positive expectancy, at least 30 completed trades, and drawdown no worse than baseline.

- Both assets passed incremental return and drawdown non-inferiority.
- Both failed positive return, profit factor, and positive expectancy.
- BTC also failed the 30-trade adequacy floor with 23 validation trades.
- Status: **reject**.

These universal profitability/adequacy criteria were encoded after the candidate was designed and before any holdout unsealing. They are now the prospective minimum for later candidates.

## Regime interpretation

Development was dominated by a broad rise: BTC buy-and-hold gained 78.13% and ETH gained 42.27%. The candidate still lost 3.99% and 7.32%. It reduced participation but did not identify profitable entries; for ETH it slightly worsened drawdown, profit factor, and expectancy.

Validation was a broad decline: BTC buy-and-hold lost 32.37% and ETH lost 37.85%. The filter cut exposure and avoided many baseline trades, reducing loss and drawdown materially. That supports breadth as a defensive veto or regime feature. It does not support the feature as alpha because the trades that survived selection still had negative expectancy.

## Sealed holdout

- Period: 2026-04-06 16:00 UTC through 2026-08-30 16:00 UTC
- Scored: **false**
- Data fingerprint: `b54c3b8f51d466accfad360e1445154bc7c5dc5ac80132b826510920ed3fa2b1`

Do not score this holdout for the rejected candidate. Preserve it for a future candidate that first passes development and validation.
