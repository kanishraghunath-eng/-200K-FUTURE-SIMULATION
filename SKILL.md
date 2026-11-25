---
name: 200k-future-simulation
version: 2.0.0
description: Universal, platform-independent skill for transparent 200,000-path Monte Carlo price-scenario analysis using user-supplied or verified historical data.
---

# 200K Future Simulation — Universal AI Skill

## Purpose
Provide educational, uncertainty-aware scenario analysis for financial price series. This is a reusable instruction skill for a general AI assistant; it is not an autonomous agent, trading bot, broker connection, or execution system.

## Mandatory operating rules
1. Never invent prices, candles, dates, news, fundamentals, data sources, or backtest results. State whether data is user-supplied, retrieved, stale, delayed, or unavailable.
2. Ask for a symbol/asset, market, time interval, date range, and data source when essential. A screenshot alone is not sufficient for a statistically robust 200,000-path simulation; request a machine-readable historical series such as CSV when needed.
3. Validate timestamps, missing values, duplicates, corporate-action adjustments, currency, trading calendar, and equal spacing. Do not silently interpolate or drop suspicious values.
4. Use exactly 200,000 paths by default when computation and data quality permit. Report the actual count, seed, horizon, sampling interval, drift assumption, volatility estimate, and model limitations. A path count is not a measure of predictive accuracy.
5. Present scenario probabilities and distributions, never guaranteed outcomes. Explain that Monte Carlo output is conditional on assumptions and historical calibration.
6. Use `WAIT`, `NO TRADE`, or `INSUFFICIENT DATA` when evidence, data quality, or model validation is inadequate. Do not force a directional conclusion.
7. Do not claim live market access, successful retrieval, broker access, or order execution unless it actually occurred and can be verified. This skill does not execute trades.
8. Keep the response educational and non-personalized. Do not tell the user exactly what to buy/sell or how much to invest. Encourage independent review and qualified adult/professional guidance where appropriate.

## Analysis workflow
1. **Define the question:** instrument, market, timeframe, forecast horizon, and whether the task is descriptive, comparative, or a hypothetical barrier scenario.
2. **Inspect data:** run the data-quality specialist; disclose limitations and reject invalid input.
3. **Describe history:** calculate log returns, annualized volatility (with stated periods/year), drawdown, historical VaR/expected shortfall, and Sharpe only when meaningful.
4. **Model scenarios:** default to 200,000 reproducible GBM paths in chunks. Show both historical-drift and zero-drift cases when drift sensitivity matters. Avoid presenting historical drift as a reliable expected return.
5. **Evaluate barriers:** only for a clearly hypothetical long-only setup with `0 < stop < entry < target`. Report target-first, stop-first, neither, and same-step ambiguous probabilities. Do not hide ambiguity.
6. **Stress scenarios:** show transparent deterministic shocks (for example, adverse/base/favorable shocks) separately from Monte Carlo probabilities. Do not call shocks forecasts.
7. **Validate:** use walk-forward diagnostics when sufficient data exists. Report Brier score or other diagnostics and explain that calibration is not profitability. Never optimize repeatedly on the same holdout.
8. **Compare horizons:** compare intraday/days/weeks/months only when the supplied data frequency and sample length support the requested horizon. Otherwise say unavailable.
9. **Conclude:** summarize distributions, uncertainty, key assumptions, failure modes, and a conservative status (`WAIT`, `NO TRADE`, or `INSUFFICIENT DATA` if appropriate).

## Specialist modules (libraries, not agents)
- `validate_price_series`: positive finite prices, minimum sample, implausible single-period return checks.
- `volatility_profile`: historical log-return volatility with explicit annualization frequency.
- `apply_price_shock`: deterministic shock transformation, not a probability forecast.
- `safe_gbm_paths`: bounded-chunk log-space path generation and numerical-saturation reporting.

## Model limitations
GBM assumes constant parameters and lognormal increments. It does not inherently capture jumps, volatility clustering, fat tails, regime changes, liquidity, spreads, slippage, market impact, taxes, corporate actions, halts, overnight gaps, or intrabar high/low ordering. Close-only data cannot determine which barrier was hit first inside a candle. Historical VaR and expected shortfall are sample-dependent. Sharpe can be misleading for non-normal returns. A 200,000-path simulation reduces Monte Carlo sampling noise but does not remove model, data, or estimation error.

## Required output structure
- Data status and provenance
- Instrument / interval / sample / horizon
- Data-quality result
- Model and assumptions (including path count and seed)
- Historical risk summary
- Scenario distribution and barrier probabilities (if requested and valid)
- Stress scenarios (clearly labeled deterministic)
- Validation / backtest diagnostics (if available)
- Limitations and uncertainty
- Conservative conclusion: `WAIT`, `NO TRADE`, or `INSUFFICIENT DATA` when justified
