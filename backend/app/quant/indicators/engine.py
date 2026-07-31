"""Batch computation and contract serialization for the indicator engine.

The engine turns a set of indicator requests into the body of
`indicators_response.schema.json`. It deliberately does not build the
`provenance` object: provenance is the data layer's statement about the
bars, and inventing one here would let the quant layer assert a data
version and freshness status it has no knowledge of. `build_indicators_payload`
returns everything except `provenance`, and the API owner merges the
provenance that came with the bars.

**Series naming convention.** `IndicatorSeries.indicator_id` in the contract
is a single free-text string, and it is the only identifying field a series
carries. That one string therefore has to distinguish three things the
contract does not model separately: which indicator, which of its outputs,
and which parameters it was run at. A chart showing the 20, 50, and 200 day
moving averages would otherwise send three different lines all labelled
`sma`. The rule is:

- Default parameters, single output: the bare id, so `sma`, `ema`, and `rsi`
  appear exactly as the contract's examples show.
- Non-default parameters: a bracketed suffix listing only the parameters
  that differ from the documented defaults, sorted by name, as in
  `sma[period=50]`.
- More than one output: a dot and the output name, as in `macd.signal` and
  `bollinger_bands.upper`.

Neither `.` nor `[` appears in any indicator id or output name, so a
consumer can parse the three parts unambiguously.
`build_indicators_payload` refuses to emit a payload containing two series
with the same id, so a collision fails loudly here rather than silently
overwriting a line in the frontend.

This is a convention layered on an open string field rather than a contract
change. The cleaner fix is for `IndicatorSeries` to carry `parameters` and
`output` as their own fields, which is raised as a change proposal in the
WP5 handoff.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import registry
from .money_flow import build_money_flow_block
from .types import IndicatorError, IndicatorResult, OHLCVSeries


@dataclass(frozen=True, slots=True)
class IndicatorRequest:
    """One indicator to compute, with any parameter overrides."""

    indicator_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


#: The Section 14 initial indicator list at its documented default parameters.
#: Relative strength is absent because it needs a benchmark series, which in
#: turn needs the index code-to-name mapping the data stream owns; pass those
#: requests explicitly once the mapping exists.
DEFAULT_INDICATOR_SET: tuple[IndicatorRequest, ...] = (
    IndicatorRequest("sma", {"period": 20}),
    IndicatorRequest("sma", {"period": 50}),
    IndicatorRequest("sma", {"period": 200}),
    IndicatorRequest("ema", {"period": 20}),
    IndicatorRequest("rsi", {"period": 14}),
    IndicatorRequest("macd"),
    IndicatorRequest("atr", {"period": 14}),
    IndicatorRequest("bollinger_bands"),
    IndicatorRequest("rolling_high", {"period": 52}),
    IndicatorRequest("rolling_low", {"period": 52}),
    IndicatorRequest("rate_of_change", {"period": 12}),
    IndicatorRequest("volume_sma", {"period": 20}),
    IndicatorRequest("volume_price_trend"),
    IndicatorRequest("pivot_levels"),
    IndicatorRequest("rolling_volatility", {"period": 20}),
    IndicatorRequest("drawdown"),
    IndicatorRequest("accumulation_distribution"),
    IndicatorRequest("on_balance_volume"),
    IndicatorRequest("up_down_volume_ratio", {"window": 20}),
    IndicatorRequest("unusual_volume", {"window": 20, "multiple": 2.0}),
    IndicatorRequest("volume_at_price"),
)


def compute_many(
    series: OHLCVSeries,
    requests: Sequence[IndicatorRequest] = DEFAULT_INDICATOR_SET,
) -> tuple[IndicatorResult, ...]:
    """Run every request against one security's bars, in the order given."""

    return tuple(
        registry.compute(request.indicator_id, series, **dict(request.parameters))
        for request in requests
    )


def _parameter_suffix(indicator_id: str, parameters: Mapping[str, Any]) -> str:
    """`[name=value,...]` for parameters that differ from the documented defaults."""

    defaults = registry.spec(indicator_id).parameters
    differing: list[str] = []
    for name in sorted(parameters):
        value = parameters[name]
        if name not in defaults or value == defaults[name]:
            continue
        if name == "benchmark":
            # A benchmark is an object; identify it by its index code.
            differing.append(f"benchmark={getattr(value, 'code', value)}")
        elif isinstance(value, float) and value.is_integer():
            differing.append(f"{name}={int(value)}")
        else:
            differing.append(f"{name}={value}")
    return f"[{','.join(differing)}]" if differing else ""


def series_key(
    indicator_id: str,
    output: str,
    outputs: Sequence[str],
    parameters: Mapping[str, Any] | None = None,
) -> str:
    """Contract `indicator_id` for one output line; see the module docstring."""

    key = indicator_id + _parameter_suffix(indicator_id, parameters or {})
    if tuple(outputs) == ("value",):
        return key
    return f"{key}.{output}"


def _points(
    trading_dates: Sequence[Any], values: np.ndarray
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for trading_day, value in zip(trading_dates, values):
        numeric = float(value)
        points.append(
            {
                "trading_date": trading_day.isoformat(),
                "value": None if not np.isfinite(numeric) else numeric,
            }
        )
    return points


def to_indicator_series(
    series: OHLCVSeries, result: IndicatorResult
) -> list[dict[str, Any]]:
    """One `IndicatorSeries` payload per output line of `result`.

    NaN becomes null, which is what `IndicatorPoint.value` is typed as and
    what Section 14's missing-value requirement needs a wire representation
    for. Values are emitted at full float64 precision; rounding for display
    belongs to the frontend, not to the numbers of record.
    """

    outputs = registry.spec(result.indicator_id).outputs
    payload: list[dict[str, Any]] = []
    for output in outputs:
        payload.append(
            {
                "indicator_id": series_key(
                    result.indicator_id, output, outputs, result.parameters
                ),
                "values": _points(series.trading_dates, result[output]),
            }
        )
    return payload


def build_indicators_payload(
    series: OHLCVSeries,
    requests: Sequence[IndicatorRequest] = DEFAULT_INDICATOR_SET,
    *,
    timeframe: str = "1D",
    money_flow_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Body of `indicators_response.schema.json` without `provenance`.

    The caller adds `provenance`, which must be the provenance of the bars
    that were passed in. See the module docstring for why it is not
    synthesized here.
    """

    results = compute_many(series, requests)
    indicators: list[dict[str, Any]] = []
    for result in results:
        indicators.extend(to_indicator_series(series, result))

    seen: set[str] = set()
    duplicates = sorted(
        {
            item["indicator_id"]
            for item in indicators
            if item["indicator_id"] in seen or seen.add(item["indicator_id"])
        }
    )
    if duplicates:
        raise IndicatorError(
            f"the request set produces duplicate series ids {duplicates}. The contract "
            "identifies a series by that one string, so two lines sharing an id would "
            "silently overwrite each other in the frontend. Requesting the same "
            "indicator twice at the same parameters is the usual cause."
        )

    return {
        "symbol": series.symbol,
        "timeframe": timeframe,
        "indicators": indicators,
        "money_flow": build_money_flow_block(series, **dict(money_flow_options or {})),
    }
