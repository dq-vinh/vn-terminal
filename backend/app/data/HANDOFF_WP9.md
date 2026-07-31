# VN Terminal Pro WP9 financial-module handoff

Date: 31 July 2026  
Owner: Data/backend specialist  
Scope: `backend/app/data/**` and `tests/backend/**`  
Frozen contract version: `0.1.0`

## Outcome

WP9 is implemented without modifying `contracts/**` or adding an endpoint.
The existing `GET /api/fundamentals/{symbol}` operation is now present in the
data router.

The implementation:

- Normalizes quarterly and annual observations.
- Retains consolidated and separate statements independently.
- Encodes cumulative quarterly flows with the `_cumulative` metric suffix,
  retains those source observations, and derives standalone quarters only
  from compatible cumulative periods.
- Preserves provider restatement versions. When a source exposes no version,
  changed content receives a deterministic sequential local version and the
  assignment is warned.
- Stores currency, unit, publication date, source URL, and ingestion time.
- Keeps missing-publication observations available for display and current
  screening, while the backtest selector excludes them.
- Calculates growth, margins, ROE, ROA, leverage, free cash flow, P/E, and P/B
  with decimal arithmetic and round-half-even quantization.
- Emits valuation multiples only with positive denominators and a sourced
  price with matching symbol, currency, and unit.
- Adds a source-bearing `derived_metric` trace observation for each derived
  panel figure because the frozen `DerivedMetric` schema has no source field.

## Files changed

Production:

- `backend/app/data/api.py`
- `backend/app/data/service.py`
- `backend/app/data/HANDOFF_WP9.md`
- `backend/app/data/fundamentals/__init__.py`
- `backend/app/data/fundamentals/DESIGN.md`
- `backend/app/data/fundamentals/models.py`
- `backend/app/data/fundamentals/normalization.py`
- `backend/app/data/fundamentals/store.py`
- `backend/app/data/fundamentals/metrics.py`
- `backend/app/data/fundamentals/vnstock_adapter.py`
- `backend/app/data/fundamentals/pipeline.py`
- `backend/app/data/fundamentals/service.py`

Tests:

- `tests/backend/data/test_api.py`
- `tests/backend/data/test_fundamentals_normalization.py`
- `tests/backend/data/test_fundamentals_point_in_time.py`
- `tests/backend/data/test_fundamentals_metrics.py`
- `tests/backend/data/test_vnstock_financial_adapter.py`
- `tests/backend/data/test_fundamentals_service.py`
- `tests/backend/data/test_fundamentals_pipeline.py`

No file under `contracts/**`, `backend/app/quant/**`, `backend/app/ai/**`, or
`frontend/**` was intentionally changed for WP9.

## Commands and results

```powershell
.\.venv\Scripts\ruff.exe check backend\app\data tests\backend
.\.venv\Scripts\mypy.exe backend\app\data --ignore-missing-imports
.\.venv\Scripts\bandit.exe -r backend\app\data -ll -q
.\.venv\Scripts\python.exe -m pytest tests\backend -q
.\.venv\Scripts\python.exe -m pytest tests\contracts\test_openapi.py -q
.\.venv\Scripts\python.exe -m pytest `
  tests\contracts\test_fixtures_against_schemas.py -q -k "fundamentals"
```

Results:

- Ruff: all checks passed.
- MyPy: success, no issues in 24 source files.
- Bandit, medium/high threshold: no findings.
- Backend pytest: 53 passed.
- Frozen OpenAPI tests: 39 passed.
- Frozen fundamentals-fixture schema tests: 4 passed.
- `fundamentals_response.schema.json`: valid UTF-8 JSON.

The broader non-mutating contract run has two unrelated failures while reading
the frozen `contracts/schemas/json/ai_fact_bundle.schema.json`: byte `0x97` at
offset 8,091 is not valid UTF-8. This file is outside WP9 ownership and was not
repaired.

## Data fixtures used

- Synthetic statement rows created in pytest temporary directories and
  temporary DuckDB databases.
- Fake Vnstock `Fundamental` and equity objects returning pandas DataFrames.
- No contract fixture was used as live data.
- No Vnstock network request was made.

## Degraded-mode behavior

Display/current query:

- Returns observations even when `publication_date` is null.
- Sets provenance freshness to `degraded_point_in_time`.
- Adds an explicit warning naming the affected symbol, period, and metric.

Historical query:

- Requires `publication_date IS NOT NULL`.
- Requires `publication_date <= decision_date`.
- Selects the latest eligible restatement version known by that date.
- Never substitutes ingestion date, filing-period end, or model inference for
  a missing publication date.

## Known limitations and integration actions

1. The project virtual environment does not currently include `vnstock`.
   `VnstockFinancialAdapter` imports it only when the default factory is used
   and otherwise supports dependency injection. The lead must approve and pin
   the runtime package version rather than modifying lead-owned dependency
   files in this workstream.
2. Live provider schemas were not supplied. `FinancialFrameSchema` therefore
   requires explicit column, unit, scope, basis, version, and URL mappings and
   stops on schema drift instead of guessing provider columns.
3. A generic Vnstock page is not assumed to be a filing URL. Production jobs
   must supply either a row-level source URL column or an explicit source URL
   appropriate for every displayed observation.
4. FData prices currently have local source-file provenance, not an HTTP(S)
   source URL. P/E and P/B remain unavailable until a sourced `PricePoint`
   provider is injected; the module does not fabricate a URL.
5. `backend/app/main.py` remains lead-owned integration work. The lead must
   construct `FundamentalsService`, pass it to `DataService`, and mount the
   existing data router.

## Security implications

- Financial SQL uses static statements and bound values.
- Provider source URLs and valuation-price URLs must be absolute HTTP(S)
  addresses.
- Provider column mappings are configuration, never interpolated into SQL.
- No credential, API key, personal information, or network secret is stored.
- Missing or conflicting metadata fails closed for historical use.

