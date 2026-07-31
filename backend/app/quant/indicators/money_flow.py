"""Money-flow and accumulation block (Section 14).

Section 14 makes this block a first-class requirement, not an optional
extra: it exists to answer whether large money appears to be entering a
security and whether accumulation is visible. Its members are the
accumulation/distribution line, on-balance volume, the up-day versus
down-day volume ratio, volume-at-price concentration, and unusual-volume
flags. Close-versus-VWAP joins the block only once `Aux1` is confirmed as
unadjusted VWAP.

Everything here is deterministic arithmetic on bars the caller already
holds. Nothing in this module interprets the numbers. Section 18.1 puts
interpretation in the AI layer, and the AI layer never computes: it reads
the values produced here.

Two market-structure facts about Vietnamese equities shape the conventions
below and are repeated in each indicator's documentation because they
change how the outputs should be read:

- HOSE, HNX, and UPCoM all impose daily price bands. On a limit day a bar
  can print high == low == close, which makes the classic money-flow
  multiplier a 0/0 form. The convention adopted here is the standard one,
  multiplier = 0, which scores the single most one-sided session in the
  band regime as neutral flow. The count of such bars is reported in
  `zero_range_bars` so a reader can see how often the convention bit.
- Prices are back-adjusted and volume is not (Section 19.1). Cumulative
  price-weighted volume series are therefore comparable over time only
  between corporate actions. Read their slope, not their level.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from .registry import register
from .types import (
    IndicatorError,
    IndicatorResult,
    IndicatorSpec,
    OHLCVSeries,
    Tolerance,
)
from .volume import VOLUME_ADJUSTMENT
from .windows import (
    cumulative_with_gaps,
    previous,
    rolling_median,
    rolling_sum,
    safe_divide,
)


class MoneyFlowUndefined(IndicatorError):
    """Raised when a required money-flow block value is not defined.

    The contract (`money_flow_block.schema.json`) requires
    `accumulation_distribution_line`, `on_balance_volume`,
    `up_down_volume_ratio`, and `volume_at_price_concentration` to be
    present and numeric, and JSON has no representation for NaN or
    infinity. Rather than substituting a placeholder number, the builder
    refuses and names what is missing.
    """


@register(
    IndicatorSpec(
        indicator_id="accumulation_distribution",
        title="Accumulation/distribution line",
        block="money_flow",
        outputs=("value", "money_flow_multiplier", "money_flow_volume"),
        parameters={},
        formula=(
            "money_flow_multiplier[i] = ((close - low) - (high - close)) / (high - low), "
            "which simplifies to (2 * close - high - low) / (high - low) and lies in "
            "[-1, +1]; money_flow_volume[i] = multiplier * volume; "
            "value[i] = value[i-1] + money_flow_volume[i]."
        ),
        input_price="High, low, and close of the same bar; volume in shares.",
        adjustment_convention=VOLUME_ADJUSTMENT,
        warm_up=(
            "None. The multiplier uses only the current bar, so the first bar "
            "already has a value."
        ),
        missing_value_behavior=(
            "NaN wherever high, low, close, or volume is missing, with the running "
            "total unchanged across the gap (cumulative rule). "
            "ZERO-RANGE CONVENTION: when high == low the multiplier is 0/0 and is "
            "set to 0, the standard convention. In Vietnam this is not a rare "
            "degenerate case: a limit-up or limit-down session prints high == low, "
            "so the most one-sided sessions contribute nothing to this line. The "
            "count of affected bars is returned as the `zero_range_bars` scalar, and "
            "on-balance volume, which has no such blind spot, should be read "
            "alongside it."
        ),
        comparison_reference=(
            "Naive reference implementation plus a hand-computed three-bar case "
            "covering one ordinary bar, one close-at-high bar (multiplier exactly "
            "+1), and one zero-range bar (multiplier 0 by convention). The origin of "
            "the cumulative series is arbitrary and starts at the first defined "
            "bar's money flow volume, so any external comparison must be on "
            "differences, not levels."
        ),
        tolerance=Tolerance(
            absolute=1e-6,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation, on differences of the "
                "series. The absolute arm is loose because the running total reaches "
                "1e8 and above on liquid names."
            ),
        ),
        warm_up_bars=lambda: 0,
        scalar_outputs=("zero_range_bars",),
    )
)
def accumulation_distribution(series: OHLCVSeries) -> IndicatorResult:
    span = series.high - series.low
    multiplier = safe_divide(2.0 * series.close - series.high - series.low, span)

    bar_defined = (
        np.isfinite(series.high)
        & np.isfinite(series.low)
        & np.isfinite(series.close)
        & np.isfinite(series.volume)
    )
    zero_range = bar_defined & (span == 0.0)
    multiplier = np.where(zero_range, 0.0, multiplier)
    multiplier = np.where(bar_defined, multiplier, np.nan)

    money_flow_volume = multiplier * series.volume
    return IndicatorResult(
        indicator_id="accumulation_distribution",
        parameters={},
        series={
            "value": cumulative_with_gaps(money_flow_volume),
            "money_flow_multiplier": multiplier,
            "money_flow_volume": money_flow_volume,
        },
        scalars={"zero_range_bars": int(np.count_nonzero(zero_range))},
    )


@register(
    IndicatorSpec(
        indicator_id="on_balance_volume",
        title="On-balance volume",
        block="money_flow",
        outputs=("value", "signed_volume"),
        parameters={},
        formula=(
            "signed_volume[i] = +volume[i] if close[i] > close[i-1], "
            "-volume[i] if close[i] < close[i-1], 0 if unchanged; "
            "value[i] = value[i-1] + signed_volume[i]."
        ),
        input_price="Close, for direction only; volume in shares for magnitude.",
        adjustment_convention=(
            VOLUME_ADJUSTMENT
            + " Direction is taken from the adjusted close, so a price change that "
            "is purely a corporate-action artifact can sign a day's volume. Days on "
            "which the security master records a corporate action should be treated "
            "as unreliable for this indicator."
        ),
        warm_up="1 bar; the first bar has no previous close to compare against.",
        missing_value_behavior=(
            "NaN wherever the close, the previous close, or the volume is missing, "
            "with the running total unchanged across the gap (cumulative rule). "
            "Unlike the accumulation/distribution line, on-balance volume has no "
            "zero-range blind spot: a limit-up session is signed fully positive."
        ),
        comparison_reference=(
            "Naive reference implementation plus a hand-computed four-bar case "
            "covering an up day, a down day, and an unchanged day. Origin is "
            "arbitrary; compare differences, not levels."
        ),
        tolerance=Tolerance(
            absolute=1e-6,
            relative=1e-9,
            basis="Against the naive reference implementation, on differences.",
        ),
        warm_up_bars=lambda: 1,
    )
)
def on_balance_volume(series: OHLCVSeries) -> IndicatorResult:
    change = series.close - previous(series.close)
    defined = np.isfinite(change) & np.isfinite(series.volume)
    signed = np.where(defined, np.sign(change) * series.volume, np.nan)
    return IndicatorResult(
        indicator_id="on_balance_volume",
        parameters={},
        series={"value": cumulative_with_gaps(signed), "signed_volume": signed},
    )


@register(
    IndicatorSpec(
        indicator_id="up_down_volume_ratio",
        title="Up-day versus down-day volume ratio",
        block="money_flow",
        outputs=("value", "up_volume_share", "up_volume", "down_volume"),
        parameters={"window": 20},
        formula=(
            "Over the trailing `window` bars: up_volume = sum of volume on bars "
            "where close > previous close; down_volume = sum of volume on bars where "
            "close < previous close; unchanged bars are counted in neither. "
            "value = up_volume / down_volume; "
            "up_volume_share = up_volume / (up_volume + down_volume)."
        ),
        input_price="Close for direction, volume in shares for magnitude.",
        adjustment_convention=VOLUME_ADJUSTMENT,
        warm_up=(
            "window bars. The direction of the first bar is undefined, so `window` "
            "signed bars require window + 1 closes and the first defined value sits "
            "at index `window`."
        ),
        missing_value_behavior=(
            "Windowed rule on the two sums: NaN if any bar in the window has a "
            "missing close or volume. `value` is additionally NaN when down_volume "
            "is zero, which is a real Vietnamese case during a limit-up streak "
            "rather than a defect; `up_volume_share` stays defined there and equals "
            "1.0, which is why both are exposed. safe_divide returns NaN rather than "
            "an infinity so the undefined case cannot survive unnoticed into a "
            "strategy comparison."
        ),
        comparison_reference=(
            "Naive reference implementation plus a hand-computed case with a known "
            "answer (three up days of 100 shares against two down days of 50 gives "
            "exactly 3.0 and a share of 0.75). No standard external reference "
            "exists; this is a defined statistic rather than a published indicator, "
            "so its definition here is the reference."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis="Against the naive reference implementation.",
        ),
        warm_up_bars=lambda window=20: max(0, int(window)),
    )
)
def up_down_volume_ratio(series: OHLCVSeries, *, window: int = 20) -> IndicatorResult:
    change = series.close - previous(series.close)
    defined = np.isfinite(change) & np.isfinite(series.volume)

    up = np.where(defined, np.where(change > 0.0, series.volume, 0.0), np.nan)
    down = np.where(defined, np.where(change < 0.0, series.volume, 0.0), np.nan)

    up_sum = rolling_sum(up, window)
    down_sum = rolling_sum(down, window)
    return IndicatorResult(
        indicator_id="up_down_volume_ratio",
        parameters={"window": window},
        series={
            "value": safe_divide(up_sum, down_sum),
            "up_volume_share": safe_divide(up_sum, up_sum + down_sum),
            "up_volume": up_sum,
            "down_volume": down_sum,
        },
    )


@register(
    IndicatorSpec(
        indicator_id="unusual_volume",
        title="Unusual-volume flags",
        block="money_flow",
        outputs=("flag", "ratio", "baseline"),
        parameters={"window": 20, "multiple": 2.0},
        formula=(
            "baseline[i] = median(volume[i - window .. i - 1]), the trailing median "
            "excluding the current bar; ratio[i] = volume[i] / baseline[i]; "
            "flag[i] = 1.0 when ratio[i] >= multiple, else 0.0."
        ),
        input_price="Volume in shares; no price input.",
        adjustment_convention=VOLUME_ADJUSTMENT,
        warm_up=(
            "window bars, because the baseline excludes the current bar and needs "
            "`window` prior bars."
        ),
        missing_value_behavior=(
            "All three outputs are NaN when the current volume is missing or the "
            "trailing window is incomplete or contains a missing volume. ratio and "
            "flag are NaN when the baseline median is zero, which happens for a "
            "security that has not traded for most of the window; Section 19.2 "
            "treats such runs as an inactivity signal, and flagging the first trade "
            "after a dormant month as an infinite volume spike would be noise."
        ),
        comparison_reference=(
            "Naive reference implementation plus hand-computed cases. The median "
            "baseline is chosen over a mean because a single prior spike would "
            "otherwise raise the bar enough to hide the next one; the current bar is "
            "excluded so that a large bar cannot inflate its own baseline. The "
            "default multiple of 2.0 is a convention with no external authority: "
            "Section 14 requires unusual-volume flags but sets no threshold, so the "
            "threshold is a parameter and the screener should tune it per liquidity "
            "band rather than treat 2.0 as meaningful."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation. `flag` is exact, being "
                "0.0 or 1.0; note that a ratio exactly equal to `multiple` flags, "
                "the comparison being >=."
            ),
        ),
        warm_up_bars=lambda window=20, multiple=2.0: max(0, int(window)),
    )
)
def unusual_volume(
    series: OHLCVSeries, *, window: int = 20, multiple: float = 2.0
) -> IndicatorResult:
    if float(multiple) <= 0:
        raise IndicatorError("multiple must be positive")

    trailing_median = previous(rolling_median(series.volume, window))
    ratio = safe_divide(series.volume, trailing_median)
    flag = np.where(np.isfinite(ratio), (ratio >= float(multiple)).astype(np.float64), np.nan)
    return IndicatorResult(
        indicator_id="unusual_volume",
        parameters={"window": window, "multiple": multiple},
        series={"flag": flag, "ratio": ratio, "baseline": trailing_median},
    )


@register(
    IndicatorSpec(
        indicator_id="volume_at_price",
        title="Volume-at-price concentration",
        block="money_flow",
        outputs=("typical_price",),
        parameters={"lookback": 120, "bins": 20, "value_area_share": 0.70},
        formula=(
            "typical_price[i] = (high + low + close) / 3. Over the last `lookback` "
            "bars, the price span [min(low), max(high)] is divided into `bins` equal "
            "width bins and each bar's entire volume is assigned to the bin "
            "containing its typical price. From that histogram: "
            "point_of_control is the bin holding the most volume; "
            "herfindahl is the sum of squared bin shares (1 / bins under a perfectly "
            "flat distribution, 1.0 when all volume sits in one bin); "
            "normalized_herfindahl rescales that onto [0, 1]; the value area is the "
            "smallest set of bins, taken in descending volume order with ties broken "
            "by the lower bin, whose combined share reaches `value_area_share`."
        ),
        input_price=(
            "High, low, and close, combined into the typical price; volume in shares."
        ),
        adjustment_convention=(
            VOLUME_ADJUSTMENT
            + " The histogram is built on back-adjusted prices, so its bin prices are "
            "adjusted prices and will not line up with an unadjusted chart if a "
            "corporate action falls inside the lookback window."
        ),
        warm_up=(
            "The histogram needs at least one bar with a defined typical price and "
            "volume inside the lookback; the `typical_price` series itself has no "
            "warm-up."
        ),
        missing_value_behavior=(
            "Bars with a missing typical price or volume are excluded from the "
            "histogram, and the count of excluded bars is reported as "
            "`excluded_bars` so a thin histogram is visible rather than implied. If "
            "no bar survives, or if every surviving bar shares one price so the span "
            "is zero, the scalars are returned as None rather than as a degenerate "
            "single-bin histogram."
        ),
        comparison_reference=(
            "Naive reference implementation plus a hand-computed case with a "
            "constructed histogram. This is a defined statistic rather than a "
            "published indicator. Two modelling choices are conventions, not "
            "measurements, and a different tool will disagree without either being "
            "wrong: assigning a bar's whole volume to the typical-price bin, rather "
            "than spreading it across the high-low range, and choosing the value "
            "area greedily rather than by the classic market-profile expansion from "
            "the point of control. Spreading volume across the range is the more "
            "faithful model and is recorded as a follow-up."
        ),
        tolerance=Tolerance(
            absolute=1e-9,
            relative=1e-9,
            basis=(
                "Against the naive reference implementation, for the histogram and "
                "every derived share. Bin assignment at an exact bin boundary is "
                "resolved to the lower bin, and the top edge to the last bin, so "
                "boundary cases are deterministic rather than tolerance-dependent."
            ),
        ),
        warm_up_bars=lambda lookback=120, bins=20, value_area_share=0.70: 0,
        scalar_outputs=(
            "bin_edges",
            "bin_volume",
            "bin_volume_share",
            "point_of_control_price",
            "point_of_control_share",
            "top_three_bin_share",
            "herfindahl",
            "normalized_herfindahl",
            "value_area_low",
            "value_area_high",
            "included_bars",
            "excluded_bars",
        ),
    )
)
def volume_at_price(
    series: OHLCVSeries,
    *,
    lookback: int = 120,
    bins: int = 20,
    value_area_share: float = 0.70,
) -> IndicatorResult:
    if int(bins) < 2:
        raise IndicatorError("bins must be >= 2")
    if int(lookback) < 1:
        raise IndicatorError("lookback must be >= 1")
    if not 0.0 < float(value_area_share) <= 1.0:
        raise IndicatorError("value_area_share must lie in (0, 1]")

    typical = (series.high + series.low + series.close) / 3.0

    window_typical = typical[-int(lookback) :]
    window_volume = series.volume[-int(lookback) :]
    window_high = series.high[-int(lookback) :]
    window_low = series.low[-int(lookback) :]

    usable = np.isfinite(window_typical) & np.isfinite(window_volume)
    included = int(np.count_nonzero(usable))
    excluded = int(len(window_typical) - included)

    empty: dict[str, Any] = {
        "bin_edges": None,
        "bin_volume": None,
        "bin_volume_share": None,
        "point_of_control_price": None,
        "point_of_control_share": None,
        "top_three_bin_share": None,
        "herfindahl": None,
        "normalized_herfindahl": None,
        "value_area_low": None,
        "value_area_high": None,
        "included_bars": included,
        "excluded_bars": excluded,
    }

    if included == 0:
        return IndicatorResult(
            indicator_id="volume_at_price",
            parameters={
                "lookback": lookback,
                "bins": bins,
                "value_area_share": value_area_share,
            },
            series={"typical_price": typical},
            scalars=empty,
        )

    finite_low = window_low[np.isfinite(window_low)]
    finite_high = window_high[np.isfinite(window_high)]
    lower = float(np.min(finite_low)) if len(finite_low) else float(np.min(window_typical[usable]))
    upper = float(np.max(finite_high)) if len(finite_high) else float(np.max(window_typical[usable]))
    if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
        return IndicatorResult(
            indicator_id="volume_at_price",
            parameters={
                "lookback": lookback,
                "bins": bins,
                "value_area_share": value_area_share,
            },
            series={"typical_price": typical},
            scalars=empty,
        )

    bin_count = int(bins)
    edges = np.linspace(lower, upper, bin_count + 1)
    width = (upper - lower) / bin_count

    prices = window_typical[usable]
    volumes = window_volume[usable]
    indices = np.floor((prices - lower) / width).astype(np.int64)
    indices = np.clip(indices, 0, bin_count - 1)

    histogram = np.zeros(bin_count, dtype=np.float64)
    np.add.at(histogram, indices, volumes)

    total = float(histogram.sum())
    if total <= 0.0:
        return IndicatorResult(
            indicator_id="volume_at_price",
            parameters={
                "lookback": lookback,
                "bins": bins,
                "value_area_share": value_area_share,
            },
            series={"typical_price": typical},
            scalars=empty,
        )

    shares = histogram / total
    poc_index = int(np.argmax(histogram))
    order = sorted(range(bin_count), key=lambda index: (-histogram[index], index))

    selected: list[int] = []
    accumulated = 0.0
    for index in order:
        selected.append(index)
        accumulated += float(shares[index])
        if accumulated >= float(value_area_share):
            break

    midpoints = (edges[:-1] + edges[1:]) / 2.0
    scalars: dict[str, Any] = {
        "bin_edges": [round(float(edge), 6) for edge in edges],
        "bin_volume": [float(value) for value in histogram],
        "bin_volume_share": [float(value) for value in shares],
        "point_of_control_price": round(float(midpoints[poc_index]), 6),
        "point_of_control_share": float(shares[poc_index]),
        "top_three_bin_share": float(np.sum(np.sort(shares)[::-1][:3])),
        "herfindahl": float(np.sum(shares**2)),
        "normalized_herfindahl": float(
            (np.sum(shares**2) - 1.0 / bin_count) / (1.0 - 1.0 / bin_count)
        ),
        "value_area_low": round(float(edges[min(selected)]), 6),
        "value_area_high": round(float(edges[max(selected) + 1]), 6),
        "included_bars": included,
        "excluded_bars": excluded,
    }

    return IndicatorResult(
        indicator_id="volume_at_price",
        parameters={
            "lookback": lookback,
            "bins": bins,
            "value_area_share": value_area_share,
        },
        series={"typical_price": typical},
        scalars=scalars,
    )


def close_versus_vwap(
    unadjusted_close: Any,
    vwap: Any,
) -> np.ndarray:
    """Percentage position of the close relative to the day's average price.

    `100 * (unadjusted_close / vwap - 1)`, positive when the session closed
    above its own volume-weighted average and negative when it closed below.

    Both arguments must be on the SAME adjustment basis, and specifically
    both must be UNADJUSTED. `docs/data_dictionary.md` records the WP1
    verification of 30 July 2026 concluding that FData's `Aux1` is the
    unadjusted daily average price, while Section 19.1 records that OHLC is
    back-adjusted. Feeding `OHLCVSeries.close` into this function would
    therefore divide an adjusted price by an unadjusted one, which is
    correct only for bars after the most recent corporate action and
    silently wrong for every bar before it. The function takes the
    unadjusted close as an explicit argument rather than reading it off the
    series precisely so that this cannot happen by accident.

    Section 14 admits this measure to the money-flow block "once Aux1 is
    confirmed as unadjusted VWAP". The confirmation now exists, but three
    things stand between it and the block, and they belong to other owners:
    the canonical `PriceBar` contract carries no VWAP or unadjusted-close
    field, so there is no way to deliver the inputs; the data dictionary's
    own safeguard states that `Aux1` "remains excluded from the canonical
    PriceBar, Parquet bar schema, API responses, indicators, and every
    calculation" pending an explicit downstream design decision; and the
    same entry limits the verification to five liquid HOSE equities on one
    session, with corporate-action dates and non-equity categories still
    untested. The mathematics is therefore implemented and tested here and
    left unwired, and `build_money_flow_block` accepts the finished value
    from a caller that can legitimately produce it.
    """

    close_array = np.asarray(unadjusted_close, dtype=np.float64)
    vwap_array = np.asarray(vwap, dtype=np.float64)
    if close_array.shape != vwap_array.shape:
        raise IndicatorError(
            f"unadjusted_close has shape {close_array.shape} but vwap has "
            f"{vwap_array.shape}; both must cover the same bars"
        )
    return 100.0 * (safe_divide(close_array, vwap_array) - 1.0)


def build_money_flow_block(
    series: OHLCVSeries,
    *,
    close_vs_vwap: float | None = None,
    ratio_window: int = 20,
    unusual_window: int = 20,
    unusual_multiple: float = 2.0,
    unusual_flag_lookback: int = 60,
    vap_lookback: int = 120,
    vap_bins: int = 20,
    value_area_share: float = 0.70,
) -> dict[str, Any]:
    """Assemble the block in the shape of `money_flow_block.schema.json`.

    Returns latest values for the three scalar members, the volume-at-price
    summary as the open object the contract allows, and the ISO dates of
    unusual-volume bars within `unusual_flag_lookback` bars of the end.

    `close_vs_vwap` defaults to None and is only ever the value the caller
    passed in. Nothing here derives it, because the inputs it needs are not
    in `OHLCVSeries` and are not in the canonical `PriceBar` contract; see
    `close_versus_vwap` above for the full reasoning and for the correct
    formula once the data layer can supply an unadjusted close and an
    unadjusted VWAP on the same basis.

    Raises `MoneyFlowUndefined` when a contract-required value is not
    defined, naming the reason, because the contract types those fields as
    required numbers and JSON cannot carry NaN or infinity. The most common
    causes are a series shorter than the warm-up and, for the ratio, a
    window with no down-volume at all.
    """

    if len(series) == 0:
        raise MoneyFlowUndefined("cannot build a money-flow block from an empty series")

    ad = accumulation_distribution(series)
    obv = on_balance_volume(series)
    ratio = up_down_volume_ratio(series, window=ratio_window)
    flags = unusual_volume(series, window=unusual_window, multiple=unusual_multiple)
    vap = volume_at_price(
        series, lookback=vap_lookback, bins=vap_bins, value_area_share=value_area_share
    )

    required = {
        "accumulation_distribution_line": ad.last("value"),
        "on_balance_volume": obv.last("value"),
        "up_down_volume_ratio": ratio.last("value"),
    }
    for name, value in required.items():
        if not np.isfinite(value):
            if name == "up_down_volume_ratio" and np.isfinite(ratio.last("down_volume")):
                raise MoneyFlowUndefined(
                    "up_down_volume_ratio is undefined because down-volume over the "
                    f"last {ratio_window} bars is zero (up-volume share is "
                    f"{ratio.last('up_volume_share')}). The contract types this "
                    "field as a required number, so the caller must decide how to "
                    "present it; see the WP5 handoff note proposing that the field "
                    "become nullable with up_volume_share added alongside."
                )
            raise MoneyFlowUndefined(
                f"{name} is undefined at the last bar; the series has "
                f"{len(series)} bars, which is probably shorter than the indicator's "
                "warm-up, or the last bars contain missing values."
            )

    flag_values = flags["flag"]
    start = max(0, len(flag_values) - int(unusual_flag_lookback))
    flagged_dates: list[str] = []
    for offset in range(start, len(flag_values)):
        value = flag_values[offset]
        if np.isfinite(value) and value >= 1.0:
            trading_day: date = series.trading_dates[offset]
            flagged_dates.append(trading_day.isoformat())

    concentration = dict(vap.scalars)
    concentration["method"] = (
        "typical-price binning over the trailing lookback; see the volume_at_price "
        "indicator specification for the exact definition and its two conventions"
    )
    concentration["lookback"] = vap_lookback
    concentration["bins"] = vap_bins
    concentration["value_area_share"] = value_area_share

    return {
        "accumulation_distribution_line": float(required["accumulation_distribution_line"]),
        "on_balance_volume": float(required["on_balance_volume"]),
        "up_down_volume_ratio": float(required["up_down_volume_ratio"]),
        "volume_at_price_concentration": concentration,
        "unusual_volume_flags": flagged_dates,
        "close_vs_vwap": None if close_vs_vwap is None else float(close_vs_vwap),
    }
