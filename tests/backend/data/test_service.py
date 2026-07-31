from __future__ import annotations

from datetime import UTC, date, datetime

from backend.app.data.pipeline import RefreshPipeline
from backend.app.data.service import DataService
from backend.app.data.storage.duckdb_store import DuckDBStore
from backend.app.data.storage.snapshots import SnapshotManager


def _build_service(tmp_path, fdata_writer):
    source_root = tmp_path / "EOD"
    fdata_writer(
        source_root / "stock" / "FPT.dat",
        [
            (20260720, 10, 12, 9, 11, 100, 11, 1),
            (20260724, 11, 14, 10, 13, 200, 12, 1),
            (20260730, 13, 15, 12, 14, 300, 14, 1),
        ],
    )
    for category, symbol in (
        ("index", "0001"),
        ("der", "VN30F2608"),
        ("cw", "CFPT2601"),
    ):
        fdata_writer(
            source_root / category / f"{symbol}.dat",
            [(20260730, 10, 11, 9, 10, 100, 10, 1)],
        )
    snapshots = SnapshotManager(tmp_path / "snapshots")
    pipeline = RefreshPipeline(source_root=source_root, snapshots=snapshots)
    result = pipeline.run(
        reference_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
    )
    assert result.promoted
    store = DuckDBStore(tmp_path / "catalog.duckdb", snapshots)
    return DataService(
        store=store,
        snapshots=snapshots,
        pipeline=pipeline,
    )


def test_service_lists_symbols_and_returns_daily_bars(tmp_path, fdata_writer):
    service = _build_service(tmp_path, fdata_writer)

    symbols = service.list_symbols(
        q="FPT",
        exchange=None,
        security_type="unknown",
        trading_status=None,
        limit=100,
        offset=0,
    )
    bars = service.get_bars(
        symbol="FPT",
        timeframe="1D",
        start_date=date(2026, 7, 24),
        end_date=None,
    )

    assert symbols.total == 1
    assert symbols.items[0].symbol == "FPT"
    assert bars is not None
    assert len(bars.bars) == 2
    assert bars.provenance.data_version == "fdata-2026-07-30"
    assert service.get_bars(
        symbol="MISSING",
        timeframe="1D",
        start_date=None,
        end_date=None,
    ) is None


def test_service_aggregates_weekly_bars_without_using_aux1(
    tmp_path, fdata_writer
):
    service = _build_service(tmp_path, fdata_writer)

    response = service.get_bars(
        symbol="FPT",
        timeframe="1W",
        start_date=None,
        end_date=None,
    )

    assert response is not None
    assert len(response.bars) == 2
    first = response.bars[0]
    assert first.open == 10
    assert first.high == 14
    assert first.low == 9
    assert first.close == 13
    assert first.volume == 300
    assert first.timeframe == "1W"
