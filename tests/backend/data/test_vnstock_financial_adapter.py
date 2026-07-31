from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from backend.app.data.fundamentals.models import ValueBasis
from backend.app.data.fundamentals.vnstock_adapter import (
    FinancialFrameSchema,
    MetricColumn,
    VnstockFinancialAdapter,
    VnstockSchemaError,
)


class FakeEquity:
    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def income_statement(self, **kwargs):
        self.calls.append(("income_statement", kwargs))
        return self.frame


class FakeFundamental:
    def __init__(self, equity):
        self._equity = equity
        self.symbols = []

    def equity(self, symbol):
        self.symbols.append(symbol)
        return self._equity


def schema(**overrides):
    values = {
        "period_end_column": "period_end",
        "metrics": (
            MetricColumn(
                source_column="revenue",
                metric_code="revenue",
                metric_label_vi="Doanh thu thuần",
                unit="billion_vnd",
            ),
        ),
        "currency": "VND",
        "consolidated": True,
        "value_basis": ValueBasis.CUMULATIVE,
        "source_url": "https://example.com/provider/FPT/financials",
    }
    values.update(overrides)
    return FinancialFrameSchema(**values)


def test_adapter_uses_explicit_schema_and_degrades_missing_publication_date():
    frame = pd.DataFrame(
        [{"period_end": "2026-06-30", "revenue": 12_000.0}]
    )
    equity = FakeEquity(frame)
    fundamental = FakeFundamental(equity)
    adapter = VnstockFinancialAdapter(
        fundamental_factory=lambda: fundamental,
        source_name="vnstock",
        ingested_at_factory=lambda: datetime(2026, 7, 31, tzinfo=UTC),
    )

    result = adapter.fetch(
        symbol="fpt",
        statement_type="income_statement",
        period_type="quarter",
        schema=schema(),
    )

    assert fundamental.symbols == ["FPT"]
    assert equity.calls == [
        (
            "income_statement",
            {"period": "quarter", "orient": "time_series"},
        )
    ]
    observation = result.observations[0]
    assert observation.metric_code == "revenue_cumulative"
    assert observation.consolidated is True
    assert observation.publication_date is None
    assert observation.source_url.startswith("https://")
    assert "excluded from historical backtests" in result.warnings[0]


def test_adapter_preserves_separate_scope_publication_and_restatement_columns():
    frame = pd.DataFrame(
        [
            {
                "period_end": "2025-12-31",
                "publication_date": "2026-03-20",
                "version": 3,
                "filing_url": "https://example.com/filings/FPT-2025-v3",
                "revenue": 70_000,
            }
        ]
    )
    adapter = VnstockFinancialAdapter(
        fundamental_factory=lambda: FakeFundamental(FakeEquity(frame)),
        source_name="vnstock",
        ingested_at_factory=lambda: datetime(2026, 7, 31, tzinfo=UTC),
    )

    result = adapter.fetch(
        symbol="FPT",
        statement_type="income_statement",
        period_type="year",
        schema=schema(
            consolidated=False,
            value_basis=ValueBasis.ANNUAL,
            publication_date_column="publication_date",
            restatement_version_column="version",
            source_url_column="filing_url",
        ),
    )

    observation = result.observations[0]
    assert observation.metric_code == "revenue"
    assert observation.consolidated is False
    assert observation.restatement_version == 3
    assert observation.publication_date.isoformat() == "2026-03-20"
    assert observation.source_url.endswith("FPT-2025-v3")


def test_adapter_stops_on_schema_drift_instead_of_guessing_columns():
    frame = pd.DataFrame([{"date": "2026-06-30", "revenue": 12_000}])
    adapter = VnstockFinancialAdapter(
        fundamental_factory=lambda: FakeFundamental(FakeEquity(frame)),
        source_name="vnstock",
    )

    with pytest.raises(VnstockSchemaError, match="period_end"):
        adapter.fetch(
            symbol="FPT",
            statement_type="income_statement",
            period_type="quarter",
            schema=schema(),
        )


def test_adapter_treats_pandas_missing_publication_date_as_degraded():
    frame = pd.DataFrame(
        [
            {
                "period_end": pd.Timestamp("2026-06-30"),
                "publication_date": pd.NaT,
                "revenue": 12_000,
            }
        ]
    )
    adapter = VnstockFinancialAdapter(
        fundamental_factory=lambda: FakeFundamental(FakeEquity(frame)),
        source_name="vnstock",
    )

    result = adapter.fetch(
        symbol="FPT",
        statement_type="income_statement",
        period_type="quarter",
        schema=schema(publication_date_column="publication_date"),
    )

    assert result.observations[0].publication_date is None
