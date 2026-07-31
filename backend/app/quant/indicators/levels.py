"""Pivot levels (Section 14) and the contract-shaped support/resistance helper."""

from __future__ import annotations

from typing import Any

import numpy as np

from .registry import register
from .trend import ADJUSTMENT
from .types import IndicatorResult, IndicatorSpec, OHLCVSeries, Tolerance
from .windows import previous


@register(
    IndicatorSpec(
        indicator_id="pivot_levels",
        title="Classic floor-trader pivot levels",
        block="levels",
        outputs=("pivot", "r1", "r2", "r3", "s1", "s2", "s3"),
        parameters={},
        formula=(
            "Using the previous bar's high H, low L, and close C: "
            "pivot = (H + L + C) / 3; r1 = 2 * pivot - L; s1 = 2 * pivot - H; "
            "r2 = pivot + (H - L); s2 = pivot - (H - L); "
            "r3 = H + 2 * (pivot - L); s3 = L - 2 * (H - pivot)."
        ),
        input_price="The previous bar's high, low, and close.",
        adjustment_convention=(
            ADJUSTMENT
            + " Pivot levels are price levels, so a back-adjusted series produces "
            "back-adjusted levels. Comparing a pivot level computed on adjusted data "
            "with a quote from an unadjusted screen is a category error; the caller "
            "must keep both on the same basis."
        ),
        warm_up=(
            "1 bar. The levels published for bar i are computed from bar i - 1, so "
            "they are known before bar i trades and contain no look-ahead."
        ),
        missing_value_behavior=(
            "All seven outputs are NaN when any of the previous bar's high, low, or "
            "close is missing. Nothing is carried forward from an older bar, because "
            "a stale pivot level presented as current would be misleading."
        ),
        comparison_reference=(
            "Closed-form arithmetic; hand-computed cases in the golden fixture. The "
            "period is whatever the caller supplies: pass daily bars for daily "
            "pivots, or a weekly or monthly resampling for weekly or monthly pivots. "
            "Resampling is deliberately outside this function so that the timeframe "
            "conversion has one owner rather than being reimplemented per indicator."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis=(
                "Against hand-computed arithmetic. Note this is the classic pivot "
                "formula; Woodie, Camarilla, DeMark, and Fibonacci variants give "
                "different numbers and are not implemented."
            ),
        ),
        warm_up_bars=lambda: 1,
    )
)
def pivot_levels(series: OHLCVSeries) -> IndicatorResult:
    high = previous(series.high)
    low = previous(series.low)
    close = previous(series.close)

    pivot = (high + low + close) / 3.0
    span = high - low
    return IndicatorResult(
        indicator_id="pivot_levels",
        parameters={},
        series={
            "pivot": pivot,
            "r1": 2.0 * pivot - low,
            "r2": pivot + span,
            "r3": high + 2.0 * (pivot - low),
            "s1": 2.0 * pivot - high,
            "s2": pivot - span,
            "s3": low - 2.0 * (high - pivot),
        },
    )


def build_levels(
    series: OHLCVSeries,
    *,
    lookback: int = 52,
) -> dict[str, Any]:
    """Support and resistance candidates in the shape of `levels.schema.json`.

    Deterministic and mechanical: the support candidates are the latest s1,
    s2, and s3 pivot levels together with the rolling low over `lookback`
    bars; the resistance candidates are r1, r2, r3 and the rolling high.
    Levels are deduplicated, rounded to six decimals to avoid float noise in
    the payload, and sorted.

    `invalidation` is deliberately left null. Section 10.5 places it
    alongside a strategy's entry and exit rules, so choosing it is a
    strategy-layer decision (WP6), not something the indicator engine can
    infer from price alone. Filling it here would fabricate a view.
    """

    pivots = pivot_levels(series)
    highs = np.asarray(series.high, dtype=np.float64)
    lows = np.asarray(series.low, dtype=np.float64)
    window_high = highs[-lookback:] if len(highs) else highs
    window_low = lows[-lookback:] if len(lows) else lows

    def _collect(candidates: list[float]) -> list[float]:
        seen: list[float] = []
        for value in candidates:
            if value is None or not np.isfinite(value):
                continue
            rounded = round(float(value), 6)
            if rounded not in seen:
                seen.append(rounded)
        return sorted(seen)

    resistance = [pivots.last(name) for name in ("r1", "r2", "r3")]
    support = [pivots.last(name) for name in ("s1", "s2", "s3")]
    if len(window_high) and np.any(np.isfinite(window_high)):
        resistance.append(float(np.nanmax(window_high)))
    if len(window_low) and np.any(np.isfinite(window_low)):
        support.append(float(np.nanmin(window_low)))

    return {
        "support": _collect(support),
        "resistance": _collect(resistance),
        "invalidation": None,
    }
