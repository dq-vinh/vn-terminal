"""WP9 ingestion and frozen-contract response service."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from contracts.schemas.models.api_envelopes import FundamentalsResponse
from contracts.schemas.models.common import PeriodType, Provenance
from contracts.schemas.models.financial_observation import FinancialObservation

from .metrics import PricePoint, calculate_panel_metrics
from .models import NormalizedFinancialObservation
from .normalization import (
    NormalizationResult,
    derive_standalone_quarters,
)
from .store import AppendStats, FinancialObservationStore


@dataclass(frozen=True, slots=True)
class FinancialIngestionResult:
    append_stats: AppendStats
    warnings: tuple[str, ...]


def _contract_observation(
    item: NormalizedFinancialObservation,
) -> FinancialObservation:
    return FinancialObservation(
        symbol=item.symbol,
        period_end=item.period_end,
        period_type=PeriodType(item.period_type),
        statement_type=item.statement_type,
        metric_code=item.metric_code,
        metric_label_vi=item.metric_label_vi,
        value=float(item.value),
        currency=item.currency,
        unit=item.unit,
        consolidated=item.consolidated,
        restatement_version=item.restatement_version,
        publication_date=item.publication_date,
        source_url=item.source_url,
        ingested_at=item.ingested_at,
    )


def _data_version(
    observations: tuple[NormalizedFinancialObservation, ...],
) -> str:
    digest = hashlib.sha256()
    for item in sorted(
        observations,
        key=lambda value: (
            value.symbol,
            value.period_end,
            value.statement_type,
            value.metric_code,
            value.consolidated,
            value.restatement_version,
        ),
    ):
        fields = (
            item.symbol,
            item.period_end.isoformat(),
            item.period_type,
            item.statement_type,
            item.metric_code,
            item.base_metric_code,
            str(item.value),
            item.currency,
            item.unit,
            str(item.consolidated),
            item.value_basis.value,
            str(item.restatement_version),
            (
                item.publication_date.isoformat()
                if item.publication_date is not None
                else ""
            ),
            item.source_url,
        )
        digest.update("\x1f".join(fields).encode())
        digest.update(b"\n")
    return f"financial-{digest.hexdigest()[:16]}"


class FundamentalsService:
    """Serve display/current views and an explicit fail-closed backtest view."""

    def __init__(
        self,
        *,
        store: FinancialObservationStore,
        price_provider: Callable[[str], PricePoint | None] | None = None,
    ):
        self.store = store
        self.price_provider = price_provider

    def ingest(
        self,
        normalized: NormalizationResult,
        *,
        version_policy: Literal["provider", "local"] = "provider",
    ) -> FinancialIngestionResult:
        derived = derive_standalone_quarters(normalized.observations)
        local_warnings: tuple[str, ...] = ()
        if version_policy == "local":
            local_result = self.store.append_locally_versioned(
                derived.observations
            )
            stats = local_result.append_stats
            local_warnings = local_result.warnings
        else:
            stats = self.store.append(derived.observations)
        return FinancialIngestionResult(
            append_stats=stats,
            warnings=(
                normalized.warnings + derived.warnings + local_warnings
            ),
        )

    def get_fundamentals(
        self, symbol: str
    ) -> FundamentalsResponse | None:
        observations = self.store.get_display(symbol)
        if not observations:
            return None
        normalized_symbol = observations[0].symbol
        price = (
            self.price_provider(normalized_symbol)
            if self.price_provider is not None
            else None
        )
        calculations = calculate_panel_metrics(observations, price=price)
        all_observations = observations + calculations.trace_observations
        warnings = list(calculations.warnings)
        for item in observations:
            if item.publication_date is None:
                warning = (
                    f"{item.symbol} {item.period_end.isoformat()} "
                    f"{item.metric_code} has no publication date; it is "
                    "available for display and current screening but excluded "
                    "from historical backtests."
                )
                if warning not in warnings:
                    warnings.append(warning)
        missing_publication = any(
            item.publication_date is None for item in observations
        )
        sources = ", ".join(
            sorted({item.source_name for item in observations})
        )
        return FundamentalsResponse(
            symbol=normalized_symbol,
            observations=[
                _contract_observation(item) for item in all_observations
            ],
            derived_metrics=list(calculations.metrics),
            provenance=Provenance(
                as_of_date=max(item.period_end for item in observations),
                data_version=_data_version(observations),
                source=sources,
                freshness_status=(
                    "degraded_point_in_time"
                    if missing_publication
                    else "current"
                ),
                warnings=warnings,
            ),
        )

    def get_for_backtest(
        self, symbol: str, as_of_date: date
    ) -> tuple[NormalizedFinancialObservation, ...]:
        return self.store.get_for_backtest(symbol, as_of_date)
