# Open items

Every ambiguity found while building `contracts/openapi.yaml` and the
canonical schemas, logged here instead of guessed, per this session's
constraint: "Where the plan is ambiguous, list the ambiguity in
contracts/OPEN_ITEMS.md rather than guessing." Each item names the field or
decision, the plan section it comes from, what is unresolved, and what this
session did in the meantime so downstream agents are not blocked.

Resolving an item is a contract change (`contracts/OWNERSHIP.md`, Section
24.2): edit the model in `contracts/schemas/models/`, regenerate, update
this file to mark the item resolved with a date, and record the decision in
`docs/decision_log.md`.

This file is distinct from Section 30 of the plan ("Open questions
requiring confirmation before implementation"), which are the user's
product-level decisions. Section 30's thirteen questions still stand and
are not repeated here; see the plan directly. The items below are
contract-shape ambiguities specific to writing schemas, discovered during
WP0.

## A. Fields left as open strings instead of closed enums

For each of these, the plan mentions the field but does not give a closed
vocabulary. The interim treatment is an unconstrained JSON `string`, so no
valid downstream value is rejected by a guessed enum that turns out wrong.

| Field | Plan section | Evidenced value(s) | What is unresolved |
|---|---|---|---|
| `PriceBar.exchange`, `SecurityMaster.exchange` | Doc header, 10.1 | `HOSE`, `HNX`, `UPCoM` | Whether other values (e.g. an OTC market) can ever appear. |
| `PriceBar.security_type`, `SecurityMaster.security_type` | 3.2, WP1, 19.2 | `equity` (10.1 example) | Section 3.2 lists "equities, bonds, indices, derivatives, warrants" but WP1's four FData category directories are `stock`, `index`, `der`, `cw`, with no confirmed `bond` directory. Section 19.2 also reports "Mixed security types in the stock directory," so directory name alone cannot determine this value; WP2's classification logic must define it. |
| `PriceBar.adjustment_status` | 10.1 | `adjusted_unknown_method` | Only one example value exists; full vocabulary undefined, likely depends on the Aux1/WP1 outcome (`docs/data_dictionary.md`). |
| `PriceBar.quality_status` | 10.1 | `valid` | Only one example value exists. Section 19.2's four severity levels (`critical`/`high`/`medium`/`low`) are a plausible basis but are not stated to be the same vocabulary as `quality_status`. |
| `SecurityMaster.trading_status` | 3.2, WP2 (Section 22) | implied: active, suspended, delisted | Section 3.2 speaks of "suspended securities, and delisted securities" as things to distinguish; WP2 speaks of "Active/inactive status." Not clear whether this is a 3+ value set or a 2-value active/inactive flag with suspension detail recorded elsewhere. |
| `FinancialObservation.statement_type` | 10.3, 17 | none given | Section 17 says "Financial statements" (plural) but never enumerates statement categories. Schema docstring suggests `income_statement`/`balance_sheet`/`cash_flow_statement` as examples only. |
| `FinancialObservation.restatement_version` | 10.3, 17 | none given | Modeled as an incrementing integer starting at 1. Could instead be a string tag. |
| `FinancialObservation.unit` | 17 | none given | Section 17 requires recording "currency and units" but gives no unit vocabulary (VND vs thousand VND vs million VND). |
| `StrategyDefinition.category` | 13.1 | trend following, moving-average alignment, breakout, momentum, relative strength, volume/liquidity, mean reversion, sideways/range, Weinstein, Minervini, Wyckoff, pivot/support-resistance, composite scorecard | Section 13.1's own closing sentence: "This list describes categories, not the final strategy catalogue." Deliberately left open. |
| `StrategyDefinition.timeframe` | 10.4, 12.1 | `1D`/`1W`/`1M` (see Timeframe enum) | Kept as a plain string rather than the `Timeframe` enum because a strategy could plausibly reference more than one timeframe (e.g. a weekly filter plus a daily trigger), which the plan does not resolve either way. |
| `StrategyEvaluationResult.signal` | 10.5 | `watch` | Only one example value exists. Whether `buy`/`sell`/`hold`/other values exist is unstated. |
| `StructuredAIResponse.confidence` | 18.3, 18.4 | none given | Section 18.4 requires "a confidence level" but not its scale (qualitative label vs. 0-1 numeric score). |
| Job/run status fields (`DataRefreshResponse.status`, `DataStatusResponse.status`, `ScreenStartResponse.status`, `ScreenResultsResponse.status`, `BacktestStartResponse.status`, `BacktestResultsResponse.status`, `HealthResponse.status`) | 11 (implied by "progress," "background execution") | none given | The plan never gives a job-status vocabulary. Examples in the schemas (`queued`/`running`/`completed`/`failed`, `ok`) are illustrative only. |
| `Provenance.freshness_status` | 3.4 | none given | Section 3.4 requires "freshness status" on every analytical output without defining its values. |
| `ErrorResponse.error_code` | 11 | none given | Section 11 requires "explicit error responses" without an error-code vocabulary. |

## B. Fields or objects with no defined internal shape

| Field | Plan section | What this session did |
|---|---|---|
| `StrategyDefinition.parameter_schema` | 10.4 | Typed as an open JSON object. Unclear whether it should itself be a JSON Schema for the strategy's parameters or a simpler name-to-spec mapping. |
| `StrategyDefinition.entry_rule` / `exit_rule` / `invalidation_rule` / `liquidity_rule` | 10.4 | Typed as free-text strings, consistent with `docs/strategy_catalogue.md` being written in prose by the user (P7 workflow in `vn_terminal_ai_execution_playbook.md`). Could instead need to be a structured condition tree or small DSL once WP6 is implemented; that decision belongs to the quantitative specialist and should come back as a contract-change proposal, not a unilateral WP6 choice. |
| `MoneyFlowBlock.volume_at_price_concentration` | 14 | Typed as an open object. Section 14 names this metric but not its representation (a full price-to-volume histogram vs. a single concentration score). |
| `MoneyFlowBlock.unusual_volume_flags` | 14 | Modeled as a list of ISO dates. Section 14 says "unusual-volume flags" (plural) but does not define the detection threshold or the record shape. |
| `AIFactBundle.price_summary`, `.indicators`, `.financial_summary`, `.data_quality` | 10.6 | Section 10.6 gives bundle contents as a bullet list ("Price and volume summary," "Deterministic indicators," "Financial history and growth metrics," "Data freshness and quality warnings"), not literal field names or sub-shapes. Typed as open objects. |
| `AIFactBundle.sources`, `.calculation_definitions` | 10.6 | Modeled as lists of strings (URLs, and human-readable definitions respectively). Reasonably concrete but not literally specified. |
| `StructuredAIResponse.facts` | 18.3 | Modeled as a list of strings. Unclear whether these are restated fact strings or references (ids/paths) into the `AIFactBundle` the response was built from. |
| `BacktestRequest.position_size` | 16 | Typed as an open object. Fixed amount vs. percent-of-equity vs. volatility-scaled is unresolved. |
| `BacktestRequest.liquidity_constraint` | 16 | Typed as an open object; no shape given. |
| `BacktestRequest.price_adjustment_convention` | 16 | Typed as an open string; no enumerated set of conventions given. |
| `BacktestRequest.exit_convention` | 16 | Typed as an open string. Unlike `entry_convention` (explicitly `next_open`/`next_close`), Section 16 does not give a closed list for exit convention. |
| `BacktestMetrics.benchmark_comparison` | 16 | Typed as an open object; "Benchmark comparison" is a required output with no defined shape. |
| `Trade` record fields | 16 | Section 16 requires a "Trade list" output without a per-trade field list. This session's shape (symbol, entry/exit date and price, quantity, cost/slippage paid, pnl) is a reasonable default, not a plan-given schema. |
| `WatchlistItem` fields | 12.4, WP12 | Section 12.4 names "Watchlist" as a UI tab and WP12 lists "Watchlists" as a deliverable, without a field list. This session's shape (id, name, symbols, created_at, updated_at) is minimal and may need to grow. |
| `SettingsResponse.settings` | 12.1, 18.2, WP12 | Individual settings (model selection, data source, saved layout, etc.) are scattered across several sections with no single enumerated settings object. Typed as a fully open object. |

## C. Session design decisions that go beyond a literal reading of Section 11

These are not ambiguities in the plan so much as choices this session made
to turn Section 11's endpoint table into concrete schemas. Listed here (and
in `docs/decision_log.md`) so a downstream agent who disagrees knows these
are changeable via the contract-change process, not fixed plan text.

- **Provenance is a nested object**, not four flat fields, on every
  response (see `docs/decision_log.md`).
- **`additionalProperties: false`** on every canonical contract and API
  envelope (see `docs/decision_log.md`).
- **`/api/symbols` pagination** (`limit`/`offset` query parameters) was
  added. The plan requires "Search and filter the security universe" but
  never mentions pagination; added given the full-market universe is
  1,500-1,800 securities (Section 3.3).
- **`/api/ai/analyze` response embeds the fact bundle** alongside the
  structured analysis (`AIAnalyzeResponse.fact_bundle`), not just the
  Section 18.3 response fields, so the frontend AI panel can satisfy the
  WP11 acceptance criterion "User can inspect facts behind the response"
  without a second round trip.
- **`DataRefreshRequest.force`** was added; not named by the plan.
- **`ScreenUniverseFilters.last_positive_volume_within_days` default of 5
  sessions** was chosen to match the "terminal zero-volume runs of five or
  more sessions" language used elsewhere in Section 19.2, not because the
  plan states this as the screener's default lookback.
- **`BacktestRequest.symbol_universe` is an explicit list of symbols.** The
  plan does not say whether a backtest targets an explicit list, a named
  universe, or "the full market" as a single token. A full-market run is
  expressed here by passing every eligible symbol from `/api/symbols`.
- **`AIAnalyzeRequest`'s Python attribute is `ai_model_config`, aliased to
  the wire field name `model_config`.** Pydantic reserves the `model_`
  attribute-name prefix for its own API; the JSON key is still
  `model_config`, matching Section 18.2's
  `analyze(fact_bundle, prompt_template, model_config)` signature exactly.
- **`SecurityMaster.index_code`** was added. Section 10.2's required-field
  list does not include it, but the paragraph immediately below that list
  requires "an index code-to-name mapping" for the 207 numerically named
  files under `EOD/index`. This session interprets that requirement as a
  field on the security master; it could instead be a separate mapping
  table, which would be a contract change.
- **`.env` variable names** (`FDATA_ROOT`, `OPENROUTER_API_KEY`,
  `AI_DEFAULT_PROVIDER`, and so on, in `.env.example`) are this session's
  choice. Section 20 requires secrets to live in environment variables but
  does not name any of them.
- **Whether a frontend build tool (Vite, esbuild, or none) is expected**
  is unresolved. Section 7 names TypeScript/ES modules, Vitest, and
  Playwright, but no bundler. `package.json` intentionally does not add
  one; the frontend specialist should request a contract/tooling change if
  WP4 needs one.
- **Supporting library versions not named by the plan** (`uvicorn`,
  `pyarrow`, `jsonschema`, `pyyaml`, `openapi-spec-validator`,
  `email-validator`, `typescript` on the frontend side) were pinned to
  current stable releases as of 2026-07-30 per web search, since they are
  necessary to run the plan-mandated stack (FastAPI needs an ASGI server;
  DuckDB/Parquet workflows commonly need `pyarrow`; contract testing needs
  a JSON Schema validator) even though the plan does not name them
  individually. See `pyproject.toml` / `package.json` comments.

## D. Deliberately not resolved by this session

- **`docs/strategy_catalogue.md` is empty.** Strategy specification is the
  user's analytical work (Section 13.2, the P7 prompt in
  `vn_terminal_ai_execution_playbook.md`), not a lead-integrator task.
  Writing example rules here, even as illustration, would pre-empt that
  work.
- **`contracts/fixtures/strategy_definitions.json`** contains one entry
  with every rule field set to a literal `PLACEHOLDER` string, for the same
  reason. See `contracts/fixtures/README.md`.
