from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from backend.app.data.fundamentals.pipeline import (
    FinancialFetchJob,
    FinancialRefreshPipeline,
)

from backend.app.data.fundamentals.models import (
    RawFinancialObservation,
    ValueBasis,
)
from backend.app.data.fundamentals.normalization import normalize_observations
from backend.app.data.fundamentals.service import FundamentalsService
from backend.app.data.fundamentals.store import FinancialObservationStore
from backend.app.data.fundamentals.vnstock_adapter import (
    FinancialFrameSchema,
    MetricColumn,
)


class SequenceAdapter:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.results)


def raw(value):
    return RawFinancialObservation(
        symbol="FPT",
        period_end=date(2026, 6, 30),
        period_type="quarter",
        statement_type="income_statement",
        metric_code="revenue",
        metric_label_vi="Doanh thu thuần",
        value=value,
        currency="VND",
        unit="billion_vnd",
        consolidated=True,
        value_basis=ValueBasis.STANDALONE,
        restatement_version=1,
        publication_date=None,
        source_url="https://example.com/provider/FPT/financials",
        source_name="vnstock",
        ingested_at=datetime(2026, 7, 31, tzinfo=UTC),
    )


def test_refresh_pipeline_versions_changed_unversioned_provider_rows(tmp_path):
    first = normalize_observations((raw(100),))
    second = normalize_observations((replace(raw(100), value=110),))
    adapter = SequenceAdapter((first, second))
    service = FundamentalsService(
        store=FinancialObservationStore(tmp_path / "financial.duckdb")
    )
    pipeline = FinancialRefreshPipeline(adapter=adapter, service=service)
    schema = FinancialFrameSchema(
        period_end_column="period_end",
        metrics=(
            MetricColumn(
                source_column="revenue",
                metric_code="revenue",
                metric_label_vi="Doanh thu thuần",
                unit="billion_vnd",
            ),
        ),
        currency="VND",
        consolidated=True,
        value_basis=ValueBasis.STANDALONE,
        source_url="https://example.com/provider/FPT/financials",
    )
    job = FinancialFetchJob(
        statement_type="income_statement",
        period_type="quarter",
        schema=schema,
    )

    first_result = pipeline.refresh_symbol("fpt", (job,))
    second_result = pipeline.refresh_symbol("fpt", (job,))

    assert first_result.inserted == 1
    assert second_result.inserted == 1
    assert adapter.calls[0]["symbol"] == "FPT"
    assert [
        item.restatement_version
        for item in service.store.get_display("FPT")
    ] == [1, 2]
    assert any(
        "excluded from historical backtests" in warning
        for warning in second_result.warnings
    )

