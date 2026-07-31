# VN Terminal Pro v1.0 Strategy Catalogue

This catalogue contains the normative, deterministic definitions of strategies approved for VN Terminal Pro v1.0. The words **must**, **must not**, **required**, and **prohibited** are binding implementation requirements.

Each strategy is versioned independently. Any change that can alter a signal, order, reported criterion, or evidence value requires a strategy-version change.

---

## 1. Dual-SMA Trend Crossover

**Specification status:** Approved  
**Approval date:** 2026-07-30  
**Position direction:** Long only  
**Position policy:** At most one open position per symbol; pyramiding is prohibited.

### Understanding summary

- This is a minimal moving-average trend reference strategy for testing the strategy interface, signal timing, chart markers, backtests, and golden datasets.
- It evaluates completed daily EOD bars and uses a strict crossover between a configurable fast SMA and slow SMA.
- Entry is subject to universe, data-quality, current-volume, and 20-session average-volume gates.
- Exit and invalidation occur on the symmetrical bearish crossover and are never suppressed by the average-volume gate.
- Signals are calculated deterministically from versioned local data. AI may explain supplied evidence but must not calculate or modify signals.
- Position sizing, transaction costs, slippage, portfolio constraints, and benchmark selection are external backtester controls.

### Strategy-definition contract

#### `strategy_id`

`dual_sma_trend_crossover`

The identifier does not include `20_50` because those values are configurable defaults rather than fixed rules.

#### `version`

`1.1.0`

Revision history:

| Version | Date | Change |
|---|---|---|
| `1.0.0` | 2026-07-30 | Initial specification |
| `1.1.0` | 2026-07-30 | Added `halt_exit_rule` after empirical testing found positions held indefinitely on halted symbols. Corrected `security_type` and `exchange` enumerations to match the frozen contract. Documented the executability test as a fill-feasibility model. Defined order semantics while an exit is pending. |

#### `title_vi`

`Giao cắt xu hướng hai đường SMA`

#### `title_en`

`Dual-SMA Trend Crossover`

#### `category`

`trend_following`

#### `timeframe`

- Bar interval: `1d`
- Evaluation frequency: once per completed Vietnamese exchange trading session
- Evaluation time: after the EOD bar is complete
- Time zone: `Asia/Ho_Chi_Minh`
- Index notation: `t` is the completed candidate bar; `t-1` is the immediately preceding chronological daily row, not the preceding calendar date.
- Missing calendar dates must not be synthesized.

#### `required_fields`

##### Bar data

| Field | Type and unit | Requirement |
|---|---|---|
| `session_date` | Local exchange date | Unique and strictly increasing within each symbol |
| `open` | Numeric, thousand VND | Required for execution; must be finite and greater than zero on an execution bar |
| `close` | Numeric, thousand VND | Canonical FData back-adjusted close; must be finite and greater than zero |
| `volume` | Integer, shares | Must be finite, integral, and greater than or equal to zero |
| `quality_status` | String | Only the exact value `valid` is usable |

##### Point-in-time security master

| Field | Required entry value |
|---|---|
| `symbol` | Non-empty canonical symbol |
| `exchange` | One of `HOSE`, `HNX`, or `UPCoM` |
| `security_type` | `equity` |
| `listing_status_as_of_date` | `active` on `session_date` |

These enumeration values are taken verbatim from the frozen canonical contract in Section 10 of the development plan and must not be altered here. If the strategy requires a narrower classification than `equity`, for example to exclude investment funds, that distinction must be added to the security-master contract by the lead integrator through the change process in Section 24.2, never redefined inside a strategy specification.

##### Provenance and interpretation

- `data_version`
- `source`
- `adjustment_status`
- `price_unit`
- `volume_unit`

`high` and `low` are not direct strategy inputs. Upstream OHLC validation is represented by `quality_status`.

#### `warmup_bars`

```text
warmup_bars = max(slow_period + 1, 20)
```

This is the number of chronological daily rows required through and including candidate bar `t`. With the default parameters, the requirement is 51 rows.

The extra row beyond `slow_period` is mandatory because the crossover requires both `SMA_slow[t]` and `SMA_slow[t-1]`. The fixed minimum of 20 rows is mandatory for the liquidity calculation.

No signal may be inferred from a partial window. If warm-up is insufficient, the result is `unavailable`.

#### `parameter_schema`

| Parameter | Type | Default | Minimum | Maximum | Increment | Additional constraint |
|---|---|---:|---:|---:|---:|---|
| `fast_period` | Integer bars | 20 | 2 | 100 | 1 | Must be strictly less than `slow_period` |
| `slow_period` | Integer bars | 50 | 10 | 250 | 1 | Must be strictly greater than `fast_period` |
| `min_avg_volume_20` | Integer shares per day | 200,000 | 0 | 100,000,000 | 10,000 | A value of zero disables average-volume exclusion only |
| `halt_exit_sessions` | Integer sessions | 5 | 1 | 60 | 1 | Consecutive zero-volume sessions that trigger a forced exit |

The default `min_avg_volume_20` of 200,000 shares is a deliberate owner decision. Measured against the 30 July 2026 snapshot it admits 244 of 1,671 stocks, or 14.6 percent of the universe, restricting the strategy to approximately the top sixth of the market by share volume. This is intended, on the reasoning that a medium-term position must be exitable without moving the price.

Configurations for which `fast_period >= slow_period` must be rejected before evaluation. SMA type, input price, 20-bar liquidity lookback, timeframe, and execution convention are fixed strategy rules, not configurable parameters.

#### Deterministic derived values

For any permitted SMA period `p`, first compute:

```text
raw_sma_p[t] =
    sum_oldest_to_newest(close[t-p+1], ..., close[t]) / p

SMA_p[t] = quantize(raw_sma_p[t], 6 decimal places, ROUND_HALF_EVEN)
```

Rules:

1. The window contains exactly `p` chronological rows and includes bar `t`.
2. Summation order is oldest to newest.
3. Every close in the window must be canonical, finite, greater than zero, and from a bar whose `quality_status` is `valid`.
4. Partial-window values are prohibited.
5. `SMA_p[t-1]` is calculated independently from rows `t-p` through `t-1`.
6. Both SMAs are quantized before relational comparison.
7. Quantized SMA evidence is reported to the same six-decimal precision in the stored price unit, thousand VND.

Define:

```text
sma_fast_t      = SMA_fast_period[t]
sma_slow_t      = SMA_slow_period[t]
sma_fast_prev   = SMA_fast_period[t-1]
sma_slow_prev   = SMA_slow_period[t-1]

fast_minus_slow_t    = quantize(sma_fast_t - sma_slow_t, 6, ROUND_HALF_EVEN)
fast_minus_slow_prev = quantize(sma_fast_prev - sma_slow_prev, 6, ROUND_HALF_EVEN)
```

Define the 20-bar volume sum and mean:

```text
volume_sum_20[t] = sum(volume[t-19], ..., volume[t])
avg_volume_20[t] = volume_sum_20[t] / 20
```

All 20 volumes must be finite non-negative integers from `quality_status == "valid"` bars. Zero-volume rows remain in the calculation. To avoid floating-point ambiguity, the liquidity comparison must be implemented equivalently as:

```text
volume_sum_20[t] >= 20 * min_avg_volume_20
```

Equality therefore passes.

#### `entry_rule`

The technical bullish-crossover event is:

```text
bullish_crossover[t] =
    sma_fast_t > sma_slow_t
    AND sma_fast_prev <= sma_slow_prev
```

Equality on the current bar is not bullish. Equality on the preceding bar permits a crossover when the fast SMA becomes strictly greater on the current bar.

Define the entry gates:

```text
universe_pass[t] =
    exchange IN {"HOSE", "HNX", "UPCOM"}
    AND security_type == "ordinary_equity"
    AND listing_status_as_of_date == "active"

signal_bar_volume_pass[t] = volume[t] > 0

liquidity_pass[t] =
    volume_sum_20[t] >= 20 * min_avg_volume_20

entry_eligible[t] =
    universe_pass[t]
    AND signal_bar_volume_pass[t]
    AND liquidity_pass[t]
    AND data_quality_pass[t]
    AND warmup_pass[t]
```

An entry order is created if and only if:

```text
position_state[t] == "flat"
AND bullish_crossover[t]
AND entry_eligible[t]
```

Bullish crossovers while already long are recorded in rule evidence but create no order. Pyramiding is prohibited.

#### `exit_rule`

The bearish-crossover event is:

```text
bearish_crossover[t] =
    sma_fast_t < sma_slow_t
    AND sma_fast_prev >= sma_slow_prev
```

An exit order is created if and only if:

```text
position_state[t] == "long"
AND bearish_crossover[t]
```

Equality on the current bar is not bearish. Equality on the preceding bar permits a crossover when the fast SMA becomes strictly lower on the current bar.

The average-volume threshold, current-bar positive-volume gate, and active-universe gate must not suppress an exit from an existing position. A bearish crossover while flat is recorded in rule evidence but creates no order.

#### `halt_exit_rule`

A trading halt, suspension, or delisting must terminate an open position. Without this rule the two moving averages freeze on carry-forward zero-volume bars, never cross, and the position is held indefinitely. Empirical testing of this specification at version `1.0.0` against the 30 July 2026 snapshot confirmed the defect, with AMD and IBC both left holding an open long at the final bar and no order outstanding.

Define:

```text
consecutive_zero_volume[t] =
    count of consecutive chronological rows ending at t
    for which volume == 0

halt_exit[t] =
    listing_status_as_of_date != "active"
    OR consecutive_zero_volume[t] >= halt_exit_sessions
```

Rules:

1. While `position_state == "long"`, a true `halt_exit[t]` creates a full exit order regardless of crossover state, data-quality status, or liquidity.
2. The fill occurs at the close of the most recent chronological row with `volume > 0`, which is the last price at which the position could genuinely have been sold. This is a deliberate departure from the next-open convention, because by construction no executable next bar exists.
3. If no such row exists within the position's holding period, the fill occurs at the entry price and the trade is recorded with `warnings` containing `halt_exit_no_executable_price`.
4. A halt exit supersedes any scheduled or pending order for the same position. The superseded order is recorded with `order_status = "cancelled"`.
5. `halt_exit_rule` never creates an entry and never applies while flat.
6. When `listing_status_as_of_date` is unavailable because point-in-time security-master coverage is incomplete, the zero-volume-run condition alone governs. Missing status metadata must never leave a position open.
7. A symbol that has triggered a halt exit is ineligible for re-entry until it records `halt_exit_sessions` consecutive rows with `volume > 0` and `listing_status_as_of_date == "active"`.

The `halt_exit_sessions` default of 5 sessions matches the terminal zero-volume run threshold used in the data-quality inventory in Section 19.2 of the development plan, so the strategy and the security master classify halted securities consistently.

#### `invalidation_rule`

The trend thesis is invalidated by either the bearish crossover used by `exit_rule` or a trading halt:

```text
invalidation_rule[t] = bearish_crossover[t] OR halt_exit[t]
```

While long, invalidation creates a full exit order. This strategy has no separate percentage stop, ATR stop, time stop, profit target, or price-level invalidation rule.

#### `liquidity_rule`

Entry requires both:

```text
volume[t] > 0
AND mean(volume[t-19], ..., volume[t]) >= min_avg_volume_20
```

The signal bar is included in the 20-bar mean. Zero-volume historical rows are included and reduce the mean. Setting `min_avg_volume_20` to zero disables only the average-volume threshold; `volume[t] > 0` remains mandatory.

The liquidity rule applies only to entries. It must never delay, cancel, or suppress an exit.

#### Data-quality and missing-value rule

`data_quality_pass[t]` is true only when every bar needed by the current and previous SMA windows and the current 20-bar volume window has `quality_status == "valid"` and every required numeric field satisfies its field constraint.

Rules:

1. Missing, non-finite, non-positive close values are never imputed.
2. Missing, non-finite, or negative volume values are never imputed.
3. A zero volume is valid for rolling calculations but fails the current-bar entry-volume gate.
4. A required invalid observation makes the affected rolling result unavailable.
5. Calculation resumes only after the invalid observation has left every required window.
6. An existing position is not closed solely because data become unavailable. A previously created exit order remains governed by the pending-exit execution rule.

#### `execution_convention`

##### Entry

1. Evaluate the entry rule only after completed bar `t`.
2. Schedule execution for the open of the immediately following chronological daily row, `t+1`.
3. The entry executes at `open[t+1]` only if:
   - `quality_status[t+1] == "valid"`;
   - `open[t+1]` is finite and greater than zero; and
   - `volume[t+1] > 0`.
4. If any execution condition fails, cancel the entry.
5. A cancelled entry must not be carried to a later bar.

##### Exit

1. Evaluate the exit rule only after completed bar `t`.
2. Schedule execution for the open of row `t+1`.
3. Apply the same executable-bar checks used for entry.
4. If row `t+1` is not executable, set `order_status = "pending_exit"`.
5. Execute the full exit at the first later chronological bar having `quality_status == "valid"`, finite positive open, and positive volume.
6. A pending exit does not expire through the passage of time. It terminates only by execution or by being superseded by a halt exit under `halt_exit_rule`.

##### Order semantics while an exit is pending

1. At most one exit order may exist per position. A further `bearish_crossover` while `order_status == "pending_exit"` must not create a duplicate order. It is recorded in rule evidence with `signal = none`.
2. A `bullish_crossover` while an exit is pending creates no entry, because `position_state` remains `long`. It is recorded in rule evidence with `signal = none` and a warning of `bullish_crossover_suppressed_by_pending_exit`, so that a suppressed opportunity is visible rather than silently lost.
3. A pending exit that is superseded by a halt exit is recorded with `order_status = "cancelled"` and the halt exit is recorded separately.

##### Fill feasibility and the use of full-bar information

The executability test for row `t+1` reads `quality_status[t+1]`, `open[t+1]`, and `volume[t+1]`, all of which are known only after row `t+1` completes, while the fill itself is priced at the open of that row. This is a deliberate fill-feasibility model rather than a signal input, and it is bounded by three requirements.

1. The test may only cancel or delay an order. It must never select a better fill price, alter the signal date, or change which securities generate signals.
2. `volume[t+1] > 0` is the economically valid part of the test, since a session with no trading offers no fill at any price.
3. `quality_status[t+1] == "valid"` is the weaker part, because it uses a whole-bar quality judgment to decide a fill at the open, and could systematically skip anomalous sessions. Backtest reports must therefore disclose the count of cancelled entries and delayed exits alongside the trade list, and the QA review in WP14 must confirm that cancellation is not treated as a costless skip.

Position sizing, commission, slippage, portfolio-wide maximum positions, and benchmark assumptions are external backtester settings and must not alter signal dates.

#### Signal classification

`signal` must contain exactly one of:

| Value | Deterministic meaning |
|---|---|
| `unavailable` | Warm-up is insufficient, or the crossover cannot be validly computed because a required input is missing, invalid, or blocked by quality status |
| `entry` | Flat, valid bullish crossover, and every entry gate passes |
| `entry_blocked` | Flat and valid bullish crossover, but at least one computable non-data entry gate fails: universe, current positive volume, or average-volume threshold |
| `exit` | Long and valid bearish crossover; a full exit order is created |
| `halt_exit` | Long and `halt_exit[t]` is true; a full exit order is created regardless of crossover state or data quality |
| `none` | Every other valid and computable evaluation |

`halt_exit` takes precedence over every other classification while long. It is reported even when `data_quality_pass[t]` is false, because a halt exit must not depend on the data quality of a security that has stopped trading.

`entry_blocked` must not be used when the crossover itself is indeterminate. This distinction prevents “no qualifying entry” from being confused with “the calculation could not be performed.”

`order_status` must contain exactly one of:

- `none`
- `scheduled`
- `executed`
- `cancelled`
- `pending_exit`

#### `evidence_fields`

The strategy must populate the following fields for the AI fact bundle. The AI layer must consume these values as facts and must not recalculate them.

##### Identity, date, and state

- `as_of_date`
- `signal`
- `position_state`
- `strategy_id`
- `strategy_version`
- `parameter_values`

##### Price and crossover evidence

- `close`
- `sma_fast_t`
- `sma_slow_t`
- `sma_fast_t_minus_1`
- `sma_slow_t_minus_1`
- `fast_minus_slow_t`
- `fast_minus_slow_t_minus_1`

##### Eligibility and data evidence

- `volume_t`
- `volume_sum_20_t`
- `avg_volume_20_t`
- `min_avg_volume_20`
- `liquidity_pass`
- `signal_bar_volume_pass`
- `universe_pass`
- `data_quality_pass`
- `warmup_bars_required`
- `usable_bars_available`

##### Rule evidence

- `bullish_crossover`
- `bearish_crossover`
- `entry_rule_pass`
- `exit_rule_pass`
- `invalidation_rule_pass`
- `halt_exit_pass`
- `consecutive_zero_volume_t`
- `halt_exit_sessions`
- `listing_status_as_of_date`
- `passed_criteria`
- `failed_criteria`

##### Execution evidence

- `execution_convention`
- `order_status`
- `execution_date`
- `execution_price`

For a live scheduled order, `execution_date` and `execution_price` must be `null` until execution. For `none`, `unavailable`, or `entry_blocked` without an order, both fields must be `null`.

##### Provenance and warnings

- `data_version`
- `adjustment_status`
- `warnings`

Warnings must identify insufficient warm-up, invalid fields, blocked quality status, unavailable point-in-time classifications, cancelled entry execution, delayed exit execution, halt exits, suppressed bullish crossovers during a pending exit, and halt exits with no executable price, when applicable.

#### `reference`

```text
Reference type: owner_judgment
Reference: VN Terminal Pro specification, 30 July 2026.

Owner-approved at v1.1.0 on 30 July 2026:
  - halt_exit_rule design, trigger, and fill convention
  - min_avg_volume_20 default of 200,000 shares

Agent-proposed and pending explicit owner confirmation:
  - fast_period and slow_period defaults of 20 and 50
  - next-open execution convention
  - treatment of the two MA AFL files as non-governing
  - symmetrical bearish crossover as both exit and invalidation
```

The distinction above is binding. Any parameter listed as agent-proposed must be reviewed and either confirmed or changed by the owner before this strategy is used to generate a trading decision. A specification must never attribute an unreviewed default to owner judgment.

The following AFL files are contextual material only and are expressly **non-governing** for this strategy:

- `BO CAI PHAMTUAN - NEW VERSION1/BACKTEST - CHART TRADING WITH MA NEW.afl`
- `BO CAI PHAMTUAN - NEW VERSION1/LOC CP - TRADING WITH MA NEW.afl`

Those AFL files combine MA rebounds, pocket pivots, and breakout logic and do not define this clean reference strategy.

### Assumptions and dependencies

- The canonical pipeline preserves the stored FData close and its adjustment metadata in versioned snapshots.
- The price unit is thousand VND and the volume unit is shares.
- A point-in-time security master supplies the approved exchange, security type, and listing status values.
- Upstream validation supplies the exact `quality_status` value `valid`.
- The strategy engine supports decimal quantization with round-half-to-even.
- Changes to upstream field semantics or enumeration mappings require compatibility review and may require a new strategy version.

### Explicit non-goals

- No short selling or position reversal.
- No pyramiding or partial entry.
- No partial exit.
- No stop-loss, profit target, ATR stop, or time stop. The halt exit is a tradability rule, not a risk stop.
- No portfolio sizing, commission, slippage, or benchmark rule.
- No intraday or weekly calculation.
- No AI-generated indicator or signal value.
- No broker connectivity or automated order placement.

### Deterministic edge-case requirements

| Case | Required result |
|---|---|
| `SMA_fast[t] == SMA_slow[t]` after quantization | No bullish or bearish crossover on `t` |
| Previous SMAs equal and current fast SMA is greater | Bullish crossover |
| Previous SMAs equal and current fast SMA is lower | Bearish crossover |
| Bullish crossover with mean volume exactly equal to threshold | Liquidity passes |
| `min_avg_volume_20 == 0` and `volume[t] == 0` | Entry remains blocked by current-bar volume rule |
| Valid bullish crossover while already long | `signal = none`; no additional order |
| Valid bearish crossover while flat | `signal = none`; no order |
| Insufficient warm-up or indeterminate crossover | `signal = unavailable`, never `entry_blocked` |
| Entry signal followed by an unexecutable next bar | Entry cancelled and not carried forward |
| Exit signal followed by an unexecutable next bar | Exit remains pending until the first executable bar |
| Long, and the symbol records `halt_exit_sessions` consecutive zero-volume rows | `signal = halt_exit`; full exit filled at the close of the last positive-volume row |
| Long, and `listing_status_as_of_date` leaves `active` | `signal = halt_exit`, even if volume is still positive |
| Long, halted, and `listing_status_as_of_date` is unavailable | Zero-volume-run condition alone governs; the position must not remain open |
| Halt exit while an exit order is already pending | Pending order recorded as `cancelled`; halt exit recorded separately |
| Second bearish crossover while an exit is pending | No duplicate order; `signal = none` |
| Bullish crossover while an exit is pending | No entry; `signal = none` with a `bullish_crossover_suppressed_by_pending_exit` warning |
| Halted symbol resumes trading | Re-entry permitted only after `halt_exit_sessions` consecutive positive-volume rows and `listing_status_as_of_date == "active"` |

### Specification decision log

| Decision | Alternatives considered | Reason |
|---|---|---|
| Create a clean reference strategy | Rationalize the MA AFL; copy a published method | Isolates the crossover mechanism and avoids importing composite AFL logic |
| Use daily EOD bars | Weekly or intraday bars | Matches the available FData feed and medium-term workstation scope |
| Use SMA 20/50 defaults | EMA 20/50; SMA 50/200 | Simple, auditable medium-term reference configuration |
| Make periods configurable | Fix periods permanently | Supports controlled testing while retaining canonical defaults |
| Use back-adjusted FData close | Unadjusted close or candidate VWAP | It is the available canonical v1.0 historical price series |
| Use strict event crossovers | Treat alignment as a continuing signal | Produces one deterministic transition event |
| Use symmetrical bearish exit and invalidation | Price-below-MA or stop-based rules | Keeps the reference strategy internally consistent |
| Execute at the next open | Signal close or next close | Separates observation from execution and prevents look-ahead |
| Cancel an unexecuted entry | Carry entry indefinitely | Prevents stale entries |
| Carry an unexecuted exit | Cancel or expire exit | Preserves an established risk-reduction instruction |
| Use 20-bar mean share volume | Median volume or traded value | Available and reproducible without unadjusted historical prices |
| Apply liquidity only to entry | Apply it to exit | Liquidity should not suppress risk reduction |
| Require only active ordinary equities | Include all instruments | Prevents mixed-security contamination |
| Permit only `quality_status == valid` | Permit warnings or ignore flags | Makes the golden reference fail loudly on suspect data |
| Quantize SMAs to six decimals | Raw binary comparison or epsilon | Gives equality and crossover consistent cross-implementation semantics |
| Add `unavailable` signal | Fold indeterminate cases into `none` or `entry_blocked` | Separates absence of a signal from inability to calculate one |
| Keep portfolio assumptions external | Embed costs and sizing | Preserves strategy portability and separates signal logic from simulation |
| Add `halt_exit_rule` at v1.1.0 | Leave halts to the backtester; freeze and exclude halted symbols | Empirical testing found positions held indefinitely on halted symbols, since carry-forward zero-volume bars freeze both SMAs and no crossover ever occurs |
| Trigger the halt exit on a zero-volume run or a status change | Status change alone | Point-in-time listing status is not yet sourced, so a status-only rule would leave positions open exactly where coverage is missing |
| Fill the halt exit at the last positive-volume close | Next open; entry price; no fill | It is the last price at which the position could genuinely have been sold, and no executable next bar exists by construction |
| Set `halt_exit_sessions` default to 5 | 1, 10, or 20 sessions | Matches the terminal zero-volume run threshold used in the data-quality inventory, so the strategy and security master classify halts consistently |
| Adopt the contract enumerations `equity` and `UPCoM` | Keep the narrower `ordinary_equity` and `UPCOM` | A strategy specification must not redefine a frozen canonical enumeration; narrower classifications belong in the security-master contract |
| Document the executability test as fill feasibility | Remove the test; treat it as a signal input | The test uses full-bar information, which is acceptable for modeling whether a fill was possible but must never influence signal selection |
| Confirm `min_avg_volume_20 = 200,000` | 100,000; 50,000; median traded value | Owner decision on 30 July 2026, accepting a universe of approximately 14.6 percent of listed stocks in exchange for exitable positions |

