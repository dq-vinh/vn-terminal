from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.data.fundamentals.models import (
    NormalizedFinancialObservation,
    ValueBasis,
)
from backend.app.data.fundamentals.normalization import (
    derive_standalone_quarters,
)
from backend.app.data.fundamentals.store import (
    FinancialDataConflict,
    FinancialObservationStore,
)

INGESTED_AT = datetime(2026, 7, 31, 1, 0, tzinfo=UTC)


def observation(**overrides) -> NormalizedFinancialObservation:
    values = {
        "symbol": "FPT",
        "period_end": date(2025, 12, 31),
        "period_type": "quarter",
        "statement_type": "income_statement",
        "metric_code": "revenue",
        "base_metric_code": "revenue",
        "metric_label_vi": "Doanh thu thuần",
        "value": Decimal(100),
        "currency": "VND",
        "unit": "billion_vnd",
        "consolidated": True,
        "value_basis": ValueBasis.STANDALONE,
        "restatement_version": 1,
        "publication_date": date(2026, 1, 30),
        "source_url": "https://example.com/filings/FPT-2025-Q4-v1",
        "source_name": "issuer_filing",
        "ingested_at": INGESTED_AT,
        "calculation": None,
    }
    values.update(overrides)
    return NormalizedFinancialObservation(**values)


def test_cumulative_quarters_are_retained_and_derived_as_standalone():
    q1 = observation(
        period_end=date(2026, 3, 31),
        metric_code="revenue_cumulative",
        value_basis=ValueBasis.CUMULATIVE,
        value=Decimal(100),
        source_url="https://example.com/filings/FPT-2026-Q1",
    )
    q2 = replace(
        q1,
        period_end=date(2026, 6, 30),
        value=Decimal(250),
        source_url="https://example.com/filings/FPT-2026-Q2",
    )

    result = derive_standalone_quarters((q1, q2))
    standalone = [
        item
        for item in result.observations
        if item.value_basis is ValueBasis.STANDALONE
    ]

    assert [item.value for item in standalone] == [
        Decimal(100),
        Decimal(150),
    ]
    assert all(item.metric_code == "revenue" for item in standalone)
    assert [item.calculation for item in standalone] == [
        "standalone_from_q1_cumulative",
        "standalone_from_cumulative_difference",
    ]
    assert len(result.observations) == 4


def test_cumulative_gap_is_warned_and_never_bridged():
    q1 = observation(
        period_end=date(2026, 3, 31),
        metric_code="revenue_cumulative",
        value_basis=ValueBasis.CUMULATIVE,
    )
    q3 = replace(q1, period_end=date(2026, 9, 30), value=Decimal(400))

    result = derive_standalone_quarters((q1, q3))

    standalone = [
        item
        for item in result.observations
        if item.value_basis is ValueBasis.STANDALONE
    ]
    assert [item.period_end for item in standalone] == [date(2026, 3, 31)]
    warning = (
        "FPT 2026-09-30 revenue cumulative value has no compatible prior "
        "quarter; standalone value was not derived."
    )
    assert result.warnings == (warning,)


def test_store_preserves_versions_and_fails_closed_for_backtests(tmp_path):
    store = FinancialObservationStore(tmp_path / "financial.duckdb")
    version_1 = observation()
    version_2 = replace(
        version_1,
        value=Decimal(110),
        restatement_version=2,
        publication_date=date(2026, 3, 1),
        source_url="https://example.com/filings/FPT-2025-Q4-v2",
    )
    undated_version_3 = replace(
        version_2,
        value=Decimal(120),
        restatement_version=3,
        publication_date=None,
        source_url="https://example.com/filings/FPT-2025-Q4-v3",
    )

    stats = store.append((version_1, version_2, undated_version_3))
    duplicate = store.append((version_1,))

    assert stats.inserted == 3
    assert duplicate.duplicates == 1
    assert [item.restatement_version for item in store.get_display("FPT")] == [
        1,
        2,
        3,
    ]
    assert [
        item.restatement_version
        for item in store.get_for_backtest("FPT", date(2026, 2, 15))
    ] == [1]
    assert [
        item.restatement_version
        for item in store.get_for_backtest("FPT", date(2026, 3, 15))
    ] == [2]


def test_store_rejects_same_version_with_conflicting_payload(tmp_path):
    store = FinancialObservationStore(tmp_path / "financial.duckdb")
    original = observation()
    store.append((original,))

    with pytest.raises(FinancialDataConflict, match="restatement version"):
        store.append((replace(original, value=Decimal(999)),))


def test_store_assigns_deterministic_local_version_when_provider_has_none(
    tmp_path,
):
    store = FinancialObservationStore(tmp_path / "financial.duckdb")
    original = observation()
    store.append_locally_versioned((original,))
    changed = replace(
        original,
        value=Decimal(101),
        publication_date=None,
    )

    result = store.append_locally_versioned((changed,))
    duplicate = store.append_locally_versioned((changed,))

    assert result.observations[0].restatement_version == 2
    assert result.append_stats.inserted == 1
    assert duplicate.append_stats.duplicates == 1
    assert [item.restatement_version for item in store.get_display("FPT")] == [
        1,
        2,
    ]
    assert "assigned local restatement version 2" in result.warnings[0]
