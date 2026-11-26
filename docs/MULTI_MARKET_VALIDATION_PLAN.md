# Multi-Market Validation Plan

Status: design baseline for the next development stage
Target branch: `feature/v2.3.0`
Scope: reusable simulation engine and evidence-based validation; no broker connectivity or order execution.

## 1. Objective

Demonstrate that the same core simulation engine can process valid price series from different markets and asset classes without assuming NIFTY 50, one exchange calendar, one currency, or one sampling frequency.

"Universal" means the input and validation workflow is market-agnostic where mathematically appropriate. It does not mean every asset class has identical market mechanics or that one model is suitable for every instrument.

## 2. Asset-class coverage

Build validation in stages:

1. Equity indices: NIFTY 50, S&P 500, NASDAQ-100, FTSE 100, Nikkei 225.
2. Individual equities and ETFs: multiple regions, currencies, and corporate-action profiles.
3. FX: major currency pairs; explicitly model quote/base convention and 24x5 session structure.
4. Commodities: representative spot or futures series; record contract/roll methodology and avoid stitching unadjusted futures contracts as if they were one continuous instrument.
5. Cryptoassets: 24x7 observations, exchange/source identity, quote currency, and venue-specific gaps.

Options, leveraged products, and complex derivatives are not certified merely by accepting a close-price CSV. They require separate instrument-specific data and model validation before being included in a supported-claims list.

## 3. Core engine versus market metadata

Keep the GBM/Monte Carlo calculation core independent of provider symbols and exchange names. Introduce or standardize an explicit dataset manifest containing:

- instrument identifier and asset class;
- venue/source and source URL or file provenance;
- currency and price units;
- bar interval and annualization convention;
- exchange timezone and session/calendar identifier where applicable;
- price field and adjustment basis (raw, split-adjusted, total-return/adjusted);
- corporate-action review status;
- futures contract and roll methodology when applicable;
- first/last observation, row count, and data hash.

The existing CSV date/close path remains supported. Missing or unverified metadata must be reported as unknown; never infer it silently.

## 4. Data validation requirements

Retain strict checks for positive finite prices, valid timestamps, chronological ordering, duplicates, and interval anomalies. Add tests and reporting for:

- timezone-aware timestamps and daylight-saving transitions;
- irregular sessions, exchange holidays, and 24x7 assets;
- missing bars versus legitimate closed sessions;
- currency/unit consistency;
- split/dividend adjustments for equities;
- futures expiry and roll discontinuities;
- extreme returns, stale prices, and provider gaps.

A generic validator cannot prove an exchange calendar or corporate-action adjustment is correct. Those checks require trusted reference metadata or an explicit human review.

## 5. Validation programme

A. Engine compatibility: deterministic synthetic series representing daily, weekly, intraday, 24x5, and 24x7 intervals. Verify that the same engine accepts valid inputs and rejects invalid metadata/data.

B. Real-data smoke tests: at least two independent instruments per asset class and multiple regions, with provenance and hashes recorded.

C. Historical out-of-sample tests: rolling-origin forecasts, multiple untouched periods, leakage-safe baselines, and per-instrument results. Never pool all markets into one score without also showing each market and asset-class result.

D. Regime coverage: calm, high-volatility, crisis, trend, and sideways periods where data is available.

E. Robustness: path-count convergence, repeated seeds, parameter sensitivity, missing-data handling, and provider cross-checks.

F. Model suitability: compare GBM against simple historical/empirical baselines. If model assumptions are materially violated, report limitations or unsupported status rather than forcing a forecast.

## 6. Metrics and success gates

Report separately for each instrument, asset class, and aggregate:

- data-integrity pass rate and unresolved metadata;
- forecast coverage and skipped origins;
- direction metrics only when a direction forecast is explicitly defined;
- price forecast error and interval coverage;
- probability calibration (Brier score/log loss) against leakage-safe baselines;
- stability across seeds/path counts;
- results by period/regime.

Do not label a Brier score, directional hit rate, or Monte Carlo sampling convergence as "profit accuracy". Do not use one 0-100 score as the sole success criterion. Any summary score must be defined in advance, accompanied by component metrics, and withheld if data-integrity gates fail.

## 7. Implementation order

1. Preserve and audit the existing v2.3.0 engine and tests.
2. Define the dataset manifest and interval/annualization contract.
3. Add market-calendar/session metadata without embedding one exchange's rules in the core engine.
4. Add synthetic cross-asset and interval tests.
5. Refactor the OOS evaluator so instrument datasets are configuration-driven rather than hard-coded to six US ETFs.
6. Add real-data datasets incrementally with provenance, licensing/source constraints, and reproducible hashes.
7. Run the full test suite and CI on this feature branch.
8. Publish a coverage matrix showing supported, tested, pending, and unsupported instrument classes.

## 8. Guardrails

- All work stays on `feature/v2.3.0`; do not merge, release, or deploy to `main` without separate approval.
- Do not modify the core simulation mathematics unless a reproducible defect and regression test justify it.
- No fabricated market observations, forecasts, or test results.
- No claim of universal accuracy from a small sample or a single index.
- This is statistical research software, not an investment recommendation or execution system.
