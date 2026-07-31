"""DuckDB catalog and direct Parquet querying."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from contracts.schemas.models.price_bar import PriceBar
from contracts.schemas.models.security_master import SecurityMaster

from .snapshots import SnapshotManager


class DuckDBStore:
    def __init__(self, database_path: Path, snapshots: SnapshotManager):
        self.database_path = Path(database_path)
        self.snapshots = snapshots
        self._initialize()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.database_path))

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot_catalog (
                    data_version VARCHAR PRIMARY KEY,
                    as_of_date DATE NOT NULL,
                    snapshot_path VARCHAR NOT NULL,
                    content_sha256 VARCHAR NOT NULL,
                    promoted_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_runs (
                    run_id VARCHAR PRIMARY KEY,
                    status VARCHAR NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    finished_at TIMESTAMPTZ,
                    issue_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def get_bars(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        snapshot = self.snapshots.current_snapshot_path()
        if snapshot is None:
            return []
        parquet_glob = (snapshot / "bars" / "**" / "*.parquet").as_posix()
        sql = (
            "SELECT symbol, exchange, security_type, timeframe, trading_date, "
            "timezone, open, high, low, close, volume, adjustment_status, "
            "source, source_file, ingested_at, quality_status "
            "FROM read_parquet(?) "
            "WHERE upper(symbol) = upper(?) "
            "AND (? IS NULL OR trading_date >= ?) "
            "AND (? IS NULL OR trading_date <= ?) "
            "ORDER BY trading_date"
        )
        parameters = [
            parquet_glob,
            symbol,
            start_date,
            start_date,
            end_date,
            end_date,
        ]
        with self._connect() as connection:
            cursor = connection.execute(sql, parameters)
            columns = [item[0] for item in cursor.description]
            return [
                PriceBar.model_validate(dict(zip(columns, row, strict=True)))
                for row in cursor.fetchall()
            ]

    def list_symbols(
        self,
        *,
        q: str | None,
        exchange: str | None,
        security_type: str | None,
        trading_status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[SecurityMaster], int]:
        snapshot = self.snapshots.current_snapshot_path()
        if snapshot is None:
            return [], 0
        security_file = (snapshot / "security_master.parquet").as_posix()
        search = f"%{q}%" if q else None
        sql = (
            "SELECT symbol, isin, exchange, security_type, company_name, "
            "sector, industry, listing_date, delisting_date, trading_status, "
            "currency, price_unit, lot_size, source, valid_from, valid_to, "
            "index_code, count(*) OVER () AS total_count "
            "FROM read_parquet(?) "
            "WHERE (? IS NULL OR upper(symbol) LIKE upper(?) "
            "OR upper(company_name) LIKE upper(?)) "
            "AND (? IS NULL OR upper(exchange) = upper(?)) "
            "AND (? IS NULL OR upper(security_type) = upper(?)) "
            "AND (? IS NULL OR upper(trading_status) = upper(?)) "
            "ORDER BY symbol LIMIT ? OFFSET ?"
        )
        parameters = [
            security_file,
            search,
            search,
            search,
            exchange,
            exchange,
            security_type,
            security_type,
            trading_status,
            trading_status,
            limit,
            offset,
        ]
        with self._connect() as connection:
            cursor = connection.execute(sql, parameters)
            columns = [item[0] for item in cursor.description]
            rows = cursor.fetchall()
        if not rows:
            return [], 0
        total_index = columns.index("total_count")
        contract_columns = columns[:total_index]
        items = [
            SecurityMaster.model_validate(
                dict(zip(contract_columns, row[:total_index], strict=True))
            )
            for row in rows
        ]
        return items, int(rows[0][total_index])
