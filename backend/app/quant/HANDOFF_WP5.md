# WP5 handoff: indicator engine

Prepared against the checklist in Section 24.3 of
`vn_terminal_multi_ai_development_plan.md` v1.1. Owner: quantitative
specialist. Scope: `backend/app/quant/**` and `tests/quant/**` only.

## 1. Files changed

Nothing outside the two paths this workstream owns was touched. No file
under `contracts/`, `backend/app/data/`, `backend/app/ai/`, or `frontend/`
was created, edited, or deleted.

### New: `backend/app/quant/`

| File | Purpose |
|---|---|
| `__init__.py` | Package docstring stating the purity rule. |
| `indicators/__init__.py` | Public surface; importing it registers every indicator. |
| `indicators/types.py` | `OHLCVSeries`, `BenchmarkSeries`, `IndicatorSpec`, `IndicatorResult`, `Tolerance`, error types. |
| `indicators/registry.py` | Registry, `register` decorator, `compute`, `documentation()`. |
| `indicators/windows.py` | Rolling, recursive, and cumulative primitives with their three missing-value rules. |
| `indicators/trend.py` | SMA, EMA, MACD, rate of change, rolling high, rolling low. |
| `indicators/momentum.py` | RSI. |
| `indicators/volatility.py` | ATR, Bollinger Bands, rolling volatility, drawdown. |
| `indicators/volume.py` | Volume moving average, volume-price trend. |
| `indicators/money_flow.py` | A/D line, OBV, up/down volume ratio, volume-at-price, unusual-volume flags, block builder, `close_versus_vwap`. |
| `indicators/relative_strength.py` | RS versus VN-Index and sector, plus the blocked benchmark resolver. |
| `indicators/levels.py` | Pivot levels and the `Levels`-shaped support/resistance helper. |
| `indicators/engine.py` | Batch computation and contract serialization. |
| `indicators/NUMERICS.md` | Generated Section 14 documentation. |
| `HANDOFF_WP5.md` | This file. |

### New: `tests/quant/`

`conftest.py`, `helpers.py`, `reference.py` (independent naive
reimplementation of every indicator), `test_indicator_math.py`,
`test_money_flow.py`, `test_relative_strength.py`, `test_purity.py`,
`test_documentation.py`, `test_engine.py`, `test_golden.py`,
`generate_golden.py`, `generate_numerics.py`, and the golden baselines
`golden/indicators_FPT.json` and `golden/indicators_KDH.json`.

## 2. Contract version

`contracts/VERSION` = **0.1.0**, unchanged and unedited. The engine emits
`indicators_response.schema.json`, `money_flow_block.schema.json`, and
`levels.schema.json` shapes, each validated against the frozen schema in the
test suite. Five change proposals are listed in section 8; none of them is
required for WP5 to be usable, and none was applied unilaterally.

## 3. Commands to test

```
cd vn-terminal
python -m pytest tests/quant            # this work package
python -m pytest tests                  # full suite, for regressions
python tests/quant/generate_golden.py   # regenerate the golden baselines
python tests/quant/generate_numerics.py # regenerate NUMERICS.md
```

The two generators are deterministic; running them without a code change
reproduces byte-identical output.

## 4. Test output

```
python -m pytest tests/quant
408 passed, 2 skipped

python -m pytest tests   (see the environment caveat in section 5)
490 passed, 4 skipped
```

The two skips in `tests/quant` are the relative-strength benchmark
resolution tests, skipped with the reason in section 6.

Coverage of the WP5 acceptance criteria:

- *No network or database access inside indicator functions.*
  `test_purity.py` enforces it twice. Statically, every module in the
  package is parsed and rejected if it imports any of 28 I/O, concurrency,
  or randomness modules, calls `open`, `eval`, `exec`, or `compile`, or
  touches an attribute named `now`, `today`, `connect`, `environ`,
  `urlopen`, `system`, `seed`, and so on. Dynamically, every registered
  indicator plus both builders run inside a sandbox where `open`,
  `socket.socket`, `socket.create_connection`, `os.system`, `os.popen`,
  `subprocess.run`, `subprocess.Popen`, and `__import__` are replaced by
  functions that fail the test. A meta-test checks the sandbox itself
  blocks, so it cannot pass vacuously.
- *Pure functions produce repeatable results.* Every indicator is run
  twice and compared bit for bit; run again with a different security
  interleaved, to catch hidden state; and checked for input mutation, with
  input arrays copied and marked read-only at construction.
- *Reference tolerances are documented.* Every indicator carries a
  `Tolerance` with an absolute arm, a relative arm, and a statement of what
  it is a tolerance against. `test_documentation.py` fails on an empty or
  perfunctory entry.
- *Golden fixture per indicator.*
  `test_golden.py::test_golden_covers_every_registered_indicator` fails if
  any registered indicator is absent from the baselines, so the requirement
  cannot decay as WP6 and WP7 add indicators.

## 5. Data fixtures used

Only `contracts/fixtures/`. No live database, no FData file, and no network
call anywhere in this work package.

- `bars_FPT.json`, `bars_KDH.json` (520 daily bars each) for reference
  cross-checks and golden baselines. The golden files record the sha256 of
  each bars fixture and fail if it changes, so a fixture regeneration cannot
  silently invalidate the baseline.
- `security_master.json` for the index code-to-name mapping, which is how
  the tests discover that the mapping does not yet exist.
- `indicators_response.schema.json`, `money_flow_block.schema.json`,
  `levels.schema.json`, `price_bar.schema.json` for shape validation.

These fixtures are synthetic (`contracts/fixtures/README.md`). Nothing in
the tests or the golden files should be read as a market fact, and the
golden baselines will need regenerating once WP1 and WP2 replace the
fixtures with real bars. That is expected and the test failure message says
so.

**Environment caveat.** This workstream ran on Python 3.10, while
`pyproject.toml` requires 3.11 or later. Four data-workstream test modules
(`test_api.py`, `test_service.py`, `test_snapshots.py`, `test_storage.py`)
import `datetime.UTC`, which is 3.11 only, and could not be collected here;
they were excluded from the full-suite run above. Separately,
`tests/contracts/test_generators_reproducible.py::test_json_schema_generator_is_idempotent`
fails in this environment because the installed pydantic is 2.13.4 against
the pinned 2.13.3, which changes the generated JSON Schema bytes. Both are
pre-existing and unrelated to WP5; neither touches
`backend/app/quant/**`. Please re-run the full suite on the pinned 3.11
environment before integration.

## 6. Known limitations

1. **The AmiBroker half of the Section 14 acceptance criterion is not
   met.** The criterion is "match an independent reference or AmiBroker
   export within a documented tolerance". The independent reference exists
   and every indicator is checked against it. No AmiBroker export was
   supplied to this workstream. This is not a formality: a reference
   implementation cannot detect a wrong *convention*, only a wrong
   implementation of the chosen one. The four conventions most likely to
   differ are the EMA seeding rule, the first bar's true range, the
   population versus sample standard deviation in Bollinger Bands, and the
   RSI value on a flat window. All four are named in `NUMERICS.md` under
   "Outstanding external verification", and a test fails if that section is
   removed without supplying the export.

2. **Relative strength cannot resolve a real benchmark.** Section 10.2
   requires an index code-to-name mapping before these calculations are
   enabled; the 207 files under `EOD/index` carry numeric names; and no
   `security_master` entry with `security_type: "index"` and a populated
   `index_code` exists. The mathematics is implemented and tested against a
   synthetic benchmark, `resolve_market_index_code` and
   `resolve_sector_index_code` raise `BenchmarkMappingUnavailable` rather
   than guessing, and two end-to-end tests skip with that reason. No index
   code was fabricated. See section 7.

3. **Close-versus-VWAP is implemented but not wired.** See section 7.

4. **Volume-at-price assigns each bar's whole volume to the bin holding its
   typical price**, rather than spreading it across the high-low range. The
   spread model is more faithful and is a follow-up. The value area is
   selected greedily by descending bin volume rather than by the classic
   market-profile expansion from the point of control. Both choices are
   documented in the indicator's `comparison_reference`.

5. **Timeframe resampling is out of scope.** Pivot levels and every other
   indicator are period-agnostic: pass daily bars for daily values, weekly
   bars for weekly. Nobody currently owns the daily-to-weekly and
   daily-to-monthly conversion that Section 12.1 requires, and it should
   have exactly one owner rather than being reimplemented per indicator.

6. **No performance profiling against Section 3.3.** The engine computes
   the full default set on 520 bars in a few milliseconds, but this has not
   been measured across a 1,500 to 1,800 security universe, which is what
   the screener will do in WP7.

7. **Parameter upper bounds are not enforced.** Lower bounds are validated,
   but nothing rejects `bins=10**9` or `period=10**8`. Inside a trusted
   process that is fine; see section 9.

## 7. Dependencies on other workstreams

**On the data stream (WP2): index code-to-name mapping.** Relative strength
versus VN-Index and versus sector needs `security_master` entries with
`security_type: "index"` and a populated `index_code`, plus the index bars
themselves. Once those exist, `mapping_from_security_master()` builds the
mapping with no further work here, `resolve_market_index_code()` and
`resolve_sector_index_code()` start returning codes, and the two skipped
tests turn themselves back on. Two further things need settling at that
point: which code is VN-Index (the mapping's `market_index_code` is not
derivable from the security master as currently shaped, and is left None),
and whether the sector vocabulary in `security_master.sector` matches
whatever the sector indices are built from.

**On the data stream and the lead: close-versus-VWAP.**
`docs/data_dictionary.md` now records the WP1 conclusion that `Aux1` is the
unadjusted daily average price, which is the condition Section 14 sets for
admitting this measure to the money-flow block. It still cannot be
computed here, for three reasons that belong to other owners. The canonical
`PriceBar` contract carries no VWAP or unadjusted-close field, so the inputs
cannot be delivered. The data dictionary's own safeguard keeps `Aux1` out of
every calculation pending an explicit downstream design decision. And the
verification covers five liquid HOSE equities on one session, with
corporate-action dates untested.

There is also a substantive trap worth flagging before anyone wires this up:
`Aux1` is **unadjusted** and OHLC is **back-adjusted**, so dividing the
stored close by the stored `Aux1` is correct only for bars after the most
recent corporate action and silently wrong for every bar before it. The
formula is implemented as
`money_flow.close_versus_vwap(unadjusted_close, vwap)`, which takes the
unadjusted close as an explicit argument precisely so this mistake cannot be
made by accident, and `build_money_flow_block(..., close_vs_vwap=...)`
accepts a finished value from a caller that can legitimately produce one.
The block never derives it. A test watches `price_bar.schema.json` and fails
the moment a VWAP-like field appears, as a reminder to revisit this.

## 8. Contract-change proposals

Submitted per Section 24.2, not applied. None blocks WP5.

**A. `IndicatorSeries` should carry `output` and `parameters` as fields.**
The contract identifies a series by one free-text string, which must
currently encode three things: the indicator, which of its outputs, and at
what parameters. The convention adopted is `sma`, `sma[period=50]`,
`macd.signal`, `bollinger_bands[period=10].upper`, and
`build_indicators_payload` refuses to emit a payload with two identical ids.
It works, but a frontend has to parse the string to label a line. Two extra
fields would make it structural. This is the highest-value of the five.

**B. `MoneyFlowBlock.up_down_volume_ratio` should be nullable, with
`up_volume_share` added alongside.** The field is typed as a required
number, and the ratio is genuinely undefined when a window contains no
down-volume, which in Vietnam means any limit-up streak, not a rare edge
case. JSON cannot carry infinity, so the builder currently raises
`MoneyFlowUndefined` with an explanatory message rather than substituting a
placeholder. `up_volume_share`, which is `up / (up + down)` and equals 1.0
in exactly that case, stays defined and would let the block always render.

**C. `MoneyFlowBlock.volume_at_price_concentration` could be typed.**
`contracts/OPEN_ITEMS.md` records the shape as undecided. The engine fills
it with bin edges, bin volumes and shares, point of control, top-three
share, Herfindahl and normalized Herfindahl, value area bounds, and included
and excluded bar counts. If that set is acceptable it could become a typed
object rather than an open one.

**D. `MoneyFlowBlock.unusual_volume_flags` could record what flagged them.**
It is a list of dates. The dates mean nothing without the window and the
multiple that produced them, and the multiple is a tunable with no external
authority. Consider a small object carrying the parameters alongside the
dates.

**E. `PriceBar` would need an unadjusted close and a VWAP field** if
close-versus-VWAP is ever to be populated. See section 7. This one should
wait for the data stream's explicit design decision on `Aux1` rather than
being decided at the contract level first.

## 9. Security implications

- **No network access, no database access, no file access, no subprocess
  execution** in any indicator or in either builder. This is enforced by
  tests rather than by convention, statically and at runtime, as described
  in section 4.
- **No `eval`, `exec`, or `compile`** anywhere in the package; the static
  scan rejects them. Indicator parameters are data, never code, so a
  strategy definition cannot smuggle an expression through the registry.
- **No secrets, credentials, or environment reads.** The static scan rejects
  `os.environ` and `getenv`. Nothing here needs configuration.
- **No user data leaves the process.** The engine returns plain Python
  objects to its caller and logs nothing.
- **Input validation.** Unknown parameter names are rejected rather than
  ignored, so a typo in a strategy definition surfaces immediately instead
  of silently running at a default. Series construction rejects mismatched
  lengths and non-increasing dates.
- **Resource bounds are the caller's job.** Lower bounds on parameters are
  enforced, upper bounds are not. If the API layer ever passes a
  user-supplied `bins`, `lookback`, or `period` straight through, a large
  value would allocate proportionally large arrays. Section 20 treats this
  as a single-user local application, so this is a robustness note rather
  than a live vulnerability, but the API layer should clamp any parameter
  it accepts from a request body.
- **Division by zero returns NaN, never infinity.** An undefined value stays
  visibly undefined rather than becoming an infinity that survives into a
  strategy comparison or an AI fact bundle as an apparently enormous number.

## 10. Follow-up issues

1. Obtain an AmiBroker export for the Section 14 indicators at default
   parameters for a handful of tickers, drop it in
   `tests/quant/golden/amibroker/`, and add the comparison test. Until then
   the four conventions in `NUMERICS.md` are unverified against the platform
   the user already trusts. **Highest priority of these ten.**
2. Wire relative strength once WP2 supplies the index mapping, and remove
   the two skips.
3. Decide the `Aux1` exposure question (section 7) before anyone tries to
   populate `close_vs_vwap`.
4. Implement volume-at-price with volume spread across each bar's high-low
   range, and compare against the current typical-price binning.
5. Decide who owns daily-to-weekly and daily-to-monthly resampling, and put
   it in one place.
6. Benchmark the default indicator set across the full 1,500 to 1,800
   security universe before WP7 relies on it.
7. Re-run the full test suite on the pinned Python 3.11 environment; four
   data test modules could not be collected on 3.10 here.
8. `tests/contracts/test_generators_reproducible.py` fails on pydantic
   2.13.4 against the pinned 2.13.3. Lead integrator's call whether to pin
   harder or to loosen the test.
9. Regenerate the golden baselines once WP1 and WP2 replace the synthetic
   fixtures with real bars, and re-examine any indicator whose warm-up or
   values shift by more than the fixture change explains.
10. WP6 needs the lead's decision on `contracts/OPEN_ITEMS.md` item B, the
    structure of `StrategyDefinition.entry_rule` and its siblings, before
    the strategy registry can be built on this engine.
