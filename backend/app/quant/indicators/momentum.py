"""Momentum indicators (Section 14). Currently the relative strength index."""

from __future__ import annotations

import numpy as np

from .registry import register
from .trend import ADJUSTMENT
from .types import IndicatorResult, IndicatorSpec, OHLCVSeries, Tolerance
from .windows import previous, safe_divide, wilder_smoothing


@register(
    IndicatorSpec(
        indicator_id="rsi",
        title="Relative strength index (Wilder)",
        block="momentum",
        outputs=("value",),
        parameters={"period": 14},
        formula=(
            "change[i] = close[i] - close[i - 1]; gain = max(change, 0); "
            "loss = max(-change, 0); avg_gain and avg_loss are Wilder-smoothed over "
            "`period` (seed = simple mean of the first `period` values, then "
            "s[i] = s[i-1] + (x[i] - s[i-1]) / period); "
            "RSI = 100 * avg_gain / (avg_gain + avg_loss). "
            "That last expression is algebraically identical to the published "
            "100 - 100 / (1 + avg_gain / avg_loss) whenever avg_loss > 0, and it "
            "avoids a division by zero: a window with no down days returns exactly "
            "100, and a completely flat window (no up and no down movement) returns "
            "NaN because the index is genuinely undefined there rather than "
            "conventionally 50 or 100."
        ),
        input_price="Close.",
        adjustment_convention=ADJUSTMENT,
        warm_up=(
            "period bars. `period` price changes are needed, which requires "
            "period + 1 closes, so the first defined value sits at index `period`."
        ),
        missing_value_behavior=(
            "A missing close makes two changes undefined (the one into it and the "
            "one out of it). The Wilder recursion then applies the gap re-seed rule, "
            "so a gap costs a further full `period` of warm-up and never propagates "
            "past that."
        ),
        comparison_reference=(
            "Naive reference implementation of Wilder's recursion in "
            "tests/quant/reference.py, plus a hand-computed case with a known "
            "closed-form answer (a strictly rising series must give exactly 100, a "
            "strictly falling series exactly 0). AmiBroker RSI() cross-check pending "
            "an export."
        ),
        tolerance=Tolerance(
            absolute=1e-8,
            relative=1e-8,
            basis=(
                "Against the naive reference implementation. RSI is bounded on "
                "[0, 100], so the absolute arm dominates. A 1e-3 absolute allowance "
                "is proposed for the pending AmiBroker cross-check."
            ),
        ),
        warm_up_bars=lambda period=14: max(0, int(period)),
    )
)
def relative_strength_index(series: OHLCVSeries, *, period: int = 14) -> IndicatorResult:
    change = series.close - previous(series.close)
    gain = np.where(np.isfinite(change), np.maximum(change, 0.0), np.nan)
    loss = np.where(np.isfinite(change), np.maximum(-change, 0.0), np.nan)
    average_gain = wilder_smoothing(gain, period)
    average_loss = wilder_smoothing(loss, period)
    values = 100.0 * safe_divide(average_gain, average_gain + average_loss)
    return IndicatorResult(
        indicator_id="rsi",
        parameters={"period": period},
        series={"value": values},
    )
