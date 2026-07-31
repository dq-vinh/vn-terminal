"""Volume indicators (Section 14): volume moving averages and volume-price trend.

The money-flow and accumulation block lives in `money_flow.py`.
"""

from __future__ import annotations

from .registry import register
from .types import IndicatorResult, IndicatorSpec, OHLCVSeries, Tolerance
from .windows import cumulative_with_gaps, previous, rolling_mean, safe_divide

VOLUME_ADJUSTMENT = (
    "Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. "
    "Any indicator that multiplies a price by a volume therefore mixes an adjusted "
    "series with an unadjusted one, and its level is comparable over time only up to "
    "the next corporate action. Ratios of volume to its own moving average, which is "
    "how the screener should use these, are unaffected."
)


@register(
    IndicatorSpec(
        indicator_id="volume_sma",
        title="Volume simple moving average",
        block="volume",
        outputs=("value", "relative_volume"),
        parameters={"period": 20},
        formula=(
            "value[i] = mean(volume[i - period + 1 .. i]); "
            "relative_volume[i] = volume[i] / value[i], so 1.0 is an average day and "
            "3.0 is three times the recent average."
        ),
        input_price="Volume in shares; no price input.",
        adjustment_convention=VOLUME_ADJUSTMENT,
        warm_up="period - 1 bars.",
        missing_value_behavior=(
            "Windowed rule: NaN whenever the window is incomplete or contains a NaN "
            "volume. A genuine zero-volume session is a valid observation, not a "
            "missing one, and is averaged in as zero; relative_volume is then NaN "
            "only if the average itself is zero (an entire window of no trading), "
            "which Section 19.2 treats as an inactivity signal rather than an error."
        ),
        comparison_reference=(
            "Naive reference implementation plus hand-computed cases. AmiBroker "
            "MA(Volume, n) cross-check pending an export."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation. Volumes reach 1e7 and "
                "above, so the relative arm dominates."
            ),
        ),
        warm_up_bars=lambda period=20: max(0, int(period) - 1),
    )
)
def volume_simple_moving_average(series: OHLCVSeries, *, period: int = 20) -> IndicatorResult:
    average = rolling_mean(series.volume, period)
    return IndicatorResult(
        indicator_id="volume_sma",
        parameters={"period": period},
        series={
            "value": average,
            "relative_volume": safe_divide(series.volume, average),
        },
    )


@register(
    IndicatorSpec(
        indicator_id="volume_price_trend",
        title="Volume-price trend",
        block="volume",
        outputs=("value", "contribution"),
        parameters={},
        formula=(
            "contribution[i] = volume[i] * (close[i] - close[i-1]) / close[i-1]; "
            "value[i] = value[i-1] + contribution[i], a running total starting from "
            "zero at the first defined contribution."
        ),
        input_price="Close for the return, volume in shares for the weight.",
        adjustment_convention=VOLUME_ADJUSTMENT,
        warm_up="1 bar; the first bar has no previous close.",
        missing_value_behavior=(
            "Cumulative rule: NaN at a bar whose contribution is undefined, with the "
            "running total unchanged across the gap. The level of a cumulative "
            "volume series has no absolute meaning, so resuming at the same level is "
            "safe; the direction and slope, which are what the indicator is read "
            "for, stay intact."
        ),
        comparison_reference=(
            "Naive reference implementation plus a hand-computed three-bar case. No "
            "AmiBroker built-in is assumed; if a comparison is wanted the AFL must "
            "state its own starting value, since the origin is arbitrary. Compare "
            "differences of the series, not levels."
        ),
        tolerance=Tolerance(
            absolute=1e-6,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation. The absolute arm is "
                "loose because the running total reaches 1e8 and above on liquid "
                "names, where one unit in the last place is already about 1e-8 "
                "relative."
            ),
        ),
        warm_up_bars=lambda: 1,
    )
)
def volume_price_trend(series: OHLCVSeries) -> IndicatorResult:
    previous_close = previous(series.close)
    contribution = series.volume * safe_divide(series.close - previous_close, previous_close)
    return IndicatorResult(
        indicator_id="volume_price_trend",
        parameters={},
        series={
            "value": cumulative_with_gaps(contribution),
            "contribution": contribution,
        },
    )
