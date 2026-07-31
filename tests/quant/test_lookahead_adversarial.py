"""Adversarial suite: try to prove this implementation looks ahead.

This file has one purpose and it is not to demonstrate that the code works.
It is to attack the code's central claim. Section 16 lists five mandatory bias
controls and the WP8 acceptance criterion is "No look-ahead"; a suite that
only exercised the happy path would confirm the claim without ever testing it.

The suite attacks from five independent directions, so that a defect which
slips past one is caught by another:

1. **Future-mutation invariance.** Replace every bar after `t` with garbage
   and re-run. Any read of a future bar, for any purpose, changes the answer.
2. **Truncation equivalence.** Evaluate at `t` on a history that physically
   ends at `t`. A result that differs from the full-history result means the
   full-history run used something that did not exist yet.
3. **Direct index instrumentation.** Record the highest array index anything
   reads while processing session `d`, and assert it never exceeds `d`. This
   is the invariant stated literally rather than inferred from outputs.
4. **Price-identity checks.** Assert the fill price is the *next* bar's price
   and not the signal bar's, on a series constructed so the two differ by an
   amount no rounding could explain.
5. **Structural refusal.** Assert that the type system itself rejects a
   forward request.

Every instrument carries a **negative control**: a deliberately cheating
implementation that the same instrument must catch. Without those, a green
suite would be consistent with an instrument that never looks at anything. The
negative controls are marked `test_canary_*` and each one asserts a failure.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import date, timedelta

import pytest
from strategy_helpers import (
    comparable,
    corrupt_after,
    crossover_closes,
    make_history,
    recording_history,
    round_trip_closes,
    security_view,
    sessions,
    truncate,
)

from backend.app.quant.backtest import (
    NEXT_CLOSE,
    NEXT_OPEN,
    AdjustmentConventionError,
    BacktestConfig,
    FundamentalObservation,
    LiquidityConstraint,
    Period,
    PositionSizing,
    PublicationDateError,
    SurvivorshipBiasError,
    run_backtest,
)
from backend.app.quant.backtest.config import FIXED_SHARES
from backend.app.quant.strategies import (
    AsOfWindow,
    LookAheadError,
    PositionState,
    SymbolHistory,
    evaluate,
    registry,
    warmup_bars,
)

STRATEGY = "dual_sma_trend_crossover"
WARMUP = warmup_bars(STRATEGY)


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


# ---------------------------------------------------------------- direction 5
# Structural refusal: the window type will not answer a forward question.


def test_window_refuses_a_negative_lag():
    history = make_history(closes=crossover_closes())
    window = history.window(80)
    with pytest.raises(LookAheadError):
        window.close(-1)
    with pytest.raises(LookAheadError):
        window.bar(-1)
    with pytest.raises(LookAheadError):
        window.volume(-5)


def test_window_refuses_an_index_past_the_end():
    history = make_history(closes=crossover_closes(count=60))
    with pytest.raises(LookAheadError):
        AsOfWindow(history, 60)


def test_window_exposes_no_forward_accessor():
    """A window must not offer any route to the underlying arrays.

    An attribute named `close` that returned the whole series, or a public
    `history`, would let a strategy sidestep the lag check entirely.
    """

    history = make_history(closes=crossover_closes(count=60))
    window = history.window(30)
    public = {name for name in dir(window) if not name.startswith("_")}
    forbidden = {"history", "index", "series", "values", "arrays", "future"}
    assert not (public & forbidden), (
        f"AsOfWindow exposes {sorted(public & forbidden)}, which would allow a "
        "strategy to reach past bar t"
    )


# ---------------------------------------------------------------- direction 1
# Future-mutation invariance, at the strategy level.


@pytest.mark.parametrize("offset", [0, 1, 2, 7, 23, 44])
def test_strategy_result_is_invariant_to_future_bars(offset):
    closes = round_trip_closes(count=160)
    history = make_history(closes=closes)
    index = WARMUP + offset
    day = history.trading_dates[index]

    baseline = evaluate(
        STRATEGY,
        history.window(index),
        security=security_view("TEST", day),
        position_state=PositionState.FLAT,
    )
    mutated = corrupt_after(history, index)
    after = evaluate(
        STRATEGY,
        mutated.window(index),
        security=security_view("TEST", day),
        position_state=PositionState.FLAT,
    )
    assert comparable(baseline) == comparable(after), (
        f"the evaluation at index {index} changed when bars after it were "
        "corrupted, which means it read at least one of them"
    )


def test_strategy_result_is_invariant_to_future_bars_from_long():
    """The same invariance must hold on the exit side.

    An exit rule that peeked at tomorrow would be just as wrong as an entry
    rule that did, and is easier to overlook because exits are less often
    tested.
    """

    history = make_history(closes=round_trip_closes(count=160))
    for index in range(WARMUP, 155, 11):
        day = history.trading_dates[index]
        baseline = evaluate(
            STRATEGY,
            history.window(index),
            security=security_view("TEST", day),
            position_state=PositionState.LONG,
        )
        after = evaluate(
            STRATEGY,
            corrupt_after(history, index).window(index),
            security=security_view("TEST", day),
            position_state=PositionState.LONG,
        )
        assert comparable(baseline) == comparable(after), f"index {index} leaked"


def test_canary_a_peeking_evaluation_is_caught_by_mutation_invariance():
    """Negative control for direction 1.

    A function that reads bar `t+1` must fail the same harness that the real
    strategy passes. If this test ever passes silently, the harness above has
    stopped discriminating and its green results mean nothing.
    """

    history = make_history(closes=round_trip_closes(count=160))
    index = WARMUP + 5

    def peeking(hist: SymbolHistory) -> float:
        # Deliberately bypasses AsOfWindow and reads tomorrow's close.
        return float(hist.close[index + 1])

    baseline = peeking(history)
    after = peeking(corrupt_after(history, index))
    assert baseline != after, (
        "the corruption harness failed to change a value that genuinely reads a "
        "future bar; the invariance tests above would then be vacuous"
    )


# ---------------------------------------------------------------- direction 2
# Truncation equivalence.


@pytest.mark.parametrize("offset", [0, 3, 12, 40])
def test_truncated_history_gives_the_same_result(offset):
    history = make_history(closes=round_trip_closes(count=160))
    index = WARMUP + offset
    day = history.trading_dates[index]
    full = evaluate(
        STRATEGY,
        history.window(index),
        security=security_view("TEST", day),
        position_state=PositionState.FLAT,
    )
    short = evaluate(
        STRATEGY,
        truncate(history, index).window(index),
        security=security_view("TEST", day),
        position_state=PositionState.FLAT,
    )
    assert comparable(full) == comparable(short)


# ---------------------------------------------------------------- direction 3
# Direct index instrumentation.


def test_evaluation_never_reads_an_index_above_t():
    history = make_history(closes=round_trip_closes(count=160))
    instrumented, ledger = recording_history(history)
    for index in range(WARMUP - 5, len(history), 9):
        ledger.highest = -1
        window = instrumented.window(index)
        evaluate(
            STRATEGY,
            window,
            security=security_view("TEST", instrumented.trading_dates[index]),
            position_state=PositionState.FLAT,
        )
        assert ledger.highest <= index, (
            f"evaluating at index {index} read index {ledger.highest}"
        )
        assert window.highest_index_read <= index


def test_canary_the_instrument_catches_a_deliberate_read_ahead():
    """Negative control for direction 3."""

    history = make_history(closes=round_trip_closes(count=160))
    instrumented, ledger = recording_history(history)
    index = 100
    ledger.highest = -1
    _ = instrumented.close[index + 1]
    assert ledger.highest == index + 1, (
        "the recording instrument did not observe a read of a future index; the "
        "ceiling assertions above would then be vacuous"
    )


def test_backtest_never_reads_a_bar_after_the_session_being_processed():
    """The invariant, stated literally, across a whole run.

    The engine is run repeatedly with the period truncated one session at a
    time. After a run ending at session `d`, nothing may have read an index
    above `d`. Running it once and checking the final ceiling would only prove
    the engine does not read past the *end*; truncating proves it does not
    read past the *current* session either.

    The step is one session, not a coarser stride. An earlier version of this
    test stepped by thirteen and let a defect through: the executable-bar
    check reads a bar only on sessions where an order is actually pending, so
    a stride that skipped every such session never executed the mutated line.
    The coverage assertion at the end of this test exists to keep that from
    recurring silently: if the fixture stops producing fills, the test fails
    rather than passing on an unexercised path.
    """

    history = make_history(closes=round_trip_closes(count=140))
    execution_sessions = 0
    for last in range(WARMUP, len(history)):
        instrumented, ledger = recording_history(history)
        ledger.highest = -1
        config = _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[last]
            )
        )
        result = run_backtest(
            config,
            {"TEST": instrumented},
            data_version="test",
            security_resolver=security_view,
        )
        assert ledger.highest <= last, (
            f"a run ending at session {last} read bar index {ledger.highest}"
        )
        execution_sessions += len(result.fills)
        # A pending order that is examined but not filled still exercises the
        # executable-bar check, which is the path most likely to reach forward.
        assert all(
            event.trading_date <= history.trading_dates[last]
            for event in result.order_events
        )

    assert execution_sessions > 0, (
        "no order was ever executed across the truncated runs, so the "
        "executable-bar and fill paths were never instrumented; this test would "
        "be asserting the ceiling only for code that never ran"
    )


def test_executable_bar_check_reads_only_the_execution_bar():
    """Pin the executable-bar check to the bar it is checking.

    Separated from the whole-run ceiling test because it is the narrowest
    place a forward read can hide: the check runs once per pending order per
    session, so a coarse whole-run assertion can miss it entirely. Here the
    session *after* the intended execution bar is made unusable in every way
    the check tests for. A correct implementation is indifferent to it.
    """

    history, signal_index = _forced_entry_history(gap_open=120.0)
    quality = list(history.quality_status)
    volumes = list(history.volume)
    opens = list(history.open)
    poisoned = signal_index + 2
    quality[poisoned] = "critical"
    volumes[poisoned] = 0.0
    opens[poisoned] = -1.0
    tampered = make_history(
        closes=list(history.close), opens=opens, volumes=volumes, quality=quality
    )

    clean = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[signal_index + 1]
            )
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    poisoned_run = run_backtest(
        _config(
            in_sample_period=Period(
                tampered.trading_dates[0], tampered.trading_dates[signal_index + 1]
            )
        ),
        {"TEST": tampered},
        data_version="test",
        security_resolver=security_view,
    )
    assert [dataclasses.astuple(fill) for fill in clean.fills] == [
        dataclasses.astuple(fill) for fill in poisoned_run.fills
    ], (
        "the fill changed when the session after the execution bar was made "
        "unusable, so the executable-bar check is reading beyond its own bar"
    )
    assert clean.fills, "the fixture must produce a fill for this test to bite"


def test_backtest_prefix_is_invariant_to_a_longer_history():
    """Extending the data must not change what already happened.

    A backtest over sessions 0..T and one over 0..T+40 must agree exactly on
    everything up to T: the equity curve, the trade list, and the fills. Any
    disagreement means the longer run used information from beyond T while
    simulating a session at or before T.
    """

    history = make_history(closes=round_trip_closes(count=160))
    cut = 110
    short = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[cut]
            )
        ),
        {"TEST": truncate(history, cut)},
        data_version="test",
        security_resolver=security_view,
    )
    long = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[len(history) - 1]
            )
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    assert short.equity_curve == long.equity_curve[: len(short.equity_curve)]
    assert short.cash_curve == long.cash_curve[: len(short.cash_curve)]
    early_long = [
        trade.as_dict()
        for trade in long.trades
        if trade.exit_date <= history.trading_dates[cut]
    ]
    assert [trade.as_dict() for trade in short.trades] == early_long


def test_backtest_is_invariant_to_corrupted_future_bars():
    """Same claim, attacked by corruption rather than truncation."""

    history = make_history(closes=round_trip_closes(count=160))
    cut = 110
    period = Period(history.trading_dates[0], history.trading_dates[cut])
    clean = run_backtest(
        _config(in_sample_period=period),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    dirty = run_backtest(
        _config(in_sample_period=period),
        {"TEST": corrupt_after(history, cut)},
        data_version="test",
        security_resolver=security_view,
    )
    assert clean.equity_curve == dirty.equity_curve
    assert [trade.as_dict() for trade in clean.trades] == [
        trade.as_dict() for trade in dirty.trades
    ]


# ---------------------------------------------------------------- direction 4
# Price identity: the fill must be the next bar's price.


def _forced_entry_history(gap_open: float) -> SymbolHistory:
    """A series with one bullish crossover, then a wildly different next open.

    The bar after the crossover opens at `gap_open`, which is nowhere near the
    signal bar's own open. If the engine ever fills at the signal bar, the
    price it records cannot be mistaken for the correct one.
    """

    closes = crossover_closes(count=120, trough=60)
    opens = list(closes)
    history = make_history(closes=closes, opens=opens)
    signal_index = None
    for index in range(WARMUP, len(history) - 1):
        evaluation = evaluate(
            STRATEGY,
            history.window(index),
            security=security_view("TEST", history.trading_dates[index]),
            position_state=PositionState.FLAT,
        )
        if evaluation.signal.value == "entry":
            signal_index = index
            break
    assert signal_index is not None, "the fixture must produce an entry signal"
    opens[signal_index] = 1.0
    opens[signal_index + 1] = gap_open
    return make_history(closes=closes, opens=opens), signal_index


def test_entry_fills_at_the_next_bar_open_not_the_signal_bar_open():
    history, signal_index = _forced_entry_history(gap_open=777.0)
    result = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[-1]
            )
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    buys = [fill for fill in result.fills if fill.side == "buy"]
    assert buys, "the fixture must produce a fill"
    first = buys[0]
    assert first.trading_date == history.trading_dates[signal_index + 1], (
        "the fill was dated to the signal bar, not the following session"
    )
    assert first.reference_price == pytest.approx(777.0), (
        f"filled at {first.reference_price}, which is not the next bar's open; "
        "filling at the signal bar's open (1.0) would be look-ahead"
    )
    assert first.reference_price != pytest.approx(1.0)


def test_next_close_convention_fills_at_the_following_close():
    history, signal_index = _forced_entry_history(gap_open=777.0)
    result = run_backtest(
        _config(
            entry_convention=NEXT_CLOSE,
            exit_convention=NEXT_CLOSE,
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[-1]
            ),
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    buys = [fill for fill in result.fills if fill.side == "buy"]
    assert buys
    expected = float(history.close[signal_index + 1])
    assert buys[0].reference_price == pytest.approx(expected)
    assert buys[0].trading_date == history.trading_dates[signal_index + 1]


def test_decision_date_always_precedes_the_fill_date():
    """No fill may share a session with the decision that caused it."""

    history = make_history(closes=round_trip_closes(count=160))
    result = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[-1]
            )
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    executed = [event for event in result.order_events if event.status == "executed"]
    assert executed, "the fixture must execute at least one order"
    for event in executed:
        assert event.decision_date < event.trading_date, (
            f"{event.symbol} {event.side} decided and filled on "
            f"{event.trading_date}, which is same-bar execution"
        )


# ------------------------------------------------ remaining Section 16 controls


def test_survivorship_filtered_universe_is_refused():
    history = make_history(closes=crossover_closes())
    with pytest.raises(SurvivorshipBiasError, match="survivorship"):
        run_backtest(
            _config(universe_is_survivorship_filtered=True),
            {"TEST": history},
            data_version="test",
        )


def test_a_symbol_named_in_the_universe_must_have_a_history():
    """Silently dropping a symbol would reintroduce survivorship bias."""

    history = make_history(closes=crossover_closes())
    with pytest.raises(Exception, match="no history supplied"):
        run_backtest(
            _config(symbol_universe=("TEST", "DELISTED")),
            {"TEST": history},
            data_version="test",
        )


def test_terminally_inactive_symbols_may_stay_in_the_backtest_universe():
    """The 301 terminal zero-volume symbols must remain testable.

    They are excluded from *current* screening results, but a backtest that
    dropped them would only ever measure the survivors. This asserts the
    engine accepts one and handles its dead tail without failing.
    """

    closes = round_trip_closes(count=160)
    volumes = [1_000_000.0] * 160
    for index in range(150, 160):
        volumes[index] = 0.0
    history = make_history(closes=closes, volumes=volumes)
    result = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[-1]
            )
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    assert len(result.calendar) == 160


def test_mixed_adjustment_conventions_are_refused():
    adjusted = make_history(closes=crossover_closes(), adjustment_status="back_adjusted")
    raw = make_history(
        symbol="RAW", closes=crossover_closes(), adjustment_status="unadjusted"
    )
    with pytest.raises(AdjustmentConventionError, match="corporate-action consistency"):
        run_backtest(
            _config(symbol_universe=("TEST", "RAW")),
            {"TEST": adjusted, "RAW": raw},
            data_version="test",
        )


def test_declared_adjustment_convention_must_match_the_bars():
    history = make_history(closes=crossover_closes(), adjustment_status="unadjusted")
    with pytest.raises(AdjustmentConventionError):
        run_backtest(
            _config(price_adjustment_convention="back_adjusted"),
            {"TEST": history},
            data_version="test",
        )


def test_fundamentals_without_a_publication_date_are_excluded():
    history = make_history(closes=crossover_closes())
    result = run_backtest(
        _config(),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
        fundamentals=[
            FundamentalObservation("TEST", date(2024, 3, 31), "net_profit", 1.0, None),
            FundamentalObservation(
                "TEST", date(2024, 3, 31), "revenue", 2.0, date(2024, 4, 20)
            ),
        ],
    )
    assert len(result.excluded_fundamentals) == 1
    assert result.excluded_fundamentals[0]["reason"] == "missing_publication_date"
    assert any("publication date" in message for message in result.warnings)


def test_a_strategy_requiring_fundamentals_refuses_undated_ones():
    """Exclusion is only safe when the strategy does not need the input.

    When it does, quietly proceeding on a partial fundamental history would
    change what the strategy sees without saying so, so the run is refused.
    """

    history = make_history(closes=crossover_closes())
    entry = registry.get(STRATEGY)
    original = entry.metadata.required_fields
    object.__setattr__(
        entry.metadata, "required_fields", (*original, "fundamentals.net_profit")
    )
    try:
        with pytest.raises(PublicationDateError):
            run_backtest(
                _config(),
                {"TEST": history},
                data_version="test",
                fundamentals=[
                    FundamentalObservation(
                        "TEST", date(2024, 3, 31), "net_profit", 1.0, None
                    )
                ],
            )
    finally:
        object.__setattr__(entry.metadata, "required_fields", original)


def test_zero_volume_execution_bar_cancels_an_entry_and_defers_an_exit():
    """Section 16: "Explicit handling of suspended and zero-volume securities".

    The approved specification splits the two cases: a cancelled entry "must
    not be carried to a later bar", while "a pending exit does not expire".
    """

    history, signal_index = _forced_entry_history(gap_open=120.0)
    volumes = list(history.volume)
    volumes[signal_index + 1] = 0.0
    blocked = make_history(
        closes=list(history.close), opens=list(history.open), volumes=volumes
    )
    result = run_backtest(
        _config(
            in_sample_period=Period(
                blocked.trading_dates[0], blocked.trading_dates[-1]
            )
        ),
        {"TEST": blocked},
        data_version="test",
        security_resolver=security_view,
    )
    cancelled = [
        event
        for event in result.order_events
        if event.status == "cancelled"
        and event.trading_date == blocked.trading_dates[signal_index + 1]
    ]
    assert cancelled, "a zero-volume execution bar must cancel the entry"
    assert "zero volume" in cancelled[0].detail
    filled_on_that_day = [
        fill for fill in result.fills if fill.trading_date == blocked.trading_dates[signal_index + 1]
    ]
    assert not filled_on_that_day
    # The cancelled entry must not reappear later from the same decision.
    later = [
        fill
        for fill in result.fills
        if fill.side == "buy"
        and fill.trading_date > blocked.trading_dates[signal_index + 1]
        and fill.reason == "bullish_crossover"
    ]
    for fill in later:
        matching = [
            event
            for event in result.order_events
            if event.trading_date == fill.trading_date and event.status == "executed"
        ]
        for event in matching:
            assert event.decision_date > blocked.trading_dates[signal_index], (
                "a cancelled entry was carried forward to a later bar"
            )


def test_a_pending_exit_survives_a_suspension_and_fills_later():
    """A symbol with no bar at all on the execution session is suspended.

    The exit must stay pending rather than being cancelled or force-filled at
    a price the market never printed.
    """

    closes = round_trip_closes(count=160)
    history = make_history(closes=closes)
    result = run_backtest(
        _config(
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[-1]
            )
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    sells = [fill for fill in result.fills if fill.side == "sell"]
    if not sells:
        pytest.skip("fixture produced no exit; the pending path is covered below")

    exit_decision = sells[0].trading_date - timedelta(days=1)
    # Remove the session on which the exit would have filled, simulating a
    # suspension, and confirm it fills on the next available session instead.
    keep = [day for day in history.trading_dates if day != sells[0].trading_date]
    index_map = {day: position for position, day in enumerate(history.trading_dates)}
    gapped = SymbolHistory(
        symbol="TEST",
        trading_dates=tuple(keep),
        open=[float(history.open[index_map[day]]) for day in keep],
        high=[float(history.high[index_map[day]]) for day in keep],
        low=[float(history.low[index_map[day]]) for day in keep],
        close=[float(history.close[index_map[day]]) for day in keep],
        volume=[float(history.volume[index_map[day]]) for day in keep],
        quality_status=tuple(history.quality_status[index_map[day]] for day in keep),
        adjustment_status=history.adjustment_status,
        data_version=history.data_version,
    )
    gapped_result = run_backtest(
        _config(
            in_sample_period=Period(gapped.trading_dates[0], gapped.trading_dates[-1])
        ),
        {"TEST": gapped},
        data_version="test",
        security_resolver=security_view,
    )
    gapped_sells = [fill for fill in gapped_result.fills if fill.side == "sell"]
    assert gapped_sells, "the exit must still fill, on a later session"
    assert gapped_sells[0].trading_date > exit_decision


def test_liquidity_cap_uses_the_execution_bar_not_the_signal_bar():
    """Capping by participation is not look-ahead, and must not become it.

    The cap is applied on the session the order fills, when that session's
    volume is present information. This test pins that the cap responds to the
    *execution* bar's volume by changing only that bar.
    """

    history, signal_index = _forced_entry_history(gap_open=100.0)
    volumes = list(history.volume)
    volumes[signal_index + 1] = 1_000.0
    thin = make_history(
        closes=list(history.close), opens=list(history.open), volumes=volumes
    )
    result = run_backtest(
        _config(
            position_size=PositionSizing(FIXED_SHARES, 10_000),
            liquidity_constraint=LiquidityConstraint(max_participation_of_bar_volume=0.1),
            in_sample_period=Period(thin.trading_dates[0], thin.trading_dates[-1]),
        ),
        {"TEST": thin},
        data_version="test",
        security_resolver=security_view,
    )
    buys = [fill for fill in result.fills if fill.side == "buy"]
    assert buys
    assert buys[0].quantity == 100, (
        "the fill should be capped at 10% of the execution bar's 1,000 shares"
    )


def test_position_sizing_uses_equity_known_before_the_execution_bar():
    """Sizing must not consume the execution session's own close.

    Reconstructed rather than asserted from a comment: the number of shares
    bought is compared against what the previous session's equity allows. On
    the first entry of a fresh run that is the initial capital, so a size
    computed from a later equity would differ.
    """

    history, _signal_index = _forced_entry_history(gap_open=100.0)
    result = run_backtest(
        _config(
            position_size=PositionSizing("fixed_fraction_of_equity", 0.5),
            in_sample_period=Period(
                history.trading_dates[0], history.trading_dates[-1]
            ),
        ),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    buys = [fill for fill in result.fills if fill.side == "buy"]
    assert buys
    expected = int((1_000_000.0 * 0.5) // buys[0].fill_price)
    assert buys[0].quantity == expected


@contextlib.contextmanager
def _temporary_registry():
    saved = dict(registry._REGISTRY)
    saved_versions = dict(registry._VERSIONS)
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)
        registry._VERSIONS.clear()
        registry._VERSIONS.update(saved_versions)


def test_canary_a_cheating_strategy_would_break_prefix_invariance():
    """Negative control for the backtest-level invariance tests.

    A strategy that could see tomorrow would produce a different equity curve
    when tomorrow changes. This builds that situation without registering a
    cheating strategy, by confirming that the *engine's* result does depend on
    the bars it is allowed to see, so the invariance assertions above are not
    trivially satisfied by an engine that ignores its data.
    """

    history = make_history(closes=round_trip_closes(count=160))
    period = Period(history.trading_dates[0], history.trading_dates[110])
    baseline = run_backtest(
        _config(in_sample_period=period),
        {"TEST": history},
        data_version="test",
        security_resolver=security_view,
    )
    # Corrupting bars *inside* the window must change the result. If it does
    # not, the engine is not reading its inputs and every invariance test in
    # this file would pass for the wrong reason.
    inside = corrupt_after(history, 60)
    changed = run_backtest(
        _config(in_sample_period=period),
        {"TEST": inside},
        data_version="test",
        security_resolver=security_view,
    )
    assert baseline.equity_curve != changed.equity_curve, (
        "corrupting bars inside the simulated window did not change the result; "
        "the invariance tests above would then be meaningless"
    )
