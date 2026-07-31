"""Concrete service behind the WP3 data router."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from contracts.schemas.models.api_envelopes import (
    BarsResponse,
    DatabaseStatus,
    DataRefreshResponse,
    DataStatusResponse,
    FundamentalsResponse,
    HealthResponse,
    SnapshotInfo,
    SymbolsResponse,
)
from contracts.schemas.models.common import Provenance, Timeframe
from contracts.schemas.models.price_bar import PriceBar

from .pipeline import RefreshPipeline, RefreshResult
from .storage.duckdb_store import DuckDBStore
from .storage.snapshots import SnapshotManager

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class FundamentalsServiceProtocol(Protocol):
    def get_fundamentals(
        self, symbol: str
    ) -> FundamentalsResponse | None: ...


def _timeframe_value(timeframe: Timeframe | str) -> str:
    return timeframe.value if isinstance(timeframe, Timeframe) else timeframe


def _aggregate_bars(
    bars: Iterable[PriceBar], timeframe: str
) -> list[PriceBar]:
    materialized = list(bars)
    if timeframe == "1D":
        return materialized
    groups: dict[tuple[int, ...], list[PriceBar]] = {}
    for bar in materialized:
        if timeframe == "1W":
            iso = bar.trading_date.isocalendar()
            key = (iso.year, iso.week)
        elif timeframe == "1M":
            key = (bar.trading_date.year, bar.trading_date.month)
        else:
            raise ValueError(f"Unsupported timeframe {timeframe}")
        groups.setdefault(key, []).append(bar)

    aggregated = []
    for group_key in sorted(groups):
        group = groups[group_key]
        first, last = group[0], group[-1]
        aggregated.append(
            PriceBar(
                symbol=first.symbol,
                exchange=first.exchange,
                security_type=first.security_type,
                timeframe=Timeframe(timeframe),
                trading_date=last.trading_date,
                timezone=first.timezone,
                open=first.open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=last.close,
                volume=sum(item.volume for item in group),
                adjustment_status=first.adjustment_status,
                source=first.source,
                source_file=(
                    f"snapshot_aggregate:{timeframe}:{first.symbol}"
                ),
                ingested_at=last.ingested_at,
                quality_status="valid_aggregated",
            )
        )
    return aggregated


class DataService:
    def __init__(
        self,
        *,
        store: DuckDBStore,
        snapshots: SnapshotManager,
        pipeline: RefreshPipeline,
        fundamentals_service: FundamentalsServiceProtocol | None = None,
    ):
        self.store = store
        self.snapshots = snapshots
        self.pipeline = pipeline
        self.fundamentals_service = fundamentals_service
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="fdata-refresh"
        )
        self._lock = threading.Lock()
        self._future: Future[RefreshResult] | None = None
        self._run_id: str | None = None
        self._status = "idle"
        self._progress_pct: float | None = None
        self._issues: list[str] = []
        self._started_at: datetime | None = None

    def _provenance(self) -> Provenance:
        info = self.snapshots.current_info()
        today = datetime.now(VIETNAM_TZ).date()
        if info is None:
            return Provenance(
                as_of_date=today,
                data_version="none",
                source="Fialda FData",
                freshness_status="unavailable",
                warnings=["No validated snapshot is available."],
            )
        as_of = date.fromisoformat(info["as_of_date"])
        return Provenance(
            as_of_date=as_of,
            data_version=info["data_version"],
            source="Fialda FData",
            freshness_status="current" if as_of == today else "stale",
            warnings=[] if as_of == today else ["Snapshot is not current."],
        )

    def health(self) -> HealthResponse:
        provenance = self._provenance()
        return HealthResponse(
            status=(
                "ok"
                if self.snapshots.current_snapshot_path() is not None
                else "degraded"
            ),
            database=DatabaseStatus(
                connected=self.store.database_path.exists(),
                latest_snapshot_date=(
                    provenance.as_of_date
                    if provenance.data_version != "none"
                    else None
                ),
            ),
            providers=[],
            provenance=provenance,
        )

    def start_refresh(self, *, force: bool) -> DataRefreshResponse:
        del force  # A refresh request always re-reads source files.
        with self._lock:
            if self._future is not None and not self._future.done():
                return DataRefreshResponse(
                    run_id=self._run_id or "unknown",
                    status=self._status,
                    started_at=self._started_at
                    or datetime.now(VIETNAM_TZ),
                    provenance=self._provenance(),
                )
            self._run_id = uuid.uuid4().hex
            self._status = "queued"
            self._progress_pct = 0
            self._issues = []
            self._started_at = datetime.now(VIETNAM_TZ)
            self._future = self._executor.submit(
                self._execute_refresh, self._run_id
            )
            return DataRefreshResponse(
                run_id=self._run_id,
                status=self._status,
                started_at=self._started_at,
                provenance=self._provenance(),
            )

    def _execute_refresh(self, run_id: str) -> RefreshResult:
        with self._lock:
            if run_id != self._run_id:
                raise RuntimeError("Refresh run id changed unexpectedly")
            self._status = "running"
            self._progress_pct = 10
        try:
            result = self.pipeline.run(
                reference_date=datetime.now(VIETNAM_TZ).date()
            )
        except Exception as exc:
            with self._lock:
                self._status = "failed"
                self._progress_pct = 100
                self._issues = [str(exc)]
            raise
        with self._lock:
            self._status = "completed" if result.promoted else "failed"
            self._progress_pct = 100
            self._issues = list(result.blocking_reasons)
        return result

    def data_status(self) -> DataStatusResponse:
        info = self.snapshots.current_info()
        latest = None
        if info is not None:
            latest = SnapshotInfo(
                data_version=info["data_version"],
                as_of_date=date.fromisoformat(info["as_of_date"]),
                promoted_at=datetime.fromisoformat(info["promoted_at"]),
            )
        with self._lock:
            return DataStatusResponse(
                run_id=self._run_id,
                status=self._status,
                progress_pct=self._progress_pct,
                latest_good_snapshot=latest,
                issues=list(self._issues),
                provenance=self._provenance(),
            )

    def list_symbols(
        self,
        *,
        q: str | None,
        exchange: str | None,
        security_type: str | None,
        trading_status: str | None,
        limit: int,
        offset: int,
    ) -> SymbolsResponse:
        items, total = self.store.list_symbols(
            q=q,
            exchange=exchange,
            security_type=security_type,
            trading_status=trading_status,
            limit=limit,
            offset=offset,
        )
        return SymbolsResponse(
            items=items, total=total, provenance=self._provenance()
        )

    def get_bars(
        self,
        *,
        symbol: str,
        timeframe: Timeframe | str,
        start_date: date | None,
        end_date: date | None,
    ) -> BarsResponse | None:
        daily = self.store.get_bars(
            symbol, start_date=start_date, end_date=end_date
        )
        if not daily:
            return None
        value = _timeframe_value(timeframe)
        return BarsResponse(
            symbol=symbol.upper(),
            timeframe=Timeframe(value),
            bars=_aggregate_bars(daily, value),
            provenance=self._provenance(),
        )

    def get_fundamentals(
        self, symbol: str
    ) -> FundamentalsResponse | None:
        if self.fundamentals_service is None:
            return None
        return self.fundamentals_service.get_fundamentals(symbol)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
