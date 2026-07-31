"""Production orchestration for explicit Vnstock financial fetch jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .normalization import NormalizationResult
from .service import FundamentalsService
from .vnstock_adapter import FinancialFrameSchema


class FinancialAdapter(Protocol):
    def fetch(
        self,
        *,
        symbol: str,
        statement_type: str,
        period_type: str,
        schema: FinancialFrameSchema,
    ) -> NormalizationResult: ...


@dataclass(frozen=True, slots=True)
class FinancialFetchJob:
    statement_type: str
    period_type: str
    schema: FinancialFrameSchema


@dataclass(frozen=True, slots=True)
class FinancialRefreshResult:
    symbol: str
    inserted: int
    duplicates: int
    warnings: tuple[str, ...]


class FinancialRefreshPipeline:
    """Fetch, normalize, derive, version, and persist configured statements."""

    def __init__(
        self,
        *,
        adapter: FinancialAdapter,
        service: FundamentalsService,
    ):
        self.adapter = adapter
        self.service = service

    def refresh_symbol(
        self,
        symbol: str,
        jobs: tuple[FinancialFetchJob, ...],
    ) -> FinancialRefreshResult:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        if not jobs:
            raise ValueError("at least one financial fetch job is required")
        inserted = 0
        duplicates = 0
        warnings: list[str] = []
        for job in jobs:
            result = self.adapter.fetch(
                symbol=normalized_symbol,
                statement_type=job.statement_type,
                period_type=job.period_type,
                schema=job.schema,
            )
            ingestion = self.service.ingest(
                result,
                version_policy=(
                    "provider"
                    if job.schema.restatement_version_column is not None
                    else "local"
                ),
            )
            inserted += ingestion.append_stats.inserted
            duplicates += ingestion.append_stats.duplicates
            warnings.extend(ingestion.warnings)
        return FinancialRefreshResult(
            symbol=normalized_symbol,
            inserted=inserted,
            duplicates=duplicates,
            warnings=tuple(dict.fromkeys(warnings)),
        )

