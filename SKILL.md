---
name: 200k-future-simulation
version: 2.3.0
description: Universal educational Monte Carlo scenario skill with corrected drift semantics, collect-all data audits and memory-efficient summaries.
---

# 200K Future Simulation — Universal AI Skill

## Purpose
A reusable, platform-independent instruction skill and Python analysis library. It is not an autonomous agent, trading bot, broker connection, or execution system.

## Mandatory rules
1. Never invent prices, dates, news, fundamentals, data sources, or results. State data provenance and freshness.
2. Request instrument, market, interval, date range, currency and source when essential. Prefer machine-readable CSV with date and close columns; screenshots alone are insufficient for robust simulation.
3. Validate positive finite closes, ISO timestamps, ordering, duplicates, gaps, declared interval, currency metadata and corporate-action review status. The default validator is fail-fast; use collect_all_errors=True for structured errors and warnings. Never silently sort, interpolate, drop or adjust data.
4. A generic engine cannot independently verify exchange calendars, currency correctness or corporate-action adjustments. Mark them unverified unless source evidence or explicit review is supplied.
5. Use 200,000 paths by default when computation and data quality permit. Report actual count, seed, horizon, interval, drift assumption and volatility estimate.
6. Prefer streamed summary mode for long horizons or memory-constrained devices. It retains terminal values and optional barrier counts, not the full paths-by-steps matrix.
7. Present conditional scenarios, never guaranteed outcomes. Sampling precision does not remove model, data or estimation error.
8. Use WAIT, NO TRADE or INSUFFICIENT DATA when evidence is inadequate. Do not force a directional conclusion.
9. No claims of live data, broker access or order execution unless verified. Keep responses educational and non-personalized; do not provide individualized buy/sell or investment-sizing instructions.

## Optional external-provider cross-check
The core simulation engine and CSV-based workflow do not require a Stooq account, Stooq API key, or any external provider credential. The optional multi-market research script can attempt a separate Stooq comparison when `STOOQ_API_KEY` is configured. If it is not configured or Stooq cannot provide valid data, record `api_key_required` or another explicit unavailable status and continue the simulation/OOS evaluation. Never describe the provider comparison as completed unless valid overlapping return observations were actually compared.

## Workflow
1. Define instrument, market, timeframe, forecast horizon and analysis question.
2. Load CSV using engine.data_io.load_price_csv; review timestamp order, duplicates, price values, interval gaps, currency and corporate-action status.
3. Calculate historical returns, annualized volatility, drawdown, VaR, expected shortfall and Sharpe only when meaningful.
4. Run reproducible GBM scenarios; use return_paths=False when a full path matrix is unnecessary. By default each simulated step is one observation interval (`1/periods_per_year` years; e.g. 1/252 for daily bars, 1/52 for weekly bars). Set `step_year_fraction` explicitly when the observation interval differs. Report `horizon_years`; do not interpret `steps` as a one-year horizon. Historical mode defaults to drift_convention=corrected so simulated mean log drift matches historical mean log return. Use legacy only to reproduce v2.2.0 outputs; disclose this convention because it changes historical-mode distributions and walk-forward diagnostics.
5. For hypothetical long-only barriers require 0 < stop < entry < target and report target-first, stop-first, neither and same-step ambiguity.
6. Separate deterministic shocks from probability scenarios.
7. Run walk-forward diagnostics with a rolling estimation window (default 252 observations for daily bars). Compare the multiclass Brier score against the leakage-safe empirical baseline, which may use only prior barrier outcomes whose complete horizons were observed before the forecast origin. Fit a convex blend of raw GBM probabilities and the empirical baseline only on prior forecasts whose complete outcomes have matured; use the baseline alone until the minimum calibration sample is available. Report raw, calibrated and baseline Brier scores, the Brier skill score and per-class observed versus predicted frequencies. Use multiple untouched out-of-sample periods; calibration is not profitability.
8. Generate a structured JSON report using engine.report.
9. State limitations and conclude conservatively.

## Specialist libraries (not agents)
- validate_price_series and validate_dated_prices: numeric, timestamp, ordering, duplicate and interval checks.
- volatility_profile: historical volatility with explicit annualization frequency.
- apply_price_shock: deterministic stress transformation.
- iter_gbm_path_chunks and safe_gbm_paths: chunked GBM path generation and numerical-saturation reporting. The primitive drift argument is arithmetic GBM mu, not mean log return.

## Limitations
GBM assumes constant parameters and lognormal increments. It does not inherently capture jumps, volatility clustering, fat tails, regime changes, liquidity, spreads, slippage, market impact, taxes, corporate actions, halts, overnight gaps or intrabar high/low ordering. Close-only data cannot establish intrabar barrier order. Exchange holidays and corporate actions require trusted external calendars and adjustment metadata.

## Required output
- Data provenance, currency and interval status
- Data-quality findings and unresolved checks
- Model assumptions, path count, seed and horizon
- Historical risk summary
- Scenario distribution and barrier probabilities when applicable
- Deterministic stress scenarios, clearly labeled
- Validation diagnostics when available
- Limitations, uncertainty and conservative conclusion


## v2.3.0 compatibility note
Historical simulations now use corrected drift by default. The legacy convention reproduces the prior v2.2.0 parameterization. Walk-forward scores can change after this correction and should be re-evaluated. The walk-forward diagnostic defaults to a rolling 252-observation estimation window and reports a causal empirical baseline, a leakage-safe probability blend and Brier skill score; configure the estimation and calibration windows for the actual bar interval. The optional `min_calibration_improvement` gate can require a minimum relative Brier improvement on matured calibration history before applying a non-zero raw-model blend; the default 0.0 preserves existing behavior. Neither convention establishes profitability.
