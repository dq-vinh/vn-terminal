# VN Terminal Pro — Independent Adversarial Review Report

**Date:** 31 July 2026  
**Auditor Role:** Independent Adversarial Reviewer  
**Scope:** Complete repository audit against Development Plan v1.1  

---

## Executive Summary

An independent, un-defended adversarial audit of the VN Terminal Pro codebase was conducted across all six required review categories. The audit identified critical and high-severity defects across quantitative indicator calculations, OpenAPI and JSON Schema alignment, unit conversion in valuation metrics, AI response validation infrastructure, and generator reproducibility.

---

## 1. Look-Ahead Bias & Point-in-Time Data

### Finding 1.1: Look-Ahead Bias in Support/Resistance Candidate Calculation
* **Severity:** High
* **File & Line:** `vn-terminal/backend/app/quant/indicators/levels.py:108-126`
* **Why It Matters in Practice:** Function `build_levels` uses `highs[-lookback:]` and `lows[-lookback:]` to compute resistance and support levels. Index `-1` is bar $t$ (the current bar). When evaluating strategy entry or exit at bar $t$, including bar $t$'s own intraday High and Low to calculate support and resistance introduces look-ahead bias, as intraday extremes are unknown at decision time.
* **Suggested Fix:** Slice prices up to bar $t-1$ (`highs[:-1]` and `lows[:-1]`) or apply `previous(series.high)` and `previous(series.low)` when generating candidate levels for trading signals.

### Finding 1.2: Undated Fundamentals Degradation Risk in Screening
* **Severity:** High
* **File & Line:** `vn-terminal/backend/app/data/fundamentals/normalization.py:139-145`, `vn-terminal/backend/app/data/fundamentals/vnstock_adapter.py:171-178`
* **Why It Matters in Practice:** Normalization emits warnings for observations missing `publication_date` and permits them for display and current screening (`normalization.py:143`), while `FinancialObservationStore.get_for_backtest` excludes them (`store.py:229-230`). If a historical screen is run or used as a strategy baseline without enforcing publication date checks, financial statements leak into decisions prior to their public disclosure.
* **Suggested Fix:** Enforce `publication_date IS NOT NULL AND publication_date <= as_of_date` across all screening filters that evaluate fundamental metrics.

---

## 2. Contract Integrity

### Finding 2.1: Out-of-Sync OpenAPI and JSON Schema Artifacts
* **Severity:** Critical
* **File & Line:** `vn-terminal/contracts/schemas/generate_json_schema.py:1-40`, `vn-terminal/contracts/build_openapi.py:1-40`, `vn-terminal/tests/contracts/test_generators_reproducible.py:10-85`
* **Why It Matters in Practice:** Running `generate_json_schema.py` and `build_openapi.py` causes `symbols_response.schema.json`, `provenance.schema.json`, and `openapi.yaml` to change, failing generator idempotency tests. Underlying Pydantic models were modified without regenerating and committing the contract artifacts.
* **Suggested Fix:** Execute `python contracts/schemas/generate_json_schema.py` and `python contracts/build_openapi.py`, and commit all updated schema files and OpenAPI manifests.

### Finding 2.2: Backtest Response Envelope and Trade Model Contract Mismatches
* **Severity:** High
* **File & Line:** `vn-terminal/frontend/src/api/fixtureClient.js:123-141`, `vn-terminal/contracts/schemas/models/api_envelopes.py:386-451`
* **Why It Matters in Practice:** `fixtureClient.runBacktest()` returns `metrics` containing `sharpe_ratio`, `sortino_ratio`, `total_trades` and trade items containing `trade_id`, `profit_pct`, `holding_days`, `direction`. The `BacktestResultsResponse` contract requires `sharpe`, `sortino`, `volatility`, `average_holding_period_days`, `turnover`, `exposure`, `benchmark_comparison`, and trade items require `quantity`, `transaction_cost_paid`, `slippage_paid`. Real backend integration will fail to render workspace tabs due to key name mismatches.
* **Suggested Fix:** Update `fixtureClient.js` and frontend workspace renderers (`backtestTradesTab.js`, `equityCurveTab.js`) to strictly conform to `BacktestResultsResponse` and `Trade` Pydantic models.

### Finding 2.3: Screen Results Response Field Inconsistencies
* **Severity:** High
* **File & Line:** `vn-terminal/frontend/src/api/fixtureClient.js:111-120`, `vn-terminal/contracts/schemas/models/api_envelopes.py:288-310`
* **Why It Matters in Practice:** `fixtureClient.runScreener()` returns top-level `total_matches` (absent from contract) while omitting contract-required fields `status`, `run_date`, `strategy_versions`, `parameters`, `provenance`. Per-item results return `close`, `change_pct`, `volume`, `signal`, `exchange` (absent from contract) and omit required fields `rank`, `passed_criteria`, `failed_criteria`.
* **Suggested Fix:** Align frontend screener response payloads with `ScreenResultsResponse` and `ScreenResultItem` schemas.

### Finding 2.4: Strategy Evaluation Envelope Unwrapping Mismatch
* **Severity:** Medium
* **File & Line:** `vn-terminal/frontend/src/api/fixtureClient.js:95-103`, `vn-terminal/contracts/schemas/models/api_envelopes.py:237-240`
* **Why It Matters in Practice:** `fixtureClient.evaluateStrategy()` unwraps the first evaluation item `data.results[0]` into a flat object rather than returning the contract envelope `{ results: [StrategyEvaluationResult], provenance: Provenance }`.
* **Suggested Fix:** Maintain the `{ results: [...], provenance }` wrapper in `fixtureClient.js` and update `strategiesPanel.js` to extract from `results`.

---

## 3. Data-Quality Enforcement

### Finding 3.1: Security Master Active Status and Quality Blocking
* **Status:** Sound.
* **Notes:** Active status is determined strictly via authoritative reference records in `security_master/service.py:56-79`, never from file modification dates (`mtime`). Critical data issues set `blocks_strategy_execution = True` (`checks.py:198-215`). Terminal zero-volume stock files (301 files) match Section 19 baseline counts and are excluded from current screening via `last_positive_volume_within_days` while preserved in historical DuckDB storage.

### Finding 3.2: Missing Backend Fundamentals Modules Referenced in Tests
* **Severity:** High
* **File & Line:** `vn-terminal/tests/backend/data/test_fundamentals_pipeline.py:6-9`, `vn-terminal/tests/backend/data/test_fundamentals_service.py:5`
* **Why It Matters in Practice:** Test modules `test_fundamentals_pipeline.py` and `test_fundamentals_service.py` import `backend.app.data.fundamentals.pipeline` and `backend.app.data.fundamentals.service`, which do not exist in `backend/app/data/fundamentals/`, breaking test collection.
* **Suggested Fix:** Implement `pipeline.py` and `service.py` under `backend/app/data/fundamentals/` or clean up obsolete test modules.

---

## 4. Unit and Adjustment Errors

### Finding 4.1: Unit Comparison Mismatch Dropping P/E and P/B Metrics
* **Severity:** Critical
* **File & Line:** `vn-terminal/backend/app/data/fundamentals/metrics.py:449-462`
* **Why It Matters in Practice:** Line 454 checks `denominator.unit != price.unit`. `PricePoint.unit` is `"thousand_vnd"` (OHLC price in thousands of VND). Normalized financial observations for `eps_ttm` and `book_value_per_share` have units `"vnd_per_share"` or `"vnd"`. Because `"thousand_vnd" != "vnd"`, the string equality check fails and `metrics.py` emits a warning, dropping P/E and P/B calculation entirely. If unit matching is bypassed without converting scale, dividing 67.0 (thousand VND) by 5,000 (VND/share) yields 0.0134 instead of 13.4 (a 1000x error).
* **Suggested Fix:** Convert `price.value` from thousands of VND to single VND (`price.value * 1000`) before dividing by single-VND fundamental metrics.

### Finding 4.2: Unlabeled Back-Adjusted Prices in Frontend Display Panels
* **Severity:** Medium
* **File & Line:** `vn-terminal/frontend/src/panels/screenerPanel.js:85`, `vn-terminal/frontend/src/panels/strategiesPanel.js:95-103`
* **Why It Matters in Practice:** OHLC prices are back-adjusted and expressed in thousands of VND. Rendering raw values like `67.0` without explicit unit labeling (`thousand VND`) or `Adjusted` indicators leads to user confusion when compared against unadjusted market quotes.
* **Suggested Fix:** Add explicit unit labels (`thousand VND`) and `Adjusted Price` status badges to UI price displays.

---

## 5. AI Hallucination Surface

### Finding 5.1: Missing AI Response Validation Engine
* **Severity:** Critical
* **File & Line:** `vn-terminal/backend/app/ai/validation/` (contains only `.gitkeep`), `vn-terminal/backend/app/main.py:1-13`
* **Why It Matters in Practice:** Section 18.2 requires an AI response validator to cross-check all numbers against `AIFactBundle`, reject fabricated URLs, and enforce 4-category classification. The entire `backend/app/ai/` directory contains only `.gitkeep` files. Unvalidated model outputs containing hallucinations or fabricated facts pass through without restriction.
* **Suggested Fix:** Implement `backend/app/ai/validation/validator.py` to parse structured JSON, cross-check numerical tokens against `AIFactBundle`, verify source URLs, and enforce category tags.

### Finding 5.2: Hardcoded Fallback Numbers in Frontend AI Panel
* **Severity:** High
* **File & Line:** `vn-terminal/frontend/src/panels/aiPanel.js:96, 99, 123, 126, 158, 162`
* **Why It Matters in Practice:** When `factBundle` properties are undefined, `aiPanel.js` uses hardcoded fallback numbers (`fb.price_summary?.last_close || 67.0`, `21672.89`, `71.19`, `64.0`, `60.0`, `78.0`). If a user opens the AI panel for a ticker with missing data, fabricated values are displayed as verified facts.
* **Suggested Fix:** Replace hardcoded fallback numbers with `N/A` or explicit missing-data indicators.

---

## 6. Reproducibility

### Finding 6.1: Divergence in Golden Test Fixture Baselines
* **Severity:** High
* **File & Line:** `vn-terminal/tests/quant/test_golden.py:54`, `vn-terminal/contracts/fixtures/generate_fixtures.py:1-515`
* **Why It Matters in Practice:** `pytest tests/quant/test_golden.py` fails because SHA256 hashes of `bars_FPT.json` and `bars_KDH.json` differ from the baseline hashes recorded in `tests/quant/golden/indicators_FPT.json` and `indicators_KDH.json`. Fixtures were regenerated without updating golden test baselines.
* **Suggested Fix:** Execute `python tests/quant/generate_golden.py` to re-synchronize golden baselines after verifying fixture changes.

### Finding 6.2: Non-Deterministic Screener/Backtest Run Identifiers and Mock Equity Curves
* **Severity:** Medium
* **File & Line:** `vn-terminal/frontend/src/api/fixtureClient.js:113, 124, 143-160`
* **Why It Matters in Practice:** `runScreener()` and `runBacktest()` generate `run_id` using `Date.now()`, and `_generateMockEquityCurve()` uses unseeded `Math.random()`. Identical screen or backtest configurations produce divergent run IDs and equity curves, violating reproducibility.
* **Suggested Fix:** Generate `run_id` and mock series points using a deterministic hash of the input configuration dictionary.
