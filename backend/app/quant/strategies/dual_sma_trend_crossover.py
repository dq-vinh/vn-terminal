"""Strategy 1 of the approved v1.0 catalogue: Dual-SMA Trend Crossover.

Source of truth: `docs/strategy_catalogue.md`, section 1, "Specification
status: Approved, 2026-07-30". Every rule below is a transcription of that
document. Nothing is added. Where the specification is silent, this module is
silent too: there is no stop-loss, no profit target, no time stop, no
pyramiding, no partial fill, and no short side, because the specification's
"Explicit non-goals" section prohibits each of them by name.

Correspondence between the specification and this module:

| Specification heading            | Implementation                          |
|----------------------------------|-----------------------------------------|
| Deterministic derived values     | `_quantized_sma`, `numerics.py`         |
| `entry_rule`                     | `_evaluate`, entry branch               |
| `exit_rule` / `invalidation_rule`| `_evaluate`, exit branch (same event)   |
| `liquidity_rule`                 | `_liquidity`                            |
| Data-quality and missing-value   | `_data_quality`                         |
| `execution_convention`           | Not here. See the note below.           |
| Signal classification            | `_classify`                             |
| `evidence_fields`                | `_evidence`                             |

The execution convention is deliberately absent from this module. The
specification says to "Evaluate the entry rule only after completed bar `t`"
and "Schedule execution for the open of the immediately following
chronological daily row, `t+1`". A strategy that reached forward to bar `t+1`
to price its own fill would be the exact look-ahead defect Section 16
forbids, so this module only ever schedules an `OrderIntent`. The executable-
bar checks, the cancelled entry, and the pending exit live in
`backend/app/quant/backtest/engine.py`, which advances to `t+1` before it
looks at it. `tests/quant/test_lookahead_adversarial.py` verifies that
evaluating at `t` never reads an index above `t`.

Version 1.1.0 adds `halt_exit_rule`. Empirical testing of version 1.0.0
against the 30 July 2026 snapshot found that carry-forward zero-volume bars
on a halted symbol freeze both SMAs, so no crossover, and therefore no exit,
is ever generated; two symbols out of 121 halted candidates (AMD, IBC) were
left holding an open long at the final bar with no order outstanding.
`halt_exit_rule` is the fix. Unlike the entry and exit orders above, a halt
exit's fill price is *not* look-ahead: the specification prices it at the
close of the most recent row with positive volume, which is a row at or
before `t`, or at the entry price as a documented fallback, both of which are
already known when `t` is evaluated. That is why `OrderIntent.immediate`
exists and why this module, uniquely for this one order type, is allowed to
set `fill_price`/`fill_date` itself rather than leaving them to the caller.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from . import numerics
from .protocol import ParameterSpec, StrategyMetadata
from .registry import register
from .types import (
    AsOfWindow,
    Criterion,
    InsufficientHistory,
    OrderIntent,
    OrderSide,
    OrderStatus,
    PositionState,
    SecurityView,
    Signal,
    StrategyError,
    StrategyEvaluation,
)

#: Fixed 20-session lookback for the liquidity rule. The specification lists
#: "20-bar liquidity lookback" among the values that are "fixed strategy
#: rules, not configurable parameters", so it is a module constant rather
#: than a parameter.
LIQUIDITY_LOOKBACK = 20

#: Ordered criterion names. Fixes `max_score` at six for every symbol and
#: every date, which is what makes the screener's deterministic ranking
#: comparable across the universe.
CRITERION_NAMES = (
    "warmup_pass",
    "data_quality_pass",
    "universe_pass",
    "signal_bar_volume_pass",
    "liquidity_pass",
    "bullish_crossover",
)

METADATA = StrategyMetadata(
    strategy_id="dual_sma_trend_crossover",
    version="1.1.0",
    title_vi="Giao cắt xu hướng hai đường SMA",
    title_en="Dual-SMA Trend Crossover",
    category="trend_following",
    # The specification writes the bar interval as `1d`. The frozen contract
    # types `timeframe` as an open string (contracts/OPEN_ITEMS.md, item A),
    # while the `Timeframe` enum used by `PriceBar` spells the same interval
    # `1D`. The approved specification's spelling is used verbatim here and
    # the discrepancy is raised as a contract-change proposal in the handoff
    # rather than silently normalized in either direction.
    timeframe="1d",
    required_fields=(
        "session_date",
        "open",
        "close",
        "volume",
        "quality_status",
        "security_master.symbol",
        "security_master.exchange",
        "security_master.security_type",
        "security_master.listing_status_as_of_date",
        "provenance.data_version",
        "provenance.source",
        "provenance.adjustment_status",
        "provenance.price_unit",
        "provenance.volume_unit",
    ),
    parameters=(
        ParameterSpec(
            name="fast_period",
            kind="integer",
            unit="bars",
            default=20,
            minimum=2,
            maximum=100,
            increment=1,
            constraint="Must be strictly less than slow_period.",
        ),
        ParameterSpec(
            name="slow_period",
            kind="integer",
            unit="bars",
            default=50,
            minimum=10,
            maximum=250,
            increment=1,
            constraint="Must be strictly greater than fast_period.",
        ),
        ParameterSpec(
            name="min_avg_volume_20",
            kind="integer",
            unit="shares per day",
            default=200_000,
            minimum=0,
            maximum=100_000_000,
            increment=10_000,
            constraint="Zero disables average-volume exclusion only.",
        ),
        ParameterSpec(
            name="halt_exit_sessions",
            kind="integer",
            unit="sessions",
            default=5,
            minimum=1,
            maximum=60,
            increment=1,
            constraint=(
                "Consecutive zero-volume sessions that force a full exit; also "
                "the number of consecutive positive-volume sessions required, "
                "with the security active again, before re-entry is permitted."
            ),
        ),
    ),
    entry_rule=(
        "Create a long entry order if and only if position_state[t] is flat, "
        "bullish_crossover[t] holds, and entry_eligible[t] holds. "
        "bullish_crossover[t] = sma_fast_t > sma_slow_t AND sma_fast_prev <= "
        "sma_slow_prev, on SMAs quantized to six decimal places with "
        "ROUND_HALF_EVEN. Equality on bar t is not bullish; equality on bar "
        "t-1 permits a crossover when the fast SMA becomes strictly greater "
        "on bar t. entry_eligible[t] = universe_pass AND signal_bar_volume_"
        "pass AND liquidity_pass AND data_quality_pass AND warmup_pass. A "
        "bullish crossover while already long is recorded as evidence and "
        "creates no order; pyramiding is prohibited."
    ),
    exit_rule=(
        "Create a full exit order if and only if position_state[t] is long "
        "and bearish_crossover[t] holds, where bearish_crossover[t] = "
        "sma_fast_t < sma_slow_t AND sma_fast_prev >= sma_slow_prev. "
        "Equality on bar t is not bearish. The average-volume threshold, the "
        "current-bar positive-volume gate, and the active-universe gate must "
        "not suppress an exit from an existing position. A bearish crossover "
        "while flat is recorded as evidence and creates no order. At most one "
        "exit order may exist per position: a further bearish crossover while "
        "an exit is already pending creates no duplicate order (signal=none), "
        "and a bullish crossover while an exit is pending creates no entry "
        "(signal=none, warnings contains "
        "bullish_crossover_suppressed_by_pending_exit). Added at version "
        "1.1.0: halt_exit_rule (below) supersedes any scheduled or pending "
        "exit order, which is then recorded order_status=cancelled, and takes "
        "precedence over bearish_crossover while long regardless of crossover "
        "state or data quality."
    ),
    invalidation_rule=(
        "invalidation_rule[t] = bearish_crossover[t] OR halt_exit[t]. The "
        "trend thesis is invalidated by the bearish crossover the exit rule "
        "uses, or, added at version 1.1.0, by halt_exit_rule: "
        "halt_exit[t] = (listing_status_as_of_date != 'active') OR "
        "(consecutive_zero_volume[t] >= halt_exit_sessions), where "
        "consecutive_zero_volume[t] is the count of consecutive chronological "
        "rows ending at t with volume == 0. While long, invalidation creates "
        "a full exit order; a halt exit fills at the close of the most recent "
        "row with volume > 0, or at the entry price with a "
        "halt_exit_no_executable_price warning when no such row exists. When "
        "listing_status_as_of_date is unavailable, the zero-volume-run "
        "condition alone governs, since missing status metadata must never "
        "leave a position open. A symbol that has triggered a halt exit is "
        "ineligible for re-entry until it records halt_exit_sessions "
        "consecutive positive-volume rows with the security active again. "
        "There is no separate percentage stop, ATR stop, time stop, or profit "
        "target; the halt exit is a tradability rule, not a risk stop."
    ),
    liquidity_rule=(
        "Entry requires volume[t] > 0 AND mean(volume[t-19] .. volume[t]) >= "
        "min_avg_volume_20, the signal bar included in the mean and zero-"
        "volume historical rows included and reducing it. The comparison is "
        "implemented as volume_sum_20[t] >= 20 * min_avg_volume_20, so "
        "equality passes and no floating-point division is involved. Setting "
        "min_avg_volume_20 to zero disables only the average-volume "
        "threshold; volume[t] > 0 remains mandatory. The liquidity rule "
        "applies to entries only and must never delay, cancel, or suppress "
        "an exit."
    ),
    execution_convention="next_open",
    evidence_fields=(
        "as_of_date",
        "signal",
        "position_state",
        "strategy_id",
        "strategy_version",
        "parameter_values",
        "close",
        "sma_fast_t",
        "sma_slow_t",
        "sma_fast_t_minus_1",
        "sma_slow_t_minus_1",
        "fast_minus_slow_t",
        "fast_minus_slow_t_minus_1",
        "volume_t",
        "volume_sum_20_t",
        "avg_volume_20_t",
        "min_avg_volume_20",
        "liquidity_pass",
        "signal_bar_volume_pass",
        "universe_pass",
        "data_quality_pass",
        "warmup_bars_required",
        "usable_bars_available",
        "bullish_crossover",
        "bearish_crossover",
        "entry_rule_pass",
        "exit_rule_pass",
        "invalidation_rule_pass",
        "halt_exit_pass",
        "consecutive_zero_volume_t",
        "halt_exit_sessions",
        "listing_status_as_of_date",
        "passed_criteria",
        "failed_criteria",
        "execution_convention",
        "order_status",
        "execution_date",
        "execution_price",
        "data_version",
        "adjustment_status",
        "warnings",
    ),
    reference=(
        "Reference type: owner_judgment. Owner judgment, user-approved VN "
        "Terminal Pro specification, 30 July 2026 "
        "(docs/strategy_catalogue.md, section 1), revised to 1.1.0 on 30 "
        "July 2026 to add halt_exit_rule, correct the exchange and "
        "security_type enumerations to match the frozen contract, and "
        "document the executability test as a fill-feasibility model. The "
        "AFL files 'BACKTEST - CHART TRADING WITH MA NEW.afl' and 'LOC CP - "
        "TRADING WITH MA NEW.afl' are contextual material only and are "
        "expressly non-governing for this strategy, so the Section 13.3 "
        "AmiBroker reconciliation does not apply to it."
    ),
    # "UPCoM" and "equity" are the frozen canonical contract's enumeration
    # values (contracts/schemas/models/security_master.py, price_bar.py).
    # Version 1.0.0 carried "UPCOM" and "ordinary_equity", which matched
    # nothing the data layer emits and made the screener return zero rows
    # with no error. Corrected at 1.1.0; see docs/strategy_catalogue.md
    # section 1, "Adopt the contract enumerations equity and UPCoM" in the
    # specification decision log.
    accepted_exchanges=frozenset({"HOSE", "HNX", "UPCoM"}),
    accepted_security_types=frozenset({"equity"}),
    accepted_trading_statuses=frozenset({"active"}),
    accepted_quality_statuses=frozenset({"valid"}),
    criterion_names=CRITERION_NAMES,
    notes=(
        "Long only. At most one open position per symbol; pyramiding "
        "prohibited. Position sizing, transaction costs, slippage, portfolio "
        "constraints, and benchmark selection are external backtester "
        "controls and must not alter signal dates. Added at version 1.1.0: "
        "a trading halt, suspension, or delisting forces a full exit "
        "(halt_exit_rule) rather than being held indefinitely, since "
        "carry-forward zero-volume bars freeze both SMAs and no crossover "
        "ever occurs."
    ),
)


@dataclass(frozen=True, slots=True)
class _WindowCheck:
    """Whether one required window is individually usable, and why not."""

    ok: bool
    reasons: tuple[str, ...] = ()


def _is_integral(value: float) -> bool:
    return float(value).is_integer()


def _finite(value: float) -> bool:
    return math.isfinite(value)


class DualSmaTrendCrossover:
    """Reference implementation of the approved specification."""

    metadata = METADATA

    def warmup_bars(self, parameters: Mapping[str, Any]) -> int:
        """`max(slow_period + 1, 20)`, verbatim from the specification.

        The extra row beyond `slow_period` is required because the crossover
        needs both `SMA_slow[t]` and `SMA_slow[t-1]`; the floor of twenty is
        required by the liquidity calculation.
        """

        return max(int(parameters["slow_period"]) + 1, LIQUIDITY_LOOKBACK)

    def validate_parameters(self, parameters: Mapping[str, Any]) -> None:
        fast = int(parameters["fast_period"])
        slow = int(parameters["slow_period"])
        if fast >= slow:
            raise StrategyError(
                "dual_sma_trend_crossover: fast_period must be strictly less than "
                f"slow_period; got fast_period={fast}, slow_period={slow}. The "
                "specification requires such configurations to be rejected before "
                "evaluation."
            )

    # ---------------------------------------------------------------- rules

    def _close_window_usable(
        self, window: AsOfWindow, count: int, ending_lag: int
    ) -> _WindowCheck:
        """Field constraints for one SMA window: quality and close values."""

        try:
            closes = window.closes(count, ending_lag=ending_lag)
            statuses = window.quality_statuses(count, ending_lag=ending_lag)
        except InsufficientHistory:
            return _WindowCheck(False, ("insufficient_rows",))
        reasons: list[str] = []
        if any(status not in self.metadata.accepted_quality_statuses for status in statuses):
            reasons.append("quality_status_not_valid")
        if any(not _finite(value) or value <= 0.0 for value in closes):
            reasons.append("close_not_finite_or_not_positive")
        return _WindowCheck(not reasons, tuple(reasons))

    def _volume_window_usable(self, window: AsOfWindow) -> _WindowCheck:
        try:
            volumes = window.volumes(LIQUIDITY_LOOKBACK)
            statuses = window.quality_statuses(LIQUIDITY_LOOKBACK)
        except InsufficientHistory:
            return _WindowCheck(False, ("insufficient_rows",))
        reasons: list[str] = []
        if any(status not in self.metadata.accepted_quality_statuses for status in statuses):
            reasons.append("quality_status_not_valid")
        if any(not _finite(value) or value < 0.0 for value in volumes):
            reasons.append("volume_not_finite_or_negative")
        if any(_finite(value) and not _is_integral(value) for value in volumes):
            reasons.append("volume_not_integral")
        return _WindowCheck(not reasons, tuple(reasons))

    def _quantized_sma(
        self, window: AsOfWindow, period: int, ending_lag: int
    ) -> Decimal:
        closes: Sequence[float] = window.closes(period, ending_lag=ending_lag)
        return numerics.mean_quantized(closes)

    # ---------------------------------------------------------- halt_exit_rule

    def _consecutive_zero_volume(self, window: AsOfWindow) -> int:
        """"consecutive_zero_volume[t] = count of consecutive chronological
        rows ending at t for which volume == 0", verbatim from the
        specification. Deliberately independent of quality_status: a halt
        exit must be reported "even when data_quality_pass[t] is false".
        """

        count = 0
        lag = 0
        while True:
            try:
                volume = window.volume(lag)
            except InsufficientHistory:
                break
            if volume != 0.0:
                break
            count += 1
            lag += 1
        return count

    def _last_positive_volume_fill(
        self, window: AsOfWindow
    ) -> tuple[float, date] | None:
        """The close of the most recent chronological row with volume > 0.

        Searches the whole available window, oldest bound at bar 0. Rule 2
        of `halt_exit_rule`: "the last price at which the position could
        genuinely have been sold". Returns None only when no such row exists
        anywhere in the available history, which triggers the entry-price
        fallback in rule 3.
        """

        lag = 0
        while True:
            try:
                volume = window.volume(lag)
            except InsufficientHistory:
                return None
            if _finite(volume) and volume > 0.0:
                return window.close(lag), window.trading_date(lag)
            lag += 1

    def _recovery_clear(self, window: AsOfWindow, halt_exit_sessions: int) -> bool:
        """No unfinished halt recovery blocks re-entry as of bar t.

        Rule 7: "A symbol that has triggered a halt exit is ineligible for
        re-entry until it records halt_exit_sessions consecutive rows with
        volume > 0 [...]". The strategy tracks no position history of its
        own, so this is derived purely from the window: walk back from t
        counting positive-volume rows. Reaching halt_exit_sessions of them
        means there is nothing to recover from (whether or not a halt ever
        occurred). Falling short, the row immediately before the incomplete
        run is inspected: only a genuine halt (a zero-volume run at least
        halt_exit_sessions long) blocks re-entry; an incidental shorter
        zero-volume row does not, so this never blocks an otherwise-liquid
        symbol over an ordinary data gap. Folded into `universe_pass`, which
        already carries the specification's "listing_status_as_of_date ==
        active" requirement, so both halves of rule 7 are enforced together.
        """

        lag = 0
        positive_run = 0
        while positive_run < halt_exit_sessions:
            try:
                volume = window.volume(lag)
            except InsufficientHistory:
                return True
            if _finite(volume) and volume > 0.0:
                positive_run += 1
                lag += 1
                continue
            zero_run = 0
            while True:
                try:
                    candidate = window.volume(lag)
                except InsufficientHistory:
                    break
                if candidate == 0.0:
                    zero_run += 1
                    lag += 1
                else:
                    break
            return zero_run < halt_exit_sessions
        return True

    # ------------------------------------------------------------- evaluate

    def evaluate(
        self,
        window: AsOfWindow,
        *,
        security: SecurityView | None,
        position_state: PositionState,
        parameters: Mapping[str, Any],
        exit_pending: bool = False,
        entry_price: float | None = None,
    ) -> StrategyEvaluation:
        fast = int(parameters["fast_period"])
        slow = int(parameters["slow_period"])
        threshold = int(parameters["min_avg_volume_20"])
        halt_exit_sessions = int(parameters["halt_exit_sessions"])
        required = self.warmup_bars(parameters)
        available = window.usable_bars
        warnings: list[str] = []

        # --- halt_exit_rule. Computed unconditionally, ahead of warm-up and
        # --- data quality, because both must be reported "even when
        # --- data_quality_pass[t] is false" and halt_exit takes precedence
        # --- over every other classification while long. Rule 6: when the
        # --- point-in-time listing status is unavailable, the zero-volume
        # --- run condition alone governs.
        consecutive_zero_volume_t = self._consecutive_zero_volume(window)
        listing_status_value = security.trading_status if security is not None else None
        halt_exit_condition = consecutive_zero_volume_t >= halt_exit_sessions or (
            security is not None and security.trading_status != "active"
        )

        warmup_pass = available >= required
        if not warmup_pass:
            if position_state is PositionState.LONG and halt_exit_condition:
                criteria = (
                    Criterion("warmup_pass", False, True, f"{available} of {required} rows"),
                    Criterion("data_quality_pass", False, False, "warm-up insufficient"),
                    Criterion("universe_pass", False, False, "warm-up insufficient"),
                    Criterion(
                        "signal_bar_volume_pass", False, False, "warm-up insufficient"
                    ),
                    Criterion("liquidity_pass", False, False, "warm-up insufficient"),
                    Criterion("bullish_crossover", False, False, "warm-up insufficient"),
                )
                return self._halt_exit(
                    window,
                    position_state=position_state,
                    parameters=parameters,
                    required=required,
                    available=available,
                    threshold=threshold,
                    consecutive_zero_volume_t=consecutive_zero_volume_t,
                    halt_exit_sessions=halt_exit_sessions,
                    listing_status_value=listing_status_value,
                    entry_price=entry_price,
                    criteria=criteria,
                    warnings=warnings,
                    close=window.close(0),
                    sma_fast_t=None,
                    sma_slow_t=None,
                    sma_fast_prev=None,
                    sma_slow_prev=None,
                    fast_minus_slow_t=None,
                    fast_minus_slow_prev=None,
                    volume_t=window.volume(0),
                    volume_sum_20=None,
                    avg_volume_20=None,
                    liquidity_pass=False,
                    signal_bar_volume_pass=False,
                    universe_pass=False,
                    data_quality_pass=False,
                    bullish=False,
                    bearish=False,
                )
            warnings.append(
                f"Insufficient warm-up: {required} chronological rows are required "
                f"through {window.as_of_date.isoformat()}, {available} are available."
            )
            return self._unavailable(
                window,
                position_state=position_state,
                parameters=parameters,
                required=required,
                available=available,
                warnings=warnings,
                threshold=threshold,
                consecutive_zero_volume_t=consecutive_zero_volume_t,
                halt_exit_sessions=halt_exit_sessions,
                listing_status_value=listing_status_value,
            )

        # --- data quality, per the specification's "Data-quality and
        # --- missing-value rule". Each required window is checked
        # --- individually so that a criterion whose own inputs are sound
        # --- stays computable even when another window is not.
        sma_windows = (
            self._close_window_usable(window, fast, 0),
            self._close_window_usable(window, fast, 1),
            self._close_window_usable(window, slow, 0),
            self._close_window_usable(window, slow, 1),
        )
        sma_ok = all(check.ok for check in sma_windows)
        volume_check = self._volume_window_usable(window)
        data_quality_pass = sma_ok and volume_check.ok
        if not data_quality_pass:
            reasons = sorted(
                {
                    reason
                    for check in (*sma_windows, volume_check)
                    for reason in check.reasons
                }
            )
            warnings.append(
                "Data-quality gate failed for "
                f"{window.as_of_date.isoformat()}: {', '.join(reasons)}. Values are "
                "never imputed; calculation resumes only after the invalid "
                "observation has left every required window."
            )

        # --- current-bar volume. Independent of the rolling windows, so it
        # --- stays computable when they are not.
        current_volume = window.volume(0)
        volume_computable = _finite(current_volume) and current_volume >= 0.0
        signal_bar_volume_pass = volume_computable and current_volume > 0.0
        if not volume_computable:
            warnings.append(
                "Invalid volume on the signal bar; the current-bar volume gate "
                "could not be evaluated."
            )

        # --- liquidity, as an integer-scale comparison so that equality
        # --- passes exactly, per the specification.
        volume_sum_20: int | None = None
        avg_volume_20: float | None = None
        if volume_check.ok:
            volume_sum_20 = sum(int(value) for value in window.volumes(LIQUIDITY_LOOKBACK))
            avg_volume_20 = volume_sum_20 / LIQUIDITY_LOOKBACK
            liquidity_pass = volume_sum_20 >= LIQUIDITY_LOOKBACK * threshold
        else:
            liquidity_pass = False

        # --- universe. A missing point-in-time classification cannot satisfy
        # --- an equality against an approved value, so the conjunction is
        # --- false. This is a determinate failure, not an indeterminate one:
        # --- the specification defines universe_pass as a conjunction of
        # --- equality tests, and it lists universe among the "computable
        # --- non-data entry gates" whose failure yields entry_blocked.
        if security is None:
            universe_pass = False
            warnings.append(
                "Point-in-time security classification unavailable; the universe "
                "gate cannot be satisfied. No status is inferred from file dates or "
                "last-bar dates."
            )
        else:
            universe_pass = security.matches(
                exchanges=self.metadata.accepted_exchanges,
                security_types=self.metadata.accepted_security_types,
                trading_statuses=self.metadata.accepted_trading_statuses,
            )
            if security.as_of_date != window.as_of_date:
                warnings.append(
                    "Security classification was resolved for "
                    f"{security.as_of_date.isoformat()} but the bar is dated "
                    f"{window.as_of_date.isoformat()}; the classification is not "
                    "point-in-time for this bar."
                )
            if not universe_pass and security.trading_status == "unknown":
                warnings.append(
                    "Security classification is 'unknown' because no authoritative "
                    "security master is available (see backend/app/data/HANDOFF.md, "
                    "limitation 1). The universe gate fails rather than assuming "
                    "an active equity."
                )

        # --- re-entry block (halt_exit_rule, rule 7), folded into
        # --- universe_pass because that criterion already carries the
        # --- specification's other re-entry condition, "listing_status_as_"
        # --- "of_date == active". A symbol that has triggered a halt exit
        # --- must not be re-entered until it records halt_exit_sessions
        # --- consecutive positive-volume rows; see `_recovery_clear`.
        if universe_pass and not self._recovery_clear(window, halt_exit_sessions):
            universe_pass = False
            warnings.append(
                "Re-entry blocked: fewer than halt_exit_sessions "
                f"({halt_exit_sessions}) consecutive positive-volume rows have "
                "been recorded since the most recent halt; the universe gate "
                "fails until the symbol recovers."
            )

        # --- crossover
        sma_fast_t: Decimal | None
        sma_slow_t: Decimal | None
        sma_fast_prev: Decimal | None
        sma_slow_prev: Decimal | None
        fast_minus_slow_t: Decimal | None
        fast_minus_slow_prev: Decimal | None
        if sma_ok:
            sma_fast_t = self._quantized_sma(window, fast, 0)
            sma_slow_t = self._quantized_sma(window, slow, 0)
            sma_fast_prev = self._quantized_sma(window, fast, 1)
            sma_slow_prev = self._quantized_sma(window, slow, 1)
            fast_minus_slow_t = numerics.difference_quantized(sma_fast_t, sma_slow_t)
            fast_minus_slow_prev = numerics.difference_quantized(
                sma_fast_prev, sma_slow_prev
            )
            bullish = sma_fast_t > sma_slow_t and sma_fast_prev <= sma_slow_prev
            bearish = sma_fast_t < sma_slow_t and sma_fast_prev >= sma_slow_prev
        else:
            sma_fast_t = sma_slow_t = sma_fast_prev = sma_slow_prev = None
            fast_minus_slow_t = fast_minus_slow_prev = None
            bullish = bearish = False

        entry_eligible = (
            universe_pass
            and signal_bar_volume_pass
            and liquidity_pass
            and data_quality_pass
            and warmup_pass
        )

        criteria = (
            Criterion("warmup_pass", True, True, f"{available} of {required} rows"),
            Criterion(
                "data_quality_pass",
                data_quality_pass,
                True,
                "all required windows valid" if data_quality_pass else "see warnings",
            ),
            Criterion(
                "universe_pass",
                universe_pass,
                True,
                "active equity on an approved exchange"
                if universe_pass
                else "classification missing, not an active equity, or still "
                "recovering from a halt",
            ),
            Criterion(
                "signal_bar_volume_pass",
                signal_bar_volume_pass,
                volume_computable,
                f"volume[t]={current_volume:g}" if volume_computable else "volume invalid",
            ),
            Criterion(
                "liquidity_pass",
                liquidity_pass,
                volume_check.ok,
                f"volume_sum_20={volume_sum_20} vs threshold "
                f"{LIQUIDITY_LOOKBACK * threshold}"
                if volume_check.ok
                else "20-bar volume window unusable",
            ),
            Criterion(
                "bullish_crossover",
                bullish,
                sma_ok,
                "fast crossed above slow" if bullish else "no bullish crossover",
            ),
        )

        if position_state is PositionState.LONG and halt_exit_condition:
            return self._halt_exit(
                window,
                position_state=position_state,
                parameters=parameters,
                required=required,
                available=available,
                threshold=threshold,
                consecutive_zero_volume_t=consecutive_zero_volume_t,
                halt_exit_sessions=halt_exit_sessions,
                listing_status_value=listing_status_value,
                entry_price=entry_price,
                criteria=criteria,
                warnings=warnings,
                close=window.close(0),
                sma_fast_t=sma_fast_t,
                sma_slow_t=sma_slow_t,
                sma_fast_prev=sma_fast_prev,
                sma_slow_prev=sma_slow_prev,
                fast_minus_slow_t=fast_minus_slow_t,
                fast_minus_slow_prev=fast_minus_slow_prev,
                volume_t=current_volume,
                volume_sum_20=volume_sum_20,
                avg_volume_20=avg_volume_20,
                liquidity_pass=liquidity_pass,
                signal_bar_volume_pass=signal_bar_volume_pass,
                universe_pass=universe_pass,
                data_quality_pass=data_quality_pass,
                bullish=bullish,
                bearish=bearish,
            )

        signal, order = self._classify(
            window=window,
            position_state=position_state,
            data_quality_pass=data_quality_pass,
            crossover_computable=sma_ok,
            bullish=bullish,
            bearish=bearish,
            entry_eligible=entry_eligible,
            exit_pending=exit_pending,
            warnings=warnings,
        )
        entry_rule_pass = signal is Signal.ENTRY
        exit_rule_pass = signal is Signal.EXIT
        invalidation_rule_pass = bool((sma_ok and bearish) or halt_exit_condition)

        evidence = self._evidence(
            window=window,
            parameters=parameters,
            signal=signal,
            position_state=position_state,
            required=required,
            available=available,
            close=window.close(0),
            sma_fast_t=sma_fast_t,
            sma_slow_t=sma_slow_t,
            sma_fast_prev=sma_fast_prev,
            sma_slow_prev=sma_slow_prev,
            fast_minus_slow_t=fast_minus_slow_t,
            fast_minus_slow_prev=fast_minus_slow_prev,
            volume_t=current_volume,
            volume_sum_20=volume_sum_20,
            avg_volume_20=avg_volume_20,
            threshold=threshold,
            liquidity_pass=liquidity_pass,
            signal_bar_volume_pass=signal_bar_volume_pass,
            universe_pass=universe_pass,
            data_quality_pass=data_quality_pass,
            bullish=bullish,
            bearish=bearish,
            entry_rule_pass=entry_rule_pass,
            exit_rule_pass=exit_rule_pass,
            invalidation_rule_pass=invalidation_rule_pass,
            halt_exit_pass=halt_exit_condition,
            consecutive_zero_volume_t=consecutive_zero_volume_t,
            halt_exit_sessions=halt_exit_sessions,
            listing_status_value=listing_status_value,
            criteria=criteria,
            order=order,
            warnings=warnings,
        )

        return StrategyEvaluation(
            symbol=window.symbol,
            as_of_date=window.as_of_date,
            strategy_id=METADATA.strategy_id,
            strategy_version=METADATA.version,
            signal=signal,
            position_state=position_state,
            order_status=OrderStatus.SCHEDULED if order else OrderStatus.NONE,
            criteria=criteria,
            evidence=evidence,
            warnings=tuple(warnings),
            order=order,
            data_version=window.data_version,
            # The specification states this strategy "has no separate
            # percentage stop, ATR stop, time stop, profit target, or
            # price-level invalidation rule", so the contract's `levels`
            # object is empty by rule rather than by omission.
            support=(),
            resistance=(),
            invalidation=None,
            parameters=dict(parameters),
        )

    # ------------------------------------------------------------- helpers

    def _classify(
        self,
        *,
        window: AsOfWindow,
        position_state: PositionState,
        data_quality_pass: bool,
        crossover_computable: bool,
        bullish: bool,
        bearish: bool,
        entry_eligible: bool,
        exit_pending: bool,
        warnings: list[str],
    ) -> tuple[Signal, OrderIntent | None]:
        """The specification's "Signal classification" table, in order.

        The ordering matters. `unavailable` is tested first because the
        specification requires that "`entry_blocked` must not be used when
        the crossover itself is indeterminate." `halt_exit` is not handled
        here: it takes precedence over every other classification while
        long, so `evaluate` intercepts it before this method is ever called.

        `exit_pending`, added at version 1.1.0, implements the "Order
        semantics while an exit is pending" subsection: at most one exit
        order may exist per position, so a further bearish crossover creates
        no duplicate order, and a bullish crossover while long still creates
        no entry but is now reported with a warning rather than silently.
        """

        if not data_quality_pass or not crossover_computable:
            return Signal.UNAVAILABLE, None
        if position_state is PositionState.FLAT and bullish:
            if entry_eligible:
                return (
                    Signal.ENTRY,
                    OrderIntent(
                        symbol=window.symbol,
                        side=OrderSide.BUY,
                        decision_date=window.as_of_date,
                        execution_convention=METADATA.execution_convention,
                        reason="bullish_crossover",
                    ),
                )
            return Signal.ENTRY_BLOCKED, None
        if position_state is PositionState.LONG:
            if bullish and exit_pending:
                warnings.append(
                    "bullish_crossover_suppressed_by_pending_exit: position_state "
                    "remains long with an exit order already pending, so no entry "
                    "was created."
                )
                return Signal.NONE, None
            if bearish:
                if exit_pending:
                    # "A further bearish_crossover while order_status ==
                    # 'pending_exit' must not create a duplicate order."
                    return Signal.NONE, None
                return (
                    Signal.EXIT,
                    OrderIntent(
                        symbol=window.symbol,
                        side=OrderSide.SELL,
                        decision_date=window.as_of_date,
                        execution_convention=METADATA.execution_convention,
                        reason="bearish_crossover",
                        full_exit=True,
                    ),
                )
        return Signal.NONE, None

    def _unavailable(
        self,
        window: AsOfWindow,
        *,
        position_state: PositionState,
        parameters: Mapping[str, Any],
        required: int,
        available: int,
        warnings: list[str],
        threshold: int,
        consecutive_zero_volume_t: int,
        halt_exit_sessions: int,
        listing_status_value: str | None,
    ) -> StrategyEvaluation:
        """Warm-up failure: nothing downstream of it is computable."""

        criteria = (
            Criterion("warmup_pass", False, True, f"{available} of {required} rows"),
            Criterion("data_quality_pass", False, False, "warm-up insufficient"),
            Criterion("universe_pass", False, False, "warm-up insufficient"),
            Criterion("signal_bar_volume_pass", False, False, "warm-up insufficient"),
            Criterion("liquidity_pass", False, False, "warm-up insufficient"),
            Criterion("bullish_crossover", False, False, "warm-up insufficient"),
        )
        evidence = self._evidence(
            window=window,
            parameters=parameters,
            signal=Signal.UNAVAILABLE,
            position_state=position_state,
            required=required,
            available=available,
            close=window.close(0),
            sma_fast_t=None,
            sma_slow_t=None,
            sma_fast_prev=None,
            sma_slow_prev=None,
            fast_minus_slow_t=None,
            fast_minus_slow_prev=None,
            volume_t=window.volume(0),
            volume_sum_20=None,
            avg_volume_20=None,
            threshold=threshold,
            liquidity_pass=False,
            signal_bar_volume_pass=False,
            universe_pass=False,
            data_quality_pass=False,
            bullish=False,
            bearish=False,
            entry_rule_pass=False,
            exit_rule_pass=False,
            invalidation_rule_pass=False,
            halt_exit_pass=False,
            consecutive_zero_volume_t=consecutive_zero_volume_t,
            halt_exit_sessions=halt_exit_sessions,
            listing_status_value=listing_status_value,
            criteria=criteria,
            order=None,
            warnings=warnings,
        )
        return StrategyEvaluation(
            symbol=window.symbol,
            as_of_date=window.as_of_date,
            strategy_id=METADATA.strategy_id,
            strategy_version=METADATA.version,
            signal=Signal.UNAVAILABLE,
            position_state=position_state,
            order_status=OrderStatus.NONE,
            criteria=criteria,
            evidence=evidence,
            warnings=tuple(warnings),
            order=None,
            data_version=window.data_version,
            parameters=dict(parameters),
        )

    def _halt_exit(
        self,
        window: AsOfWindow,
        *,
        position_state: PositionState,
        parameters: Mapping[str, Any],
        required: int,
        available: int,
        threshold: int,
        consecutive_zero_volume_t: int,
        halt_exit_sessions: int,
        listing_status_value: str | None,
        entry_price: float | None,
        criteria: tuple[Criterion, ...],
        warnings: list[str],
        close: float,
        sma_fast_t: Decimal | None,
        sma_slow_t: Decimal | None,
        sma_fast_prev: Decimal | None,
        sma_slow_prev: Decimal | None,
        fast_minus_slow_t: Decimal | None,
        fast_minus_slow_prev: Decimal | None,
        volume_t: float,
        volume_sum_20: int | None,
        avg_volume_20: float | None,
        liquidity_pass: bool,
        signal_bar_volume_pass: bool,
        universe_pass: bool,
        data_quality_pass: bool,
        bullish: bool,
        bearish: bool,
    ) -> StrategyEvaluation:
        """`halt_exit_rule`: an immediate full exit, while long, that takes

        precedence over every other classification regardless of crossover
        state or data quality. Reached only when `position_state` is `LONG`
        and `halt_exit[t]` is true; the caller (`evaluate`) decides that.
        """

        fill = self._last_positive_volume_fill(window)
        if fill is not None:
            fill_price, fill_date = fill
        else:
            warnings.append(
                "halt_exit_no_executable_price: no row with volume > 0 exists in "
                "the available history; the specification's fallback fills at "
                "the entry price."
            )
            fill_price = entry_price if entry_price is not None else close
            fill_date = window.as_of_date

        order = OrderIntent(
            symbol=window.symbol,
            side=OrderSide.SELL,
            decision_date=window.as_of_date,
            execution_convention=METADATA.execution_convention,
            reason="halt_exit",
            full_exit=True,
            immediate=True,
            fill_price=fill_price,
            fill_date=fill_date,
        )

        evidence = self._evidence(
            window=window,
            parameters=parameters,
            signal=Signal.HALT_EXIT,
            position_state=position_state,
            required=required,
            available=available,
            close=close,
            sma_fast_t=sma_fast_t,
            sma_slow_t=sma_slow_t,
            sma_fast_prev=sma_fast_prev,
            sma_slow_prev=sma_slow_prev,
            fast_minus_slow_t=fast_minus_slow_t,
            fast_minus_slow_prev=fast_minus_slow_prev,
            volume_t=volume_t,
            volume_sum_20=volume_sum_20,
            avg_volume_20=avg_volume_20,
            threshold=threshold,
            liquidity_pass=liquidity_pass,
            signal_bar_volume_pass=signal_bar_volume_pass,
            universe_pass=universe_pass,
            data_quality_pass=data_quality_pass,
            bullish=bullish,
            bearish=bearish,
            entry_rule_pass=False,
            exit_rule_pass=False,
            invalidation_rule_pass=True,
            halt_exit_pass=True,
            consecutive_zero_volume_t=consecutive_zero_volume_t,
            halt_exit_sessions=halt_exit_sessions,
            listing_status_value=listing_status_value,
            criteria=criteria,
            order=order,
            warnings=warnings,
            order_status_override=OrderStatus.EXECUTED,
            execution_date_override=fill_date.isoformat(),
            execution_price_override=fill_price,
        )

        return StrategyEvaluation(
            symbol=window.symbol,
            as_of_date=window.as_of_date,
            strategy_id=METADATA.strategy_id,
            strategy_version=METADATA.version,
            signal=Signal.HALT_EXIT,
            position_state=position_state,
            order_status=OrderStatus.EXECUTED,
            criteria=criteria,
            evidence=evidence,
            warnings=tuple(warnings),
            order=order,
            data_version=window.data_version,
            support=(),
            resistance=(),
            invalidation=None,
            parameters=dict(parameters),
        )

    def _evidence(self, **kwargs: Any) -> dict[str, Any]:
        """Every field the specification's `evidence_fields` section names.

        Quantized values appear twice: once as a JSON-native float under the
        specification's own field name, and once as an exact six-decimal
        string under `<name>_exact`. Comparisons upstream are performed on
        Decimals, so the float form cannot affect a signal; the string form
        exists so a consumer that needs the exact quantized value the
        specification mandates does not have to trust float rendering.
        """

        window: AsOfWindow = kwargs["window"]
        criteria = kwargs["criteria"]
        order: OrderIntent | None = kwargs["order"]

        def number(value: Decimal | None) -> float | None:
            return None if value is None else numerics.as_float(value)

        def exact(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        evidence: dict[str, Any] = {
            "as_of_date": window.as_of_date.isoformat(),
            "signal": kwargs["signal"].value,
            "position_state": kwargs["position_state"].value,
            "strategy_id": METADATA.strategy_id,
            "strategy_version": METADATA.version,
            "parameter_values": dict(kwargs["parameters"]),
            "close": kwargs["close"],
            "sma_fast_t": number(kwargs["sma_fast_t"]),
            "sma_slow_t": number(kwargs["sma_slow_t"]),
            "sma_fast_t_minus_1": number(kwargs["sma_fast_prev"]),
            "sma_slow_t_minus_1": number(kwargs["sma_slow_prev"]),
            "fast_minus_slow_t": number(kwargs["fast_minus_slow_t"]),
            "fast_minus_slow_t_minus_1": number(kwargs["fast_minus_slow_prev"]),
            "sma_fast_t_exact": exact(kwargs["sma_fast_t"]),
            "sma_slow_t_exact": exact(kwargs["sma_slow_t"]),
            "sma_fast_t_minus_1_exact": exact(kwargs["sma_fast_prev"]),
            "sma_slow_t_minus_1_exact": exact(kwargs["sma_slow_prev"]),
            "fast_minus_slow_t_exact": exact(kwargs["fast_minus_slow_t"]),
            "fast_minus_slow_t_minus_1_exact": exact(kwargs["fast_minus_slow_prev"]),
            "volume_t": kwargs["volume_t"],
            "volume_sum_20_t": kwargs["volume_sum_20"],
            "avg_volume_20_t": kwargs["avg_volume_20"],
            "min_avg_volume_20": kwargs["threshold"],
            "liquidity_pass": kwargs["liquidity_pass"],
            "signal_bar_volume_pass": kwargs["signal_bar_volume_pass"],
            "universe_pass": kwargs["universe_pass"],
            "data_quality_pass": kwargs["data_quality_pass"],
            "warmup_bars_required": kwargs["required"],
            "usable_bars_available": kwargs["available"],
            "bullish_crossover": kwargs["bullish"],
            "bearish_crossover": kwargs["bearish"],
            "entry_rule_pass": kwargs["entry_rule_pass"],
            "exit_rule_pass": kwargs["exit_rule_pass"],
            "invalidation_rule_pass": kwargs["invalidation_rule_pass"],
            "halt_exit_pass": kwargs["halt_exit_pass"],
            "consecutive_zero_volume_t": kwargs["consecutive_zero_volume_t"],
            "halt_exit_sessions": kwargs["halt_exit_sessions"],
            "listing_status_as_of_date": kwargs["listing_status_value"],
            "passed_criteria": [
                item.name for item in criteria if item.computable and item.passed
            ],
            "failed_criteria": [
                item.name for item in criteria if item.computable and not item.passed
            ],
            "execution_convention": METADATA.execution_convention,
            "order_status": (
                kwargs["order_status_override"].value
                if kwargs.get("order_status_override") is not None
                else (OrderStatus.SCHEDULED.value if order else OrderStatus.NONE.value)
            ),
            # A live scheduled order has not executed, so both are null. The
            # backtester overwrites them when it fills the order. The one
            # exception is a halt exit (`order_status_override=EXECUTED`),
            # whose fill price is already-known information, not a look-ahead;
            # see the `OrderIntent.immediate` docstring in types.py.
            "execution_date": kwargs.get("execution_date_override"),
            "execution_price": kwargs.get("execution_price_override"),
            "data_version": window.data_version,
            "adjustment_status": window.adjustment_status,
            "price_unit": window.price_unit,
            "volume_unit": window.volume_unit,
            "warnings": list(kwargs["warnings"]),
        }
        missing = [name for name in METADATA.evidence_fields if name not in evidence]
        if missing:  # pragma: no cover - guarded by test_strategy_metadata.py
            raise StrategyError(
                f"dual_sma_trend_crossover declared evidence fields {missing} but did "
                "not populate them."
            )
        return evidence


STRATEGY = register(DualSmaTrendCrossover())
