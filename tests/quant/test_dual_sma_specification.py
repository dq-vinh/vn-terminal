"""Conformance of `dual_sma_trend_crossover` to its approved specification.

Every test here traces to a sentence in section 1 of
`docs/strategy_catalogue.md`, and the docstring names it. That is the point:
this file is the evidence that the implementation matches the written rule,
not merely that it runs. The specification's own "Deterministic edge-case
requirements" table has one test per row, in table order, at the end.

Where the specification prescribes arithmetic, the test recomputes it
independently rather than calling the implementation twice.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

import pytest
from strategy_helpers import (
    crossover_closes,
    make_history,
    round_trip_closes,
    security_view,
)

from backend.app.quant.indicators import OHLCVSeries, compute
from backend.app.quant.strategies import (
    PositionState,
    Signal,
    StrategyError,
    evaluate,
    metadata,
    registry,
    resolve_parameters,
    warmup_bars,
)

STRATEGY = "dual_sma_trend_crossover"
META = metadata(STRATEGY)


def _evaluate(history, index, *, position=PositionState.FLAT, security=True, **params):
    return evaluate(
        STRATEGY,
        history.window(index),
        security=security_view("TEST", history.trading_dates[index]) if security else None,
        position_state=position,
        parameters=params or None,
    )


def _reference_sma(closes, period, end_index):
    """Independent recomputation of the specification's quantized SMA."""

    window = closes[end_index - period + 1 : end_index + 1]
    with localcontext() as context:
        context.prec = 60
        total = Decimal(0)
        for value in window:
            total += Decimal(value)
        raw = total / Decimal(period)
    return raw.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


# ------------------------------------------------------- parameters, warm-up


def test_defaults_match_the_approved_parameter_table():
    """"fast_period 20, slow_period 50, min_avg_volume_20 200,000"."""

    assert resolve_parameters(STRATEGY) == {
        "fast_period": 20,
        "slow_period": 50,
        "min_avg_volume_20": 200_000,
    }


def test_warmup_is_max_of_slow_plus_one_and_twenty():
    """"warmup_bars = max(slow_period + 1, 20)", 51 at the defaults."""

    assert warmup_bars(STRATEGY) == 51
    assert warmup_bars(STRATEGY, {"slow_period": 10, "fast_period": 2}) == 20
    assert warmup_bars(STRATEGY, {"slow_period": 200, "fast_period": 20}) == 201


@pytest.mark.parametrize(
    "params",
    [
        {"fast_period": 50, "slow_period": 50},
        {"fast_period": 60, "slow_period": 50},
    ],
)
def test_fast_period_not_below_slow_period_is_rejected(params):
    """"Configurations for which fast_period >= slow_period must be rejected
    before evaluation"."""

    with pytest.raises(StrategyError, match="strictly less than"):
        resolve_parameters(STRATEGY, params)


@pytest.mark.parametrize(
    "params",
    [
        {"fast_period": 1},
        {"fast_period": 101},
        {"slow_period": 9},
        {"slow_period": 251},
        {"min_avg_volume_20": -1},
        {"min_avg_volume_20": 100_000_001},
    ],
)
def test_parameters_outside_the_approved_range_are_rejected(params):
    with pytest.raises(StrategyError):
        resolve_parameters(STRATEGY, params)


def test_min_avg_volume_must_advance_in_ten_thousand_share_steps():
    """The approved table gives an increment of 10,000."""

    with pytest.raises(StrategyError, match="steps of"):
        resolve_parameters(STRATEGY, {"min_avg_volume_20": 205_000})
    assert resolve_parameters(STRATEGY, {"min_avg_volume_20": 210_000})


def test_an_unknown_parameter_is_rejected_rather_than_ignored():
    with pytest.raises(StrategyError, match="no parameter"):
        resolve_parameters(STRATEGY, {"fast_periods": 20})


# ------------------------------------------------------------- SMA arithmetic


def test_quantized_sma_matches_an_independent_recomputation():
    """"SMA_p[t] = quantize(raw_sma_p[t], 6 decimal places, ROUND_HALF_EVEN)"."""

    closes = round_trip_closes(count=120)
    history = make_history(closes=closes)
    for index in (51, 70, 99, 119):
        result = _evaluate(history, index)
        assert result.evidence["sma_fast_t_exact"] == str(
            _reference_sma(closes, 20, index)
        )
        assert result.evidence["sma_slow_t_exact"] == str(
            _reference_sma(closes, 50, index)
        )
        assert result.evidence["sma_fast_t_minus_1_exact"] == str(
            _reference_sma(closes, 20, index - 1)
        )
        assert result.evidence["sma_slow_t_minus_1_exact"] == str(
            _reference_sma(closes, 50, index - 1)
        )


def test_quantized_sma_agrees_with_the_wp5_indicator_within_tolerance():
    """Cross-check against the independent WP5 engine.

    The two are expected to differ in the last bits: WP5 computes a float64
    rolling mean, this strategy computes a Decimal mean quantized to six
    places, because the specification requires quantization before
    comparison. Agreement to 1e-6 confirms the strategy is computing the same
    quantity, and the deliberate difference is the whole reason
    `numerics.py` exists.
    """

    closes = round_trip_closes(count=120)
    history = make_history(closes=closes)
    series = OHLCVSeries(
        symbol="TEST",
        trading_dates=history.trading_dates,
        open=list(history.open),
        high=list(history.high),
        low=list(history.low),
        close=list(history.close),
        volume=list(history.volume),
    )
    fast = compute("sma", series, period=20)["value"]
    slow = compute("sma", series, period=50)["value"]
    for index in (60, 80, 119):
        result = _evaluate(history, index)
        assert result.evidence["sma_fast_t"] == pytest.approx(fast[index], abs=1e-6)
        assert result.evidence["sma_slow_t"] == pytest.approx(slow[index], abs=1e-6)


def test_the_previous_sma_uses_the_previous_chronological_row():
    """"t-1 is the immediately preceding chronological daily row, not the
    preceding calendar date."

    The history is built with a deliberate calendar gap. The t-1 SMA must use
    the row before, not a synthesized bar for the missing date.
    """

    from strategy_helpers import sessions

    closes = round_trip_closes(count=120)
    calendar = list(sessions(200))
    # A ten-session hole in the middle of the calendar. The rows either side
    # of it remain adjacent chronologically even though their dates are ten
    # days apart, which is exactly the case the specification legislates for.
    gapped = calendar[:60] + calendar[70:130]
    assert len(gapped) == 120
    assert (gapped[60] - gapped[59]).days == 11

    history = make_history(closes=closes, dates=gapped)
    index = 100
    result = _evaluate(history, index)
    assert result.evidence["sma_slow_t_minus_1_exact"] == str(
        _reference_sma(closes, 50, index - 1)
    ), "the t-1 window must be the preceding rows, not the preceding calendar days"
    # No bar was synthesized for the missing dates.
    assert result.evidence["usable_bars_available"] == 101


# ----------------------------------------------------------------- liquidity


def test_liquidity_equality_passes():
    """"Bullish crossover with mean volume exactly equal to threshold:
    liquidity passes"."""

    closes = crossover_closes(count=120)
    history = make_history(closes=closes, volumes=[200_000.0] * 120)
    result = _evaluate(history, 119, min_avg_volume_20=200_000)
    assert result.evidence["volume_sum_20_t"] == 20 * 200_000
    assert result.evidence["liquidity_pass"] is True


def test_liquidity_one_share_short_fails():
    closes = crossover_closes(count=120)
    volumes = [200_000.0] * 120
    volumes[119] = 199_999.0
    history = make_history(closes=closes, volumes=volumes)
    result = _evaluate(history, 119, min_avg_volume_20=200_000)
    assert result.evidence["liquidity_pass"] is False


def test_zero_volume_rows_stay_in_the_mean_and_reduce_it():
    """"Zero-volume historical rows are included and reduce the mean"."""

    closes = crossover_closes(count=120)
    volumes = [400_000.0] * 120
    for index in range(110, 119):
        volumes[index] = 0.0
    history = make_history(closes=closes, volumes=volumes)
    result = _evaluate(history, 119, min_avg_volume_20=200_000)
    expected_sum = int(sum(volumes[100:120]))
    assert result.evidence["volume_sum_20_t"] == expected_sum
    assert result.evidence["avg_volume_20_t"] == expected_sum / 20


def test_zero_threshold_disables_only_the_average_volume_rule():
    """"Setting min_avg_volume_20 to zero disables only the average-volume
    threshold; volume[t] > 0 remains mandatory"."""

    closes = crossover_closes(count=120)
    volumes = [400_000.0] * 120
    volumes[119] = 0.0
    history = make_history(closes=closes, volumes=volumes)
    result = _evaluate(history, 119, min_avg_volume_20=0)
    assert result.evidence["liquidity_pass"] is True
    assert result.evidence["signal_bar_volume_pass"] is False


# ------------------------------------------------------------- data quality


def test_a_non_valid_quality_status_in_a_window_makes_the_result_unavailable():
    """"Only the exact value `valid` is usable" and "A required invalid
    observation makes the affected rolling result unavailable"."""

    closes = round_trip_closes(count=120)
    quality = ["valid"] * 120
    quality[100] = "high"
    history = make_history(closes=closes, quality=quality)
    result = _evaluate(history, 105)
    assert result.signal is Signal.UNAVAILABLE
    assert result.evidence["data_quality_pass"] is False


def test_calculation_resumes_once_the_invalid_bar_leaves_every_window():
    """"Calculation resumes only after the invalid observation has left every
    required window"."""

    closes = round_trip_closes(count=200)
    quality = ["valid"] * 200
    quality[100] = "critical"
    history = make_history(closes=closes, quality=quality)
    assert _evaluate(history, 140).signal is Signal.UNAVAILABLE
    resumed = _evaluate(history, 152)
    assert resumed.evidence["data_quality_pass"] is True
    assert resumed.signal is not Signal.UNAVAILABLE


def test_a_non_positive_close_is_never_imputed():
    """"Missing, non-finite, non-positive close values are never imputed"."""

    closes = round_trip_closes(count=120)
    closes[100] = 0.0
    history = make_history(closes=closes)
    result = _evaluate(history, 105)
    assert result.signal is Signal.UNAVAILABLE
    assert result.evidence["sma_fast_t"] is None


# ------------------------------------------------------------ universe gate


def test_universe_gate_requires_an_active_ordinary_equity():
    from backend.app.quant.strategies import SecurityView

    closes = crossover_closes(count=120)
    history = make_history(closes=closes)
    day = history.trading_dates[119]
    for exchange, kind, status, expected in [
        ("HOSE", "ordinary_equity", "active", True),
        ("UPCOM", "ordinary_equity", "active", True),
        ("UNKNOWN", "ordinary_equity", "active", False),
        ("HOSE", "warrant", "active", False),
        ("HOSE", "ordinary_equity", "suspended", False),
        ("HOSE", "unknown", "unknown", False),
    ]:
        result = evaluate(
            STRATEGY,
            history.window(119),
            security=SecurityView("TEST", day, exchange, kind, status),
            position_state=PositionState.FLAT,
        )
        assert result.evidence["universe_pass"] is expected, (exchange, kind, status)


def test_a_missing_classification_fails_the_gate_and_warns():
    """The data handoff reports no authoritative security master exists.

    The gate must fail rather than assume, and must say why.
    """

    history = make_history(closes=crossover_closes(count=120))
    result = _evaluate(history, 119, security=False)
    assert result.evidence["universe_pass"] is False
    assert any("classification unavailable" in item for item in result.warnings)


def test_a_stale_classification_is_flagged():
    from backend.app.quant.strategies import SecurityView

    history = make_history(closes=crossover_closes(count=120))
    result = evaluate(
        STRATEGY,
        history.window(119),
        security=SecurityView(
            "TEST", history.trading_dates[0], "HOSE", "ordinary_equity", "active"
        ),
        position_state=PositionState.FLAT,
    )
    assert any("not point-in-time" in item for item in result.warnings)


# ------------------------------------------------------------ exit behaviour


def test_the_liquidity_and_volume_gates_never_suppress_an_exit():
    """"The average-volume threshold, current-bar positive-volume gate, and
    active-universe gate must not suppress an exit from an existing
    position"."""

    closes = round_trip_closes(count=160)
    volumes = [1.0] * 160  # far below any threshold
    history = make_history(closes=closes, volumes=volumes)
    exits = [
        index
        for index in range(51, 160)
        if _evaluate(history, index, position=PositionState.LONG, security=False).signal
        is Signal.EXIT
    ]
    assert exits, (
        "an exit must still be produced with zero liquidity, no classification, "
        "and a thin signal bar"
    )


def test_invalidation_is_the_same_event_as_the_exit():
    """"invalidation_rule[t] = bearish_crossover[t]"."""

    history = make_history(closes=round_trip_closes(count=160))
    for index in range(51, 160):
        result = _evaluate(history, index, position=PositionState.LONG)
        assert result.evidence["invalidation_rule_pass"] == result.evidence[
            "bearish_crossover"
        ]


def test_levels_are_empty_because_the_strategy_defines_none():
    """"This strategy has no separate percentage stop, ATR stop, time stop,
    profit target, or price-level invalidation rule"."""

    history = make_history(closes=round_trip_closes(count=160))
    result = _evaluate(history, 120)
    assert result.support == ()
    assert result.resistance == ()
    assert result.invalidation is None


# --------------------------------------------- the specification's edge cases


def _flat_then_step(step: float, count: int = 120):
    """Closes that hold the SMAs exactly equal, then move by `step`.

    A constant series makes every SMA identical, which is the only way to
    exercise the equality rows of the edge-case table exactly rather than
    approximately.
    """

    closes = [100.0] * (count - 1)
    closes.append(100.0 + step)
    return closes


def test_edge_equal_smas_on_bar_t_are_neither_bullish_nor_bearish():
    """Row 1: "SMA_fast[t] == SMA_slow[t] after quantization: no bullish or
    bearish crossover on t"."""

    history = make_history(closes=[100.0] * 120)
    result = _evaluate(history, 119)
    assert result.evidence["sma_fast_t"] == result.evidence["sma_slow_t"]
    assert result.evidence["bullish_crossover"] is False
    assert result.evidence["bearish_crossover"] is False


def test_edge_previous_equal_and_fast_higher_is_bullish():
    """Row 2: "Previous SMAs equal and current fast SMA is greater: bullish"."""

    history = make_history(closes=_flat_then_step(+40.0))
    result = _evaluate(history, 119)
    assert result.evidence["sma_fast_t_minus_1"] == result.evidence[
        "sma_slow_t_minus_1"
    ]
    assert result.evidence["sma_fast_t"] > result.evidence["sma_slow_t"]
    assert result.evidence["bullish_crossover"] is True


def test_edge_previous_equal_and_fast_lower_is_bearish():
    """Row 3: "Previous SMAs equal and current fast SMA is lower: bearish"."""

    history = make_history(closes=_flat_then_step(-40.0))
    result = _evaluate(history, 119, position=PositionState.LONG)
    assert result.evidence["sma_fast_t_minus_1"] == result.evidence[
        "sma_slow_t_minus_1"
    ]
    assert result.evidence["sma_fast_t"] < result.evidence["sma_slow_t"]
    assert result.evidence["bearish_crossover"] is True
    assert result.signal is Signal.EXIT


def test_edge_liquidity_equality_passes():
    """Row 4, also covered above; asserted here in table order."""

    history = make_history(closes=_flat_then_step(+40.0), volumes=[200_000.0] * 120)
    result = _evaluate(history, 119, min_avg_volume_20=200_000)
    assert result.evidence["liquidity_pass"] is True
    assert result.signal is Signal.ENTRY


def test_edge_zero_threshold_with_zero_signal_bar_volume_still_blocks():
    """Row 5: "min_avg_volume_20 == 0 and volume[t] == 0: entry remains
    blocked by current-bar volume rule"."""

    volumes = [400_000.0] * 120
    volumes[119] = 0.0
    history = make_history(closes=_flat_then_step(+40.0), volumes=volumes)
    result = _evaluate(history, 119, min_avg_volume_20=0)
    assert result.signal is Signal.ENTRY_BLOCKED
    assert "signal_bar_volume_pass" in result.failed_criteria


def test_edge_bullish_crossover_while_already_long_produces_none():
    """Row 6: "Valid bullish crossover while already long: signal = none; no
    additional order"."""

    history = make_history(closes=_flat_then_step(+40.0))
    result = _evaluate(history, 119, position=PositionState.LONG)
    assert result.evidence["bullish_crossover"] is True
    assert result.signal is Signal.NONE
    assert result.order is None


def test_edge_bearish_crossover_while_flat_produces_none():
    """Row 7: "Valid bearish crossover while flat: signal = none; no order"."""

    history = make_history(closes=_flat_then_step(-40.0))
    result = _evaluate(history, 119, position=PositionState.FLAT)
    assert result.evidence["bearish_crossover"] is True
    assert result.signal is Signal.NONE
    assert result.order is None


def test_edge_insufficient_warmup_is_unavailable_never_entry_blocked():
    """Row 8: "Insufficient warm-up or indeterminate crossover: signal =
    unavailable, never entry_blocked"."""

    history = make_history(closes=round_trip_closes(count=60))
    for index in range(50):
        result = _evaluate(history, index)
        assert result.signal is Signal.UNAVAILABLE
        assert result.signal is not Signal.ENTRY_BLOCKED
    assert _evaluate(history, 49).evidence["warmup_bars_required"] == 51
    assert _evaluate(history, 50).signal is not Signal.UNAVAILABLE


def test_edge_indeterminate_crossover_is_unavailable_not_entry_blocked():
    """Row 8, second clause. A quality-blocked bar must not be reported as a
    blocked entry, because the crossover could not be computed at all."""

    closes = _flat_then_step(+40.0)
    quality = ["valid"] * 120
    quality[110] = "critical"
    history = make_history(closes=closes, quality=quality, volumes=[1.0] * 120)
    result = _evaluate(history, 119, min_avg_volume_20=200_000)
    assert result.signal is Signal.UNAVAILABLE


# ------------------------------------------------------------ scoring, order


def test_score_counts_passed_criteria_and_max_score_is_constant():
    history = make_history(closes=round_trip_closes(count=160))
    for index in range(51, 160, 17):
        result = _evaluate(history, index)
        assert result.max_score == len(META.criterion_names) == 6
        assert result.score == len(result.passed_criteria)
        assert set(result.passed_criteria) & set(result.failed_criteria) == set()


def test_an_uncomputable_criterion_counts_as_neither_passed_nor_failed():
    history = make_history(closes=round_trip_closes(count=60))
    result = _evaluate(history, 10)
    assert result.score == 0
    assert result.passed_criteria == ()
    assert result.failed_criteria == ("warmup_pass",)


def test_a_scheduled_order_reports_null_execution_fields():
    """"For a live scheduled order, execution_date and execution_price must be
    null until execution"."""

    history = make_history(closes=_flat_then_step(+40.0))
    result = _evaluate(history, 119)
    assert result.signal is Signal.ENTRY
    assert result.order_status.value == "scheduled"
    assert result.evidence["execution_date"] is None
    assert result.evidence["execution_price"] is None


def test_registry_rejects_a_result_whose_criteria_do_not_match_the_metadata():
    """A strategy that changed its criteria set would silently break ranking."""

    entry = registry.get(STRATEGY)
    original = entry.metadata.criterion_names
    object.__setattr__(entry.metadata, "criterion_names", (*original, "invented"))
    try:
        history = make_history(closes=round_trip_closes(count=120))
        with pytest.raises(StrategyError, match="max_score"):
            _evaluate(history, 100)
    finally:
        object.__setattr__(entry.metadata, "criterion_names", original)
