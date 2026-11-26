# Exploratory OOS Validation Summary — 2026-11-26

Status: exploratory; no universal validation claim.
Repository branch: `feature/v2.3.0`.
Primary multi-market OOS run: [45832999926](https://github.com/kanishraghunath-eng/-200K-FUTURE-SIMULATION/actions/runs/45832999926).
Legacy six-ETF held-out run: [45832438201](https://github.com/kanishraghunath-eng/-200K-FUTURE-SIMULATION/actions/runs/45832438201).
Historical regime run: [45832384226](https://github.com/kanishraghunath-eng/-200K-FUTURE-SIMULATION/actions/runs/45832384226).
Independent provider check: [45831833651](https://github.com/kanishraghunath-eng/-200K-FUTURE-SIMULATION/actions/runs/45831833651).

## 1. Executive result

The current evidence is mixed and dataset/protocol dependent.

- Manifest-driven multi-market OOS evaluated 8 of 9 datasets across daily and 1-hour intervals.
- All 8 manifest-market 95% moving-block-bootstrap confidence intervals for Brier Skill included zero; all Holm-adjusted p-values were 1.0. No statistically reliable improvement over the causal baseline was established in this broad representative sample.
- A separate legacy six-ETF held-out experiment found positive Brier Skill in several US ETFs. After Holm adjustment across 24 instrument/calibration-gate comparisons, four ETFs (EEM, EFA, IWM, SPY) retained evidence of improvement at the tested 0.05 level for the reported gate-0 comparison; QQQ and TLT did not. This is a separate protocol and must not be merged with the manifest results.
- Historical regime results were mixed: positive in some regimes and negative or inconclusive in others.
- 200,000-path checks establish numerical simulation stability at selected origins, not predictive accuracy or profitability.

Therefore the Skill is **not proven to generalize across all markets**. No confirmatory pass/fail threshold has been set during this exploratory stage.

## 2. Manifest-driven multi-market OOS

Configuration: 1,000 Monte Carlo paths per forecast; five-observation outcome horizon; instrument-specific causal baseline; 2,000-replicate circular moving-block bootstrap with block length five; Holm adjustment across eight evaluated instruments.

| Instrument | Interval | OOS forecasts | Brier Skill | 95% block-bootstrap CI | Holm-adjusted p |
|---|---:|---:|---:|---:|---:|
| NIFTY 50 (`^NSEI`) | Daily | 4,451 | -0.2215% | [-1.0903%, 0.6462%] | 1.000 |
| S&P 500 (`^GSPC`) | Daily | 6,509 | -0.5543% | [-1.7095%, 0.5271%] | 1.000 |
| EUR/USD | Daily | 5,708 | -0.4029% | [-2.7383%, 1.8260%] | 1.000 |
| BTC/USD | Daily | 4,197 | +0.0550% | [-0.3096%, 0.4062%] | 1.000 |
| Gold continuous futures | Daily | 6,330 | +0.1375% | [-0.6335%, 0.8748%] | 1.000 |
| TLT | Daily | 5,865 | +0.0139% | [-0.5199%, 0.5108%] | 1.000 |
| VTI (EODHD) | Daily | 6,154 | -0.4033% | [-1.5679%, 0.7312%] | 1.000 |
| SPY | 1 hour | 3,064 | -0.4596% | [-3.3076%, 1.7714%] | 1.000 |

Coverage: 8 evaluated, 1 provider error. Stooq `spy.us` returned fewer than three usable observations.

All confidence intervals include zero. Positive point estimates for BTC, gold, and TLT are small and not statistically distinguishable from no improvement under this exploratory procedure.

### Data handling notes

- Raw-source SHA-256 and canonical-dataset SHA-256 are recorded separately in the report.
- EUR/USD and gold were explicitly configured as close-only inputs; OHLCV fields were excluded because the current diagnostic consumes close prices only. Their OHLCV quality is not validated by these runs.
- SPY 1-hour data was retrieved successfully for the configured period and evaluated; session gaps and interval-specific market-calendar semantics still need review.
- Gold continuous-futures roll methodology remains unverified.
- Stooq remains an unresolved provider failure.

The uncertainty artifact from run 45832999926 records the per-instrument bootstrap results and hashes.

## 3. Separate legacy six-ETF held-out experiment

This is a different experiment: six US ETFs, 1,314 OOS forecasts per instrument, five-observation horizon, 2%/2% barriers, four calibration gates, 2,000-replicate circular moving-block bootstrap, and Holm adjustment across 24 instrument/gate comparisons.

Gate 0.0 summary:

| Instrument | Brier Skill | 95% block-bootstrap CI | Holm-adjusted p |
|---|---:|---:|---:|
| EEM | +2.364% | [1.410%, 3.263%] | 0.012 |
| EFA | +3.820% | [2.134%, 5.495%] | 0.012 |
| IWM | +2.223% | [1.399%, 3.077%] | 0.012 |
| QQQ | +1.102% | [0.171%, 2.020%] | 0.084 |
| SPY | +4.363% | [2.313%, 6.423%] | 0.012 |
| TLT | +1.505% | [0.109%, 2.843%] | 0.119 |

The EEM, EFA, IWM, and SPY gate-0 results retain a positive signal after the reported family-wise adjustment. QQQ and TLT do not. These findings are specific to this sample, protocol, and provider; adjusted-close history was not independently audited for every ETF.

Do not treat this experiment as a contradiction of the manifest-driven results: the instruments, barrier definitions, fold design, warm-up, and calibration protocol differ.

## 4. Historical regime comparison

A separate SPY close-only study used 6,454 observations from 2000-01-03 to 2025-08-29. At calibration gate 0.0:

| Regime | OOS observations | Brier Skill |
|---|---:|---:|
| Dot-com bear (later phase) | 438 | -0.004% |
| Pre-GFC bull | 1,149 | +0.661% |
| Global financial crisis bear | 351 | +4.039% |
| Long bull | 2,543 | -0.926% |
| COVID high-volatility | 46 | 0.000% |
| 2022 bear | 191 | +2.854% |
| 2023–2025 recovery/bull | 662 | -1.048% |

This is mixed evidence. The COVID segment has only 46 observations and is insufficient for a strong conclusion. The source's corporate-action adjustment status was not independently verified.

## 5. Monte Carlo path-count stability

The legacy six-ETF study compared 10,000 and 200,000 paths at selected fixed origins: 12 comparisons per instrument (four selected folds × three seeds).

Mean absolute probability differences between 10k and 200k:

| Instrument | Mean absolute difference | 95th percentile |
|---|---:|---:|
| EEM | 0.00443 | 0.00777 |
| EFA | 0.00368 | 0.00835 |
| IWM | 0.00298 | 0.00591 |
| QQQ | 0.00454 | 0.00661 |
| SPY | 0.00409 | 0.00718 |
| TLT | 0.00251 | 0.00530 |

These are Monte Carlo sampling differences, not forecast errors. The synthetic 200k benchmark separately measures compute and numerical convergence; it is not a market-data validation.

## 6. Independent provider check

For VTI, Yahoo adjusted close was compared with EODHD adjusted close:

- 6,399 overlapping daily-return observations;
- Pearson return correlation: approximately 0.999962;
- daily-return sign agreement: 100%;
- median absolute daily log-return difference: approximately 0.00000037.

This supports vendor consistency for this one VTI series and matched price basis. It does not validate other instruments or the model's forecasts.

## 7. Correctness and CI evidence

The feature branch CI passed:
- Python compilation and full unit/regression test suite;
- future-data perturbation invariance test;
- matured-label-only calibration test;
- fixed-seed reproducibility test;
- Yahoo adjusted-close/raw-OHLC separation test;
- explicit close-only OHLCV exclusion test;
- hourly Yahoo adapter test;
- block-bootstrap and Holm-adjustment tests;
- selected 200k market-origin convergence test;
- manifest OOS runner and uncertainty-analyzer CLI smoke checks;
- dedicated 200k streamed performance/convergence benchmark.

The latest test workflow is [45833023698](https://github.com/kanishraghunath-eng/-200K-FUTURE-SIMULATION/actions/runs/45833023698).

## 8. Remaining work before confirmatory claims

1. Repair or replace the Stooq data route and independently verify provider coverage.
2. Verify corporate-action basis, exchange calendars, FX session conventions, and gold futures roll methodology.
3. Expand independent provider comparisons beyond VTI.
4. Add more instruments and venues in each market family; representative samples do not prove universal support.
5. Expand multi-timeframe testing beyond the current daily and SPY 1-hour sample.
6. Pre-register numerical acceptance criteria and multiple-comparison handling before opening an untouched confirmatory holdout.
7. Evaluate transaction costs and execution effects separately if a later research phase studies economic performance.

## 9. Boundaries

All work remains on `feature/v2.3.0`. No merge to `main`, release, deployment, broker connection, or order execution was performed. No profitability claim or investment recommendation is made.
