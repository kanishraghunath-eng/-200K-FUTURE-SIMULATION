# Changelog

## [2.3.0] - 2026-11-25

### Changed
- Corrected historical GBM drift semantics. Historical annualized mean log return is converted to arithmetic GBM drift by adding half the annualized variance before path generation.
- Added explicit drift metadata to simulation outputs and JSON reports.
- Added drift_convention="corrected" as the default and "legacy" to reproduce v2.2.0 historical-mode behavior.
- Added drift_convention passthrough to walk-forward barrier diagnostics.

### Added
- Added audit_dated_prices and collect_all_errors=True for structured multi-error validation and warnings.
- Added collect_all_errors and max_abs_return options to the CSV loader; invalid audited input returns prices=None.
- Added regression coverage for drift semantics, legacy compatibility, audit aggregation and CSV audit behavior.

### Compatibility and limitations
- The corrected default changes historical-mode paths and walk-forward diagnostics relative to v2.2.0. Re-evaluate historical diagnostics before comparing results.
- The legacy convention is provided for reproducibility, not as a recommended model.
- A gap greater than three days remains a heuristic warning, not an exchange-calendar determination.
- Python 3.11 CI is the target runtime; local Python 3.11 execution was not available during this change.

## [2.2.0]
- Added dated-series validation, CSV loading, streamed GBM summary mode, terminal quantiles, optional barrier probabilities and JSON reports.
