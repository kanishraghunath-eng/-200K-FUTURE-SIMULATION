# OOS Validation Master Plan

Status: approved exploratory validation plan for `feature/v2.3.0`.
Scope: all representative market families in the current manifest plus an extensible path for adding new markets.
Decision: exploratory evidence first; numerical pass/fail thresholds will be proposed only after the diagnostic phase and documented before any confirmatory holdout is opened.

## 1. Objective

Establish whether the 200K Future Simulation Skill produces reproducible, leakage-safe, statistically credible out-of-sample probability diagnostics across different market families, instruments, providers, and observation intervals.

The purpose is to evaluate model behavior, not to recommend trades, promise returns, or claim that Monte Carlo path count equals predictive accuracy.

## 2. Scope and coverage

The validation matrix must be instrument-level and market-family-level. No pooled global score may hide weak segments.

Initial representative families:
- India equity indices (NIFTY 50; add SENSEX or another independently sourced index when data is available).
- US equity indices and ETFs (S&P 500, broad-market and technology/small-cap ETFs).
- Developed and emerging international equities.
- FX majors, with explicit 24x5 session treatment.
- Commodities, distinguishing spot from futures and documenting contract rolls.
- Digital assets, with UTC and 24x7 handling.
- Bonds/rates, distinguishing ETF price return from total-return/index series.

Existing manifest samples (NIFTY, S&P 500, EUR/USD, BTC/USD, gold continuous futures, TLT, Stooq ETF, EODHD VTI) are pilot coverage, not proof that every family or venue is supported. Each added instrument must carry explicit metadata and its own report.

## 3. Evidence stages

### Stage A — Freeze the experiment

For each run, record:
- repository, branch, commit SHA, Skill version, Python/dependency versions;
- manifest and configuration hashes;
- instrument, provider, venue, asset class, timezone, calendar, currency, interval;
- source price field and adjustment basis;
- requested and actual date ranges, observation count, missing/duplicate timestamps;
- raw-source and canonical-data SHA-256 hashes;
- random seeds, path counts, horizon, estimation window, calibration window, and scoring rule.

Never overwrite a previous report. Store each run as an immutable, dated artifact.

### Stage B — Data and leakage audit

Before scoring:
1. Validate positive finite prices, timestamp ordering, duplicate timestamps, timezone, declared interval, and expected session gaps.
2. Verify OHLC consistency only when OHLC fields share the same price basis as the close field. Adjusted close must not be compared against unadjusted OHLC.
3. Confirm corporate-action adjustments and futures roll methodology; otherwise mark the dataset as provisional or rejected.
4. Ensure chronological splits; no random shuffling of time-series observations.
5. Ensure every forecast uses only information available at its forecast origin.
6. Ensure labels are scored only after the complete outcome horizon has matured.
7. Add a horizon-sized embargo where adjacent split boundaries could otherwise share label information.
8. Test deliberately injected future-data leakage and require the audit/tests to detect it.
9. Never silently sort, interpolate, fill, resample, splice, or repair provider data.

A failed data or leakage audit is reported as rejected/blocked, not as a model failure or success.

### Stage C — Walk-forward OOS evaluation

For each valid instrument:
- Use chronological walk-forward folds.
- Fit estimation parameters only on the training window available at that origin.
- Fit or update calibration only from fully matured prior OOS outcomes.
- Keep a final untouched holdout separate from exploratory model iteration.
- Record every fold and forecast count.
- Evaluate multiple horizons where the underlying data supports them; do not compare incompatible horizons as if equivalent.
- Keep close-only barrier diagnostics explicitly labelled as close-only. Do not infer intrabar path order from daily close data.

The existing six-ETF held-out study and manifest-driven per-asset runner are separate experiments and must retain separate reports.

### Stage D — Baseline and model metrics

At minimum, report per instrument and fold:
- raw multiclass Brier score;
- calibrated multiclass Brier score;
- causal baseline Brier score;
- Brier skill score versus the same instrument's leakage-safe baseline;
- log loss where probabilities are valid and comparable;
- class frequencies and class-wise calibration;
- calibration/reliability summaries with sample counts;
- forecast count, matured-label count, and coverage;
- uncertainty intervals.

Directional metrics and price-distribution errors must be separate from probability-calibration metrics. None of these alone is a profitability measure.

### Stage E — Market and regime analysis

Report results separately by:
- market family and instrument;
- independent chronological fold;
- volatility/regime segment (trend, range, high-volatility, and low-volatility labels must be defined using past-only information);
- data provider and price basis;
- observation interval and forecast horizon.

Regime labels must be derived without looking ahead. Small segments are marked exploratory/insufficient-sample rather than force-ranked.

### Stage F — Provider and metadata cross-checks

- Compare overlapping observations and returns across providers only after matching currency, timezone, corporate-action basis, and dates.
- Report overlap count, return correlation, median absolute return difference, and sign agreement.
- Provider agreement is data-integrity evidence, not model-prediction evidence.
- Provider outages, rate limits, missing fields, and incompatible intervals must remain visible as distinct statuses.
- A provider adapter with mocked tests but no successful live retrieval is not labelled live-validated.

### Stage G — Monte Carlo path-count stability

Treat path-count convergence as numerical simulation stability, not forecast accuracy.
- Compare 1,000, 5,000, 10,000 and, on selected representative origins, 200,000 paths.
- Use fixed origins and multiple fixed seeds.
- Compare probability estimates, absolute differences, and Monte Carlo standard errors.
- Include rare-event/class probabilities and report when the path count is too small to estimate them reliably.
- Choose the expensive 200,000-path sample after measuring runtime and resource use; it need not be run for every origin in every fold.

### Stage H — Statistical uncertainty and multiplicity

- Use uncertainty estimates that respect serial dependence, such as block/bootstrap procedures over forecast sequences or fold-level aggregation.
- Do not treat overlapping forecast horizons as independent observations.
- Correct or otherwise control multiple comparisons when testing many markets, regimes, horizons, and metrics.
- Report effect sizes and uncertainty intervals, not only p-values.
- Exploratory findings generate hypotheses; they do not become confirmatory claims without a separately frozen holdout.

### Stage I — Reproducibility

A repeat run with the same commit, data hashes, configuration, and seeds must reproduce identical deterministic outputs within documented numerical tolerances. Any provider data change must create a new dataset hash and a new report identity.

## 4. Exploratory decision labels

During this approved exploratory stage, use descriptive labels only:
- `EVALUATED`: the declared diagnostic completed on valid data.
- `DATA_REJECTED`: the data failed canonical or metadata validation.
- `PROVIDER_ERROR`: data retrieval failed.
- `INSUFFICIENT_DATA`: sample or matured labels were insufficient.
- `PRELIMINARY_SIGNAL`: an apparent improvement or deterioration exists but is not yet confirmatory.
- `NO_CLEAR_IMPROVEMENT`: results are close to baseline or inconsistent.
- `ROBUSTNESS_CONCERN`: results vary materially across folds, regimes, seeds, or providers.

Do not set universal numeric pass thresholds in this exploratory phase. After reviewing the first complete diagnostic matrix, propose thresholds with rationale, record them in a versioned protocol, and freeze them before opening the confirmatory holdout.

## 5. Current pilot findings to carry forward

The 2026-11-26 pilot workflow (run 43, commit `ff92ca8eb418be59452698813c0551cc919906a7`) completed successfully at the workflow level. The manifest report covered 8 datasets: 5 evaluated, 2 rejected, and 1 provider error. EUR/USD and gold were rejected by OHLC-range validation; this requires investigation of price-basis consistency before any retry. Stooq returned fewer than three usable observations. NIFTY, S&P 500, BTC/USD, TLT, and EODHD VTI completed the manifest diagnostics.

The legacy six-ETF held-out study completed, including 5k/10k convergence samples and a Yahoo/EODHD VTI provider comparison. Its report states that no default recommendation is made automatically. These pilot results are not a final proof of generalization.

All pilot reports and artifacts must be retained as historical evidence. A corrected data pipeline must produce a new run and new hashes; do not silently replace the old results.

## 6. Execution phases

1. **Protocol registration** — commit this plan on the feature branch.
2. **Baseline audit** — inspect current reports, workflows, manifests, and code; list data-quality and leakage risks.
3. **Correctness fixes** — resolve only verified defects, especially price-basis-aware OHLC checks and point-in-time isolation.
4. **Regression suite** — add tests for adjusted-close/OHLC compatibility, future leakage, horizon maturity, split embargo, and deterministic seeds.
5. **Exploratory multi-market run** — execute all valid manifest datasets and preserve per-dataset statuses.
6. **Provider cross-check** — compare independent sources only for matching instruments and comparable price bases.
7. **Regime/timeframe expansion** — add datasets only where reliable interval/calendar metadata and sufficient history exist.
8. **Path convergence** — run fixed-origin, multi-seed 1k/5k/10k comparisons and selected 200k checks.
9. **Statistical review** — compute dependence-aware uncertainty and multiple-comparison-aware summaries.
10. **Confirmatory protocol proposal** — write numeric thresholds and freeze them before the final untouched holdout.
11. **Final report** — publish per-market evidence, rejected datasets, provider limitations, and unresolved risks.

## 7. Execution boundaries

- Work only on `feature/v2.3.0`.
- Do not merge to `main`, create a release, deploy, connect to brokers, or execute orders.
- Do not claim universal market support from representative samples.
- Do not interpret a successful CI run as proof of predictive performance.
- Do not convert exploratory results into personalized trading advice or profit guarantees.

## 8. Definition of credible evidence

Credible evidence requires all of the following:
- clean, point-in-time, reproducible datasets with verified metadata;
- leakage-safe walk-forward and untouched holdout procedures;
- per-market and per-regime results with causal baselines;
- uncertainty estimates that account for serial dependence and multiple comparisons;
- independent provider checks where comparable data exists;
- path-count convergence documented separately from predictive skill;
- transparent reporting of negative, rejected, and inconclusive cases.

The project may be described as validated only for the specific instruments, intervals, horizons, data sources, and periods supported by the completed evidence. No broader claim is permitted without new tests.
