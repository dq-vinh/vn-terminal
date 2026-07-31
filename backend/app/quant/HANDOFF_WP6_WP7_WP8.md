# WP6, WP7, WP8 handoff: strategy registry, screener, backtester

Prepared against the checklist in Section 24.3 of
`vn_terminal_multi_ai_development_plan.md` v1.1. Owner: quantitative
specialist. Date: 31 July 2026. Scope: `backend/app/quant/**` and
`tests/quant/**` only. Frozen contract version: `0.1.0`, unchanged.

## 0. Headline

The strategy protocol, registry, screener, and backtester are implemented,
with an adversarial suite whose only purpose is to detect look-ahead bias in
this implementation. Section 5 reports what that suite found, including a real
gap it found in itself.

**The strategy catalogue contains one strategy, not ten to fifteen.**
`docs/strategy_catalogue.md` carries exactly one entry with
`Specification status: Approved`: Dual-SMA Trend Crossover, approved
2026-07-30. That one is implemented in full. Nothing was invented to close the
gap to the v1.0 target, per the standing instruction, and
`tests/quant/test_strategy_registry.py::test_the_registry_holds_exactly_the_approved_specifications`
asserts the registry equals the approved list rather than merely containing
it, so padding the catalogue would fail a test rather than pass unnoticed.

Four decisions were referred to the user before implementation and are
recorded in section 7. Two conditions in the current data make the live system
return nothing until other workstreams deliver; they are stated plainly in
section 6 because they will otherwise look like defects.

## 1. Files changed

Nothing outside the two owned paths was touched. No file under `contracts/`,
`backend/app/data/`, `backend/app/ai/`, `frontend/`, `docs/`, or `scripts/`
was created, edited, or deleted.

### New: `backend/app/quant/strategies/`

| File | Purpose |
|---|---|
| `types.py` | `SymbolHistory`, `AsOfWindow`, `SecurityView`, `Criterion`, `OrderIntent`, `StrategyEvaluation`, signal and order vocabularies, `LookAheadError`. |
| `numerics.py` | Decimal quantization to six places, ROUND_HALF_EVEN, per the specification's stated arithmetic. |
| `protocol.py` | `Strategy` protocol and `StrategyMetadata`, one required field per Section 10.4 item. |
| `registry.py` | Registration keyed on `(strategy_id, version)`, parameter resolution, evaluation, run-record version map. |
| `dual_sma_trend_crossover.py` | The one approved strategy. |
| `serialization.py` | Narrowing to the frozen 0.1.0 contract shapes; the single place information is deliberately dropped. |
| `__init__.py` | Public surface; importing it registers the catalogue. |

### New: `backend/app/quant/screener/`

| File | Purpose |
|---|---|
| `universe.py` | The five Section 15 default filters, one function each, plus `TradingCalendar`. |
| `runner.py` | Batch execution, deterministic ranking, reproducible run record. |
| `export.py` | CSV export of included *and* excluded securities. |
| `jobs.py` | Background execution. The only place this package starts a thread. |
| `__init__.py` | Public surface. |

### New: `backend/app/quant/backtest/`

| File | Purpose |
|---|---|
| `config.py` | Every Section 16 control, plus the three guards that make bias controls enforceable. |
| `engine.py` | Three-phase daily session loop, fills, trades, order events. |
| `metrics.py` | Every Section 16 output metric with its definition; contract payload builder. |
| `__init__.py` | Public surface. |

### New: `tests/quant/`

`strategy_helpers.py` (builders plus the index-recording instrument),
`test_strategy_registry.py`, `test_dual_sma_specification.py`,
`test_screener.py`, `test_backtest.py`, and
`test_lookahead_adversarial.py`. No existing WP5 test file was modified.

## 2. Contract version

`contracts/VERSION` = **0.1.0**, unchanged and unedited. Everything this
workstream emits validates against the frozen schemas on disk, tested
directly rather than against a copy. Six change proposals are in section 8;
none is required for WP6, WP7, or WP8 to be usable, and none was applied.

## 3. Commands to test

```
cd vn-terminal
python -m pytest tests/quant                     # this work package plus WP5
python -m pytest tests/quant/test_lookahead_adversarial.py -v   # the bias suite
python -m pytest tests                           # full suite; see the caveat below
ruff check backend/app/quant tests/quant
mypy backend/app/quant --ignore-missing-imports
```

## 4. Test output

```
python -m pytest tests/quant
579 passed, 2 skipped, 2 failed

python -m pytest tests/quant/test_lookahead_adversarial.py
36 passed

ruff check backend/app/quant/strategies backend/app/quant/screener \
           backend/app/quant/backtest    ...   All checks passed
mypy  backend/app/quant/strategies backend/app/quant/screener \
      backend/app/quant/backtest         ...   Success: no issues in 16 files
```

The two failures are
`test_golden.py::test_golden_was_generated_from_the_current_fixture[FPT]` and
`[KDH]`. They are pre-existing and belong to WP5: the sha256 of
`contracts/fixtures/bars_FPT.json` no longer matches the golden baseline. They
failed identically on the first run of this session, before any file was
created, and nothing in this work package reads or writes those fixtures. The
remedy is WP5's documented one, `python tests/quant/generate_golden.py`, once
the lead integrator confirms the fixture change was intended.

**Environment caveat, unchanged from the WP5 handoff.** This workstream ran on
Python 3.10 while `pyproject.toml` requires 3.11 or later. Fifteen test
modules under `tests/backend/data`, `tests/contracts`, and `tests/qa` cannot
be collected here because they import `datetime.UTC` (3.11 only),
`jsonschema.Draft202012Validator`, `pyarrow`, or `openapi_spec_validator`.
None of them imports anything from `backend/app/quant`, which was verified by
grep, so they cannot be affected by this work package. Please re-run the full
suite on the pinned 3.11 environment before integration.

## 5. The adversarial bias suite: what it found

The instruction for this session put bias controls above features and above
performance and asked for an adversarial suite reported honestly, negative
results included. This section is that report.

### 5.1 How the suite attacks

`tests/quant/test_lookahead_adversarial.py`, 36 tests, attacks from five
independent directions so that a defect slipping past one is caught by
another:

1. **Future-mutation invariance.** Every bar after `t` is replaced with
   garbage and the evaluation re-run. Any read of a future bar, for any
   purpose, changes the answer.
2. **Truncation equivalence.** Evaluating at `t` on a history that physically
   ends at `t` must equal the full-history result.
3. **Direct index instrumentation.** `strategy_helpers.recording_history`
   replaces the history's arrays and tuples with subclasses that record the
   highest index anyone reads. The invariant is then asserted literally: while
   processing session `d`, nothing read an index above `d`.
4. **Price identity.** On a series where the signal bar's open is 1.0 and the
   next bar's open is 777.0, the fill must be 777.0.
5. **Structural refusal.** `AsOfWindow` raises `LookAheadError` on any
   negative lag, exposes no absolute-index accessor, and exposes no route to
   the underlying arrays.

Three `test_canary_*` negative controls assert that the instruments catch a
deliberate cheat, so a green suite cannot mean an instrument that looks at
nothing.

### 5.2 What it found in the implementation

**No look-ahead defect was found in the production code.** That is a negative
result and it is worth stating as such rather than as a clean bill of health:
the suite can only report on the defect classes it models.

### 5.3 What it found in itself

The suite found one real gap **in the suite**, which is the more useful
finding.

An earlier version of
`test_backtest_never_reads_a_bar_after_the_session_being_processed` stepped
through the calendar in strides of thirteen sessions. A deliberately injected
defect that made the executable-bar check read `quality_status[index + 1]`
**passed that test**. The reason is that the executable-bar check only runs on
sessions where an order is pending, and a stride of thirteen never landed on
one. The whole-run ceiling assertion was therefore being applied to a code
path that had not executed.

Two changes were made. The stride is now one session, and the test asserts at
the end that at least one order actually executed across the truncated runs,
so if a fixture stops producing fills the test fails rather than passing on an
unexercised path. A second, narrower test,
`test_executable_bar_check_reads_only_the_execution_bar`, poisons the session
*after* the intended execution bar in every way the check tests for and
asserts the fill is unchanged.

### 5.4 Mutation testing

To establish that the suite has detection power rather than merely passing,
nine look-ahead defects were injected into a scratch copy of the tree and the
suite re-run against each. Results after the fixes in 5.3:

| Injected defect | Tests failed |
|---|---:|
| Baseline, no defect | 0 |
| Fill at the signal bar's price instead of the next bar's | 2 |
| `AsOfWindow` lag sign flip, so the window reads forward | 26 |
| Mark-to-market uses tomorrow's close | 3 |
| Executable-bar check reads tomorrow's `quality_status` | 2 |
| Executable-bar check reads tomorrow's volume | 3 |
| Executable-bar check reads tomorrow's price | 2 |
| Liquidity cap computed on tomorrow's volume | 1 |
| Position size computed from the execution bar's close | 1 |
| Same-session execution (decide, then fill on the same bar) | 5 |
| Baseline restored | 0 |

All nine were killed. One further mutant, setting `earliest_session = session`
instead of `session + 1`, survived, and it survived because it is
semantically equivalent: the three-phase loop appends orders in phase 3 and
drains them in phase 1 of the following session, so the field cannot advance a
fill by a bar on its own. That is worth knowing, because it means
`earliest_session` is documentation of intent rather than the mechanism that
enforces it. The mechanism is the phase ordering, and the mutant that actually
reorders the phases is the one killed by five tests above.

A methodological note for whoever repeats this: the first mutation run
produced contaminated results because `sed -i` left stale `__pycache__`
bytecode in place. Clear `__pycache__` and run with `python -B
-p no:cacheprovider` between mutants.

### 5.5 The other four Section 16 bias controls

| Control | How it is enforced | Test |
|---|---|---|
| No future bars | `AsOfWindow` refuses negative lags; the engine's three-phase loop | 5.1, 5.4 |
| No later publication information | `FundamentalObservation.publication_date` is `date \| None`; a `None` is excluded, never defaulted to `period_end`. A strategy that requires fundamentals refuses to run on a partial history. `require_fundamental_publication_dates` cannot be set to False. | `test_fundamentals_without_a_publication_date_are_excluded`, `test_a_strategy_requiring_fundamentals_refuses_undated_ones` |
| No survivorship-only universe | `universe_is_survivorship_filtered=True` raises `SurvivorshipBiasError`; a symbol named in the universe with no history raises rather than being dropped | `test_survivorship_filtered_universe_is_refused`, `test_a_symbol_named_in_the_universe_must_have_a_history`, `test_terminally_inactive_symbols_may_stay_in_the_backtest_universe` |
| Corporate-action consistency | Every history's `adjustment_status` must equal the declared `price_adjustment_convention`, benchmark included; mismatch raises | `test_mixed_adjustment_conventions_are_refused`, `test_declared_adjustment_convention_must_match_the_bars` |
| Suspended and zero-volume securities | A zero-volume execution bar cancels an entry and cannot carry it forward; a missing bar leaves an exit pending, and a pending exit does not expire; a suspended position keeps its last observed mark rather than being marked to zero | `test_zero_volume_execution_bar_cancels_an_entry_and_defers_an_exit`, `test_a_pending_exit_survives_a_suspension_and_fills_later` |

Note the asymmetry between the screener and the backtester on the 301
terminally inactive symbols, which is deliberate and required by both
instructions at once: they are excluded from *current screening results* and
they must *remain in the historical backtest universe*. Both are tested.

## 6. Known limitations

Two of these mean the live system returns nothing today. Both are consequences
of decisions the user confirmed, and both are visible rather than silent.

1. **The universe gate cannot be satisfied by current data, so a live screener
   run returns zero rows.** `backend/app/data/HANDOFF.md`, limitation 1,
   records that no authoritative security master exists and that every symbol
   currently carries `exchange="UNKNOWN"`, `security_type="unknown"`,
   `trading_status="unknown"`. The approved specification requires an active
   ordinary equity on HOSE, HNX, or UPCOM. Nothing here infers status from a
   file date or a last-bar date. A screener run in this state emits a leading
   warning naming the cause and the per-symbol failed criteria are in
   `ScreenRun.excluded`, so the result is an explained empty set rather than
   an empty list. Tests and backtests inject a `SecurityView`, so WP6 to WP8
   are fully exercised. **Unblocked by:** WP2 supplying a point-in-time
   security master.

2. **`quality_status` is file-level, so one historical anomaly disables a
   symbol at every date.** `backend/app/data/storage/snapshots.py` stamps
   every bar of a file with the maximum severity of any issue found anywhere
   in that file's full history. The specification permits only the exact value
   `valid`. The data handoff reports 505 files with OHLC violations. Those
   symbols will return `signal=unavailable` on every date, not only near the
   anomaly. This was implemented literally, per the user's decision of 31 July
   2026, and the consequence is reported here rather than softened.
   **Unblocked by:** WP2 emitting per-bar rather than per-file
   `quality_status`. This is the single highest-value follow-up in this
   document.

3. **`score` is a WP6 implementation decision, not an approved rule.** The
   specification defines a five-value `signal` but no score, while the
   contract requires integer `score`/`max_score` and Section 15 requires
   deterministic ranking. Score is the count of passed criteria and
   `max_score` is the six criteria the strategy names. It is derived from
   values the specification already defines, but the user should confirm it is
   the ranking they want before the screener output is trusted for
   prioritization.

4. **No AmiBroker reconciliation, and none is due for this strategy.** Section
   13.3's eight-step process applies to strategies migrated from AFL. The
   approved specification states that the two MA AFL files are "contextual
   material only and are expressly non-governing" for this strategy, so steps
   7 and 8 have nothing to reconcile against. The process remains outstanding
   for any future strategy that *is* an AFL migration, and no AmiBroker export
   has been supplied to this workstream. This is the same gap WP5 recorded as
   its highest-priority follow-up.

5. **Timeframe resampling is still unowned.** The strategy declares `1d` and
   evaluates whatever daily rows it is given. Section 12.1's weekly and
   monthly views need a single owner, as WP5 also noted.

6. **No full-universe performance measurement.** The screener has not been
   run across 1,500 to 1,800 securities. The per-symbol cost is dominated by
   Decimal arithmetic in the SMA, which is deliberate and specification-
   mandated but roughly an order of magnitude slower than float64. If a full
   run proves too slow, the correct fix is to compute candidate crossovers in
   float64 and re-evaluate only the near-equality cases in Decimal, which
   preserves the specification's semantics exactly. It has not been done,
   because optimizing before measuring would be guesswork.

7. **Metrics on a short or trade-free window are undefined, and the contract
   cannot say so.** `win_rate`, `profit_factor`, and
   `average_holding_period_days` are genuinely undefined with no closed
   trades. `MetricSet.values` reports `None`; `contract_metrics()` must emit a
   number, so it emits `0.0` and lists the field under
   `benchmark_comparison.undefined_metrics`. A consumer that does not read
   that list will read a zero as a measurement. See proposal C.

8. **Screener recency boundary is an implementation decision.** Section 15
   gives a range without stating its inclusivity. A security passes when
   sessions since its last positive-volume bar are *strictly less than* the
   threshold, which at the contract default of five excludes exactly the
   "five or more" terminal runs the baseline scan counted. Both sides of the
   boundary are pinned by a parametrized test.

## 7. Decisions referred to the user, 31 July 2026

Four ambiguities were put to the user before any code was written, rather
than resolved unilaterally. All four were answered; the answers are
implemented as described.

| Question | Answer implemented |
|---|---|
| Only one strategy is specified. Scope? | Registry plus the one approved specification. No invented strategies, no padding to the v1.0 count. |
| The contract requires `score`; the specification defines none. | Score is the count of passed criteria; `max_score` is the number the strategy names. |
| `quality_status` is file-level but the specification requires per-bar `valid`. | Implement literally and report the consequence. See limitation 2. |
| The universe gate is unsatisfiable with no security master. | Implement literally, fail the gate, warn explicitly, and use an injectable `SecurityView` for tests and backtests. |

## 8. Contract-change proposals

Submitted per Section 24.2, not applied. None blocks this work package.
Ordered by value.

**A. `StrategyEvaluationResult` cannot carry the specified evidence.** The
approved specification names thirty-seven `evidence_fields` and requires that
"The AI layer must consume these values as facts and must not recalculate
them". The contract is `additionalProperties: false` with twelve fields, and
has no `position_state`, `order_status`, `execution_date`, `execution_price`,
or any SMA or volume evidence. Those two requirements cannot both hold.
`serialization.evaluation_payload()` returns the contract object plus the full
evidence for WP10 to consume; a contract that carried an `evidence` object
would remove the need for the parallel channel.
`test_the_contract_cannot_carry_the_specified_evidence_fields` fails if the
contract is later widened, so this proposal cannot go stale unnoticed.

**B. `StrategyDefinition.warmup_bars` should accept a formula or be documented
as parameter-dependent.** The contract holds one integer; the specification
defines `max(slow_period + 1, 20)`. `to_contract_definition()` evaluates it at
the parameters it is given, which is correct but means a published catalogue
entry is only valid for the parameters that produced it.

**C. `BacktestMetrics` should allow null for genuinely undefined metrics.**
`win_rate`, `profit_factor`, `sharpe`, `sortino`, and
`average_holding_period_days` are required non-null numbers but are undefined
with no trades or fewer than two return observations. Emitting `0.0` makes
"no trades closed" indistinguishable from "every trade lost". `cagr` and
`annualized_return` are already nullable, so the precedent exists.

**D. The `Trade` shape should carry the holding period and the exit reason.**
The frozen shape is nine fields with `additionalProperties: false` and no
`holding_sessions`, `entry_reason`, or `exit_reason`. Section 16 requires
average holding period as a metric, so the quantity exists; a trade list a
user can audit needs to say why each position was closed.
`Trade.contract_dict()` drops them and `Trade.as_dict()` keeps them.

**E. `StrategyEvaluationResult.signal` needs a vocabulary.**
`contracts/OPEN_ITEMS.md` records only `watch` as evidenced. The approved
specification defines `unavailable`, `entry`, `entry_blocked`, `exit`, and
`none`, and the distinction between `entry_blocked` and `unavailable` is
load-bearing. Either the enum should be closed on those five, or the open item
should record that the vocabulary is per strategy.

**F. Timeframe and exchange spellings disagree across documents.** The
approved specification writes the bar interval `1d` and the UPCoM exchange
`UPCOM`; the contract's `Timeframe` enum uses `1D` and its examples use
`UPCoM`. Both are carried verbatim here rather than normalized in either
direction, because guessing which is canonical is exactly the sort of quiet
choice that produces a filter matching nothing. One spelling should be
declared canonical.

## 9. Dependencies on other workstreams

**On WP2, in priority order.** Per-bar `quality_status` (limitation 2), then a
point-in-time security master with exchange, security type, and listing status
resolvable for a historical date (limitation 1), then the index code-to-name
mapping, which the screener does not need but a benchmarked backtest does.

**On the lead integrator.** The six proposals in section 8, and the decision
on whether WP10's fact bundle consumes `evaluation_payload()` or waits for a
widened contract.

**On the user.** Specifications for the remaining nine to fourteen v1.0
strategies. Section 13.2 is explicit that this is "the true critical path",
and it remains so.

## 10. Security implications

- **No network, database, file, or subprocess access** in
  `backend/app/quant/strategies/**`. Enforced by a static AST scan of every
  module and a runtime sandbox that replaces `open`, the socket constructors,
  and the process-spawning entry points, with a meta-test proving the sandbox
  is not vacuous. This mirrors the WP5 enforcement.
- **No `eval`, `exec`, or `compile`** anywhere in the owned packages;
  the static scan rejects them. Strategy parameters are data, never code, so a
  strategy definition cannot smuggle an expression through the registry.
- **File and thread use is confined to two named modules.**
  `screener/jobs.py` is the only module that starts a thread, and it schedules
  only pure functions. `screener/export.py` returns CSV *text*; writing it to
  disk is the caller's decision, so this package never chooses a path.
- **Input validation.** Unknown parameter names are rejected rather than
  ignored. Cross-parameter constraints are checked before evaluation, as the
  specification requires. Bar series reject mismatched lengths and
  non-increasing dates.
- **Resource bounds are the caller's job**, as in WP5. Parameter maxima *are*
  enforced here, since the approved parameter table supplies them, but the API
  layer should still clamp any request-supplied universe size.
- **Undefined values stay undefined.** Division by zero produces `None`, never
  infinity, so profit factor cannot reach a fact bundle as an apparently
  enormous number.
- **A partially completed screener run is never stored.** A failed background
  job records the error and no results, because a partial universe scan looks
  exactly like a complete one with fewer hits.

## 11. Follow-up issues

1. Per-bar `quality_status` from WP2. Highest value: without it, 505 files are
   permanently unscreenable. (Limitation 2.)
2. Point-in-time security master from WP2. Without it the screener returns
   zero rows. (Limitation 1.)
3. User confirmation of the score definition before screener rankings are used
   to prioritize work. (Limitation 3.)
4. Specifications for the remaining v1.0 strategies.
5. Lead integrator decisions on proposals A to F.
6. Measure a full-universe screener run and, only if it is too slow, apply the
   float64 pre-filter with Decimal re-evaluation described in limitation 6.
7. Re-run the full suite on the pinned Python 3.11 environment.
8. Resolve the two pre-existing WP5 golden-fixture failures.
9. An AmiBroker export, for any future strategy that is an AFL migration and
   for WP5's outstanding indicator reconciliation.
10. Decide the owner of daily-to-weekly and daily-to-monthly resampling.
