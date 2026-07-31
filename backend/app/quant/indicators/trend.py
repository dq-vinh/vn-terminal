"""Trend and rate-of-change indicators (Section 14).

SMA, EMA, MACD, rolling highs and lows, and rate of change.
"""

from __future__ import annotations

import numpy as np

from .registry import register
from .types import IndicatorResult, IndicatorSpec, OHLCVSeries, Tolerance
from .windows import (
    exponential_moving_average,
    rolling_max,
    rolling_mean,
    rolling_min,
    safe_divide,
    validate_window,
)

ADJUSTMENT = (
    "Inherits the caller's price adjustment verbatim. FData bars are back-adjusted "
    "and expressed in thousands of VND (Section 19.1) with adjustment_status carried "
    "on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion "
    "happens inside this package."
)

_ARITHMETIC_TOLERANCE = Tolerance(
    absolute=1e-9,
    relative=1e-9,
    basis=(
        "Against the independent naive reference implementation in "
        "tests/quant/reference.py and the hand-computed cases in the golden fixture. "
        "Float64 arithmetic only, so agreement is near machine precision. A looser "
        "1e-4 relative allowance is proposed for the pending AmiBroker cross-check "
        "because FData stores prices as float32 (Section 19.1)."
    ),
)

_RECURSIVE_TOLERANCE = Tolerance(
    absolute=1e-8,
    relative=1e-8,
    basis=(
        "Against the independent naive reference implementation in "
        "tests/quant/reference.py. Looser than the windowed indicators because the "
        "recursion accumulates rounding over the full series. A 1e-4 relative "
        "allowance is proposed for the pending AmiBroker cross-check, which also "
        "depends on AmiBroker using the same SMA seeding convention."
    ),
)


@register(
    IndicatorSpec(
        indicator_id="sma",
        title="Simple moving average",
        block="trend",
        outputs=("value",),
        parameters={"period": 20},
        formula="SMA[i] = mean(close[i - period + 1 .. i])",
        input_price="Close.",
        adjustment_convention=ADJUSTMENT,
        warm_up=(
            "period - 1 bars. The first defined value sits at index period - 1, the "
            "first bar with a complete window."
        ),
        missing_value_behavior=(
            "Windowed rule: NaN whenever the window is incomplete or contains a NaN "
            "close. A single missing bar costs exactly `period` outputs and the "
            "series then recovers on its own. No imputation or forward fill."
        ),
        comparison_reference=(
            "Naive O(n*period) reference implementation plus hand-computed values on "
            "a five-bar series. AmiBroker MA() cross-check pending an export."
        ),
        tolerance=_ARITHMETIC_TOLERANCE,
        warm_up_bars=lambda period=20: max(0, int(period) - 1),
    )
)
def simple_moving_average(series: OHLCVSeries, *, period: int = 20) -> IndicatorResult:
    return IndicatorResult(
        indicator_id="sma",
        parameters={"period": period},
        series={"value": rolling_mean(series.close, period)},
    )


@register(
    IndicatorSpec(
        indicator_id="ema",
        title="Exponential moving average",
        block="trend",
        outputs=("value",),
        parameters={"period": 20},
        formula=(
            "alpha = 2 / (period + 1); seed = mean(close[first .. first + period - 1]) "
            "placed at index first + period - 1; thereafter "
            "EMA[i] = alpha * close[i] + (1 - alpha) * EMA[i - 1]."
        ),
        input_price="Close.",
        adjustment_convention=ADJUSTMENT,
        warm_up=(
            "period - 1 bars, because the recursion is seeded with a simple mean of "
            "the first `period` closes rather than with close[0]."
        ),
        missing_value_behavior=(
            "Gap re-seed rule: the close series is split into maximal runs of "
            "consecutive non-NaN bars and the recursion runs independently inside "
            "each run, so one missing bar costs one further warm-up period and never "
            "contaminates the rest of the series. Runs shorter than `period` produce "
            "no output at all."
        ),
        comparison_reference=(
            "Naive reference implementation applying the same seeding rule, plus a "
            "hand-computed three-step recursion. AmiBroker EMA() cross-check pending "
            "an export; note AmiBroker's seeding convention must be confirmed before "
            "that comparison is meaningful."
        ),
        tolerance=_RECURSIVE_TOLERANCE,
        warm_up_bars=lambda period=20: max(0, int(period) - 1),
    )
)
def exponential_moving_average_indicator(
    series: OHLCVSeries, *, period: int = 20
) -> IndicatorResult:
    return IndicatorResult(
        indicator_id="ema",
        parameters={"period": period},
        series={"value": exponential_moving_average(series.close, period)},
    )


@register(
    IndicatorSpec(
        indicator_id="macd",
        title="Moving average convergence divergence",
        block="trend",
        outputs=("macd", "signal", "histogram"),
        parameters={"fast_period": 12, "slow_period": 26, "signal_period": 9},
        formula=(
            "MACD = EMA(close, fast_period) - EMA(close, slow_period); "
            "signal = EMA(MACD, signal_period); histogram = MACD - signal. "
            "Every EMA uses the SMA-seeded convention documented for the `ema` "
            "indicator, and the signal line is seeded from the first "
            "`signal_period` defined MACD values."
        ),
        input_price="Close.",
        adjustment_convention=ADJUSTMENT,
        warm_up=(
            "MACD line: slow_period - 1 bars. Signal and histogram: "
            "slow_period + signal_period - 2 bars, since the signal EMA is seeded "
            "from the first signal_period defined MACD values."
        ),
        missing_value_behavior=(
            "Inherits the EMA gap re-seed rule on both legs. A NaN close makes both "
            "EMAs undefined at that bar, so MACD, signal, and histogram are all NaN "
            "there; the signal line then re-seeds from the resumed MACD run."
        ),
        comparison_reference=(
            "Naive reference implementation composed from the reference EMA. "
            "AmiBroker MACD()/Signal() cross-check pending an export."
        ),
        tolerance=_RECURSIVE_TOLERANCE,
        warm_up_bars=lambda fast_period=12, slow_period=26, signal_period=9: max(
            0, int(slow_period) + int(signal_period) - 2
        ),
    )
)
def macd(
    series: OHLCVSeries,
    *,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> IndicatorResult:
    fast = exponential_moving_average(series.close, fast_period)
    slow = exponential_moving_average(series.close, slow_period)
    macd_line = fast - slow
    signal_line = exponential_moving_average(macd_line, signal_period)
    return IndicatorResult(
        indicator_id="macd",
        parameters={
            "fast_period": fast_period,
            "slow_period": slow_period,
            "signal_period": signal_period,
        },
        series={
            "macd": macd_line,
            "signal": signal_line,
            "histogram": macd_line - signal_line,
        },
    )


@register(
    IndicatorSpec(
        indicator_id="rate_of_change",
        title="Rate of change",
        block="trend",
        outputs=("value",),
        parameters={"period": 12},
        formula="ROC[i] = 100 * (close[i] / close[i - period] - 1), in percent.",
        input_price="Close.",
        adjustment_convention=ADJUSTMENT,
        warm_up="period bars; the first defined value sits at index `period`.",
        missing_value_behavior=(
            "NaN when either endpoint is missing. A zero or negative close at the "
            "lagged endpoint yields NaN rather than an infinity, via safe_divide."
        ),
        comparison_reference=(
            "Closed-form arithmetic; hand-computed cases in the golden fixture. "
            "AmiBroker ROC() cross-check pending an export."
        ),
        tolerance=_ARITHMETIC_TOLERANCE,
        warm_up_bars=lambda period=12: max(0, int(period)),
    )
)
def rate_of_change(series: OHLCVSeries, *, period: int = 12) -> IndicatorResult:
    period = validate_window(period, "period")
    close = series.close
    lagged = np.full(len(close), np.nan, dtype=np.float64)
    if len(close) > period:
        lagged[period:] = close[:-period]
    values = 100.0 * (safe_divide(close, lagged) - 1.0)
    return IndicatorResult(
        indicator_id="rate_of_change",
        parameters={"period": period},
        series={"value": values},
    )


@register(
    IndicatorSpec(
        indicator_id="rolling_high",
        title="Rolling high",
        block="trend",
        outputs=("value", "distance_pct"),
        parameters={"period": 52},
        formula=(
            "value[i] = max(high[i - period + 1 .. i]); "
            "distance_pct[i] = 100 * (close[i] / value[i] - 1), negative when the "
            "close sits below the rolling high."
        ),
        input_price=(
            "High for the extreme itself, close for the distance measure. Using the "
            "high rather than the close means the level matches what a chart shows."
        ),
        adjustment_convention=ADJUSTMENT,
        warm_up="period - 1 bars.",
        missing_value_behavior=(
            "Windowed rule: NaN whenever the window is incomplete or contains a NaN "
            "high. distance_pct is additionally NaN when the close is missing."
        ),
        comparison_reference=(
            "Naive reference implementation plus hand-computed cases. AmiBroker "
            "HHV() cross-check pending an export."
        ),
        tolerance=_ARITHMETIC_TOLERANCE,
        warm_up_bars=lambda period=52: max(0, int(period) - 1),
    )
)
def rolling_high(series: OHLCVSeries, *, period: int = 52) -> IndicatorResult:
    highs = rolling_max(series.high, period)
    return IndicatorResult(
        indicator_id="rolling_high",
        parameters={"period": period},
        series={
            "value": highs,
            "distance_pct": 100.0 * (safe_divide(series.close, highs) - 1.0),
        },
    )


@register(
    IndicatorSpec(
        indicator_id="rolling_low",
        title="Rolling low",
        block="trend",
        outputs=("value", "distance_pct"),
        parameters={"period": 52},
        formula=(
            "value[i] = min(low[i - period + 1 .. i]); "
            "distance_pct[i] = 100 * (close[i] / value[i] - 1), positive when the "
            "close sits above the rolling low."
        ),
        input_price="Low for the extreme itself, close for the distance measure.",
        adjustment_convention=ADJUSTMENT,
        warm_up="period - 1 bars.",
        missing_value_behavior=(
            "Windowed rule: NaN whenever the window is incomplete or contains a NaN "
            "low. distance_pct is additionally NaN when the close is missing, and "
            "when the rolling low is zero."
        ),
        comparison_reference=(
            "Naive reference implementation plus hand-computed cases. AmiBroker "
            "LLV() cross-check pending an export."
        ),
        tolerance=_ARITHMETIC_TOLERANCE,
        warm_up_bars=lambda period=52: max(0, int(period) - 1),
    )
)
def rolling_low(series: OHLCVSeries, *, period: int = 52) -> IndicatorResult:
    lows = rolling_min(series.low, period)
    return IndicatorResult(
        indicator_id="rolling_low",
        parameters={"period": period},
        series={
            "value": lows,
            "distance_pct": 100.0 * (safe_divide(series.close, lows) - 1.0),
        },
    )
