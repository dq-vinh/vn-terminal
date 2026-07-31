"""Numerical correctness of every Section 14 indicator.

Three layers of check, in increasing generality:

1. **Hand-computed cases.** Small constructed series whose expected values
   were worked out by hand and are written into the test as literals. These
   are the only checks that can catch a wrong convention, because they do
   not depend on any other code in the repository.
2. **Independent reference cross-checks.** Every indicator recomputed over
   the full contract fixtures by the naive implementations in
   `reference.py`, compared at the tolerance each indicator documents.
3. **Property tests.** Invariants that must hold on any input at all
   (RSI bounded, ATR non-negative, drawdown non-positive, band ordering,
   shares summing to one), per Section 25.2's "property tests for range and
   monotonicity constraints".

Warm-up and missing-value behaviour are checked separately at the end,
against the numbers each indicator's own `IndicatorSpec` documents, so the
documentation cannot drift away from the code.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest
import reference
from helpers import call_kwargs

from backend.app.quant.indicators import (
    IndicatorError,
    OHLCVSeries,
    all_indicators,
    compute,
    spec,
)

NAN = float("nan")


def build(
    closes,
    *,
    highs=None,
    lows=None,
    opens=None,
    volumes=None,
    symbol="TEST",
) -> OHLCVSeries:
    """A series on consecutive weekdays, for hand-computed cases."""

    count = len(closes)
    day = dt.date(2026, 1, 5)
    dates = []
    while len(dates) < count:
        if day.weekday() < 5:
            dates.append(day)
        day += dt.timedelta(days=1)
    return OHLCVSeries(
        symbol=symbol,
        trading_dates=tuple(dates),
        open=opens if opens is not None else closes,
        high=highs if highs is not None else closes,
        low=lows if lows is not None else closes,
        close=closes,
        volume=volumes if volumes is not None else [1000.0] * count,
    )


def assert_close(actual, expected, indicator_id: str, output: str):
    """Compare against the tolerance the indicator itself documents."""

    tolerance = spec(indicator_id).tolerance
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    np.testing.assert_allclose(
        actual,
        expected,
        rtol=tolerance.relative,
        atol=tolerance.absolute,
        equal_nan=True,
        err_msg=f"{indicator_id}.{output} outside its documented tolerance",
    )


# ---------------------------------------------------------------------------
# Hand-computed cases
# ---------------------------------------------------------------------------


def test_sma_hand_computed():
    series = build([10.0, 11.0, 12.0, 13.0, 14.0])
    result = compute("sma", series, period=3)
    assert_close(result["value"], [NAN, NAN, 11.0, 12.0, 13.0], "sma", "value")


def test_ema_hand_computed():
    # alpha = 2 / (3 + 1) = 0.5. Seed at index 2 is mean(10, 11, 12) = 11.
    # index 3: 0.5 * 13 + 0.5 * 11 = 12. index 4: 0.5 * 14 + 0.5 * 12 = 13.
    series = build([10.0, 11.0, 12.0, 13.0, 14.0])
    result = compute("ema", series, period=3)
    assert_close(result["value"], [NAN, NAN, 11.0, 12.0, 13.0], "ema", "value")


def test_rate_of_change_hand_computed():
    series = build([10.0, 11.0, 12.0, 13.0, 14.0])
    result = compute("rate_of_change", series, period=2)
    expected = [NAN, NAN, 20.0, 100.0 * (13.0 / 11.0 - 1.0), 100.0 * (14.0 / 12.0 - 1.0)]
    assert_close(result["value"], expected, "rate_of_change", "value")


def test_rsi_is_exactly_100_on_a_strictly_rising_series():
    """A closed-form case: with no down days the index must pin at 100."""

    series = build([10.0, 11.0, 12.0, 13.0, 14.0])
    result = compute("rsi", series, period=2)
    assert_close(result["value"], [NAN, NAN, 100.0, 100.0, 100.0], "rsi", "value")


def test_rsi_is_exactly_zero_on_a_strictly_falling_series():
    series = build([14.0, 13.0, 12.0, 11.0, 10.0])
    result = compute("rsi", series, period=2)
    assert_close(result["value"], [NAN, NAN, 0.0, 0.0, 0.0], "rsi", "value")


def test_rsi_is_undefined_on_a_perfectly_flat_series():
    """Documented convention: 0/0 is NaN here, not the conventional 50 or 100."""

    series = build([10.0] * 6)
    result = compute("rsi", series, period=2)
    assert np.all(np.isnan(result["value"]))


def test_bollinger_hand_computed():
    series = build([10.0, 11.0, 12.0, 13.0, 14.0])
    result = compute("bollinger_bands", series, period=3, num_std=2.0)
    sigma = math.sqrt(2.0 / 3.0)  # population std of three consecutive integers
    assert_close(result["middle"][2], 11.0, "bollinger_bands", "middle")
    assert_close(result["upper"][2], 11.0 + 2.0 * sigma, "bollinger_bands", "upper")
    assert_close(result["lower"][2], 11.0 - 2.0 * sigma, "bollinger_bands", "lower")
    # percent_b of the last close in a rising window sits at the top of the band.
    assert 0.0 <= result["percent_b"][2] <= 1.0


def test_atr_hand_computed():
    highs = [10.0, 12.0, 15.0]
    lows = [8.0, 9.0, 10.0]
    closes = [9.0, 11.0, 10.0]
    series = build(closes, highs=highs, lows=lows)
    result = compute("atr", series, period=2)
    # TR[1] = max(12 - 9, |12 - 9|, |9 - 9|) = 3
    # TR[2] = max(15 - 10, |15 - 11|, |10 - 11|) = 5
    # ATR[2] = mean(3, 5) = 4
    assert_close(result["true_range"], [NAN, 3.0, 5.0], "atr", "true_range")
    assert_close(result["value"], [NAN, NAN, 4.0], "atr", "value")


def test_drawdown_hand_computed():
    series = build([10.0, 12.0, 9.0, 11.0])
    result = compute("drawdown", series)
    assert_close(result["peak"], [10.0, 12.0, 12.0, 12.0], "drawdown", "peak")
    assert_close(
        result["value"],
        [0.0, 0.0, 100.0 * (9.0 / 12.0 - 1.0), 100.0 * (11.0 / 12.0 - 1.0)],
        "drawdown",
        "value",
    )
    assert result.scalars["max_drawdown_pct"] == pytest.approx(-25.0)
    assert result.scalars["max_drawdown_index"] == 2


def test_pivot_levels_hand_computed():
    series = build([9.0, 11.0], highs=[10.0, 12.0], lows=[8.0, 10.0])
    # Previous bar for index 1 is high 10, low 8, close 9: pivot = 9.
    result = compute("pivot_levels", series)
    assert result["pivot"][1] == pytest.approx(9.0)
    assert result["r1"][1] == pytest.approx(2 * 9.0 - 8.0)
    assert result["s1"][1] == pytest.approx(2 * 9.0 - 10.0)
    assert result["r2"][1] == pytest.approx(9.0 + 2.0)
    assert result["s2"][1] == pytest.approx(9.0 - 2.0)
    assert result["r3"][1] == pytest.approx(10.0 + 2.0 * (9.0 - 8.0))
    assert result["s3"][1] == pytest.approx(8.0 - 2.0 * (10.0 - 9.0))
    assert np.isnan(result["pivot"][0]), "the first bar has no previous bar"


def test_volume_price_trend_hand_computed():
    series = build([10.0, 11.0, 12.0], volumes=[100.0, 200.0, 300.0])
    result = compute("volume_price_trend", series)
    first = 200.0 * (1.0 / 10.0)
    second = first + 300.0 * (1.0 / 11.0)
    assert_close(result["value"], [NAN, first, second], "volume_price_trend", "value")


def test_volume_sma_hand_computed():
    series = build([10.0] * 4, volumes=[100.0, 200.0, 300.0, 800.0])
    result = compute("volume_sma", series, period=3)
    assert_close(result["value"], [NAN, NAN, 200.0, 1300.0 / 3.0], "volume_sma", "value")
    assert result["relative_volume"][2] == pytest.approx(300.0 / 200.0)


# ---------------------------------------------------------------------------
# Reference cross-checks over the contract fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("period", [3, 20, 200])
def test_sma_matches_reference(fpt: OHLCVSeries, period: int):
    assert_close(
        compute("sma", fpt, period=period)["value"],
        reference.sma(list(fpt.close), period),
        "sma",
        "value",
    )


@pytest.mark.parametrize("period", [3, 20])
def test_ema_matches_reference(fpt: OHLCVSeries, period: int):
    assert_close(
        compute("ema", fpt, period=period)["value"],
        reference.ema(list(fpt.close), period),
        "ema",
        "value",
    )


def test_macd_matches_reference(fpt: OHLCVSeries):
    fast = reference.ema(list(fpt.close), 12)
    slow = reference.ema(list(fpt.close), 26)
    line = [
        a - b if math.isfinite(a) and math.isfinite(b) else NAN for a, b in zip(fast, slow)
    ]
    signal = reference.ema(line, 9)
    result = compute("macd", fpt)
    assert_close(result["macd"], line, "macd", "macd")
    assert_close(result["signal"], signal, "macd", "signal")
    assert_close(
        result["histogram"],
        [a - b if math.isfinite(a) and math.isfinite(b) else NAN for a, b in zip(line, signal)],
        "macd",
        "histogram",
    )


def test_rsi_matches_reference(fpt: OHLCVSeries):
    assert_close(
        compute("rsi", fpt, period=14)["value"],
        reference.rsi(list(fpt.close), 14),
        "rsi",
        "value",
    )


def test_atr_matches_reference(fpt: OHLCVSeries):
    expected = reference.atr(list(fpt.high), list(fpt.low), list(fpt.close), 14)
    assert_close(compute("atr", fpt, period=14)["value"], expected, "atr", "value")


def test_bollinger_matches_reference(fpt: OHLCVSeries):
    middle, upper, lower = reference.bollinger(list(fpt.close), 20, 2.0)
    result = compute("bollinger_bands", fpt)
    assert_close(result["middle"], middle, "bollinger_bands", "middle")
    assert_close(result["upper"], upper, "bollinger_bands", "upper")
    assert_close(result["lower"], lower, "bollinger_bands", "lower")


def test_rolling_extremes_match_reference(fpt: OHLCVSeries):
    assert_close(
        compute("rolling_high", fpt, period=52)["value"],
        reference.rolling_max(list(fpt.high), 52),
        "rolling_high",
        "value",
    )
    assert_close(
        compute("rolling_low", fpt, period=52)["value"],
        reference.rolling_min(list(fpt.low), 52),
        "rolling_low",
        "value",
    )


def test_rate_of_change_matches_reference(fpt: OHLCVSeries):
    assert_close(
        compute("rate_of_change", fpt, period=12)["value"],
        reference.rate_of_change(list(fpt.close), 12),
        "rate_of_change",
        "value",
    )


def test_rolling_volatility_matches_reference(fpt: OHLCVSeries):
    annual, daily = reference.rolling_volatility(list(fpt.close), 20, 252)
    result = compute("rolling_volatility", fpt)
    assert_close(result["value"], annual, "rolling_volatility", "value")
    assert_close(result["daily_std"], daily, "rolling_volatility", "daily_std")


def test_drawdown_matches_reference(fpt: OHLCVSeries):
    values, peaks = reference.drawdown(list(fpt.close))
    result = compute("drawdown", fpt)
    assert_close(result["value"], values, "drawdown", "value")
    assert_close(result["peak"], peaks, "drawdown", "peak")


def test_volume_price_trend_matches_reference(fpt: OHLCVSeries):
    assert_close(
        compute("volume_price_trend", fpt)["value"],
        reference.volume_price_trend(list(fpt.close), list(fpt.volume)),
        "volume_price_trend",
        "value",
    )


def test_pivot_levels_match_reference(fpt: OHLCVSeries):
    expected = reference.pivot_levels(list(fpt.high), list(fpt.low), list(fpt.close))
    result = compute("pivot_levels", fpt)
    for name, values in expected.items():
        assert_close(result[name], values, "pivot_levels", name)


# ---------------------------------------------------------------------------
# Property tests (Section 25.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("symbol", ["fpt", "kdh"])
def test_rsi_is_bounded(symbol, request):
    series = request.getfixturevalue(symbol)
    values = compute("rsi", series)["value"]
    defined = values[np.isfinite(values)]
    assert defined.size > 0
    assert np.all(defined >= 0.0) and np.all(defined <= 100.0)


def test_bollinger_bands_are_ordered(fpt: OHLCVSeries):
    result = compute("bollinger_bands", fpt)
    defined = np.isfinite(result["middle"])
    assert np.all(result["lower"][defined] <= result["middle"][defined])
    assert np.all(result["middle"][defined] <= result["upper"][defined])


def test_true_range_and_atr_are_non_negative(fpt: OHLCVSeries):
    result = compute("atr", fpt)
    for output in ("value", "true_range"):
        values = result[output]
        assert np.all(values[np.isfinite(values)] >= 0.0)


def test_drawdown_is_never_positive(fpt: OHLCVSeries):
    values = compute("drawdown", fpt)["value"]
    assert np.all(values[np.isfinite(values)] <= 1e-12)


def test_rolling_extremes_bracket_the_close(fpt: OHLCVSeries):
    """high >= close >= low on every bar, so the rolling extremes bracket it."""

    high = compute("rolling_high", fpt, period=20)
    low = compute("rolling_low", fpt, period=20)
    defined = np.isfinite(high["distance_pct"]) & np.isfinite(low["distance_pct"])
    assert np.all(high["distance_pct"][defined] <= 1e-12)
    assert np.all(low["distance_pct"][defined] >= -1e-12)


def test_sma_of_a_rising_series_is_rising():
    series = build([float(value) for value in range(1, 60)])
    values = compute("sma", series, period=10)["value"]
    defined = values[np.isfinite(values)]
    assert np.all(np.diff(defined) > 0)


def test_rolling_volatility_of_a_constant_growth_series_is_zero():
    series = build([100.0 * (1.02**index) for index in range(40)])
    values = compute("rolling_volatility", series, period=10)["value"]
    defined = values[np.isfinite(values)]
    assert defined.size > 0
    assert np.all(np.abs(defined) < 1e-9)


# ---------------------------------------------------------------------------
# Warm-up, documented against each indicator's own spec
# ---------------------------------------------------------------------------


def leading_nan_count(values: np.ndarray) -> int:
    finite = np.isfinite(values)
    return int(len(values)) if not finite.any() else int(np.argmax(finite))


@pytest.mark.parametrize(
    "entry", all_indicators(), ids=lambda entry: entry.spec.indicator_id
)
def test_warm_up_matches_the_documented_warm_up(entry, fpt: OHLCVSeries):
    """The slowest output must start exactly where the spec says it does."""

    kwargs = call_kwargs(entry.spec, fpt)
    result = compute(entry.spec.indicator_id, fpt, **kwargs)
    documented = entry.spec.warm_up_bars(
        **{key: value for key, value in kwargs.items() if key != "benchmark"}
    )
    observed = max(leading_nan_count(result[output]) for output in entry.spec.outputs)
    assert observed == documented, (
        f"{entry.spec.indicator_id} documents a warm-up of {documented} bars but its "
        f"slowest output first becomes defined after {observed}"
    )


UNCONDITIONALLY_DEFINED = (
    "sma",
    "ema",
    "macd",
    "rsi",
    "atr",
    "bollinger_bands",
    "rolling_high",
    "rolling_low",
    "rate_of_change",
    "volume_sma",
    "volume_price_trend",
    "pivot_levels",
    "rolling_volatility",
    "drawdown",
    "accumulation_distribution",
    "on_balance_volume",
)


@pytest.mark.parametrize("indicator_id", UNCONDITIONALLY_DEFINED)
def test_no_holes_after_warm_up_on_complete_data(indicator_id: str, fpt: OHLCVSeries):
    """On a gap-free series these indicators must never go undefined again."""

    entry = spec(indicator_id)
    result = compute(indicator_id, fpt, **entry.parameters)
    for output in entry.outputs:
        values = result[output]
        after = values[leading_nan_count(values) :]
        assert np.all(np.isfinite(after)), f"{indicator_id}.{output} has a hole"


# ---------------------------------------------------------------------------
# Missing-value behaviour (Section 25.2, "missing-bar and suspension cases")
# ---------------------------------------------------------------------------


def test_a_windowed_indicator_recovers_exactly_one_window_after_a_gap():
    closes = [float(10 + index) for index in range(20)]
    closes[10] = NAN
    series = build(closes)
    values = compute("sma", series, period=3)["value"]
    # Indices 10, 11, 12 hold the gap in their window; index 13 does not.
    assert np.all(np.isnan(values[10:13]))
    assert np.isfinite(values[13])


def test_a_recursive_indicator_re_seeds_rather_than_propagating_a_gap():
    closes = [float(10 + index) for index in range(30)]
    closes[15] = NAN
    series = build(closes)
    values = compute("ema", series, period=3)["value"]
    assert np.isnan(values[15]), "the gap bar itself is undefined"
    # The new run starts at index 16 and its SMA seed lands at 16 + 3 - 1 = 18,
    # so the gap costs the bar itself plus one further warm-up period.
    assert np.all(np.isnan(values[15:18])), "the new run needs its own seed"
    assert np.isfinite(values[18]), "and then recovers, rather than staying poisoned"
    assert np.all(np.isfinite(values[18:]))


def test_a_cumulative_indicator_resumes_at_the_same_level_after_a_gap():
    closes = [10.0, 11.0, 12.0, NAN, 13.0, 14.0]
    volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    series = build(closes, volumes=volumes)
    values = compute("on_balance_volume", series)["value"]
    assert np.isnan(values[3]) and np.isnan(values[4]), "the gap and the bar after it"
    assert values[2] == pytest.approx(200.0)
    assert values[5] == pytest.approx(300.0), "resumes from 200, does not restart at 0"


def test_missing_values_never_become_zeros(fpt: OHLCVSeries):
    """A NaN must never be silently coerced into a number by the pipeline."""

    closes = list(fpt.close)
    closes[5] = NAN
    series = build(closes[:40], volumes=[1000.0] * 40)
    values = compute("sma", series, period=5)["value"]
    assert np.isnan(values[5])
    assert not np.any(values[:4] == 0.0)


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def test_unknown_parameter_is_rejected(fpt: OHLCVSeries):
    with pytest.raises(IndicatorError, match="has no parameter"):
        compute("sma", fpt, windwo=20)


def test_zero_and_negative_periods_are_rejected(fpt: OHLCVSeries):
    for period in (0, -1):
        with pytest.raises(IndicatorError):
            compute("sma", fpt, period=period)
        with pytest.raises(IndicatorError):
            compute("rate_of_change", fpt, period=period)


def test_unknown_indicator_is_rejected(fpt: OHLCVSeries):
    with pytest.raises(IndicatorError, match="unknown indicator"):
        compute("not_an_indicator", fpt)


def test_series_rejects_unsorted_dates():
    with pytest.raises(IndicatorError, match="strictly increasing"):
        OHLCVSeries(
            symbol="TEST",
            trading_dates=(dt.date(2026, 1, 6), dt.date(2026, 1, 5)),
            open=[1.0, 1.0],
            high=[1.0, 1.0],
            low=[1.0, 1.0],
            close=[1.0, 1.0],
            volume=[1.0, 1.0],
        )


def test_series_rejects_mismatched_lengths():
    with pytest.raises(IndicatorError, match="trading dates"):
        OHLCVSeries(
            symbol="TEST",
            trading_dates=(dt.date(2026, 1, 5),),
            open=[1.0],
            high=[1.0],
            low=[1.0],
            close=[1.0],
            volume=[1.0, 2.0],
        )
