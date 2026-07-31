"""Batch computation and contract serialization.

Checks that what the engine emits is exactly what
`indicators_response.schema.json` accepts, that NaN reaches the wire as
null rather than as a number, and that the multi-output series naming
convention is stable and unambiguous.
"""

from __future__ import annotations

import json

import jsonschema
import numpy as np
import pytest
from helpers import load_fixture

from backend.app.quant.indicators import (
    DEFAULT_INDICATOR_SET,
    IndicatorRequest,
    OHLCVSeries,
    build_indicators_payload,
    build_levels,
    compute,
    compute_many,
    series_key,
    spec,
    to_indicator_series,
)


@pytest.fixture(scope="module")
def indicators_schema(repo_root):
    path = repo_root / "contracts" / "schemas" / "json" / "indicators_response.schema.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("symbol", ["FPT", "KDH"])
def test_payload_validates_against_the_contract(symbol, indicators_schema, request):
    fixture = load_fixture(f"bars_{symbol}.json")
    series = OHLCVSeries.from_bars(fixture["bars"])
    payload = build_indicators_payload(series)
    payload["provenance"] = fixture["provenance"]
    jsonschema.validate(payload, indicators_schema)


def test_payload_is_json_serializable_without_nan(fpt: OHLCVSeries):
    """JSON has no NaN literal; a warm-up value must be null, not 'NaN'."""

    payload = build_indicators_payload(fpt)
    encoded = json.dumps(payload, allow_nan=False)
    assert "NaN" not in encoded
    assert '"value": null' in encoded


def test_warm_up_values_are_null_and_later_values_are_numbers(fpt: OHLCVSeries):
    payload = build_indicators_payload(fpt, [IndicatorRequest("sma", {"period": 20})])
    points = payload["indicators"][0]["values"]
    assert len(points) == len(fpt)
    assert all(point["value"] is None for point in points[:19])
    assert all(isinstance(point["value"], float) for point in points[19:])


def test_single_output_indicators_keep_their_bare_contract_id(fpt: OHLCVSeries):
    """`sma`, `ema`, `rsi` appear exactly as the contract's examples show."""

    payload = build_indicators_payload(
        fpt,
        [
            IndicatorRequest("sma", {"period": 20}),
            IndicatorRequest("ema", {"period": 20}),
            IndicatorRequest("rsi", {"period": 14}),
        ],
    )
    assert [item["indicator_id"] for item in payload["indicators"]] == [
        "sma",
        "ema",
        "rsi",
    ]


def test_multi_output_indicators_are_namespaced(fpt: OHLCVSeries):
    payload = build_indicators_payload(fpt, [IndicatorRequest("macd")])
    assert [item["indicator_id"] for item in payload["indicators"]] == [
        "macd.macd",
        "macd.signal",
        "macd.histogram",
    ]


def test_series_ids_are_unique_across_the_default_set(fpt: OHLCVSeries):
    """Three moving averages must be three distinguishable lines."""

    ids = [item["indicator_id"] for item in build_indicators_payload(fpt)["indicators"]]
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    assert not duplicates, f"duplicate series ids: {duplicates}"
    assert {"sma", "sma[period=50]", "sma[period=200]"}.issubset(set(ids))


def test_series_ids_are_splittable_into_indicator_parameters_and_output():
    """A consumer must be able to recover each part from the single string."""

    import re

    pattern = re.compile(r"^(?P<id>[a-z_]+)(?:\[(?P<params>[^\]]*)\])?(?:\.(?P<output>[a-z_]+))?$")
    for name in ("sma", "sma[period=50]", "macd.signal", "bollinger_bands[period=10].upper"):
        match = pattern.match(name)
        assert match, f"{name} does not parse"
        assert match.group("id") in {"sma", "macd", "bollinger_bands"}


def test_series_key_helper_is_consistent_with_the_registry():
    assert series_key("sma", "value", spec("sma").outputs) == "sma"
    assert series_key("sma", "value", spec("sma").outputs, {"period": 20}) == "sma"
    assert (
        series_key("sma", "value", spec("sma").outputs, {"period": 50}) == "sma[period=50]"
    )
    assert series_key("macd", "signal", spec("macd").outputs) == "macd.signal"
    assert (
        series_key("macd", "signal", spec("macd").outputs, {"slow_period": 30})
        == "macd[slow_period=30].signal"
    )


def test_duplicate_requests_are_rejected_rather_than_silently_collapsed(fpt: OHLCVSeries):
    from backend.app.quant.indicators import IndicatorError

    with pytest.raises(IndicatorError, match="duplicate series ids"):
        build_indicators_payload(
            fpt,
            [IndicatorRequest("sma", {"period": 20}), IndicatorRequest("sma", {"period": 20})],
        )


def test_default_set_covers_the_section_14_list_except_relative_strength():
    ids = {request.indicator_id for request in DEFAULT_INDICATOR_SET}
    assert "relative_strength_vnindex" not in ids, (
        "relative strength must stay out of the default set until a benchmark "
        "can be resolved"
    )
    for indicator_id in (
        "sma",
        "ema",
        "rsi",
        "macd",
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
        "up_down_volume_ratio",
        "unusual_volume",
        "volume_at_price",
    ):
        assert indicator_id in ids


def test_engine_does_not_invent_provenance(fpt: OHLCVSeries):
    """Provenance is the data layer's statement, not the quant layer's."""

    payload = build_indicators_payload(fpt)
    assert "provenance" not in payload


def test_compute_many_preserves_request_order(fpt: OHLCVSeries):
    requests = [
        IndicatorRequest("rsi", {"period": 14}),
        IndicatorRequest("sma", {"period": 5}),
        IndicatorRequest("sma", {"period": 10}),
    ]
    results = compute_many(fpt, requests)
    assert [result.indicator_id for result in results] == ["rsi", "sma", "sma"]
    assert results[1].parameters["period"] == 5
    assert results[2].parameters["period"] == 10


def test_to_indicator_series_emits_one_line_per_output(fpt: OHLCVSeries):
    result = compute("bollinger_bands", fpt)
    lines = to_indicator_series(fpt, result)
    assert len(lines) == len(spec("bollinger_bands").outputs)
    assert all(len(line["values"]) == len(fpt) for line in lines)


def test_dates_are_emitted_in_series_order(fpt: OHLCVSeries):
    payload = build_indicators_payload(fpt, [IndicatorRequest("sma", {"period": 5})])
    dates = [point["trading_date"] for point in payload["indicators"][0]["values"]]
    assert dates == [day.isoformat() for day in fpt.trading_dates]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Levels helper
# ---------------------------------------------------------------------------


def test_build_levels_matches_the_contract_shape(fpt: OHLCVSeries, repo_root):
    path = repo_root / "contracts" / "schemas" / "json" / "levels.schema.json"
    with path.open(encoding="utf-8") as handle:
        jsonschema.validate(build_levels(fpt), json.load(handle))


def test_build_levels_leaves_invalidation_to_the_strategy_layer(fpt: OHLCVSeries):
    """Choosing an invalidation level is a strategy view, not an indicator fact."""

    assert build_levels(fpt)["invalidation"] is None


def test_build_levels_are_sorted_deduplicated_and_bracket_the_price(fpt: OHLCVSeries):
    levels = build_levels(fpt)
    assert levels["support"] == sorted(set(levels["support"]))
    assert levels["resistance"] == sorted(set(levels["resistance"]))
    assert min(levels["support"]) <= float(np.nanmax(fpt.high))
    assert max(levels["resistance"]) >= float(np.nanmin(fpt.low))
