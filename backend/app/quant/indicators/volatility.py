"""Volatility and dispersion indicators (Section 14).

ATR, Bollinger Bands, rolling volatility, and drawdown.
"""

from __future__ import annotations

import numpy as np

from .registry import register
from .trend import ADJUSTMENT
from .types import (
    IndicatorError,
    IndicatorResult,
    IndicatorSpec,
    OHLCVSeries,
    Tolerance,
)
from .windows import previous, rolling_mean, rolling_std, safe_divide, wilder_smoothing


def true_range(series: OHLCVSeries) -> np.ndarray:
    """Wilder's true range, NaN on the first bar.

    TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, |low[i] - close[i-1]|).
    The first bar has no previous close, so it is NaN rather than being
    approximated by high - low; that approximation would make the first ATR
    value depend on how much history the caller happened to load.
    """

    previous_close = previous(series.close)
    candidates = np.vstack(
        [
            series.high - series.low,
            np.abs(series.high - previous_close),
            np.abs(series.low - previous_close),
        ]
    )
    return np.max(candidates, axis=0)


@register(
    IndicatorSpec(
        indicator_id="atr",
        title="Average true range (Wilder)",
        block="volatility",
        outputs=("value", "percent_of_close", "true_range"),
        parameters={"period": 14},
        formula=(
            "TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, "
            "|low[i] - close[i-1]|); ATR = Wilder smoothing of TR over `period`; "
            "percent_of_close = 100 * ATR / close."
        ),
        input_price="High, low, and the previous close.",
        adjustment_convention=ADJUSTMENT,
        warm_up=(
            "period bars. TR is undefined on the first bar, and the Wilder seed "
            "consumes the next `period` TR values, so the first ATR sits at index "
            "`period`."
        ),
        missing_value_behavior=(
            "TR is NaN wherever the bar or the previous close is missing. ATR then "
            "applies the gap re-seed rule, costing a further full `period`. "
            "percent_of_close is additionally NaN when the close is zero or missing."
        ),
        comparison_reference=(
            "Naive reference implementation of TR and of Wilder's recursion, plus a "
            "hand-computed three-bar case. AmiBroker ATR() cross-check pending an "
            "export."
        ),
        tolerance=Tolerance(
            absolute=1e-8,
            relative=1e-8,
            basis=(
                "Against the naive reference implementation. A 1e-4 relative "
                "allowance is proposed for the pending AmiBroker cross-check, which "
                "also requires confirming AmiBroker's first-bar TR convention."
            ),
        ),
        warm_up_bars=lambda period=14: max(0, int(period)),
    )
)
def average_true_range(series: OHLCVSeries, *, period: int = 14) -> IndicatorResult:
    ranges = true_range(series)
    values = wilder_smoothing(ranges, period)
    return IndicatorResult(
        indicator_id="atr",
        parameters={"period": period},
        series={
            "value": values,
            "percent_of_close": 100.0 * safe_divide(values, series.close),
            "true_range": ranges,
        },
    )


@register(
    IndicatorSpec(
        indicator_id="bollinger_bands",
        title="Bollinger Bands",
        block="volatility",
        outputs=("middle", "upper", "lower", "bandwidth", "percent_b"),
        parameters={"period": 20, "num_std": 2.0},
        formula=(
            "middle = SMA(close, period); sigma = population standard deviation of "
            "close over the same window (ddof = 0); upper = middle + num_std * sigma; "
            "lower = middle - num_std * sigma; "
            "bandwidth = 100 * (upper - lower) / middle; "
            "percent_b = (close - lower) / (upper - lower)."
        ),
        input_price="Close.",
        adjustment_convention=ADJUSTMENT,
        warm_up="period - 1 bars, the same as the underlying SMA.",
        missing_value_behavior=(
            "Windowed rule on both the mean and the standard deviation: NaN whenever "
            "the window is incomplete or contains a NaN close. bandwidth is NaN when "
            "the middle band is zero, and percent_b is NaN on a zero-width band "
            "(a window of identical closes), both via safe_divide rather than "
            "returning an infinity."
        ),
        comparison_reference=(
            "Naive reference implementation using the population standard deviation, "
            "plus a hand-computed case. The ddof = 0 choice matches the original "
            "publication and AmiBroker's StDev; a package using the sample standard "
            "deviation will differ by a factor sqrt(period / (period - 1)), which is "
            "about 2.6 percent at period = 20. AmiBroker BBandTop()/BBandBot() "
            "cross-check pending an export."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation. Does not cover the "
                "ddof convention difference described above, which is a definitional "
                "difference rather than a numerical one."
            ),
        ),
        warm_up_bars=lambda period=20, num_std=2.0: max(0, int(period) - 1),
    )
)
def bollinger_bands(
    series: OHLCVSeries, *, period: int = 20, num_std: float = 2.0
) -> IndicatorResult:
    middle = rolling_mean(series.close, period)
    sigma = rolling_std(series.close, period, ddof=0)
    upper = middle + num_std * sigma
    lower = middle - num_std * sigma
    return IndicatorResult(
        indicator_id="bollinger_bands",
        parameters={"period": period, "num_std": num_std},
        series={
            "middle": middle,
            "upper": upper,
            "lower": lower,
            "bandwidth": 100.0 * safe_divide(upper - lower, middle),
            "percent_b": safe_divide(series.close - lower, upper - lower),
        },
    )


@register(
    IndicatorSpec(
        indicator_id="rolling_volatility",
        title="Rolling realized volatility",
        block="volatility",
        outputs=("value", "daily_std"),
        parameters={"period": 20, "trading_days_per_year": 252},
        formula=(
            "r[i] = ln(close[i] / close[i - 1]); "
            "daily_std = sample standard deviation of r over `period` (ddof = 1); "
            "value = 100 * daily_std * sqrt(trading_days_per_year), in annualized "
            "percent."
        ),
        input_price="Close, as log returns.",
        adjustment_convention=(
            ADJUSTMENT
            + " Log returns require a positive close; a zero or negative adjusted "
            "close yields NaN rather than a complex or infinite return."
        ),
        warm_up=(
            "period bars. `period` returns are needed, which requires period + 1 "
            "closes, so the first defined value sits at index `period`."
        ),
        missing_value_behavior=(
            "A missing close makes two returns undefined, and the windowed rule then "
            "makes `period` volatility values undefined. ddof = 1 means a window "
            "must hold at least two returns, which `period >= 2` guarantees."
        ),
        comparison_reference=(
            "Naive reference implementation. The annualization factor is a "
            "convention, not a measurement: 252 is the common international default "
            "and is used here, but Ho Chi Minh City and Hanoi trade roughly 247 to "
            "250 sessions a year, so a VN-specific caller should pass the realized "
            "session count. Changing it rescales `value` by a known constant and "
            "leaves `daily_std` untouched."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation, at a fixed "
                "trading_days_per_year. Comparisons across packages must first "
                "reconcile the annualization factor and the ddof choice."
            ),
        ),
        warm_up_bars=lambda period=20, trading_days_per_year=252: max(0, int(period)),
    )
)
def rolling_volatility(
    series: OHLCVSeries, *, period: int = 20, trading_days_per_year: int = 252
) -> IndicatorResult:
    if int(period) < 2:
        raise IndicatorError("rolling_volatility needs period >= 2 for a sample std")
    if float(trading_days_per_year) <= 0:
        raise IndicatorError("trading_days_per_year must be positive")

    ratio = safe_divide(series.close, previous(series.close))
    log_returns = np.full(len(ratio), np.nan, dtype=np.float64)
    positive = np.isfinite(ratio) & (ratio > 0.0)
    np.log(ratio, out=log_returns, where=positive)
    log_returns[~positive] = np.nan

    daily = rolling_std(log_returns, period, ddof=1)
    return IndicatorResult(
        indicator_id="rolling_volatility",
        parameters={"period": period, "trading_days_per_year": trading_days_per_year},
        series={
            "value": 100.0 * daily * np.sqrt(float(trading_days_per_year)),
            "daily_std": daily,
        },
    )


@register(
    IndicatorSpec(
        indicator_id="drawdown",
        title="Drawdown from running peak",
        block="volatility",
        outputs=("value", "peak"),
        parameters={},
        formula=(
            "peak[i] = max(close[0 .. i]) over defined closes; "
            "value[i] = 100 * (close[i] / peak[i] - 1), which is zero at a new high "
            "and negative below it."
        ),
        input_price=(
            "Close. Computed on the closing price, not on intraday lows, so it "
            "measures close-to-close drawdown rather than peak-to-trough."
        ),
        adjustment_convention=(
            ADJUSTMENT
            + " Drawdown is scale-invariant, so it is unaffected by the price unit, "
            "but it is sensitive to the adjustment method: an unadjusted series "
            "shows an artificial drawdown on every ex-dividend and split date."
        ),
        warm_up=(
            "None. The first defined close is its own peak, so value[first] = 0."
        ),
        missing_value_behavior=(
            "NaN at a missing close. The running peak carries across the gap "
            "unchanged (it is a maximum over defined closes only), so the series "
            "resumes correctly rather than restarting."
        ),
        comparison_reference=(
            "Naive reference implementation plus hand-computed cases; the "
            "definition is closed-form."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis="Against the naive reference implementation.",
        ),
        warm_up_bars=lambda: 0,
        scalar_outputs=("max_drawdown_pct", "max_drawdown_index"),
    )
)
def drawdown(series: OHLCVSeries) -> IndicatorResult:
    close = series.close
    peak = np.full(len(close), np.nan, dtype=np.float64)
    running = np.nan
    for index, value in enumerate(close):
        if np.isfinite(value):
            running = value if not np.isfinite(running) else max(running, float(value))
            peak[index] = running
    values = 100.0 * (safe_divide(close, peak) - 1.0)

    if np.any(np.isfinite(values)):
        worst_index = int(np.nanargmin(values))
        worst = float(values[worst_index])
    else:
        worst_index = -1
        worst = float("nan")

    return IndicatorResult(
        indicator_id="drawdown",
        parameters={},
        series={"value": values, "peak": peak},
        scalars={"max_drawdown_pct": worst, "max_drawdown_index": worst_index},
    )
