"""Version 1.1.0 `halt_exit_rule`: the nine new edge-case rows, plus the two
empirical regressions the fix must hold under.

Rows 1-8 of the specification's "Deterministic edge-case requirements" table
are unchanged from version 1.0.0 and are tested in
`test_dual_sma_specification.py`. This file tests exactly the nine rows added
at version 1.1.0 (docs/strategy_catalogue.md, section 1), in table order:

    9.  Entry signal followed by an unexecutable next bar
    10. Exit signal followed by an unexecutable next bar
    11. Long, halt_exit_sessions consecutive zero-volume rows
    12. Long, listing_status_as_of_date leaves active
    13. Long, halted, listing_status_as_of_date unavailable
    14. Halt exit while an exit order is already pending
    15. Second bearish crossover while an exit is pending
    16. Bullish crossover while an exit is pending
    17. Halted symbol resumes trading (re-entry block)

Rows 9 and 10 restate the pre-existing next-bar-execution convention and are
included here because the specification's revised table lists them alongside
the new halt-exit rows; `test_lookahead_adversarial.py` already covers the
same mechanics from the bias-control angle.

Two more tests close the loop docs/pre_integration_fixes.md asks for: a
halted symbol must not remain open forever, and FPT (continuously traded,
never halted) must produce the same signal sequence it did at version 1.0.0.
"""

from __future__ import annotations

from helpers import load_fixture
from strategy_helpers import (
    load_baseline_dual_sma_v1_0_0,
    make_history,
    round_trip_closes,
    security_view,
    sessions,
)

from backend.app.quant.backtest import (
    NEXT_OPEN,
    BacktestConfig,
    LiquidityConstraint,
    Period,
    PositionSizing,
    run_backtest,
)
from backend.app.quant.backtest.config import FIXED_SHARES
from backend.app.quant.strategies import (
    OrderStatus,
    PositionState,
    SecurityView,
    Signal,
    SymbolHistory,
    evaluate,
    warmup_bars,
)

STRATEGY = "dual_sma_trend_crossover"
WARMUP = warmup_bars(STRATEGY)
HALT_EXIT_SESSIONS = 5  # the approved default


def _config(**overrides):
    defaults: dict = {
        "strategy_id": STRATEGY,
        "symbol_universe": ("TEST",),
        "entry_convention": NEXT_OPEN,
        "exit_convention": NEXT_OPEN,
        "transaction_cost_rate": 0.0,
        "slippage_rate": 0.0,
        "position_size": PositionSizing(FIXED_SHARES, 100),
        "max_concurrent_positions": 1,
        "liquidity_constraint": LiquidityConstraint(),
        "price_adjustment_convention": "back_adjusted",
        "benchmark": None,
        "in_sample_period": Period(sessions(1)[0], sessions(400)[-1]),
        "initial_capital": 1_000_000.0,
    }
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def _flat_then_step(step: float, count: int = 120) -> list[float]:
    """Closes that hold every SMA exactly equal, then move by `step`."""

    closes = [100.0] * (count - 1)
    closes.append(100.0 + step)
    return closes


def _walk_to_first_signal(history, signal, *, start_state=PositionState.FLAT):
    """The first index (>= warm-up) at which `evaluate` reports `signal`.

    A minimal position-tracking walk: FLAT until ENTRY, LONG until EXIT (or
    HALT_EXIT). Good enough to *locate* a decision bar in a synthetic fixture;
    it is not a backtester and is never used to assert fill mechanics.
    """

    state = start_state
    for index in range(WARMUP - 1, len(history)):
        result = evaluate(
            STRATEGY,
            history.window(index),
            security=security_view("TEST", history.trading_dates[index]),
            position_state=state,
        )
        if result.signal is signal:
            return index
        if result.signal is Signal.ENTRY:
            state = PositionState.LONG
        elif result.signal in (Signal.EXIT, Signal.HALT_EXIT):
            state = PositionState.FLAT
    return None


# ---------------------------------------------------------------- row 9, 10
# Restated from version 1.0.0's execution convention; see the module docstring.


def test_edge_entry_cancelled_on_unexecutable_next_bar_is_not_carried_forward():
    """Row 9: "Entry signal followed by an unexecutable next bar: Entry
    cancelled and not carried forward"."""

    closes = round_trip_closes(count=160)
    entry_index = _walk_to_first_signal(make_history(closes=closes), Signal.ENTRY)
    assert entry_index is not None

    volumes = [1_000_000.0] * len(closes)
    volumes[entry_index + 1] = 0.0  # the execution bar becomes unexecutable
    history = make_history(closes=closes, volumes=volumes)

    result = run_backtest(
        _config(
            in_sample_period=Period(history.trading_dates[0], history.trading_dates[-1])
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    decision_date = history.trading_dates[entry_index]
    cancelled = [
        event
        for event in result.order_events
        if event.side == "buy"
        and event.status == OrderStatus.CANCELLED.value
        and event.decision_date == decision_date
    ]
    assert cancelled, "the entry must be cancelled when its execution bar is unexecutable"
    executed_later = [
        event
        for event in result.order_events
        if event.side == "buy"
        and event.status == OrderStatus.EXECUTED.value
        and event.decision_date == decision_date
    ]
    assert not executed_later, "a cancelled entry must not be carried to a later bar"


def test_edge_exit_remains_pending_until_first_executable_bar():
    """Row 10: "Exit signal followed by an unexecutable next bar: Exit
    remains pending until the first executable bar"."""

    closes = round_trip_closes(count=200)
    exit_index = _walk_to_first_signal(make_history(closes=closes), Signal.EXIT)
    assert exit_index is not None

    volumes = [1_000_000.0] * len(closes)
    volumes[exit_index + 1] = 0.0  # deferred once
    history = make_history(closes=closes, volumes=volumes)

    result = run_backtest(
        _config(
            in_sample_period=Period(history.trading_dates[0], history.trading_dates[-1])
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    pending_day = history.trading_dates[exit_index + 1]
    executed_day = history.trading_dates[exit_index + 2]
    assert any(
        event.side == "sell"
        and event.status == OrderStatus.PENDING_EXIT.value
        and event.trading_date == pending_day
        for event in result.order_events
    )
    assert any(
        event.side == "sell"
        and event.status == OrderStatus.EXECUTED.value
        and event.trading_date == executed_day
        for event in result.order_events
    )
    assert len(result.trades) == 1
    assert result.trades[0].exit_date == executed_day


# --------------------------------------------------------------- row 11-13
# The halt-exit trigger itself.


def test_edge_halt_exit_fires_on_the_zero_volume_run_and_fills_at_the_last_trade():
    """Row 11: "Long, and the symbol records halt_exit_sessions consecutive
    zero-volume rows: signal = halt_exit; full exit filled at the close of
    the last positive-volume row"."""

    count = 120
    closes = [100.0 + 0.01 * index for index in range(count)]
    volumes = [1_000_000.0] * (count - HALT_EXIT_SESSIONS) + [0.0] * HALT_EXIT_SESSIONS
    history = make_history(closes=closes, volumes=volumes)
    last = count - 1

    result = evaluate(
        STRATEGY,
        history.window(last),
        security=security_view("TEST", history.trading_dates[last]),
        position_state=PositionState.LONG,
    )
    assert result.signal is Signal.HALT_EXIT
    assert result.evidence["halt_exit_pass"] is True
    assert result.evidence["consecutive_zero_volume_t"] == HALT_EXIT_SESSIONS
    assert result.order is not None
    assert result.order.reason == "halt_exit"
    assert result.order.full_exit is True
    assert result.order.immediate is True
    last_positive_index = count - HALT_EXIT_SESSIONS - 1
    assert result.order.fill_price == closes[last_positive_index]
    assert result.order.fill_date == history.trading_dates[last_positive_index]
    assert result.order_status is OrderStatus.EXECUTED
    assert result.evidence["execution_price"] == closes[last_positive_index]


def test_edge_halt_exit_fires_when_listing_status_leaves_active_even_with_volume():
    """Row 12: "Long, and listing_status_as_of_date leaves active: signal =
    halt_exit, even if volume is still positive"."""

    history = make_history(
        closes=round_trip_closes(count=120), volumes=[1_000_000.0] * 120
    )
    last = len(history) - 1
    suspended = SecurityView(
        "TEST", history.trading_dates[last], "HOSE", "equity", "suspended"
    )

    result = evaluate(
        STRATEGY,
        history.window(last),
        security=suspended,
        position_state=PositionState.LONG,
    )
    assert result.signal is Signal.HALT_EXIT
    assert result.evidence["consecutive_zero_volume_t"] == 0
    assert result.evidence["listing_status_as_of_date"] == "suspended"


def test_edge_unavailable_listing_status_leaves_the_zero_volume_run_governing():
    """Row 13: "Long, halted, and listing_status_as_of_date is unavailable:
    Zero-volume-run condition alone governs; the position must not remain
    open"."""

    count = 120
    closes = round_trip_closes(count=count)

    halted_volumes = [1_000_000.0] * (count - HALT_EXIT_SESSIONS) + [0.0] * HALT_EXIT_SESSIONS
    halted = make_history(closes=closes, volumes=halted_volumes)
    last = count - 1
    result = evaluate(
        STRATEGY,
        halted.window(last),
        security=None,
        position_state=PositionState.LONG,
    )
    assert result.signal is Signal.HALT_EXIT, (
        "missing listing-status metadata must never leave a position open when "
        "the zero-volume run alone already justifies a halt exit"
    )
    assert result.evidence["listing_status_as_of_date"] is None

    trading_volumes = [1_000_000.0] * count
    trading = make_history(closes=closes, volumes=trading_volumes)
    still_trading = evaluate(
        STRATEGY,
        trading.window(last),
        security=None,
        position_state=PositionState.LONG,
    )
    assert still_trading.signal is not Signal.HALT_EXIT, (
        "an unavailable listing status must not, by itself, trigger a halt exit"
    )


def test_halt_exit_falls_back_to_the_entry_price_with_a_warning():
    """Rule 3 of halt_exit_rule: fall back to the entry price, with
    halt_exit_no_executable_price, when no positive-volume row exists."""

    history = make_history(
        closes=round_trip_closes(count=120), volumes=[0.0] * 120
    )
    last = len(history) - 1
    result = evaluate(
        STRATEGY,
        history.window(last),
        security=security_view("TEST", history.trading_dates[last]),
        position_state=PositionState.LONG,
        entry_price=123.45,
    )
    assert result.signal is Signal.HALT_EXIT
    assert result.order.fill_price == 123.45
    assert any("halt_exit_no_executable_price" in warning for warning in result.warnings)


# --------------------------------------------------------- row 14-16 (pending)


def test_edge_halt_exit_supersedes_an_already_pending_exit():
    """Row 14: "Halt exit while an exit order is already pending: Pending
    order recorded as cancelled; halt exit recorded separately"."""

    count = 120
    closes = round_trip_closes(count=count)
    volumes = [1_000_000.0] * (count - HALT_EXIT_SESSIONS) + [0.0] * HALT_EXIT_SESSIONS
    history = make_history(closes=closes, volumes=volumes)
    last = count - 1

    result = evaluate(
        STRATEGY,
        history.window(last),
        security=security_view("TEST", history.trading_dates[last]),
        position_state=PositionState.LONG,
        exit_pending=True,
    )
    assert result.signal is Signal.HALT_EXIT, (
        "halt_exit_rule takes precedence over an already-pending exit"
    )
    assert result.order is not None
    assert result.order.reason == "halt_exit"


def test_engine_cancels_a_pending_exit_when_a_halt_exit_supersedes_it():
    """Row 14, engine-level: the superseded order is recorded cancelled and
    the halt exit is recorded separately, as two distinct order events."""

    count = 160
    closes = round_trip_closes(count=count)
    exit_index = _walk_to_first_signal(make_history(closes=closes), Signal.EXIT)
    assert exit_index is not None

    volumes = [1_000_000.0] * count
    # The exit's own execution bar is unexecutable, so the exit order is still
    # pending when the halt begins on the immediately following rows.
    for offset in range(1, 1 + HALT_EXIT_SESSIONS):
        volumes[exit_index + offset] = 0.0
    history = make_history(closes=closes, volumes=volumes)

    result = run_backtest(
        _config(
            in_sample_period=Period(history.trading_dates[0], history.trading_dates[-1])
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    cancelled_sells = [
        event
        for event in result.order_events
        if event.side == "sell" and event.status == OrderStatus.CANCELLED.value
    ]
    assert cancelled_sells, "the superseded exit order must be recorded as cancelled"
    halt_trades = [trade for trade in result.trades if trade.exit_reason == "halt_exit"]
    assert len(halt_trades) == 1
    assert not result.open_positions, "the position must not remain open through a halt"


def test_edge_second_bearish_crossover_while_pending_creates_no_duplicate_order():
    """Row 15: "Second bearish crossover while an exit is pending: No
    duplicate order; signal = none"."""

    history = make_history(closes=_flat_then_step(-40.0), volumes=[1_000_000.0] * 120)
    last = len(history) - 1
    result = evaluate(
        STRATEGY,
        history.window(last),
        security=security_view("TEST", history.trading_dates[last]),
        position_state=PositionState.LONG,
        exit_pending=True,
    )
    assert result.evidence["bearish_crossover"] is True
    assert result.signal is Signal.NONE
    assert result.order is None


def test_edge_bullish_crossover_while_pending_is_suppressed_with_a_warning():
    """Row 16: "Bullish crossover while an exit is pending: No entry; signal
    = none with a bullish_crossover_suppressed_by_pending_exit warning"."""

    history = make_history(closes=_flat_then_step(+40.0), volumes=[1_000_000.0] * 120)
    last = len(history) - 1
    result = evaluate(
        STRATEGY,
        history.window(last),
        security=security_view("TEST", history.trading_dates[last]),
        position_state=PositionState.LONG,
        exit_pending=True,
    )
    assert result.evidence["bullish_crossover"] is True
    assert result.signal is Signal.NONE
    assert result.order is None
    assert any(
        "bullish_crossover_suppressed_by_pending_exit" in warning
        for warning in result.warnings
    )


# ------------------------------------------------------------------- row 17


def test_edge_reentry_blocked_until_recovery_sessions_recorded():
    """Row 17: "Halted symbol resumes trading: Re-entry permitted only after
    halt_exit_sessions consecutive positive-volume rows and
    listing_status_as_of_date == active"."""

    closes = _flat_then_step(+40.0, count=120)

    # Fewer than halt_exit_sessions positive-volume rows since the halt ended.
    blocked_volumes = (
        [1_000_000.0] * 112 + [0.0] * HALT_EXIT_SESSIONS + [1_000_000.0] * 3
    )
    assert len(blocked_volumes) == 120
    blocked = make_history(closes=closes, volumes=blocked_volumes)
    blocked_result = evaluate(
        STRATEGY,
        blocked.window(119),
        security=security_view("TEST", blocked.trading_dates[119]),
        position_state=PositionState.FLAT,
    )
    assert blocked_result.evidence["bullish_crossover"] is True
    assert blocked_result.signal is Signal.ENTRY_BLOCKED
    assert blocked_result.evidence["universe_pass"] is False
    assert any("Re-entry blocked" in warning for warning in blocked_result.warnings)

    # At least halt_exit_sessions consecutive positive-volume rows recorded.
    recovered_volumes = (
        [1_000_000.0] * 107 + [0.0] * HALT_EXIT_SESSIONS + [1_000_000.0] * 8
    )
    assert len(recovered_volumes) == 120
    recovered = make_history(closes=closes, volumes=recovered_volumes)
    recovered_result = evaluate(
        STRATEGY,
        recovered.window(119),
        security=security_view("TEST", recovered.trading_dates[119]),
        position_state=PositionState.FLAT,
    )
    assert recovered_result.evidence["universe_pass"] is True
    assert recovered_result.signal is Signal.ENTRY


# ------------------------------------------------------ empirical regressions


def test_a_halted_symbol_with_an_open_position_closes_via_halt_exit():
    """docs/pre_integration_fixes.md: "Testing 121 halted symbols [...] left
    two of them [...] holding an open long at the final bar with no order
    outstanding." This is that scenario in miniature: a position enters
    normally, the symbol then goes permanently silent (a terminal
    zero-volume run, exactly the "carry-forward zero-volume bars" the
    module docstring describes), and the run must not end with the position
    still open.
    """

    closes = round_trip_closes(count=140)
    entry_index = _walk_to_first_signal(make_history(closes=closes), Signal.ENTRY)
    assert entry_index is not None

    # A terminal halt: volume drops to zero from shortly after entry through
    # the end of the available history, exactly the "carry-forward
    # zero-volume bars" defect scenario, with no subsequent bearish crossover
    # possible because the SMAs freeze.
    halt_start = entry_index + 3
    volumes = [1_000_000.0] * halt_start + [0.0] * (len(closes) - halt_start)
    history = make_history(closes=closes, volumes=volumes)

    result = run_backtest(
        _config(
            in_sample_period=Period(history.trading_dates[0], history.trading_dates[-1])
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    assert not result.open_positions, (
        "a halted symbol must not be left holding an open long with no order "
        "outstanding"
    )
    halt_trades = [trade for trade in result.trades if trade.exit_reason == "halt_exit"]
    assert len(halt_trades) == 1


def test_fpt_signal_sequence_is_unchanged_between_version_1_0_0_and_1_1_0():
    """docs/pre_integration_fixes.md: "leaving FPT's 80 signal events
    byte-identical." FPT never halts (no zero-volume row anywhere in its
    fixture) and is treated as a continuously active equity throughout, so
    halt_exit_rule's trigger is never true for it; the fix must therefore be
    a no-op on FPT's signal sequence.

    Compares the *current* registered strategy against the actual version
    1.0.0 source, loaded from the git history tagged before this fix
    (`strategy_helpers.load_baseline_dual_sma_v1_0_0`), rather than against a
    hand-copied expectation that could silently drift from what 1.0.0 really
    did.

    This isolates halt_exit_rule from defect 2 (the enumeration fix): each
    version is fed the security_type/exchange values *it* accepts
    ("ordinary_equity"/"UPCOM" for 1.0.0, "equity"/"UPCoM" for 1.1.0) so that
    both see an equally-eligible active equity throughout. Feeding both
    versions today's contract values would make 1.0.0 universe_pass fail on
    every bar, which is defect 2's own effect, not something this halt-exit
    regression is meant to isolate.
    """

    bars = load_fixture("bars_FPT.json")["bars"]
    assert not any(bar["volume"] == 0 for bar in bars), (
        "this regression only proves anything if FPT is genuinely never halted"
    )
    history = SymbolHistory.from_bars(bars, symbol="FPT", data_version="fdata-2026-07-30")

    def current_security(day):
        return SecurityView("FPT", day, "HOSE", "equity", "active")

    def baseline_security(day):
        return SecurityView("FPT", day, "HOSE", "ordinary_equity", "active")

    baseline = load_baseline_dual_sma_v1_0_0()
    current_state = PositionState.FLAT
    baseline_state = PositionState.FLAT
    current_signals: list[tuple[str, str]] = []
    baseline_signals: list[tuple[str, str]] = []

    for index in range(WARMUP - 1, len(history)):
        window = history.window(index)
        day = history.trading_dates[index]

        current = evaluate(
            STRATEGY,
            window,
            security=current_security(day),
            position_state=current_state,
        )
        current_signals.append((day.isoformat(), current.signal.value))
        if current.signal is Signal.ENTRY:
            current_state = PositionState.LONG
        elif current.signal in (Signal.EXIT, Signal.HALT_EXIT):
            current_state = PositionState.FLAT

        baseline_result = baseline.evaluate(
            history.window(index),
            security=baseline_security(day),
            position_state=baseline_state,
            parameters=baseline.metadata.defaults,
        )
        baseline_signals.append((day.isoformat(), baseline_result.signal.value))
        if baseline_result.signal.value == "entry":
            baseline_state = PositionState.LONG
        elif baseline_result.signal.value == "exit":
            baseline_state = PositionState.FLAT

    assert current_signals == baseline_signals, (
        "the halt_exit_rule fix must not change FPT's signal sequence, since "
        "FPT is never halted"
    )
    non_trivial = [
        pair for pair in current_signals if pair[1] not in ("none", "unavailable")
    ]
    assert non_trivial, "the fixture must exercise at least one non-trivial signal"
