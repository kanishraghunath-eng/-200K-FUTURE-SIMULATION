# Data Source, Corporate-Action, and Futures-Roll Audit

Status: implementation and verification gates; provider evidence remains dataset-specific.

## Stooq

The previous Stooq failure was caused by a changed upstream access requirement, not just CSV parsing. The adapter now:
- requires `STOOQ_API_KEY` from the runtime secret store;
- sends the key as the `apikey` query parameter;
- rejects API-key prompts, HTML/challenge pages, quota messages, and non-CSV responses explicitly;
- stores a provenance URL with the credential removed;
- records the response SHA-256.

GitHub Actions passes `secrets.STOOQ_API_KEY` to the manifest-driven OOS step. If the secret is absent, invalid, or quota-limited, the dataset is reported as a provider error. Do not attempt to bypass the provider's access controls.

Reference: https://github.com/pydata/pandas-datareader/issues/1012

## Corporate actions

Yahoo chart retrieval now retains dated dividend and split events separately from price observations and records a hash of the normalized event list.

For ETF datasets configured with `corporate_actions_provider: eodhd`, the runner:
1. obtains Yahoo event records (daily reference interval for intraday datasets);
2. obtains EODHD dividend and split histories;
3. compares exact event dates, dividend amounts (using unadjusted values where available), and split ratios;
4. reports `matched`, `mismatch`, or `unavailable`, with independent response hashes and source names.

A mismatch or unavailable independent source blocks confirmatory OOS. Event agreement alone does not prove that either provider's adjusted-close calculation is correct; price-adjustment reconciliation remains a separate limitation. API credentials are not written into provenance URLs.

EODHD reference:
https://eodhd.com/financial-apis/api-splits-dividends

## Futures roll methodology

The Yahoo `GC=F` continuous ticker does not expose the constituent contract chain and vendor roll schedule required to independently verify its construction. It is therefore excluded from confirmatory OOS.

A new contract-level audit requires rows containing:
- `date`
- `contract_symbol`
- `expiry_date`
- `close`
- `volume`
- `open_interest`

The audit supports explicitly declared calendar, volume, or open-interest selection rules. A detected roll must have overlapping old/new contract observations on the roll date. It records the raw price gap and ratio and the declared adjustment method. Missing overlap, invalid contracts, or no observed roll prevents a verified status.

No contract-level COMEX gold data has been supplied or independently fetched in this research run. Consequently GC futures roll status remains unverified; no roll rule has been invented.

## Remaining data review

- Confirm exchange holidays/session boundaries and vendor timestamp semantics for each market.
- Confirm the exact price basis and adjustment coverage for all ETF datasets.
- Obtain contract-level futures history and the intended roll rule before including futures.
- Keep raw close, adjusted close, settlement, spot, and continuous futures series as distinct data bases.
- Preserve provider failures in reports; do not silently replace a failed source.
