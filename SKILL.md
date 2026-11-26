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

## Validation tooling
Use `scripts/evaluate_multi_market_oos.py` for held-out multi-market diagnostics and the Yahoo/EODHD VTI adjusted-return comparison. The provider check is complete only when at least 100 matched return intervals are actually compared; otherwise report the exact non-success status. Use `scripts/benchmark_200k.py` for a separate streamed 200K-path performance and sampling-convergence study. Its synthetic input is for engine benchmarking only, not market prediction validation.

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


## Multi-market data workflow
Use `engine.dataset_manifest.DatasetManifest` to declare each instrument's asset class, source, currency, bar interval, timezone, calendar and adjustment basis. Intraday/tick inputs must declare `periods_per_year`; do not assume the same annualization across equity sessions, FX, and 24x7 crypto.
Use `engine.canonical_data` to map and validate provider rows. Validation never repairs data. Interval gaps may be warnings when exchange calendars or session breaks are not independently available.
Optional provider adapters are in `engine.providers`: CSV, Yahoo Finance chart, Stooq daily and EODHD daily. Keep provider failures and source provenance explicit.
For reproducible multi-instrument evaluation, use `scripts/evaluate_dataset_manifest_oos.py`. It reports each dataset separately; do not combine the outputs into one universal accuracy score. A successful input audit is not evidence of predictive accuracy.

Canonical market-data rows may include optional open/high/low/volume. Validate OHLC range consistency and volume, and never combine raw OHLC with adjusted close as if they shared one price basis.

## Cross-market coverage policy
This project must not be optimized only for NIFTY 50. Design instruments and tests across distinct market structures, including equity indices, listed equities/ETFs, FX, crypto spot, commodity spot, and exchange-traded futures when contract-level roll data is available. A representative test set is not universal coverage: name the instruments, providers, intervals and exclusions in every report. Do not pool heterogeneous instruments into one headline accuracy score.

## Multi-agent development and independent testing
This skill may be used by Claude, Gemini, ChatGPT or another coding assistant. Treat all assistants as contributors to one repository, not as sources of authority:
1. Read the current SKILL.md, project README, roadmap, relevant source, tests and latest CI evidence before editing.
2. Work only on the explicitly assigned development branch (currently feature/v2.3.0). Never push directly to main, merge, release or deploy unless the project owner explicitly authorizes that exact action.
3. Before editing, state the files and acceptance criteria. Make small, reviewable commits with tests. Do not overwrite another assistant's unreviewed changes; fetch the latest branch before each work session.
4. Use a primary implementer and a different assistant as independent reviewer/test designer. The reviewer should challenge assumptions and add tests, not merely repeat the implementer's claims. Rotate roles between tasks.
5. Run the full unit/regression suite, focused tests, CLI smoke tests and relevant workflow checks. Report exact commands, exit codes, commit SHA, workflow run IDs and artifacts. A green CI proves only that its checks passed; it does not prove predictive skill or profitability.
6. Never fabricate test results, market observations, API access, data coverage, or completed work. Separate PASS, FAIL, BLOCKED and NOT RUN.
7. Keep API keys and other secrets in the provider's secret manager (for example GitHub Actions Secrets). Never request that the owner paste a secret into a chat, commit it, log it, include it in a report, or expose it in a source URL.
8. If a provider credential is unavailable, continue with mock-based tests, CSV fixtures and other verified no-key data sources. Mark live-provider and independent-source checks BLOCKED; do not simulate a successful live response.
9. If an assistant reaches a usage limit, the owner may hand the exact task, branch, commit SHA, test evidence and remaining blockers to another assistant. The next assistant must first inspect repository state and continue from the existing branch; do not recreate work blindly.

## Current project validation state (2026-11-26)
- Active development branch: feature/v2.3.0. Keep all further work there unless the owner explicitly changes scope.
- Universal unit/regression CI: PASS on Python 3.11.
- Dedicated 200K-path performance/convergence workflow: PASS. This is a compute/sampling benchmark, not market forecast validation.
- Manifest-driven exploratory OOS: 10 datasets configured; 6 evaluated and 4 provider errors in the latest recorded run. Failed providers: EODHD TLT (HTTP 401), EODHD VTI.US (HTTP 401), Stooq SPY (API key required), and XAUUSD=X corporate-action reference (EODHD HTTP 404). The exploratory run must not be called confirmatory.
- Exploratory bootstrap uncertainty was computed for six evaluated datasets. The confidence intervals crossed zero and Holm-adjusted p-values were 1.0 in the reported tests; there is no demonstrated statistical superiority over the causal baseline in those results.
- Yahoo continuous ticker GC=F is exploratory only. It remains excluded from confirmatory work until actual contract-level constituents, declared roll rule, overlapping contract observations and adjustment method are independently audited.
- ETF candidates require successful corporate-action reconciliation. Without the EODHD token currently available to the project, TLT/VTI corporate-action verification is BLOCKED. Do not claim it passed.
- Confirmatory protocol 200K-FS-CONFIRMATORY-OOS-v1 is frozen: holdout starts 2026-11-27 and ends 2027-12-31. At the 2026-11-26 freeze, the correct status is blocked_preconditions / awaiting_future_holdout; zero holdout forecasts exist. Do not score pre-holdout observations as confirmatory, peek early, replace failed candidates after the start, or extend the end date after seeing results.
- The pre-registered family contains seven candidates: ^NSEI, ^GSPC, EURUSD=X, BTC-USD, TLT, VTI.US, and XAUUSD=X. Family-level confirmation requires all seven to pass the frozen data gates and statistical acceptance criteria. A missing provider credential is a blocker, not permission to weaken the protocol.

## Immediate next development tasks
1. Diagnose the EODHD 401 and 404 paths without a live token; add explicit provider error classification and tests. Do not invent a token or use credentials from another user.
2. Investigate lawful, stable, no-key alternative sources for adjusted ETF prices and corporate actions. Verify documentation, coverage, symbol support, rate limits, adjustment semantics and reproducibility before changing the manifest. Do not silently substitute a raw close for adjusted close.
3. Treat Stooq as optional. Without STOOQ_API_KEY, report api_key_required and keep the core engine, CSV workflow and other tests working.
4. For gold, distinguish spot reference data from futures. Do not route XAUUSD=X through an EODHD endpoint unless the provider documents that exact symbol and endpoint.
5. Improve futures audit only with contract-level fixtures and genuine documented source data. Synthetic tests validate code paths, not actual futures roll history.
6. Keep the confirmatory manifest and protocol immutable after the freeze unless a new, separately versioned protocol is preregistered before its own holdout begins.
7. Add cross-market tests for multiple intervals and calendars. Never imply that one successful NIFTY test establishes universal skill performance.

## Owner handoff report format
At the end of each work session provide:
- Branch and exact head commit SHA
- Files changed and purpose
- Tests run with exact pass/fail counts
- CI workflow run IDs and artifact names/links
- Dataset/provider status table
- Unresolved risks and blockers
- The single safest next task
Do not merge, release or deploy merely because a test run is green.
