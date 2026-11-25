# 200K Future Simulation — Universal AI Skill v2.2.0

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

## v2.2.0
- Added dated-series validation for ISO timestamps, ordering, duplicates, positive finite closes and optional interval checks.
- Added standard-library CSV loader for date,close files.
- Added streamed GBM chunks and return_paths=False summary mode to avoid allocating the full paths-by-steps output matrix.
- Added terminal quantiles and optional barrier probabilities in streamed mode.
- Added dependency-free JSON report generation.
- Preserved the original full-path API as the default.

## Limitations
Currency labels and corporate-action review flags are metadata, not independent verification. Exchange holidays require a trusted market calendar. GBM scenarios are conditional illustrations, not predictions or guarantees.
