# 200K Future Simulation — Universal AI Skill v2.3.0

Reusable platform-neutral skill instructions plus a Python scenario-analysis engine. Libraries and instructions only: no AI agents, broker integration or trade execution.

## Contents
- SKILL.md: universal assistant operating instructions.
- engine/: Monte Carlo, barrier probabilities, risk metrics, walk-forward diagnostics, CSV loading and report generation.
- engine/specialists/: data-quality, volatility, deterministic shock and numerical-stability libraries.
- tests/: unit and integration tests.

## Quick start
    python -m pip install -r requirements.txt
    python -m compileall -q engine tests
    python -m unittest discover -s tests -v

## v2.3.0
- Fixed forecast timestep scaling: each simulated step now defaults to one observation interval (`1/periods_per_year` years), rather than dividing a one-year horizon by the requested number of steps.
- Added explicit `step_year_fraction` override and horizon metadata; walk-forward diagnostics use the same interval as their observed future bars.
- Corrected historical GBM drift: historical mean log return is converted to arithmetic GBM drift before simulation.
- Added drift_convention=legacy to reproduce v2.2.0 historical simulation semantics; corrected is the default.
- Added drift metadata to simulation and JSON reports; walk-forward diagnostics accept the convention.
- Added rolling-window walk-forward calibration (default 252 observations) and a leakage-safe empirical baseline using only fully observed prior barrier outcomes.
- Reports raw GBM, calibrated blend and baseline multiclass Brier scores, Brier skill score and per-class observed/predicted frequencies. The blend weight is fitted only on prior forecasts with fully matured outcomes; it falls back to the empirical baseline until enough calibration history exists.
- Added collect-all dated-data audit with structured errors and warnings; default fail-fast behavior is preserved.
- CSV audit mode returns prices=None when validation fails; no automatic sorting, dropping or repair.

## v2.2.0
- Added dated-series validation for ISO timestamps, ordering, duplicates, positive finite closes and optional interval checks.
- Added standard-library CSV loader for date,close files.
- Added streamed GBM chunks and return_paths=False summary mode to avoid allocating the full paths-by-steps output matrix.
- Added terminal quantiles and optional barrier probabilities in streamed mode.
- Added dependency-free JSON report generation.
- Preserved the original full-path API as the default.

## Optional Stooq provider cross-check
The simulation engine, CSV input workflow, and ordinary tests do **not** need a Stooq API key or any provider credential. The multi-market OOS workflow also continues when `STOOQ_API_KEY` is absent: its report records `api_key_required` for the optional SPY/Stooq comparison, while the Yahoo-based OOS and Monte Carlo stability diagnostics still run. Configure the `STOOQ_API_KEY` GitHub Actions repository secret only if you separately want to attempt that provider comparison. A missing or rejected key must never be represented as a successful independent-provider validation.

## Walk-forward calibration
The walk-forward diagnostic defaults to a rolling 252-observation estimation window (appropriate for daily data when configured as 252 sessions per year). It reports a causal empirical baseline built only from prior barrier outcomes whose full forecast horizons were already observed. A convex blend of raw GBM probabilities and that baseline is calibrated on prior forecasts whose outcomes have fully matured; until the minimum calibration sample is available, the baseline is used. The Brier skill score compares the calibrated probabilities with the empirical baseline on the evaluated sample; it does not establish profitability or future reliability. Set `estimation_window` explicitly for other sampling intervals and compare multiple untouched out-of-sample periods. The regime-evaluation script compares improvement gates of 0%, 0.5%, 1%, and 2%; these are experiments, not an assertion that any threshold is universally optimal.

## Limitations
Currency labels and corporate-action review flags are metadata, not independent verification. Exchange holidays require a trusted market calendar. GBM scenarios are conditional illustrations, not predictions or guarantees.


## Drift conventions
The GBM primitive accepts arithmetic drift mu and applies log increments `(mu - sigma^2 / 2) * dt`. Historical mode estimates annualized mean log return. The corrected default adds `0.5 * sigma^2` before calling the primitive so the simulated expected log drift matches the historical estimate. Set `drift_convention="legacy"` only when reproducing v2.2.0 outputs. This correction changes historical-mode path distributions and walk-forward scores; compare and re-baseline diagnostics before interpreting results.

## Data audit
`validate_dated_prices(..., collect_all_errors=True)` returns structured `errors` and `warnings`. `load_price_csv(..., collect_all_errors=True)` returns `prices=None` for invalid input. The default remains fail-fast for compatibility. A gap greater than three days is a warning when no strict calendar-daily interval is declared; this is not an exchange-calendar determination.
