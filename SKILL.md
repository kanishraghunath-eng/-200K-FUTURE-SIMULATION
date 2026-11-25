---
name: 200k-future-simulation
version: 2.2.0
description: Universal educational Monte Carlo scenario skill with dated-data validation, CSV loading and memory-efficient summaries.
---

# 200K Future Simulation — Universal AI Skill

## Purpose
A reusable, platform-independent instruction skill and Python analysis library. It is not an autonomous agent, trading bot, broker connection, or execution system.

## Mandatory rules
1. Never invent prices, dates, news, fundamentals, data sources, or results. State data provenance and freshness.
2. Request instrument, market, interval, date range, currency and source when essential. Prefer machine-readable CSV with date and close columns; screenshots alone are insufficient for robust simulation.
3. Validate positive finite closes, ISO timestamps, ordering, duplicates, gaps, declared interval, currency metadata and corporate-action review status. Never silently sort, interpolate, drop or adjust data.
4. A generic engine cannot independently verify exchange calendars, currency correctness or corporate-action adjustments. Mark them unverified unless source evidence or explicit review is supplied.
5. Use 200,000 paths by default when computation and data quality permit. Report actual count, seed, horizon, interval, drift assumption and volatility estimate.
6. Prefer streamed summary mode for long horizons or memory-constrained devices. It retains terminal values and optional barrier counts, not the full paths-by-steps matrix.
7. Present conditional scenarios, never guaranteed outcomes. Sampling precision does not remove model, data or estimation error.
8. Use WAIT, NO TRADE or INSUFFICIENT DATA when evidence is inadequate. Do not force a directional conclusion.
9. No claims of live data, broker access or order execution unless verified. Keep responses educational and non-personalized; do not provide individualized buy/sell or investment-sizing instructions.

## Workflow
1. Define instrument, market, timeframe, forecast horizon and analysis question.
2. Load CSV using engine.data_io.load_price_csv; review timestamp order, duplicates, price values, interval gaps, currency and corporate-action status.
3. Calculate historical returns, annualized volatility, drawdown, VaR, expected shortfall and Sharpe only when meaningful.
4. Run reproducible GBM scenarios; use return_paths=False when a full path matrix is unnecessary.
5. For hypothetical long-only barriers require 0 < stop < entry < target and report target-first, stop-first, neither and same-step ambiguity.
6. Separate deterministic shocks from probability scenarios.
7. Run walk-forward diagnostics only with sufficient data; calibration is not profitability.
8. Generate a structured JSON report using engine.report.
9. State limitations and conclude conservatively.

## Specialist libraries (not agents)
- validate_price_series and validate_dated_prices: numeric, timestamp, ordering, duplicate and interval checks.
- volatility_profile: historical volatility with explicit annualization frequency.
- apply_price_shock: deterministic stress transformation.
- iter_gbm_path_chunks and safe_gbm_paths: chunked GBM path generation and numerical-saturation reporting.

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
