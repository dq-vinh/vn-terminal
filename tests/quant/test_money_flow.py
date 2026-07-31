"""Money-flow and accumulation block (Section 14).

Section 14 makes this block a first-class requirement, so it gets its own
test module rather than sharing the general indicator tests. The cases below
cover the arithmetic, the two conventions that a Vietnamese market makes
consequential (the zero-range bar and a window with no down-volume), and the
contract shape of the assembled block.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import reference
from test_indicator_math import assert_close, build

from backend.app.quant.indicators import (
    MoneyFlowUndefined,
    OHLCVSeries,
    build_money_flow_block,
    compute,
)

NAN = float("nan")


# ---------------------------------------------------------------------------
# Accumulation/distribution line
# ---------------------------------------------------------------------------


def test_money_flow_multiplier_hand_computed():
    series = build(
        [9.0, 12.0, 11.0],
        highs=[10.0, 12.0, 11.0],
        lows=[8.0, 10.0, 11.0],
        volumes=[100.0, 200.0, 300.0],
    )
    result = compute("accumulation_distribution", series)
    # Bar 0 closes at the midpoint: multiplier 0.
    # Bar 1 closes at its high: multiplier exactly +1.
    # Bar 2 has high == low: multiplier 0 by the documented convention.
    assert_close(
        result["money_flow_multiplier"],
        [0.0, 1.0, 0.0],
        "accumulation_distribution",
        "money_flow_multiplier",
    )
    assert_close(
        result["value"], [0.0, 200.0, 200.0], "accumulation_distribution", "value"
    )
    assert result.scalars["zero_range_bars"] == 1


def test_money_flow_multiplier_is_bounded(fpt: OHLCVSeries):
    values = compute("accumulation_distribution", fpt)["money_flow_multiplier"]
    defined = values[np.isfinite(values)]
    assert defined.size > 0
    assert np.all(defined >= -1.0) and np.all(defined <= 1.0)


def test_accumulation_distribution_matches_reference(fpt: OHLCVSeries):
    expected = reference.accumulation_distribution(
        list(fpt.high), list(fpt.low), list(fpt.close), list(fpt.volume)
    )
    assert_close(
        compute("accumulation_distribution", fpt)["value"],
        expected,
        "accumulation_distribution",
        "value",
    )


def test_a_limit_up_bar_is_neutral_for_the_ad_line_but_positive_for_obv():
    """The documented blind spot, made explicit as a regression test.

    A Vietnamese limit-up session can print high == low == close. The
    accumulation/distribution line scores it as zero flow by convention,
    while on-balance volume signs the whole day positive. Anyone reading the
    block must see both, which is why both are members of it.
    """

    series = build(
        [10.0, 10.7],
        highs=[10.0, 10.7],
        lows=[10.0, 10.7],
        volumes=[1000.0, 5000.0],
    )
    ad = compute("accumulation_distribution", series)
    obv = compute("on_balance_volume", series)
    assert ad["money_flow_volume"][1] == pytest.approx(0.0)
    assert obv["signed_volume"][1] == pytest.approx(5000.0)
    assert ad.scalars["zero_range_bars"] == 2


# ---------------------------------------------------------------------------
# On-balance volume
# ---------------------------------------------------------------------------


def test_on_balance_volume_hand_computed():
    series = build([10.0, 11.0, 11.0, 9.0], volumes=[100.0, 200.0, 300.0, 400.0])
    result = compute("on_balance_volume", series)
    # Up, unchanged, down: +200, +0, -400 on a running total from zero.
    assert_close(
        result["signed_volume"], [NAN, 200.0, 0.0, -400.0], "on_balance_volume", "signed_volume"
    )
    assert_close(result["value"], [NAN, 200.0, 200.0, -200.0], "on_balance_volume", "value")


def test_on_balance_volume_matches_reference(fpt: OHLCVSeries):
    assert_close(
        compute("on_balance_volume", fpt)["value"],
        reference.on_balance_volume(list(fpt.close), list(fpt.volume)),
        "on_balance_volume",
        "value",
    )


# ---------------------------------------------------------------------------
# Up-day versus down-day volume ratio
# ---------------------------------------------------------------------------


def test_up_down_volume_ratio_hand_computed():
    """Three up days of 100 against two down days of 50: exactly 3.0."""

    series = build(
        [10.0, 11.0, 12.0, 13.0, 12.5, 12.0],
        volumes=[999.0, 100.0, 100.0, 100.0, 50.0, 50.0],
    )
    result = compute("up_down_volume_ratio", series, window=5)
    assert result["up_volume"][5] == pytest.approx(300.0)
    assert result["down_volume"][5] == pytest.approx(100.0)
    assert result["value"][5] == pytest.approx(3.0)
    assert result["up_volume_share"][5] == pytest.approx(0.75)


def test_up_down_volume_ratio_matches_reference(fpt: OHLCVSeries):
    up, down = reference.up_down_volume(list(fpt.close), list(fpt.volume), 20)
    result = compute("up_down_volume_ratio", fpt, window=20)
    assert_close(result["up_volume"], up, "up_down_volume_ratio", "up_volume")
    assert_close(result["down_volume"], down, "up_down_volume_ratio", "down_volume")


def test_up_volume_share_is_bounded(fpt: OHLCVSeries):
    values = compute("up_down_volume_ratio", fpt)["up_volume_share"]
    defined = values[np.isfinite(values)]
    assert defined.size > 0
    assert np.all(defined >= 0.0) and np.all(defined <= 1.0)


def test_ratio_is_undefined_but_share_is_defined_during_an_unbroken_advance():
    """A limit-up streak leaves no down-volume, so the ratio has no value.

    This is the case that makes `up_volume_share` worth exposing, and the
    reason the block builder refuses rather than substituting a number.
    """

    series = build([10.0, 11.0, 12.0, 13.0], volumes=[100.0] * 4)
    result = compute("up_down_volume_ratio", series, window=3)
    assert math.isnan(result["value"][3]), "no down-volume means no ratio"
    assert result["up_volume_share"][3] == pytest.approx(1.0)

    with pytest.raises(MoneyFlowUndefined, match="down-volume"):
        build_money_flow_block(series, ratio_window=3, unusual_window=2, vap_lookback=4)


# ---------------------------------------------------------------------------
# Unusual-volume flags
# ---------------------------------------------------------------------------


def test_unusual_volume_hand_computed():
    series = build([10.0] * 6, volumes=[10.0, 10.0, 10.0, 10.0, 10.0, 25.0])
    result = compute("unusual_volume", series, window=5, multiple=2.0)
    assert np.all(np.isnan(result["flag"][:5])), "warm-up is the full window"
    assert result["baseline"][5] == pytest.approx(10.0)
    assert result["ratio"][5] == pytest.approx(2.5)
    assert result["flag"][5] == pytest.approx(1.0)


def test_unusual_volume_threshold_is_inclusive():
    series = build([10.0] * 6, volumes=[10.0, 10.0, 10.0, 10.0, 10.0, 20.0])
    result = compute("unusual_volume", series, window=5, multiple=2.0)
    assert result["flag"][5] == pytest.approx(1.0), "a ratio exactly at the multiple flags"


def test_a_spike_does_not_raise_its_own_baseline():
    """The baseline excludes the current bar, by design."""

    series = build([10.0] * 7, volumes=[10.0] * 5 + [100.0, 25.0])
    result = compute("unusual_volume", series, window=5, multiple=2.0)
    assert result["flag"][5] == pytest.approx(1.0)
    # The median is robust to the single prior spike, so the next bar still flags.
    assert result["flag"][6] == pytest.approx(1.0)


def test_unusual_volume_is_undefined_for_a_dormant_security():
    """A month of no trading gives a zero median; the first trade is not a spike."""

    series = build([10.0] * 7, volumes=[0.0] * 6 + [1000.0])
    result = compute("unusual_volume", series, window=5, multiple=2.0)
    assert math.isnan(result["ratio"][6])
    assert math.isnan(result["flag"][6])


def test_unusual_volume_matches_reference(fpt: OHLCVSeries):
    flag, ratio = reference.unusual_volume(list(fpt.volume), 20, 2.0)
    result = compute("unusual_volume", fpt, window=20, multiple=2.0)
    assert_close(result["flag"], flag, "unusual_volume", "flag")
    assert_close(result["ratio"], ratio, "unusual_volume", "ratio")


def test_flags_are_only_ever_zero_or_one(fpt: OHLCVSeries):
    values = compute("unusual_volume", fpt)["flag"]
    defined = values[np.isfinite(values)]
    assert set(np.unique(defined)).issubset({0.0, 1.0})


# ---------------------------------------------------------------------------
# Volume at price
# ---------------------------------------------------------------------------


def test_volume_at_price_hand_computed():
    """Two price clusters with a known split of volume between them."""

    series = build(
        [10.0, 10.0, 20.0, 20.0],
        highs=[10.0, 10.0, 20.0, 20.0],
        lows=[10.0, 10.0, 20.0, 20.0],
        volumes=[100.0, 100.0, 300.0, 300.0],
    )
    result = compute("volume_at_price", series, lookback=4, bins=2, value_area_share=0.7)
    scalars = result.scalars
    assert scalars["bin_volume"] == [200.0, 600.0]
    assert scalars["bin_volume_share"] == [0.25, 0.75]
    assert scalars["point_of_control_share"] == pytest.approx(0.75)
    assert scalars["herfindahl"] == pytest.approx(0.25**2 + 0.75**2)
    assert scalars["included_bars"] == 4
    assert scalars["excluded_bars"] == 0


def test_volume_at_price_shares_sum_to_one(fpt: OHLCVSeries):
    scalars = compute("volume_at_price", fpt).scalars
    assert sum(scalars["bin_volume_share"]) == pytest.approx(1.0)
    assert 1.0 / len(scalars["bin_volume_share"]) <= scalars["herfindahl"] <= 1.0
    assert 0.0 <= scalars["normalized_herfindahl"] <= 1.0


def test_volume_at_price_value_area_covers_the_requested_share(fpt: OHLCVSeries):
    scalars = compute("volume_at_price", fpt, value_area_share=0.70).scalars
    edges = scalars["bin_edges"]
    inside = [
        share
        for share, low, high in zip(scalars["bin_volume_share"], edges[:-1], edges[1:])
        if low >= scalars["value_area_low"] - 1e-9 and high <= scalars["value_area_high"] + 1e-9
    ]
    assert sum(inside) >= 0.70


def test_volume_at_price_matches_reference(fpt: OHLCVSeries):
    expected = reference.volume_at_price(
        list(fpt.high), list(fpt.low), list(fpt.close), list(fpt.volume), 120, 20
    )
    scalars = compute("volume_at_price", fpt, lookback=120, bins=20).scalars
    assert_close(
        scalars["bin_volume"], expected["bin_volume"], "volume_at_price", "bin_volume"
    )
    assert scalars["herfindahl"] == pytest.approx(expected["herfindahl"])
    assert scalars["included_bars"] == expected["included_bars"]


def test_volume_at_price_reports_rather_than_hides_a_thin_histogram():
    series = build(
        [10.0, NAN, 12.0, 13.0],
        highs=[10.0, NAN, 12.0, 13.0],
        lows=[10.0, NAN, 12.0, 13.0],
        volumes=[100.0, 100.0, 100.0, 100.0],
    )
    scalars = compute("volume_at_price", series, lookback=4, bins=2).scalars
    assert scalars["included_bars"] == 3
    assert scalars["excluded_bars"] == 1


def test_volume_at_price_returns_nothing_rather_than_a_degenerate_histogram():
    series = build([10.0] * 3, highs=[10.0] * 3, lows=[10.0] * 3, volumes=[100.0] * 3)
    scalars = compute("volume_at_price", series, lookback=3, bins=2).scalars
    assert scalars["bin_volume"] is None, "a zero-width price span has no histogram"
    assert scalars["included_bars"] == 3


# ---------------------------------------------------------------------------
# The assembled block
# ---------------------------------------------------------------------------


def test_block_matches_the_contract_shape(fpt: OHLCVSeries, repo_root):
    import json

    import jsonschema

    block = build_money_flow_block(fpt)
    schema_path = repo_root / "contracts" / "schemas" / "json" / "money_flow_block.schema.json"
    with schema_path.open(encoding="utf-8") as handle:
        jsonschema.validate(block, json.load(handle))


def test_block_values_agree_with_the_underlying_indicators(fpt: OHLCVSeries):
    block = build_money_flow_block(fpt)
    assert block["accumulation_distribution_line"] == pytest.approx(
        compute("accumulation_distribution", fpt).last("value")
    )
    assert block["on_balance_volume"] == pytest.approx(
        compute("on_balance_volume", fpt).last("value")
    )
    assert block["up_down_volume_ratio"] == pytest.approx(
        compute("up_down_volume_ratio", fpt).last("value")
    )


def test_block_flag_dates_are_iso_dates_drawn_from_the_series(fpt: OHLCVSeries):
    import datetime as dt

    block = build_money_flow_block(fpt)
    known = {day.isoformat() for day in fpt.trading_dates}
    for value in block["unusual_volume_flags"]:
        assert value in known
        dt.date.fromisoformat(value)


def test_close_vs_vwap_is_never_derived_from_the_bars(fpt: OHLCVSeries, repo_root):
    """The block leaves close_vs_vwap null while the contract carries no VWAP.

    Section 14 admits close-versus-VWAP to this block once Aux1 is confirmed
    as unadjusted VWAP, and `docs/data_dictionary.md` now records that
    confirmation. The measure still cannot be computed from the inputs the
    quant layer receives: the canonical `PriceBar` contract has no VWAP or
    unadjusted-close field. Deriving it from the back-adjusted close alone
    would divide an adjusted price by an unadjusted one.

    This test watches the contract, so it starts failing the moment a VWAP
    field is added and the block needs revisiting.
    """

    import json

    schema_path = repo_root / "contracts" / "schemas" / "json" / "price_bar.schema.json"
    with schema_path.open(encoding="utf-8") as handle:
        fields = set(json.load(handle)["properties"])
    assert not fields & {"aux1", "vwap", "average_price", "unadjusted_close"}, (
        "PriceBar now carries a VWAP-like field. Revisit close_vs_vwap in "
        "build_money_flow_block and in NUMERICS.md."
    )
    assert build_money_flow_block(fpt)["close_vs_vwap"] is None


def test_close_versus_vwap_arithmetic_is_ready_for_when_the_inputs_arrive():
    """The formula itself, tested now so the wiring is the only work left."""

    from backend.app.quant.indicators.money_flow import close_versus_vwap

    values = close_versus_vwap([10.0, 20.0, 30.0], [10.0, 25.0, 0.0])
    assert values[0] == pytest.approx(0.0), "a close at its own average is neutral"
    assert values[1] == pytest.approx(-20.0), "closing below the average is negative"
    assert math.isnan(values[2]), "a zero average price is undefined, not infinite"


def test_close_versus_vwap_refuses_mismatched_inputs():
    from backend.app.quant.indicators.money_flow import close_versus_vwap

    with pytest.raises(Exception, match="same bars"):
        close_versus_vwap([10.0, 20.0], [10.0])


def test_a_caller_supplied_close_vs_vwap_is_passed_through_unchanged(fpt: OHLCVSeries):
    block = build_money_flow_block(fpt, close_vs_vwap=1.25)
    assert block["close_vs_vwap"] == pytest.approx(1.25)


def test_block_refuses_an_empty_series():
    with pytest.raises(MoneyFlowUndefined):
        build_money_flow_block(
            OHLCVSeries(
                symbol="TEST",
                trading_dates=(),
                open=[],
                high=[],
                low=[],
                close=[],
                volume=[],
            )
        )


def test_block_refuses_a_series_shorter_than_the_warm_up():
    series = build([10.0, 11.0, 12.0], volumes=[100.0, 100.0, 100.0])
    with pytest.raises(MoneyFlowUndefined):
        build_money_flow_block(series)
