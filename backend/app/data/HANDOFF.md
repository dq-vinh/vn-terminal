# VN Terminal Pro data/backend handoff

Date: 30 July 2026  
Owner: Data/backend specialist  
Scope: WP1, WP2, and WP3 data operations  
Frozen contract version: `0.1.0`  
Snapshot format version: `1.0.0`

## Outcome

The read-only FData pipeline, fourteen data-quality controls, security-master
adapter, immutable Parquet snapshots, atomic pointer promotion, DuckDB access,
and the five WP3-owned API operations are implemented under
`backend/app/data/**`.

The final full refresh was promoted successfully:

- Data version: `fdata-2026-07-30`
- Content SHA-256:
  `4b5e0b5cf65fa849fd18f4edb9cd6002bc1195cbc706dd5a96ad04b8f9fac1a9`
- Source files: 2,471
- Source records: 3,632,818
- Valid Parquet symbol partitions: 2,436
- Quarantined files: 35, comprising the malformed `CSHB2604.dat` and
  34 files with critical nonpositive-price anomalies
- Historical revisions detected on the verification refresh: 0
- Promotion blockers: none

Baseline reconciliation:

| Measure | Observed | Expected |
|---|---:|---:|
| Files | 2,471 | 2,471 |
| Records | 3,632,818 | 3,632,818 |
| Files with OHLC violations | 505 | 505 |
| Files with zero or negative prices | 34 | 34 |
| Stock zero-volume records | 11,020 | 11,020 |
| Stock files with terminal zero-volume runs of at least five | 301 | 301 |
| Files current to 30 July 2026 | 2,315 | 2,315 |

The all-category zero-volume count is 11,912. The plan's 11,020 baseline is
exactly the stock-category count; the difference is 265 warrant, 6
derivative, and 621 index records.

## Files changed

Production:

- `backend/app/data/__init__.py`
- `backend/app/data/models.py`
- `backend/app/data/api.py`
- `backend/app/data/aux1_validation.py`
- `backend/app/data/pipeline.py`
- `backend/app/data/service.py`
- `backend/app/data/tasks.py`
- `backend/app/data/fdata/__init__.py`
- `backend/app/data/fdata/parser.py`
- `backend/app/data/quality/__init__.py`
- `backend/app/data/quality/checks.py`
- `backend/app/data/security_master/__init__.py`
- `backend/app/data/security_master/service.py`
- `backend/app/data/storage/__init__.py`
- `backend/app/data/storage/duckdb_store.py`
- `backend/app/data/storage/snapshots.py`
- `backend/app/data/HANDOFF.md`

Tests:

- `tests/backend/conftest.py`
- `tests/backend/data/test_api.py`
- `tests/backend/data/test_aux1_validation.py`
- `tests/backend/data/test_parser.py`
- `tests/backend/data/test_pipeline.py`
- `tests/backend/data/test_quality.py`
- `tests/backend/data/test_security_master.py`
- `tests/backend/data/test_service.py`
- `tests/backend/data/test_snapshots.py`
- `tests/backend/data/test_storage.py`

Authorized documentation append:

- `docs/data_dictionary.md`, only the marked WP1 Aux1 result section

Runtime artifacts:

- `data/quality_reports/fdata_quality_2026-07-30.json`
- `data/quality_reports/aux1_validation_2026-07-30.json`
- `data/snapshots/CURRENT`
- The immutable snapshot directory referenced by `data/snapshots/CURRENT`
- `data/vn_terminal.duckdb`

No file under `contracts/**`, `backend/app/quant/**`, `backend/app/ai/**`,
or `frontend/**` is part of this handoff.

## Commands to test

```powershell
.\.venv\Scripts\ruff.exe check backend/app/data tests/backend
.\.venv\Scripts\mypy.exe backend/app/data --ignore-missing-imports
.\.venv\Scripts\bandit.exe -r backend/app/data -ll -q
.\.venv\Scripts\python.exe -m pytest tests/backend -q
.\.venv\Scripts\python.exe -m pytest tests/contracts -q -k "not idempotent"
```

Full source scan:

```powershell
.\.venv\Scripts\python.exe -m backend.app.data.tasks scan `
  --source-root "C:\FDATA\AmiBroker\EOD" `
  --reference-date "2026-07-30" `
  --output "data\quality_reports\fdata_scan_2026-07-30.json"
```

Atomic refresh:

```powershell
.\.venv\Scripts\python.exe -m backend.app.data.tasks refresh `
  --source-root "C:\FDATA\AmiBroker\EOD" `
  --snapshots-root "data\snapshots" `
  --reference-date "2026-07-30" `
  --output "data\quality_reports\fdata_quality_2026-07-30.json"
```

Aux1 verification:

```powershell
.\.venv\Scripts\python.exe -m backend.app.data.tasks aux1 `
  --source-root "C:\FDATA\AmiBroker\EOD" `
  --output "data\quality_reports\aux1_validation_2026-07-30.json"
```

## Test output

- Ruff: all checks passed.
- Mypy: success, no issues in 16 source files.
- Bandit at medium/high threshold: no findings.
- Backend pytest: 26 passed in 19.07 seconds.
- Non-mutating contract pytest: 64 passed, 3 deselected.
- Full refresh: promoted, no blocking reasons.
- Three-year FPT chart query:
  - Initial query: 2.7367 seconds.
  - Repeated query: 0.5244 seconds.
  - Both satisfy the plan's under-three-second uncached and under-one-second
    cached targets.

The three deselected lead-owned contract tests execute code generators and
rewrite frozen JSON/YAML line endings on Windows before comparing hashes.
They were not run in the final audit to preserve `contracts/**`.

## Data fixtures used

- Live required malformed fixture:
  `C:\FDATA\AmiBroker\EOD\cw\CSHB2604.dat`, header 43, actual 44,
  out-of-order date, quarantined.
- Synthetic valid and malformed 40-byte files generated only under pytest
  temporary directories.
- Live full FData repository under `C:\FDATA\AmiBroker\EOD`.
- Aux1 published comparisons for FPT, HPG, SSI, MBB, and VNM on
  21 July 2026, using the Stockbiz historical-price tables listed in
  `docs/data_dictionary.md`.

## Known limitations and blocked items

1. No authoritative security-master source is available. Active status is
   never inferred from file modification time or last-bar date. Without a
   supplied `SecurityReference`, status remains `unknown`.
2. The installation contains 207 index files, of which 182 have purely
   numeric filenames and 25 have symbolic filenames. No authoritative
   numeric code-to-name source was found. Numeric entries are marked
   `blocked_missing_index_mapping`; no names are guessed.
3. The stock directory contains mixed security types. Unreferenced stock
   entries remain type `unknown`, so they are not silently treated as active
   equities.
4. Aux1 is confirmed for the five-symbol sample as unadjusted daily average
   price within 0.05 thousand VND, but remains excluded from the canonical
   bar, Parquet schema, API, and calculations. Aux2 remains unused.
5. The router implements only the five data operations assigned to WP3:
   health, refresh, status, symbols, and bars. The lead integrator must mount
   it in `backend/app/main.py`. Fundamentals belong to WP9; quant, AI,
   watchlist, and settings operations belong to their respective owners.
6. Editable installation with `pip install -e .[dev]` currently fails because
   the lead-owned `pyproject.toml` does not constrain setuptools package
   discovery in the flat multi-package repository. The exact pinned
   dependencies were installed directly into `.venv`; `pyproject.toml` was
   not changed.

## Security implications

- Source `.dat` files are opened only with `rb`; a pytest guard fails on any
  write-capable mode.
- All user filters and values in DuckDB queries are bound parameters.
- Snapshot promotion changes only the small `CURRENT` pointer with
  `os.replace`; completed candidates are immutable and invalid candidates
  cannot replace the last good pointer.
- Pointer resolution is confined to the configured snapshot root and
  requires a `READY` marker.
- Critical data anomalies are quarantined and cannot enter the canonical
  bar partitions or downstream strategy execution.
- No credential, network secret, or personal information is stored.

## Follow-up issues for the lead integrator

1. Supply or approve an authoritative point-in-time security master,
   including exchange, type, trading status, lot size, names, and validity
   intervals.
2. Supply the index code-to-name mapping for the 182 numeric filenames.
3. Mount `create_data_router(DataAPIContext(service=...))` in
   `backend/app/main.py`.
4. Decide whether to repair the lead-owned Windows line-ending behavior in
   the three contract idempotency tests/generators.
5. Decide whether the confirmed Aux1 field should receive a future contract
   extension. Until then it stays unused.

## Implementation decisions

- Chose one Parquet partition per valid source file to bound memory and make
  symbol-level quarantine auditable.
- Chose a versioned logical content hash over sorted source fingerprints plus
  snapshot-format version.
- Chose immutable completed candidates plus an atomic `CURRENT` pointer swap.
  This avoids non-atomic in-place replacement and Windows cloud-sync locks on
  directory renames.
- Chose explicit `unknown`/blocked classifications when external evidence is
  absent.
- Chose direct Parquet querying through DuckDB instead of duplicating all bars
  into database tables.
