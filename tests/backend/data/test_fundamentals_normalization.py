from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.app.data.fundamentals.models import (
    RawFinancialObservation,
    ValueBasis,
)
from backend.app.data.fundamentals.normalization import normalize_observations

INGESTED_AT = datetime(2026, 7, 31, 1, 0, tzinfo=UTC)
SOURCE_URL = "https://example.com/filings/FPT-2026-Q2"


def raw_observation(**overrides) -> RawFinancialObservation:
    values = {
        "symbol": "FPT",
        "period_end": date(2026, 6, 30),
        "period_type": "quarter",
        "statement_type": "income_statement",
        "metric_code": "revenue",
        "metric_label_vi": "Doanh thu thuần",
        "value": 12_000.0,
        "currency": "VND",
        "unit": "billion_vnd",
        "consolidated": True,
        "value_basis": ValueBasis.CUMULATIVE,
        "restatement_version": 2,
        "publication_date": date(2026, 7, 25),
        "source_url": SOURCE_URL,
        "source_name": "issuer_filing",
        "ingested_at": INGESTED_AT,
    }
    values.update(overrides)
    return RawFinancialObservation(**values)


def test_normalization_keeps_scope_basis_units_dates_sources_and_restatement():
    result = normalize_observations([raw_observation()])

    observation = result.observations[0]
    assert observation.symbol == "FPT"
    assert observation.metric_code == "revenue_cumulative"
    assert observation.base_metric_code == "revenue"
    assert observation.consolidated is True
    assert observation.value_basis is ValueBasis.CUMULATIVE
    assert observation.currency == "VND"
    assert observation.unit == "billion_vnd"
    assert observation.restatement_version == 2
    assert observation.publication_date == date(2026, 7, 25)
    assert observation.source_url == SOURCE_URL
    assert observation.backtest_eligible is True
    assert result.warnings == ()


def test_missing_publication_date_degrades_without_blocking_display():
    result = normalize_observations(
        [raw_observation(publication_date=None, value_basis=ValueBasis.STANDALONE)]
    )

    assert len(result.observations) == 1
    assert result.observations[0].metric_code == "revenue"
    assert result.observations[0].backtest_eligible is False
    warning = (
        "FPT 2026-06-30 revenue has no publication date; it is available "
        "for display and current screening but excluded from historical backtests."
    )
    assert result.warnings == (warning,)


def test_quarterly_flow_basis_must_be_explicit():
    with pytest.raises(ValueError, match="value_basis"):
        raw_observation(value_basis=ValueBasis.UNKNOWN)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("currency", "", "currency"),
        ("unit", "millions-ish", "unit"),
        ("source_url", "provider-row-123", "source_url"),
    ],
)
def test_normalization_rejects_ambiguous_metadata(field, value, message):
    with pytest.raises(ValueError, match=message):
        normalize_observations([raw_observation(**{field: value})])


def test_annual_and_balance_sheet_observations_do_not_get_cumulative_suffix():
    annual = raw_observation(
        period_end=date(2025, 12, 31),
        period_type="year",
        value_basis=ValueBasis.ANNUAL,
    )
    balance = raw_observation(
        statement_type="balance_sheet",
        metric_code="total_assets",
        metric_label_vi="Tổng tài sản",
        value_basis=ValueBasis.POINT_IN_TIME,
    )

    result = normalize_observations([annual, balance])

    assert [item.metric_code for item in result.observations] == [
        "revenue",
        "total_assets",
    ]


def test_dimensionless_ratio_records_currency_as_not_applicable():
    ratio = raw_observation(
        statement_type="ratio",
        metric_code="roe_reported",
        metric_label_vi="ROE công bố",
        currency="N/A",
        unit="ratio",
        value_basis=ValueBasis.RATIO,
    )

    result = normalize_observations([ratio])

    assert result.observations[0].currency == "N/A"
