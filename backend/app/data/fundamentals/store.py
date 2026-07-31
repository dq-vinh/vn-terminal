"""Append-only DuckDB storage and fail-closed point-in-time selection."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import duckdb

from .models import NormalizedFinancialObservation, ValueBasis


class FinancialDataConflict(ValueError):
    """A provider reused a restatement version for different content."""


@dataclass(frozen=True, slots=True)
class AppendStats:
    inserted: int
    duplicates: int


@dataclass(frozen=True, slots=True)
class LocalVersionAppendResult:
    append_stats: AppendStats
    observations: tuple[NormalizedFinancialObservation, ...]
    warnings: tuple[str, ...]


SELECT_IDENTITY_SQL = """
    SELECT symbol, period_end, period_type, statement_type, metric_code,
        base_metric_code, metric_label_vi, value_text, currency, unit,
        consolidated, value_basis, restatement_version, publication_date,
        source_url, source_name, ingested_at, calculation
    FROM financial_observations
    WHERE symbol = ? AND period_end = ? AND period_type = ?
      AND statement_type = ? AND metric_code = ? AND consolidated = ?
      AND restatement_version = ?
"""
SELECT_DISPLAY_SQL = """
    SELECT symbol, period_end, period_type, statement_type, metric_code,
        base_metric_code, metric_label_vi, value_text, currency, unit,
        consolidated, value_basis, restatement_version, publication_date,
        source_url, source_name, ingested_at, calculation
    FROM financial_observations
    WHERE upper(symbol) = upper(?)
    ORDER BY period_end, statement_type, metric_code, consolidated,
        restatement_version
"""
SELECT_LATEST_SERIES_SQL = """
    SELECT symbol, period_end, period_type, statement_type, metric_code,
        base_metric_code, metric_label_vi, value_text, currency, unit,
        consolidated, value_basis, restatement_version, publication_date,
        source_url, source_name, ingested_at, calculation
    FROM financial_observations
    WHERE symbol = ? AND period_end = ? AND period_type = ?
      AND statement_type = ? AND metric_code = ? AND consolidated = ?
    ORDER BY restatement_version DESC LIMIT 1
"""
SELECT_BACKTEST_SQL = """
    SELECT symbol, period_end, period_type, statement_type, metric_code,
        base_metric_code, metric_label_vi, value_text, currency, unit,
        consolidated, value_basis, restatement_version, publication_date,
        source_url, source_name, ingested_at, calculation
    FROM (
        SELECT symbol, period_end, period_type, statement_type, metric_code,
            base_metric_code, metric_label_vi, value_text, currency, unit,
            consolidated, value_basis, restatement_version, publication_date,
            source_url, source_name, ingested_at, calculation,
            row_number() OVER (
                PARTITION BY symbol, period_end, period_type,
                    statement_type, metric_code, consolidated
                ORDER BY restatement_version DESC, publication_date DESC,
                    ingested_at DESC
            ) AS version_rank
        FROM financial_observations
        WHERE upper(symbol) = upper(?)
          AND publication_date IS NOT NULL
          AND publication_date <= ?
    ) WHERE version_rank = 1
    ORDER BY period_end, statement_type, metric_code, consolidated
"""


def _identity(item: NormalizedFinancialObservation) -> list[object]:
    return [
        item.symbol,
        item.period_end,
        item.period_type,
        item.statement_type,
        item.metric_code,
        item.consolidated,
        item.restatement_version,
    ]


def _semantic_payload(
    item: NormalizedFinancialObservation,
) -> tuple[object, ...]:
    return (
        item.base_metric_code,
        item.metric_label_vi,
        item.value,
        item.currency,
        item.unit,
        item.value_basis,
        item.publication_date,
        item.source_url,
        item.source_name,
        item.calculation,
    )


def _from_row(row: tuple[object, ...]) -> NormalizedFinancialObservation:
    return NormalizedFinancialObservation(
        symbol=str(row[0]),
        period_end=cast(date, row[1]),
        period_type=str(row[2]),
        statement_type=str(row[3]),
        metric_code=str(row[4]),
        base_metric_code=str(row[5]),
        metric_label_vi=str(row[6]),
        value=Decimal(str(row[7])),
        currency=str(row[8]),
        unit=str(row[9]),
        consolidated=bool(row[10]),
        value_basis=ValueBasis(str(row[11])),
        restatement_version=int(str(row[12])),
        publication_date=cast(date | None, row[13]),
        source_url=str(row[14]),
        source_name=str(row[15]),
        ingested_at=datetime.fromisoformat(str(row[16])),
        calculation=str(row[17]) if row[17] is not None else None,
    )


class FinancialObservationStore:
    """Preserve revisions and expose explicit display/backtest views."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.database_path))

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_observations (
                    symbol VARCHAR NOT NULL,
                    period_end DATE NOT NULL,
                    period_type VARCHAR NOT NULL,
                    statement_type VARCHAR NOT NULL,
                    metric_code VARCHAR NOT NULL,
                    base_metric_code VARCHAR NOT NULL,
                    metric_label_vi VARCHAR NOT NULL,
                    value_text VARCHAR NOT NULL,
                    currency VARCHAR NOT NULL,
                    unit VARCHAR NOT NULL,
                    consolidated BOOLEAN NOT NULL,
                    value_basis VARCHAR NOT NULL,
                    restatement_version INTEGER NOT NULL,
                    publication_date DATE,
                    source_url VARCHAR NOT NULL,
                    source_name VARCHAR NOT NULL,
                    ingested_at VARCHAR NOT NULL,
                    calculation VARCHAR
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS financial_observation_version
                ON financial_observations (
                    symbol, period_end, period_type, statement_type,
                    metric_code, consolidated, restatement_version
                )
                """
            )

    def append(
        self,
        observations: tuple[NormalizedFinancialObservation, ...],
    ) -> AppendStats:
        inserted = 0
        duplicates = 0
        with self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                for item in observations:
                    existing = connection.execute(
                        SELECT_IDENTITY_SQL,
                        _identity(item),
                    ).fetchone()
                    if existing is not None:
                        stored = _from_row(existing)
                        if _semantic_payload(stored) != _semantic_payload(item):
                            raise FinancialDataConflict(
                                f"{item.symbol} {item.period_end} "
                                f"{item.metric_code} restatement version "
                                f"{item.restatement_version} conflicts with "
                                "stored content"
                            )
                        duplicates += 1
                        continue
                    connection.execute(
                        """
                        INSERT INTO financial_observations VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?
                        )
                        """,
                        [
                            item.symbol,
                            item.period_end,
                            item.period_type,
                            item.statement_type,
                            item.metric_code,
                            item.base_metric_code,
                            item.metric_label_vi,
                            str(item.value),
                            item.currency,
                            item.unit,
                            item.consolidated,
                            item.value_basis.value,
                            item.restatement_version,
                            item.publication_date,
                            item.source_url,
                            item.source_name,
                            item.ingested_at.isoformat(),
                            item.calculation,
                        ],
                    )
                    inserted += 1
            except Exception:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
        return AppendStats(inserted=inserted, duplicates=duplicates)

    def get_display(
        self, symbol: str
    ) -> tuple[NormalizedFinancialObservation, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                SELECT_DISPLAY_SQL,
                [symbol],
            ).fetchall()
        return tuple(_from_row(row) for row in rows)

    def append_locally_versioned(
        self,
        observations: tuple[NormalizedFinancialObservation, ...],
    ) -> LocalVersionAppendResult:
        """Assign sequential versions when the provider has no version field."""

        inserted = 0
        duplicates = 0
        effective: list[NormalizedFinancialObservation] = []
        warnings: list[str] = []
        for item in observations:
            with self._connect() as connection:
                row = connection.execute(
                    SELECT_LATEST_SERIES_SQL,
                    _identity(item)[:-1],
                ).fetchone()
            if row is None:
                candidate = replace(item, restatement_version=1)
                stats = self.append((candidate,))
                inserted += stats.inserted
                duplicates += stats.duplicates
                effective.append(candidate)
                continue
            latest = _from_row(row)
            if _semantic_payload(latest) == _semantic_payload(item):
                duplicates += 1
                effective.append(latest)
                continue
            version = latest.restatement_version + 1
            candidate = replace(item, restatement_version=version)
            stats = self.append((candidate,))
            inserted += stats.inserted
            duplicates += stats.duplicates
            effective.append(candidate)
            warnings.append(
                f"{item.symbol} {item.period_end.isoformat()} "
                f"{item.metric_code}: provider supplied no restatement "
                f"version; assigned local restatement version {version}."
            )
        return LocalVersionAppendResult(
            append_stats=AppendStats(
                inserted=inserted,
                duplicates=duplicates,
            ),
            observations=tuple(effective),
            warnings=tuple(warnings),
        )

    def get_for_backtest(
        self, symbol: str, as_of_date: date
    ) -> tuple[NormalizedFinancialObservation, ...]:
        """Select only observations known by the historical decision date."""

        with self._connect() as connection:
            rows = connection.execute(
                SELECT_BACKTEST_SQL,
                [symbol, as_of_date],
            ).fetchall()
        return tuple(_from_row(row) for row in rows)
