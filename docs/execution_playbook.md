# VN Terminal Pro

## Multi-AI Execution Playbook: Tool Allocation, Prompts, and Integration

**Document version:** 1.0
**Date:** 30 July 2026
**Companion to:** `vn_terminal_multi_ai_development_plan.md` v1.1
**Subscriptions assumed:** Claude Pro, ChatGPT Plus, Google AI Pro
**Purpose:** Convert the amended development plan into an executable assignment of work across three AI subscriptions, with copy-ready prompts and a final integration procedure.

---

## 1. The governing cost principle

Three subscriptions at roughly USD 60 per month combined give you four usable agentic surfaces. The binding constraint is not money, it is Claude Pro quota, because that quota is shared across Claude Code, Claude.ai chat, and Cowork, so every token spent in one reduces what remains for the others.

That produces the allocation rule for this project.

**Spend the scarcest and most capable resource on the domains where errors are silent.**

A frontend defect announces itself the moment you open the browser. A look-ahead bias in a backtester, an off-by-one in a warm-up period, or a contract mismatch between two modules produces plausible output that is wrong, and you may not discover it for weeks. Claude Pro quota therefore goes to the quantitative engine, the contracts, and the integration, and the visually self-correcting work goes elsewhere.

A second principle follows from the plan's structure. Contracts are frozen before parallel work begins, so agents that cannot see each other's code can still produce compatible modules. Every hour of contract discipline saves several hours of quota spent on rework.

---

## 2. What each subscription actually gives you

| Subscription | Primary agentic surface | Practical strength for this project | Known constraint |
|---|---|---|---|
| Claude Pro, about USD 20/month | Claude Code (CLI), Cowork | Multi-file agentic coding, long-specification adherence, numerical care, tool use | Rolling 5-hour session limits plus a weekly cap, shared with chat and Cowork. Non-interactive use draws on a separate USD 20 monthly credit |
| ChatGPT Plus, USD 20/month | Codex (cloud and CLI), GPT-5.6 family | Long-running isolated tasks delegated to the cloud, strong on well-specified backend work | Message limits per rolling window plus a weekly cap. The 5-hour window was temporarily lifted in July 2026, so treat the weekly cap as the real ceiling |
| Google AI Pro, about USD 20/month | Antigravity, Jules, Gemini 3.1 Pro with raised AI Studio limits | Very large context for whole-repository review, asynchronous coding, generous allowance | As of 18 June 2026 consumer AI Pro plans no longer include Gemini CLI; terminal use routes through Antigravity instead |

Verify your own current quota display before starting, since all three vendors changed limits during 2026 and may change them again.

---

## 3. Build-time cost versus runtime cost

Keep these separate in your budgeting, because they behave differently.

**Build time** is covered entirely by the three subscriptions. No additional spending is required to construct the workstation.

**Runtime** is the AI analysis panel, and it should not run on any of these subscriptions. It should call OpenRouter directly, priced per token, because that is the only way to keep the cost predictable and the model replaceable.

A concrete estimate for the daily close routine in WP16. A fact bundle for one security runs roughly 4,000 input tokens, and a structured scenario response runs roughly 1,500 output tokens. Pre-computing 20 watchlist names each evening on DeepSeek V4 Flash at USD 0.09 per million input and USD 0.18 per million output costs about USD 0.013 per day, which is roughly USD 0.38 per month. Even on DeepSeek V4 Pro at five times that rate, the figure stays under USD 2 per month. Ollama gives you a zero-marginal-cost fallback for prompt development and for days when you would rather not send anything outside the machine.

The practical conclusion is that runtime AI cost is negligible for a single user, so choose the runtime model on output quality, not price, and develop prompts against Ollama to avoid paying for iteration.

---

## 4. Division of labor

Six streams, mapped to the work packages in the amended plan.

| Stream | Assigned tool | Work packages | Rationale |
|---|---|---|---|
| A. Lead architect and integrator | Claude Code, Sonnet default | WP0, WP10, WP13, WP15, WP16 | Contract authorship, the AI gateway, integration, and packaging are where silent incompatibilities originate. This stream owns `contracts/**` exclusively |
| B. Quantitative engine | Claude Code, same session family as A | WP5, WP6, WP7, WP8 | Indicators, strategies, the screener, and the backtester fail silently and plausibly. Highest correctness stakes in the project |
| C. Data and backend | Codex, cloud tasks | WP1, WP2, WP3, WP9 | Well-specified, isolated, heavily testable against a verified binary format. Ideal for delegating to a cloud agent and collecting later |
| D. Frontend | Antigravity or Jules | WP4, WP11, WP12 | Visually self-correcting, tolerant of iteration, and the largest volume of code. Cheapest place to spend the most generous allowance |
| E. Adversarial QA | Gemini 3.1 Pro, large-context review | WP14 | A whole-repository read in a single context is exactly what a very large window is for, and an independent model reduces correlated blind spots |
| F. Strategy specification | Cowork, with you | Feeds WP6 | Not a coding task. This is your analytical judgment being written down, and it is the true critical path |

Stream A and Stream B share the Claude Pro quota pool, so run them in the same working blocks rather than concurrently, and prefer Sonnet, reserving Opus for genuinely hard debugging.

A note on the frontend assignment, since it is the arguable one. Claude is generally the strongest frontend coder of the three, and if quota were unlimited you would put Stream D on Claude Code. The assignment above is a deliberate economy. If Antigravity stalls on the chart integration specifically, that is the one place to spend Claude quota on frontend work, because Lightweight Charts integration has more silent-failure surface than ordinary panel layout.

---

## 5. Sequencing across three to four calendar weeks

The plan estimates 8 to 12 agent working days. Spread across your availability, expect the following rhythm.

**Week 1.** Stream F first, with you and Cowork writing the specifications for the three reference strategies. Then Stream A freezes contracts. Only after the freeze do Streams C and D start, in parallel, since they now have fixtures to build against. Stream B starts on indicators.

**Week 2.** Streams B, C, and D run in parallel. Stream A performs the first vertical-slice integration on FPT and KDH. Stream F continues, expanding specifications toward the 10 to 15 strategy set.

**Week 3.** Screener, backtester, financial panels, and the daily close routine. Stream A integrates continuously.

**Week 4.** Stream E performs adversarial review, then remediation, packaging, and the pilot exit check.

Do not start Streams C and D before the contract freeze. That single discipline is worth more quota than any other optimization in this document.

---

## 6. Prompts

Each prompt is self-contained and copy-ready. Every one states path ownership, because the plan's integration protocol depends on agents not editing each other's files. Attach or reference `vn_terminal_multi_ai_development_plan.md` v1.1 in each session.

### P0. Contract freeze, Claude Code, Stream A

```
You are the lead architect and integrator for VN Terminal Pro, a local
Vietnamese-equities research workstation. Read the attached development plan
v1.1 in full before writing any code.

Your exclusive ownership is contracts/** and the repository scaffold. You will
not implement backend logic, quantitative functions, or frontend components.
Other agents will do that against what you produce.

Deliverables for this session:

1. Create the repository structure exactly as specified in Section 9 of the plan.
2. Write contracts/openapi.yaml covering every endpoint in Section 11. Every
   endpoint must carry typed request and response schemas, explicit error
   responses, and the as_of_date, data_version, and source fields.
3. Write Pydantic and JSON Schema definitions for all five canonical contracts
   in Section 10: price bar, security master, financial observation, strategy
   definition, and strategy evaluation result. Add the AI fact bundle schema
   from Section 10.6, and include the money-flow block described in Section 14.
4. Generate mock JSON fixtures under contracts/fixtures/ for FPT and KDH,
   sufficient for the frontend and quantitative agents to develop with no
   backend present. Include at least 500 daily bars per symbol, one full
   fundamentals payload, one strategy evaluation result, and one AI fact bundle.
5. Write docs/data_dictionary.md containing the verified FData binary format
   from Section 19.1 of the plan, reproduced exactly.
6. Write contracts/OWNERSHIP.md stating the path ownership rules from
   Section 24.1 and the contract-change process from Section 24.2.
7. Pin all dependency versions in pyproject.toml and package.json.
8. Write contract tests that validate every fixture against its schema. These
   must pass before you finish.

Constraints:
- Do not invent endpoints or fields that are not in the plan.
- Every schema field must be traceable to a section of the plan. Where the plan
  is ambiguous, list the ambiguity in contracts/OPEN_ITEMS.md rather than
  guessing.
- Output OpenAPI 3.1.

When finished, produce a handoff summary listing files created, the contract
version string, and the exact commands each downstream agent should run to
validate their work against these contracts.
```

### P1. FData adapter, security master, storage, Codex, Stream C

```
You are the data and backend specialist for VN Terminal Pro. Read the attached
development plan v1.1, and treat contracts/ in the repository as frozen and
authoritative. You may read contracts/ but never modify it.

Your exclusive ownership is backend/app/data/**. Do not create or edit files
under backend/app/quant/**, backend/app/ai/**, or frontend/**.

The FData binary format has been verified by direct inspection and is not to be
re-derived. It is:

- Every EOD file is an exact multiple of 40 bytes.
- A 40-byte header whose first uint32 little-endian is the record count.
- 40-byte records, each a uint32 date in YYYYMMDD form followed by nine float32
  fields in this order: unused, open, high, low, close, volume, unused, Aux1,
  Aux2.
- OHLC are back-adjusted, expressed in thousands of VND. Volume is in shares.
- Source root is C:\FDATA\AmiBroker\EOD with subdirectories stock, index, der,
  and cw. The 1m, 5m, 15m, and Tick directories are empty and must be ignored,
  not treated as errors.

Implement, in this order:

WP1, the read-only parser.
- Parse all four category directories into the canonical price-bar contract.
- Never open a source file in write mode. Assert this in a test.
- Emit versioned Parquet snapshots with provenance metadata.
- Produce reproducible output hashes for a fixed input.
- Handle the known malformed file EOD/cw/CSHB2604.dat, whose header claims 43
  records against 44 actual, with one out-of-order date. This file is a required
  test fixture and must be quarantined, not silently corrected.
- Add a task that tests the hypothesis that Aux1 holds the unadjusted daily
  average price. Evidence: for FPT in December 2006, Aux1 reads 420 to 463 while
  adjusted close reads about 10 to 11; on current bars Aux1 sits near but not
  equal to close, for example FPT 66.57 against close 67.0. Compare against a
  published VWAP source for at least five tickers and write the conclusion into
  docs/data_dictionary.md. Do not use Aux1 in any calculation until confirmed.
  Aux2 is a small integer of unknown meaning and stays unused.

WP2, security master and data quality.
- Classify securities by type and active status. Never infer active status from
  file modification date.
- Compute last positive-volume date per symbol.
- Implement all fourteen automated checks in Section 19 of the plan with the
  four severity levels.
- Map the 207 numeric-coded index files, for example 0001.dat and 0500.dat, to
  index names. Flag this as blocked and report it if no mapping source is
  available; do not guess.
- Implement atomic snapshot promotion. A partial or invalid refresh must never
  replace the last good snapshot.

WP3, storage and API.
- DuckDB schema plus Parquet access.
- Implement exactly the data endpoints defined in contracts/openapi.yaml.

Expected baseline from a full-repository scan on 30 July 2026, to validate your
implementation against. Your quality report should reproduce approximately these
figures: 2,471 files, 3,632,818 records, 505 files with OHLC violations, 34 files
with zero or negative prices, 11,020 zero-volume records, 301 stock files with
terminal zero-volume runs of five or more sessions, 2,315 files current to
30 July 2026. Material deviation means a bug in your parser, so investigate
before reporting completion.

Every module needs pytest coverage. Report using the handoff checklist in
Section 24.3 of the plan.
```

### P2. Financial data module, Codex, Stream C, second task

```
You are the data specialist for VN Terminal Pro, continuing in
backend/app/data/**. contracts/ is frozen and read-only for you.

Implement WP9, the financial module, per Section 17 of the plan. The existing
vnstock_mcp.py is a starting reference, not a production pipeline.

Requirements:
- Normalize quarterly and annual statements into the financial-observation
  contract.
- Distinguish consolidated from separate statements, and cumulative from
  standalone quarterly values.
- Preserve publication dates and restatement versions.
- Record currency and units explicitly.
- Compute growth and margins deterministically, never by model inference.
- Link every displayed figure to a source URL.

Critical design constraint, the degraded mode. Vietnamese free sources including
vnstock often lack reliable publication dates. When a publication date is
missing, the observation remains available for display and current screening but
must be excluded from historical backtests and flagged with an explicit warning.
Missing point-in-time metadata degrades functionality; it must never block the
module or silently enter a backtest.

Implement the panels listed in Section 17 and expose them through the
fundamentals endpoints already defined in contracts/openapi.yaml. Do not add
endpoints. If you need one, file a contract change request per Section 24.2 and
stop.
```

### P3. Indicator engine and money-flow block, Claude Code, Stream B

```
You are the quantitative specialist for VN Terminal Pro. Read the attached
development plan v1.1. contracts/ is frozen and authoritative.

Your exclusive ownership is backend/app/quant/**. Do not edit
backend/app/data/**, backend/app/ai/**, or frontend/**. Develop against
contracts/fixtures/, not against a live database.

Implement WP5, the indicator engine, per Section 14.

Hard constraints:
- Indicator functions are pure. No network access, no database access, no file
  access inside them. Enforce this with tests.
- Every indicator documents formula, input price, adjustment convention, warm-up
  period, missing-value behavior, comparison reference, and numerical tolerance.
- Every indicator has a golden-fixture test.

Standard indicators: SMA, EMA, RSI, MACD, ATR, Bollinger Bands, rolling highs and
lows, rate of change, relative strength versus VN-Index and sector, volume moving
averages, volume-price trend, pivot levels, rolling volatility, drawdown.

Money-flow and accumulation block, which is a first-class requirement and not
optional. It must answer whether large money appears to be entering a security
and whether accumulation is visible. Implement the accumulation/distribution
line, on-balance volume, up-day versus down-day volume ratio, volume-at-price
concentration, and unusual-volume flags. All must be deterministic. The AI layer
interprets these numbers later; it never computes them.

Relative strength depends on an index code-to-name mapping owned by the data
stream. If it is unavailable, implement the function, mark the test skipped with
a clear reason, and report the dependency. Do not fabricate the mapping.

Report using the handoff checklist in Section 24.3.
```

### P4. Strategy registry, screener, and backtester, Claude Code, Stream B

```
You are the quantitative specialist for VN Terminal Pro, continuing in
backend/app/quant/**. The indicator engine from WP5 is complete and is your
dependency. contracts/ remains frozen.

Implement WP6, WP7, and WP8.

WP6, strategy registry.
- Implement the strategy protocol matching the strategy-definition contract in
  Section 10.4, with every declared field populated.
- Implement the strategy specifications I supply separately. Implement only what
  is specified in writing. Never invent a rule to fill a gap, and never add a
  strategy to reach a target count. If a specification is ambiguous, stop and
  ask.
- v1.0 scope is 10 to 15 strategies. The approximately 52-strategy catalogue is
  v1.1 and out of scope for this session.
- For strategies migrated from AmiBroker AFL, follow the eight-step process in
  Section 13.3. The Python result must match the AmiBroker reference export
  within a documented tolerance before the strategy is accepted.

WP7, screener, per Section 15.
- Run across a defined universe, excluding non-equities, inactive securities,
  and severely illiquid securities by default.
- The default filters are active equity status, a last positive-volume date
  within a configurable range, a minimum 20-day median trading value, a minimum
  history length, and no unresolved critical data-quality issue.
- Never treat a current file date as proof that a security is actively traded.
  301 stock files end in terminal zero-volume runs, and they must not appear in
  current screening results.
- Show passed and failed criteria per security, rank by deterministic score, and
  store run date, strategy versions, parameters, and data version so any run is
  reproducible.
- Support background execution, since the screener runs unattended inside the
  daily close routine, and export to CSV.

WP8, backtester, daily bars.
- Implement every control in Section 16: entry convention explicitly selected as
  next open or next close, exit convention, transaction cost, slippage, position
  size, maximum concurrent positions, liquidity constraint, price-adjustment
  convention, benchmark, and in-sample and out-of-sample periods.
- Produce every output metric in Section 16, each with its definition recorded.

Bias controls are the highest priority in this session, above features and above
performance:
- No future bars, ever. Write explicit tests that would fail if a signal used
  bar t to trade at bar t.
- No use of financial information published after the simulated decision date.
  Fundamentals lacking publication dates are excluded from backtests entirely.
- No survivorship-only universe. The 301 symbols with terminal zero-volume runs
  must remain in the historical universe.
- Corporate-action consistency across the adjusted series.
- Explicit handling of suspended and zero-volume securities.

Before you report completion, write and run an adversarial test suite whose only
purpose is to detect look-ahead bias in your own implementation. Report what it
found, including negative results.
```

### P5. Frontend workstation, Antigravity or Jules, Stream D

```
You are the frontend specialist for VN Terminal Pro, a local Vietnamese-equities
research workstation for a single user. Read the attached development plan v1.1,
Section 12 in particular.

Your exclusive ownership is frontend/**. Never edit backend/**, contracts/**, or
tests outside frontend/tests/.

Develop entirely against the mock JSON in contracts/fixtures/. The backend is
being built in parallel by another agent, and your work must run correctly before
it exists.

Stack: HTML5, modern JavaScript ES modules or TypeScript, scoped CSS,
TradingView Lightweight Charts under Apache 2.0 with attribution retained. No
frontend framework beyond this unless the plan specifies one.

Implement WP4, WP11, and WP12.

Layout per Section 12: a top toolbar, a central chart, a right analytical panel
with tabs for Indicators, Strategies, Screener, Fundamentals, AI analysis, and
Data quality, and a bottom workspace with tabs for Watchlist, Current signals,
Signal history, Backtest trades, Equity curve and drawdown, Portfolio notes, and
Data-refresh log.

Chart requirements: candlesticks, volume, multiple panes, EMA and SMA overlays,
support and resistance levels, strategy entry, exit, and invalidation markers,
corporate-action markers, crosshair, zoom, pan, export, and indicator toggles.
Daily, weekly, and monthly timeframes. Must render 5,000 daily bars smoothly.

The AI panel has one non-negotiable requirement. It must visually distinguish
four categories at all times: Fact, Calculated result, AI inference, and
Unavailable or unverified. Use distinct visual treatment, not just labels. The
user must be able to expand any AI statement and see the underlying facts that
were supplied to the model.

The interface is bilingual Vietnamese and English. Externalize all strings.

There is no realtime or streaming data. This is a post-session analysis tool, so
build no polling, no websockets, and no live-tick handling.

Handle loading, empty, error, and stale-data states explicitly for every panel.
Data-quality warnings must be visible, not buried.

Write Playwright tests covering the workflows in Section 25.6.
```

### P6. Adversarial QA review, Gemini 3.1 Pro, Stream E

```
You are an independent adversarial reviewer for VN Terminal Pro. You did not
write any of this code, and your value comes from not defending it. Read the
entire repository and the attached development plan v1.1 in one pass, then hunt
for defects the authoring agents would not find in their own work.

You have read-only access. Write only to tests/qa/** and docs/qa_report.md.

Review in this priority order.

1. Look-ahead bias. Trace every strategy and backtest path. Does any signal at
   bar t use information from bar t or later to trade at bar t? Does any
   fundamental input enter a decision before its publication date? Quote the
   specific lines.

2. Contract integrity. Compare every frontend API call against
   contracts/openapi.yaml, and every backend response against the same. List
   every mismatch in field name, type, nullability, or units. This is where
   independently built modules fail.

3. Data-quality enforcement. Confirm that critical anomalies actually block
   downstream calculations rather than merely being logged. Confirm that active
   status is never inferred from file modification date. Confirm the 301
   terminal zero-volume symbols are excluded from current screening but retained
   in historical universes.

4. Unit and adjustment errors. OHLC are in thousands of VND and back-adjusted,
   volume is in shares. Find every place these are mixed, and every place an
   adjusted price is displayed as if it were a quoted market price.

5. AI hallucination surface. Attempt to make the AI validator pass a response
   containing a number absent from the fact bundle, a fabricated source URL, or
   a confident claim on missing data. Report every bypass you find.

6. Reproducibility. Run the same screen and the same backtest twice with
   identical configuration. Report any divergence.

For every finding, give severity as Critical, High, Medium, or Low, the exact
file and line, why it matters in practice, and a suggested fix. Do not soften
findings, and do not pad the report with praise. If a module is sound, say so in
one line and move on. An empty section is an acceptable result.
```

### P7. Strategy specification session, Cowork, Stream F

```
I need to write deterministic specifications for the strategies in my VN
Terminal Pro v1.0 catalogue. This is the critical path, since agents can code a
strategy only after its rules are unambiguous.

Work through one strategy per session with me. For each, interrogate me until
the following are fully determined, and challenge me whenever I am vague:

- Exact entry condition, expressed so two people would compute identical signals
- Exact exit condition
- Invalidation condition
- Every parameter, with its default and permitted range
- Required input fields and warm-up bars
- Timeframe
- Liquidity filter
- Execution convention, next open or next close
- Which evidence fields the strategy must report for the AI fact bundle
- Source or reference for the rule, whether a book, an AFL file, or my own
  judgment

Push back when a rule is underspecified. "Price above the moving average" is not
a specification until we settle which price, which average, what period, what
happens on equality, and what happens during warm-up.

Output each finished strategy as a section of docs/strategy_catalogue.md in the
strategy-definition contract format from Section 10.4 of the plan.

Start with the three reference strategies, one moving-average trend strategy,
one breakout and volume strategy, and one medium-term strategy from my existing
AFL files.
```

---

## 7. The final combination job

Integration is the only genuinely sequential part of the project, and it stays with Stream A on Claude Code. Do not distribute it.

### 7.1 Precondition

Do not begin integration until every stream has delivered a handoff per Section 24.3 of the plan, all module-level tests pass in isolation, and no agent has modified a path it does not own. Verify the last point with a git diff review, since it is the most common silent violation.

### 7.2 Integration prompt for Claude Code, Stream A

```
You are the lead integrator for VN Terminal Pro. Four independent agents have
delivered modules built against frozen contracts and mock fixtures. None of them
has seen another's code. Your job is WP13 and WP16, bringing these together into
a working application and proving it correct.

You own contracts/**, backend/app/ai/**, tests/integration/**, tests/contracts/**,
and all release files. You may read everything. When another module needs a fix,
prefer a precise, minimal change and record it in the handoff log rather than
rewriting the module.

Use subagents for the parallelizable verification work, and keep the sequential
integration in the main thread.

Phase 1, contract reconciliation.
Dispatch one subagent per module to compare that module's actual inputs and
outputs against contracts/openapi.yaml and the canonical schemas. Collect all
mismatches before fixing any, because fixing them one at a time creates
inconsistent intermediate states. Then reconcile in the order data, quant,
frontend.

Phase 2, vertical slice.
Integrate in the order given in Section 24.4 of the plan. After each step the
application must run end to end for FPT and KDH before you proceed:
1. Contracts and fixtures
2. Data adapter and chart on real bars
3. Indicator engine
4. Strategy result display
5. Screener
6. Fundamentals
7. AI fact bundle and analysis
8. Backtesting
9. Daily close routine
10. Settings and packaging

Phase 3, AI gateway, which is yours to build.
Implement WP10 per Section 18. The fact-bundle builder assembles only
deterministic outputs, including the money-flow block. The provider interface is
analyze(fact_bundle, prompt_template, model_config) -> structured_response, with
an OpenRouter adapter and an Ollama adapter behind it. API keys live in backend
environment variables and never reach browser code, prompts, or logs.
The response validator must reject any response containing a number absent from
the fact bundle, reject unvalidated source IDs, require a confidence level, and
require an explicit warning when data is incomplete. Develop and test prompts
against Ollama to avoid paid iteration, then verify schema compatibility on
OpenRouter.

Phase 4, daily close routine, WP16.
Build the scheduled pipeline that runs at about 22:00 on trading days, after
FData completes its evening write, observed at 21:19 to 21:30. Sequence is
refresh, validation, full-library screening, fact-bundle pre-computation for
watchlist names, then an evening summary of new signals and data-quality flags.
The validation gate must refuse to promote any snapshot whose latest date is not
the most recent trading day, and a failed refresh must leave the previous
snapshot active and report clearly.

Phase 5, verification.
Dispatch subagents in parallel for these independent checks:
- Every Playwright workflow in Section 25.6
- The full Definition of Done list in Section 26, item by item, reporting pass
  or fail with evidence for each of the sixteen items
- A reproducibility check running the same screen and backtest twice
- A secrets audit confirming no key appears in browser code, prompts, or logs

Phase 6, packaging, WP15.
Only after every Definition of Done item passes, produce the PowerShell launcher,
the dependency installation instructions, the user guide, and the backup and
upgrade procedures. Test on a clean machine. Do not wrap the application in
Tauri or Electron; that decision is deferred per Section 6 Option C of the plan.

Report a single integrated status against the sixteen Definition of Done items.
Do not report the application complete while any item fails. Where an item
cannot be satisfied, say so plainly and document it as a known limitation
instead of working around it silently.
```

### 7.3 Pilot exit criteria

Before scaling past the pilot, confirm the four criteria in Section 31 Step 5 of the plan. All components integrate through contracts, the latest bars match reference evidence, the AI introduces no unsupported numbers, and actual elapsed time and model usage are recorded. That last one matters most for your own planning, since it tells you whether the remaining estimate is realistic.

---

## 8. Quota discipline, practical rules

Seven habits that will materially extend what these three subscriptions can build.

Freeze contracts before parallel work, without exception. Rework caused by contract drift is the single largest avoidable quota expense in a multi-agent project.

Never paste large data into a chat window. Give CLI and cloud agents file access instead. A 144 MB dataset summarized by a script costs a fraction of what the same information costs pasted as text.

Default to Sonnet in Claude Code and escalate to Opus only for hard debugging. Most of this project is specification-following, which does not need the larger model.

Give Codex complete, self-contained task descriptions and let it run in the cloud. Its value here is unattended work, which is wasted if you supervise it turn by turn.

Send whole-repository reading to Gemini. A single large-context pass is far cheaper than many small reads across a scarcer quota.

Develop runtime prompts against Ollama, then verify on OpenRouter. Prompt iteration is where token spend accumulates invisibly.

Batch your review. Agents idle while waiting for your approval, and you are the bottleneck. Reviewing three handoffs in one sitting beats three interruptions.

---

## 9. Sources

- [Claude Code usage limits and pricing, 2026](https://www.morphllm.com/claude-code-usage-limits)
- [Claude Code limits and pricing explained](https://ccforeveryone.com/guides/claude-code-limits-and-pricing)
- [Codex pricing and usage limits, July 2026](https://www.morphllm.com/codex-pricing)
- [OpenAI Codex pricing](https://chatgpt.com/codex/pricing/)
- [Google AI Pro and Ultra subscription details](https://gemini.google/subscriptions/)
- [Gemini CLI and Code Assist access changes](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-cli-code-assist-higher-limits/)
- [DeepSeek V4 Flash pricing on OpenRouter](https://openrouter.ai/deepseek/deepseek-v4-flash)
- [DeepSeek V4 Pro pricing on OpenRouter](https://openrouter.ai/deepseek/deepseek-v4-pro)
