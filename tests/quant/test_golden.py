"""Golden-fixture tests: every indicator, every output, frozen.

WP5 requires a golden-fixture test for every indicator. `test_golden_covers_
every_registered_indicator` is the one that enforces "every": it fails if an
indicator is added to the registry without being regenerated into the golden
files, so the requirement cannot quietly decay as WP6 and WP7 add
indicators.

The comparison uses each indicator's own documented tolerance, so a change
that moves a value by more than the indicator claims to be reproducible to
is a failure, and the fixture also pins the warm-up length of every output
and the sha256 of the input bars.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from helpers import FIXTURES, GOLDEN, call_kwargs, load_series

from backend.app.quant.indicators import (
    all_ids,
    build_indicators_payload,
    build_money_flow_block,
    compute,
    spec,
)

SYMBOLS = ("FPT", "KDH")

REGENERATE = (
    "Run `python tests/quant/generate_golden.py` after confirming the change is "
    "intended and the correctness tests in test_indicator_math.py still pass."
)


def load_golden(symbol: str) -> dict:
    path = GOLDEN / f"indicators_{symbol}.json"
    if not path.exists():  # pragma: no cover - only on a fresh checkout
        pytest.fail(f"missing golden fixture {path}. {REGENERATE}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_golden_was_generated_from_the_current_fixture(symbol: str):
    """A changed input fixture invalidates the baseline; say so explicitly."""

    golden = load_golden(symbol)
    digest = hashlib.sha256((FIXTURES / f"bars_{symbol}.json").read_bytes()).hexdigest()
    assert digest == golden["source_sha256"], (
        f"contracts/fixtures/bars_{symbol}.json changed since the golden baseline "
        f"was generated. {REGENERATE}"
    )


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_golden_covers_every_registered_indicator(symbol: str):
    """The 'every indicator has a golden-fixture test' requirement, enforced."""

    golden = load_golden(symbol)
    covered = {entry["indicator_id"] for entry in golden["indicators"]}
    missing = sorted(set(all_ids()) - covered)
    assert not missing, f"no golden fixture for {missing}. {REGENERATE}"


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_golden_values_still_reproduce(symbol: str):
    golden = load_golden(symbol)
    series = load_series(symbol)

    for entry in golden["indicators"]:
        indicator_id = entry["indicator_id"]
        indicator_spec = spec(indicator_id)
        parameters = dict(entry["parameters"])
        if indicator_spec.requires_benchmark:
            parameters["benchmark"] = call_kwargs(indicator_spec, series)["benchmark"]

        result = compute(indicator_id, series, **parameters)
        tolerance = indicator_spec.tolerance

        for output, expected in entry["outputs"].items():
            values = result[output]
            finite = np.isfinite(values)
            observed_warm_up = (
                int(len(values)) if not finite.any() else int(np.argmax(finite))
            )
            assert observed_warm_up == expected["warm_up_bars"], (
                f"{symbol} {indicator_id}.{output} warm-up moved from "
                f"{expected['warm_up_bars']} to {observed_warm_up}. {REGENERATE}"
            )
            for index, value in expected["samples"].items():
                actual = float(values[int(index)])
                if value is None:
                    assert not np.isfinite(actual), (
                        f"{symbol} {indicator_id}.{output}[{index}] was undefined in "
                        f"the baseline and is now {actual}. {REGENERATE}"
                    )
                    continue
                assert np.isfinite(actual), (
                    f"{symbol} {indicator_id}.{output}[{index}] was {value} in the "
                    f"baseline and is now undefined. {REGENERATE}"
                )
                assert actual == pytest.approx(
                    value, rel=tolerance.relative, abs=tolerance.absolute
                ), (
                    f"{symbol} {indicator_id}.{output}[{index}] moved from {value} to "
                    f"{actual}, beyond the indicator's documented tolerance. {REGENERATE}"
                )


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_golden_scalars_still_reproduce(symbol: str):
    golden = load_golden(symbol)
    series = load_series(symbol)

    for entry in golden["indicators"]:
        indicator_id = entry["indicator_id"]
        indicator_spec = spec(indicator_id)
        parameters = dict(entry["parameters"])
        if indicator_spec.requires_benchmark:
            parameters["benchmark"] = call_kwargs(indicator_spec, series)["benchmark"]
        result = compute(indicator_id, series, **parameters)

        for name, expected in entry["scalars"].items():
            actual = result.scalars[name]
            if isinstance(expected, list):
                assert len(actual) == len(expected)
                for left, right in zip(actual, expected):
                    assert float(left) == pytest.approx(
                        right, rel=1e-9, abs=1e-9
                    ), f"{symbol} {indicator_id}.{name} changed. {REGENERATE}"
            elif isinstance(expected, (int, float)):
                assert float(actual) == pytest.approx(
                    expected, rel=1e-9, abs=1e-9
                ), f"{symbol} {indicator_id}.{name} changed. {REGENERATE}"
            else:
                assert actual == expected, (
                    f"{symbol} {indicator_id}.{name} changed. {REGENERATE}"
                )


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_golden_money_flow_block_still_reproduces(symbol: str):
    golden = load_golden(symbol)
    block = build_money_flow_block(load_series(symbol))
    expected = golden["money_flow_block"]

    for name in ("accumulation_distribution_line", "on_balance_volume", "up_down_volume_ratio"):
        assert block[name] == pytest.approx(expected[name], rel=1e-9, abs=1e-6), (
            f"{symbol} money-flow block field {name} changed. {REGENERATE}"
        )
    assert block["unusual_volume_flags"] == expected["unusual_volume_flags"], (
        f"{symbol} unusual-volume flag dates changed. {REGENERATE}"
    )
    assert block["close_vs_vwap"] == expected["close_vs_vwap"]
    assert (
        block["volume_at_price_concentration"]["point_of_control_price"]
        == pytest.approx(
            expected["volume_at_price_concentration"]["point_of_control_price"],
            rel=1e-9,
            abs=1e-9,
        )
    )


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_golden_payload_series_names_are_stable(symbol: str):
    """The wire-facing series ids are a published surface; freeze them too."""

    golden = load_golden(symbol)
    payload = build_indicators_payload(load_series(symbol))
    assert [item["indicator_id"] for item in payload["indicators"]] == golden[
        "payload_series_ids"
    ], (
        f"{symbol}: the indicator series names in the API payload changed, which is a "
        f"breaking change for the frontend. {REGENERATE}"
    )
