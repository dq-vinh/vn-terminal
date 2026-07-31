from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.data.fundamentals.metrics import (
    PricePoint,
    calculate_panel_metrics,
)
from backend.app.data.fundamentals.models import (
    NormalizedFinancialObservation,
    ValueBasis,
)

INGESTED_AT = datetime(2026, 7, 31, 1, 0, tzinfo=UTC)


def item(
    metric_code: str,
    value: int,
    *,
    period_end: date = date(2026, 6, 30),
    statement_type: str = "income_statement",
    unit: str = "billion_vnd",
    value_basis: ValueBasis = ValueBasis.STANDALONE,
    source_url: str = "https://example.com/filings/FPT-2026-Q2",
) -> NormalizedFinancialObservation:
    return NormalizedFinancialObservation(
        symbol="FPT",
        period_end=period_end,
        period_type="quarter",
        statement_type=statement_type,
        metric_code=metric_code,
        base_metric_code=metric_code,
        metric_label_vi=metric_code,
        value=Decimal(value),
        currency="VND",
        unit=unit,
        consolidated=True,
        value_basis=value_basis,
        restatement_version=1,
        publication_date=date(2026, 7, 25),
        source_url=source_url,
        source_name="issuer_filing",
        ingested_at=INGESTED_AT,
    )


def metric_map(result):
    return {
        (metric.period_end, metric.metric_code): metric.value
        for metric in result.metrics
    }


def test_growth_margins_returns_leverage_and_cash_flow_are_deterministic():
    observations = (
        item("revenue", 100, period_end=date(2025, 6, 30)),
        item("revenue", 120, period_end=date(2026, 3, 31)),
        item("equity", 80, period_end=date(2026, 3, 31), statement_type="balance_sheet", value_basis=ValueBasis.POINT_IN_TIME),
        item("total_assets", 200, period_end=date(2026, 3, 31), statement_type="balance_sheet", value_basis=ValueBasis.POINT_IN_TIME),
        item("revenue", 150),
        item("gross_profit", 60),
        item("operating_profit", 30),
        item("net_income", 15),
        item("equity", 100, statement_type="balance_sheet", value_basis=ValueBasis.POINT_IN_TIME),
        item("total_assets", 220, statement_type="balance_sheet", value_basis=ValueBasis.POINT_IN_TIME),
        item("total_liabilities", 100, statement_type="balance_sheet", value_basis=ValueBasis.POINT_IN_TIME),
        item("operating_cash_flow", 25, statement_type="cash_flow_statement"),
        item("capital_expenditure", 10, statement_type="cash_flow_statement"),
    )

    result = calculate_panel_metrics(observations)
    metrics = metric_map(result)
    period = date(2026, 6, 30)

    assert metrics[(period, "revenue_qoq_growth")] == 0.25
    assert metrics[(period, "revenue_yoy_growth")] == 0.5
    assert metrics[(period, "gross_margin")] == 0.4
    assert metrics[(period, "operating_margin")] == 0.2
    assert metrics[(period, "net_margin")] == 0.1
    assert metrics[(period, "roe")] == 0.666667
    assert metrics[(period, "roa")] == 0.285714
    assert metrics[(period, "debt_to_equity")] == 1.0
    assert metrics[(period, "free_cash_flow")] == 15.0


def test_cumulative_values_never_enter_quarterly_growth_or_margins():
    result = calculate_panel_metrics(
        (
            item(
                "revenue_cumulative",
                250,
                value_basis=ValueBasis.CUMULATIVE,
            ),
            item(
                "net_income_cumulative",
                30,
                value_basis=ValueBasis.CUMULATIVE,
            ),
        )
    )

    assert result.metrics == ()
    assert any("standalone" in warning for warning in result.warnings)


def test_pe_and_pb_require_positive_denominators_and_sourced_price():
    price = PricePoint(
        symbol="FPT",
        trading_date=date(2026, 7, 30),
        value=Decimal(100_000),
        currency="VND",
        unit="vnd_per_share",
        source_url="https://example.com/market/FPT/2026-07-30",
    )
    valid = calculate_panel_metrics(
        (
            item("eps_ttm", 5_000, unit="vnd_per_share", value_basis=ValueBasis.RATIO),
            item(
                "book_value_per_share",
                20_000,
                statement_type="balance_sheet",
                unit="vnd_per_share",
                value_basis=ValueBasis.POINT_IN_TIME,
            ),
        ),
        price=price,
    )

    metrics = metric_map(valid)
    assert metrics[(date(2026, 6, 30), "pe")] == 20.0
    assert metrics[(date(2026, 6, 30), "pb")] == 5.0
    assert {
        item.metric_code for item in valid.trace_observations
    } >= {"pe", "pb"}
    assert all(
        item.source_url.startswith("https://")
        for item in valid.trace_observations
    )

    invalid = calculate_panel_metrics(
        (
            item("eps_ttm", 0, unit="vnd_per_share", value_basis=ValueBasis.RATIO),
            item(
                "book_value_per_share",
                -1,
                statement_type="balance_sheet",
                unit="vnd_per_share",
                value_basis=ValueBasis.POINT_IN_TIME,
            ),
        ),
        price=price,
    )
    assert not {"pe", "pb"} & {
        metric.metric_code for metric in invalid.metrics
    }
    assert any("positive denominator" in warning for warning in invalid.warnings)


def test_price_point_requires_an_absolute_source_url():
    with pytest.raises(ValueError, match="source_url"):
        PricePoint(
            symbol="FPT",
            trading_date=date(2026, 7, 30),
            value=Decimal(100_000),
            currency="VND",
            unit="vnd_per_share",
            source_url="market-row-123",
        )


def test_valuation_uses_latest_available_denominator_not_latest_other_statement():
    price = PricePoint(
        symbol="FPT",
        trading_date=date(2026, 7, 30),
        value=Decimal(100_000),
        currency="VND",
        unit="vnd_per_share",
        source_url="https://example.com/market/FPT/2026-07-30",
    )
    result = calculate_panel_metrics(
        (
            item(
                "eps_ttm",
                5_000,
                period_end=date(2026, 3, 31),
                unit="vnd_per_share",
                value_basis=ValueBasis.RATIO,
            ),
            item("revenue", 150, period_end=date(2026, 6, 30)),
        ),
        price=price,
    )

    assert metric_map(result)[(date(2026, 3, 31), "pe")] == 20.0


def test_missing_input_publication_date_propagates_to_metric_trace():
    result = calculate_panel_metrics(
        (
            item("revenue", 100, period_end=date(2025, 6, 30)),
            item("revenue", 150),
        )
    )
    result_with_undated = calculate_panel_metrics(
        (
            item("revenue", 100, period_end=date(2025, 6, 30)),
            replace(item("revenue", 150), publication_date=None),
        )
    )

    assert result.metrics
    trace = next(
        item
        for item in result_with_undated.trace_observations
        if item.metric_code == "revenue_yoy_growth"
    )
    assert trace.publication_date is None
    assert any(
        "excluded from historical backtests" in warning
        for warning in result_with_undated.warnings
    )


def test_roe_trace_includes_prior_balance_publication_quality():
    prior_equity = replace(
        item(
            "equity",
            80,
            period_end=date(2026, 3, 31),
            statement_type="balance_sheet",
            value_basis=ValueBasis.POINT_IN_TIME,
        ),
        publication_date=None,
    )
    result = calculate_panel_metrics(
        (
            item("revenue", 150),
            item("net_income", 15),
            prior_equity,
            item(
                "equity",
                100,
                statement_type="balance_sheet",
                value_basis=ValueBasis.POINT_IN_TIME,
            ),
        )
    )

    trace = next(
        item
        for item in result.trace_observations
        if item.metric_code == "roe"
    )
    assert trace.publication_date is None
