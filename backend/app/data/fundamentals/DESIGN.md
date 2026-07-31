# WP9 financial module design

## Understanding lock

- Implement Section 17 inside `backend/app/data/**` and `tests/backend/**`.
- Keep contract version `0.1.0` and all of `contracts/**` unchanged.
- Expose only the existing `GET /api/fundamentals/{symbol}` operation.
- Normalize quarterly and annual observations without guessing statement scope,
  value basis, currency, unit, publication date, or source URL.
- Retain every restatement as an append-only version.
- Display observations with missing publication dates, but exclude them from
  all point-in-time selections and add an explicit provenance warning.
- Calculate panel values with deterministic decimal arithmetic.

## Assumptions

- The provider or an operator-supplied schema mapping must explicitly provide
  consolidated versus separate scope and cumulative versus standalone basis.
- `period_type` remains the frozen `quarter` or `year` value. For quarterly
  flow observations, cumulative values use a `_cumulative` metric-code suffix;
  standalone values use the base metric code. Balance-sheet observations are
  point-in-time and do not use the suffix.
- The frozen `DerivedMetric` shape has no source field. Each displayed derived
  figure is therefore accompanied by a trace observation with the same metric
  code and period under `statement_type=derived_metric`; that observation
  carries the source URL required by Section 17.
- Valuation multiples are emitted only when a positive, point-in-time-safe
  denominator and a price input with an explicit source URL are available.

## Considered approaches

1. Recommended: append-only normalized observations plus deterministic
   calculation and an API projection. This preserves revisions and supports
   point-in-time filtering without changing the contract.
2. Return provider DataFrames directly. Rejected because provider column
   layouts are not a stable contract and do not preserve point-in-time rules.
3. Add fields or endpoints for panels and value basis. Rejected because the
   user froze `contracts/**`; WP9 can be completed through the existing open
   metric-code and statement-type strings.

## Decision log

| Decision | Reason |
|---|---|
| Require explicit provider mappings | The Vnstock documentation warns callers not to guess returned columns. |
| Keep missing-publication observations displayable | Section 17 explicitly defines this degraded mode. |
| Make backtest selection fail closed | Missing or future publication metadata must never leak into a historical run. |
| Derive standalone flow quarters only from compatible cumulative versions | Prevents mixing scope, currency, unit, or restatement states. |
| Use decimal arithmetic and declared rounding | Makes growth, margins, returns, leverage, and valuation reproducible. |
| Preserve all source versions and select the latest eligible version at query time | Supports restatements without look-ahead. |

