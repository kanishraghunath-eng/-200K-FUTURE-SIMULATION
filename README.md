# 200K Future Simulation — Universal AI Skill

A reusable, platform-neutral instruction skill plus a Python scenario-analysis engine. This repository contains **libraries and instructions only — no AI agents, broker integration, or trade execution**.

## Contents
- `SKILL.md`: assistant operating instructions and analysis workflow.
- `engine/`: reproducible Monte Carlo, barrier probabilities, historical risk metrics, walk-forward diagnostics, and specialist modules.
- `tests/`: automated unit and integration tests.
- `examples/sample_prices.csv`: small illustrative dataset.
- `adapters/PLATFORM_NOTES.md`: platform-neutral installation notes.

## Quick start
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Core behavior
- 200,000 Monte Carlo paths by default when computation and data quality permit.
- Reproducible GBM scenario paths with explicit seed and assumptions.
- Long-only target/stop first-hit probabilities, including same-step ambiguity.
- Historical volatility, VaR, expected shortfall, drawdown, and Sharpe diagnostics.
- Walk-forward multiclass Brier-score diagnostic (not a profitability test).
- Conservative `WAIT`, `NO TRADE`, or `INSUFFICIENT DATA` conclusions when justified.

## Important limitations
Monte Carlo outputs are conditional scenarios, not guaranteed predictions. GBM does not inherently model jumps, volatility clustering, fat tails, regime changes, liquidity, costs, or market impact. Close-only data cannot establish intrabar barrier ordering. Never claim live data or execution unless actually available and verified.

See [SKILL.md](SKILL.md) for the complete operating rules.
