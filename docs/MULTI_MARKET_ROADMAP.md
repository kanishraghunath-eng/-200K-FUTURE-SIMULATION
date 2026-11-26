# Multi-Market and Multi-Asset Expansion Plan

Status: design baseline for v2.3.x; no engine behavior is changed by this document.

## 1. Product objective

The 200K Future Simulation Skill must remain instrument- and venue-agnostic. NIFTY 50 is one validation case, not the product boundary. The same validated simulation core should accept compatible price series from multiple exchanges, countries, asset classes, data vendors, and observation intervals.

"Works across markets" means:
- the same core can process valid normalized observations without market-specific hardcoding;
- market-specific calendars, currencies, contract conventions, corporate actions, and data quality are explicit inputs or independently verified metadata;
- each asset/market family has its own held-out validation evidence;
- unsupported data semantics fail clearly rather than being silently treated as equivalent.

It does not mean one model is automatically accurate on every market or asset class.

## 2. Current v2.3.0 baseline (repository inspection)

- The core Monte Carlo engine accepts a positive close-price sequence and estimates log-return drift and volatility. It is not hardcoded to NIFTY.
- The CSV loader currently requires `date,close`; it validates dated prices but does not normalize exchange-specific feeds.
- The default annualization assumes 252 periods/year unless overridden. This is suitable only when the input interval and market convention justify it.
- The walk-forward barrier diagnostic is close-only and its default thresholds are percentage barriers. It cannot infer intrabar order, transaction costs, liquidity, or contract roll behavior.
- The current multi-market OOS script is not universal: it hardcodes six US-listed ETFs (SPY, QQQ, IWM, EFA, EEM, TLT), Yahoo adjusted-close retrieval, 252-period annualization, and one 5-observation horizon.
- Therefore the engine is partly generic, while ingestion, metadata, validation coverage, and OOS orchestration remain narrow.

## 3. Target architecture

### Layer A — Instrument and market metadata
Define a validated instrument specification containing:
- instrument identifier and asset class;
- venue/market and timezone;
- quote currency and price unit;
- observation interval and periods-per-year convention;
- session/calendar identifier or explicit unknown status;
- price field/basis (close, adjusted close, settlement, etc.);
- corporate-action status;
- contract specification and roll methodology where relevant;
- source/provider and retrieval timestamp.

No metadata should be guessed. Unknown values remain explicitly unknown.

### Layer B — Provider adapters
Keep external data retrieval outside the simulation engine. Each provider adapter should:
- fetch raw observations;
- preserve provider/source provenance;
- normalize into a common schema;
- retain raw timestamps and source price basis;
- report missing, rejected, stale, or rate-limited data distinctly.

The core must continue to work with user-supplied CSV and must not require a provider API key.

### Layer C — Canonical observations and validation
Establish a canonical time-series schema with at least timestamp, close, currency, interval, and price-basis metadata. Add optional OHLCV fields without requiring them for close-only simulation.

Validation must check:
- timestamp timezone/ordering/duplicates;
- positive finite prices;
- expected interval and missing-session gaps;
- currency and units;
- price basis and corporate actions;
- futures expiry/roll consistency where applicable;
- crypto/FX 24x7 interval expectations where applicable.

Never silently sort, interpolate, fill, resample, adjust, or splice a series.

### Layer D — Shared simulation core
Keep the GBM and risk-statistics core independent of ticker, exchange, country, and provider. Make interval/annualization explicit. Preserve reproducibility metadata (paths, seed, interval, horizon, drift convention, model assumptions).

Do not claim all asset classes are adequately modeled by GBM. Model limitations and unsupported characteristics must be surfaced.

### Layer E — Validation matrix
Run separate, untouched out-of-sample evaluations by market and asset family. Do not pool all instruments into one score that hides weak segments.

Initial coverage matrix:
1. India equities/index: NIFTY 50 and SENSEX (daily).
2. US equities/index: broad-market and technology benchmarks (daily).
3. International equity index: at least one developed and one emerging market (daily).
4. FX: major currency pair(s), with explicit 24x5 session treatment.
5. Commodities: representative spot or futures series, with contract/roll policy documented.
6. Digital assets: representative 24x7 spot series, with UTC timestamp handling.
7. Bonds/rates: representative bond ETF/index series, with price/total-return basis documented.

A category is not marked supported merely because a CSV parses. It needs metadata validation, interval/calendar checks, and a held-out evaluation report.

## 4. Validation protocol

For every dataset:
1. Freeze the instrument, source, date range, interval, currency, price basis, and data hash.
2. Split chronologically into estimation, calibration, and untouched test periods.
3. Enforce point-in-time isolation: no future observations or future corporate-action information may enter a forecast.
4. Compare raw model probabilities with a leakage-safe baseline.
5. Report Brier score/skill, calibration by class, sample count, and confidence/uncertainty.
6. Report price-distribution errors separately from directional/classification scores.
7. Repeat across regimes and independent instruments.
8. Label small samples as preliminary; never turn a single instrument/date result into a universal accuracy claim.

Monte Carlo path-count convergence is a computational stability test, not forecast accuracy.

## 5. Release gates

A market/asset family may be labelled:
- **Input-compatible**: canonical data passes schema and quality checks.
- **Research-validated**: held-out diagnostics completed and baseline comparison reported.
- **Supported with limitations**: multiple untouched periods/instruments pass predefined quality gates and known limitations are documented.

No global "all markets accurate" claim is permitted. Publish per-family results and failure cases.

## 6. Implementation phases

- Phase 0: document current capabilities and gaps (this file).
- Phase 1: define instrument metadata and canonical schema; add unit tests.
- Phase 2: generalize CSV ingestion and interval-aware annualization without breaking v2.3.0 defaults.
- Phase 3: add provider adapters as optional modules, starting with documented public datasets.
- Phase 4: create parameterized multi-market OOS runner driven by a dataset manifest, not hardcoded symbols.
- Phase 5: add separate asset-family fixtures and held-out regression tests.
- Phase 6: publish per-family validation reports and limitations.

## 7. Non-goals and safeguards

- No broker connectivity, order execution, or autonomous trading.
- No personalized buy/sell or position-sizing recommendations.
- No accuracy/profit guarantees.
- No automatic data repair.
- No claim of universal validity from one market or one backtest.
- Do not modify main, publish a release, or deploy as part of this roadmap.

## 8. Definition of success

Success is not "one NIFTY test scores highly." Success means:
- one shared engine processes multiple correctly described market datasets;
- invalid or ambiguous inputs are rejected transparently;
- interval, currency, calendar, adjustment, and contract metadata are handled explicitly;
- each supported market/asset family has reproducible, leakage-safe, out-of-sample evidence;
- results are reported per family, including failures and limitations;
- existing v2.3.0 tests and compatibility behavior remain intact unless a versioned change is intentionally introduced.


## Implementation progress — 2026-11-26

The feature branch now contains the first implementation slice:
- Existing `engine/dataset_manifest.py` and `engine/instrument.py` provide explicit instrument/dataset metadata, IANA timezone validation, corporate-action and futures-roll status, and interval declarations.
- `periods_per_year` is now included in the dataset manifest. Intraday/tick intervals require an explicit annualization convention; daily/weekly/monthly have conservative defaults that must still be checked against the instrument's session convention.
- `engine/canonical_data.py` maps provider fields and checks timestamp order, duplicate times, close validity, declared currency/price basis, and interval gaps without repairing input.
- `engine/providers.py` supplies pluggable CSV, Yahoo Finance chart, Stooq daily, and EODHD daily adapters. Provider network access is optional and failures are captured per dataset.
- `scripts/evaluate_dataset_manifest_oos.py` runs independent diagnostics for each dataset and writes source hashes, metadata, audit findings, and per-instrument OOS metrics.
- `datasets/multi_asset_manifest.json` defines representative India/US equity indices, FX, crypto, commodity futures, and bond ETF datasets, plus Stooq and EODHD ETF samples.
- Unit tests cover metadata, canonical validation, CSV provider behavior, mocked Yahoo/Stooq/EODHD parsing, and insufficient-history handling.

Important: these are implementation and plumbing milestones, not proof that every market family is validated. The hosted multi-asset OOS workflow is still running; final provider coverage and per-market metrics must be read from its artifact. Data-source availability, adjustment quality, exchange calendars, futures roll construction, and model fit remain independent review items.
