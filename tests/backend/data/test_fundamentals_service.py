from __future__ import annotations

from datetime import UTC, date, datetime

from backend.app.data.fundamentals.service import FundamentalsService

from backend.app.data.fundamentals.models import (
    RawFinancialObservation,
    ValueBasis,
)
from backend.app.data.fundamentals.normalization import normalize_observations
from backend.app.data.fundamentals.store import FinancialObservationStore


def raw(metric_code, value, **overrides):
    values = {
        "symbol": "FPT",
        "period_end": date(2026, 6, 30),
        "period_type": "quarter",
        "statement_type": "income_statement",
        "metric_code": metric_code,
        "metric_label_vi": metric_code,
        "value": value,
        "currency": "VND",
        "unit": "billion_vnd",
        "consolidated": True,
        "value_basis": ValueBasis.STANDALONE,
        "restatement_version": 1,
        "publication_date": date(2026, 7, 25),
        "source_url": "https://example.com/filings/FPT-2026-Q2",
        "source_name": "issuer_filing",
        "ingested_at": datetime(2026, 7, 31, tzinfo=UTC),
    }
    values.update(overrides)
    return RawFinancialObservation(**values)


def test_service_exposes_panels_sources_versions_and_degraded_warning(tmp_path):
    store = FinancialObservationStore(tmp_path / "fundamentals.duckdb")
    service = FundamentalsService(store=store)
    rows = (
        raw("revenue", 100, period_end=date(2025, 6, 30)),
        raw("revenue", 150),
        raw("gross_profit", 60),
        raw("operating_profit", 30),
        raw("net_income", 15, publication_date=None),
        raw(
            "revenue",
            140,
            consolidated=False,
            source_url="https://example.com/filings/FPT-2026-Q2-separate",
        ),
        raw(
            "revenue",
            145,
            consolidated=False,
            restatement_version=2,
            source_url="https://example.com/filings/FPT-2026-Q2-separate-v2",
        ),
        raw(
            "revenue",
            600,
            period_end=date(2025, 12, 31),
            period_type="year",
            value_basis=ValueBasis.ANNUAL,
        ),
    )
    service.ingest(normalize_observations(rows))

    response = service.get_fundamentals("fpt")

    assert response is not None
    assert response.symbol == "FPT"
    assert {
        observation.period_type for observation in response.observations
    } == {"quarter", "year"}
    assert {observation.consolidated for observation in response.observations} == {
        True,
        False,
    }
    assert {
        observation.restatement_version
        for observation in response.observations
        if not observation.consolidated
    } == {1, 2}
    assert {
        metric.metric_code for metric in response.derived_metrics
    } >= {
        "revenue_yoy_growth",
        "gross_margin",
        "operating_margin",
        "net_margin",
    }
    assert all(
        observation.source_url.startswith("https://")
        for observation in response.observations
    )
    assert response.provenance.freshness_status == "degraded_point_in_time"
    assert any(
        "excluded from historical backtests" in warning
        for warning in response.provenance.warnings
    )
    undated = [
        observation
        for observation in response.observations
        if observation.publication_date is None
    ]
    assert undated


def test_service_returns_none_for_unknown_symbol(tmp_path):
    service = FundamentalsService(
        store=FinancialObservationStore(tmp_path / "fundamentals.duckdb")
    )

    assert service.get_fundamentals("MISSING") is None

