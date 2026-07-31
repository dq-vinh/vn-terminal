from __future__ import annotations

from datetime import UTC, date, datetime

from backend.app.data.fdata.parser import FDataParser
from backend.app.data.storage.duckdb_store import DuckDBStore
from backend.app.data.storage.snapshots import SnapshotManager


def test_duckdb_queries_parquet_bars(tmp_path, fdata_writer):
    source = fdata_writer(
        tmp_path / "source" / "stock" / "FPT.dat",
        [
            (20260729, 63, 65.3, 62.5, 65.1, 100, 63.79, 1),
            (20260730, 65.2, 67.2, 64.8, 67.0, 200, 66.56, 1),
        ],
    )
    parsed = FDataParser().parse_file(source, "stock")
    manager = SnapshotManager(tmp_path / "snapshots")
    candidate = manager.stage(
        [parsed],
        data_version="fdata-test",
        as_of_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
    )
    manager.promote(candidate, valid=True)
    store = DuckDBStore(tmp_path / "catalog.duckdb", manager)

    bars = store.get_bars("FPT", start_date=date(2026, 7, 30))

    assert len(bars) == 1
    assert bars[0].symbol == "FPT"
    assert bars[0].close == 67.0
    assert bars[0].volume == 200
