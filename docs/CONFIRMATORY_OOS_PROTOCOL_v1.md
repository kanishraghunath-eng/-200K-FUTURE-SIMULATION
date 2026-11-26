# Confirmatory OOS Protocol v1

Status: pre-registered; waiting for future observations.
Freeze date: 2026-11-26.
Untouched holdout: 2026-11-27 through 2027-12-31 inclusive.
Manifest: `datasets/confirmatory_oos_manifest.json`.
Runner: `scripts/run_confirmatory_oos.py`.

## Research question

Does the fixed close-only GBM probability model improve multiclass Brier Skill over the causal rolling empirical baseline on new, post-freeze forecast origins?

This is a probability-score research test. It does not test profitability, execution quality, or suitability for real-money trading.

## Frozen candidate family

All seven instruments below must pass data and quality gates. If one fails, the family is incomplete; no instrument may be silently dropped or replaced after the holdout begins.

1. `^NSEI` — India equity index, daily.
2. `^GSPC` — US equity index, daily.
3. `EURUSD=X` — FX, daily.
4. `BTC-USD` — crypto spot, daily.
5. `TLT` — US bond ETF, adjusted close, subject to independent corporate-action event reconciliation.
6. `VTI.US` — US equity ETF, adjusted close, subject to independent corporate-action event reconciliation.
7. `XAUUSD=X` — gold spot proxy, daily.

The following are explicitly excluded from this family, with reasons retained in the manifest:
- `GC=F`: vendor continuous-futures ticker without contract-level constituent and roll records.
- `spy.us`: Stooq raw close is a provider-crosscheck input, not a dividend-adjusted confirmatory ETF series.
- SPY 1-hour: raw intraday ETF close does not provide an independently verified distribution-adjusted hourly series.

## Model configuration (frozen)

- 1,000 Monte Carlo paths per forecast; seed 7.
- Target barrier +3%; stop barrier -2%; five-observation outcome horizon.
- 252-observation minimum training and estimation window.
- 252-observation calibration window; at least 100 matured calibration observations.
- Zero minimum calibration improvement; causal convex blend only on matured prior forecast outcomes.
- Corrected drift convention.
- Instrument-specific annualization from the frozen dataset metadata.

Any parameter change requires a new protocol version and a new untouched holdout.

## Primary metric and decision rule

Primary metric:

`Brier Skill = 1 - (model multiclass Brier / causal baseline multiclass Brier)`

For every instrument:
- At least 250 fully matured holdout forecasts per instrument, with forecast origins on or after 2026-11-27 and no later than 2027-12-31.
- The holdout end date is fixed; no early evaluation, repeated peeking, or extension after inspecting results.
- 5,000 circular moving-block bootstrap replicates, block length 5 observations.
- One-sided bootstrap p-values adjusted with Holm across the complete seven-instrument family.
- Instrument passes only if the 95% confidence interval lower bound is greater than zero and the Holm-adjusted p-value is below 0.05.
- Family passes only if all seven instruments pass.

A missing provider, failed canonical audit, unknown price basis, unavailable or mismatched ETF corporate-action audit, or insufficient sample blocks the family-level conclusion.

## Data isolation

Historical observations before 2026-11-27 may be used only for estimation and matured calibration. They are not scored as confirmatory outcomes. Each forecast's complete five-observation outcome must be present before it is included.

No sorting, interpolation, filling, resampling, retroactive manual correction, or post-hoc symbol substitution is allowed. The report records raw-source and canonical-data SHA-256 hashes, provider, metadata, and audit results.

## Why no confirmatory score exists yet

The freeze date is 2026-11-26. At protocol creation, the holdout has not begun. The readiness runner therefore reports `awaiting_future_holdout` until the fixed window has ended and every instrument has 250 matured forecast origins. This is intentional; earlier exploratory data cannot be relabelled as untouched confirmatory evidence. If the fixed window ends with fewer than 250 forecasts for any candidate, the result is insufficient sample and the protocol is not silently extended.

## Interpretation boundary

A positive result supports only the specified instruments, providers, intervals, sample period, and model configuration. It does not prove that the Skill works on every market, nor does Brier Skill establish trading profitability.
