"""Section 14's documentation requirement, enforced as a test.

Section 14: "Each indicator must document: Formula. Input price. Adjustment
convention. Warm-up period. Missing-value behaviour. Comparison reference.
Numerical tolerance."

Documentation that lives only in prose rots. Every one of those seven
attributes is a required field on `IndicatorSpec`, and the tests here check
that each is present, substantive, and consistent with what the code
actually does. `NUMERICS.md` is generated from these same records, so the
document and the engine cannot disagree.
"""

from __future__ import annotations

import json

import pytest

from backend.app.quant.indicators import all_ids, all_indicators, documentation

#: The seven Section 14 attributes, with the minimum length that counts as
#: documentation rather than a placeholder. "Close." is a complete answer to
#: "input price", so the bar there is low; a one-line formula or a one-line
#: account of missing-value behaviour is not.
REQUIRED_TEXT_FIELDS = {
    "formula": 25,
    "input_price": 6,
    "adjustment_convention": 40,
    "warm_up": 12,
    "missing_value_behavior": 40,
    "comparison_reference": 40,
}

SECTION_14_INDICATORS = {
    "sma": "SMA",
    "ema": "EMA",
    "rsi": "RSI",
    "macd": "MACD",
    "atr": "ATR",
    "bollinger_bands": "Bollinger Bands",
    "rolling_high": "Rolling highs",
    "rolling_low": "Rolling lows",
    "rate_of_change": "Rate of change",
    "relative_strength_vnindex": "Relative strength versus VN-Index",
    "relative_strength_sector": "Relative strength versus sector",
    "volume_sma": "Volume moving averages",
    "volume_price_trend": "Volume-price trend measures",
    "pivot_levels": "Pivot levels",
    "rolling_volatility": "Rolling volatility",
    "drawdown": "Drawdown",
    "accumulation_distribution": "Money-flow block: accumulation/distribution line",
    "on_balance_volume": "Money-flow block: on-balance volume",
    "up_down_volume_ratio": "Money-flow block: up-day versus down-day volume ratio",
    "volume_at_price": "Money-flow block: volume-at-price concentration",
    "unusual_volume": "Money-flow block: unusual-volume flags",
}


def test_every_section_14_indicator_is_implemented():
    """The Section 14 list, item by item, including the whole money-flow block."""

    missing = sorted(set(SECTION_14_INDICATORS) - set(all_ids()))
    assert not missing, f"Section 14 requires {missing}, which are not registered"


@pytest.mark.parametrize(
    "entry", all_indicators(), ids=lambda entry: entry.spec.indicator_id
)
@pytest.mark.parametrize("field", sorted(REQUIRED_TEXT_FIELDS))
def test_every_documentation_field_is_present_and_substantive(entry, field: str):
    value = getattr(entry.spec, field)
    assert isinstance(value, str)
    assert len(value.strip()) >= REQUIRED_TEXT_FIELDS[field], (
        f"{entry.spec.indicator_id}.{field} is too short to be documentation: "
        f"{value!r}"
    )


@pytest.mark.parametrize(
    "entry", all_indicators(), ids=lambda entry: entry.spec.indicator_id
)
def test_every_indicator_documents_a_usable_tolerance(entry):
    tolerance = entry.spec.tolerance
    assert tolerance.absolute > 0 or tolerance.relative > 0
    assert tolerance.absolute >= 0 and tolerance.relative >= 0
    assert len(tolerance.basis.strip()) >= 20, (
        f"{entry.spec.indicator_id} states a tolerance without saying what it is a "
        "tolerance against, which makes it unusable"
    )


@pytest.mark.parametrize(
    "entry", all_indicators(), ids=lambda entry: entry.spec.indicator_id
)
def test_warm_up_prose_and_warm_up_function_agree_on_being_defined(entry):
    """The prose is checked against behaviour in test_indicator_math.py.

    Here we only check the machine-readable half exists and is callable at
    the documented defaults, so the two halves cannot get out of step by one
    of them being absent.
    """

    parameters = {
        key: value for key, value in entry.spec.parameters.items() if key != "benchmark"
    }
    warm_up = entry.spec.warm_up_bars(**parameters)
    assert isinstance(warm_up, int) and warm_up >= 0


@pytest.mark.parametrize(
    "entry", all_indicators(), ids=lambda entry: entry.spec.indicator_id
)
def test_outputs_and_parameters_are_declared(entry):
    assert entry.spec.outputs, f"{entry.spec.indicator_id} declares no outputs"
    assert len(set(entry.spec.outputs)) == len(entry.spec.outputs)
    assert entry.spec.block, f"{entry.spec.indicator_id} declares no block"


@pytest.mark.parametrize(
    "entry", all_indicators(), ids=lambda entry: entry.spec.indicator_id
)
def test_conventions_that_a_reader_could_get_wrong_are_named(entry):
    """Where a choice exists, the documentation must say which was taken.

    These are the four places a second implementation most often disagrees,
    so each is checked for an explicit statement rather than trusted to the
    author's memory.
    """

    text = " ".join(
        [
            entry.spec.formula,
            entry.spec.comparison_reference,
            entry.spec.missing_value_behavior,
        ]
    ).lower()

    if entry.spec.indicator_id in {"bollinger_bands", "rolling_volatility"}:
        assert "ddof" in text or "population" in text or "sample" in text

    if entry.spec.indicator_id in {"ema", "macd"}:
        assert "seed" in text

    if entry.spec.indicator_id in {"rsi", "atr"}:
        assert "wilder" in text

    if entry.spec.indicator_id == "accumulation_distribution":
        assert "zero" in text and "limit" in text


def test_documentation_export_is_json_serializable():
    """`registry.documentation()` is what NUMERICS.md and any API view read."""

    records = documentation()
    assert len(records) == len(all_ids())
    encoded = json.dumps(records, sort_keys=True)
    assert "formula" in encoded


def numerics_path():
    from generate_numerics import TARGET

    return TARGET


def test_numerics_document_covers_every_indicator():
    """NUMERICS.md is the human-readable half of the same record."""

    path = numerics_path()
    assert path.exists(), "NUMERICS.md is missing from the indicator package"
    text = path.read_text(encoding="utf-8")
    missing = [indicator_id for indicator_id in all_ids() if indicator_id not in text]
    assert not missing, f"NUMERICS.md does not mention {missing}"


def test_numerics_document_is_up_to_date():
    """The document is generated, so a stale copy is a test failure.

    This is what stops the Section 14 documentation from drifting: change a
    formula or a tolerance in the code and this fails until NUMERICS.md is
    regenerated.
    """

    from generate_numerics import render

    path = numerics_path()
    assert path.read_text(encoding="utf-8") == render(), (
        "NUMERICS.md is out of date with the indicator registry. Regenerate it with "
        "`python tests/quant/generate_numerics.py`."
    )


def test_amibroker_cross_check_is_recorded_as_outstanding():
    """Section 14's acceptance criterion is not yet fully met; say so in writing.

    Section 14 accepts an indicator when results "match an independent
    reference or AmiBroker export within a documented tolerance". The
    independent reference exists (tests/quant/reference.py). No AmiBroker
    export has been supplied to this workstream. That gap is a documented
    limitation, and this test fails if someone quietly removes the note
    without supplying the export.
    """

    text = numerics_path().read_text(encoding="utf-8")
    assert "Outstanding external verification" in text
    assert "AmiBroker" in text
    assert "No AmiBroker export has been supplied" in text
