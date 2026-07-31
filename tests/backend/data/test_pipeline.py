from __future__ import annotations

from datetime import date

import pyarrow.parquet as pq

from backend.app.data.pipeline import RefreshPipeline
from backend.app.data.storage.snapshots import SnapshotManager


def _complete_source(root, fdata_writer):
    rows = [(20260730, 10, 11, 9, 10, 100, 10, 1)]
    for category, symbol in (
        ("stock", "FPT"),
        ("index", "0001"),
        ("der", "VN30F2608"),
        ("cw", "CFPT2601"),
    ):
        fdata_writer(root / category / f"{symbol}.dat", rows)


def test_refresh_writes_quality_and_security_parquet_then_promotes(
    tmp_path, fdata_writer
):
    source_root = tmp_path / "EOD"
    _complete_source(source_root, fdata_writer)
    snapshots = SnapshotManager(tmp_path / "snapshots")
    pipeline = RefreshPipeline(source_root=source_root, snapshots=snapshots)

    result = pipeline.run(reference_date=date(2026, 7, 30))

    assert result.promoted
    assert result.summary.file_count == 4
    assert result.summary.record_count == 4
    assert result.index_mapping_status == "blocked_no_authoritative_source"
    current = snapshots.current_snapshot_path()
    assert current is not None
    assert (current / "security_master.parquet").exists()
    assert (current / "quality_issues.parquet").exists()
    security = pq.read_table(current / "security_master.parquet").to_pylist()
    numeric_index = next(row for row in security if row["symbol"] == "0001")
    assert numeric_index["trading_status"] == "blocked_missing_index_mapping"
    assert numeric_index["last_positive_volume_date"] == date(2026, 7, 30)
    fpt_bar = pq.read_table(
        current / "bars" / "stock" / "FPT.parquet"
    ).to_pylist()[0]
    assert fpt_bar["quality_status"] == "high"


def test_partial_refresh_never_replaces_last_good_snapshot(
    tmp_path, fdata_writer
):
    source_root = tmp_path / "EOD"
    _complete_source(source_root, fdata_writer)
    snapshots = SnapshotManager(tmp_path / "snapshots")
    pipeline = RefreshPipeline(source_root=source_root, snapshots=snapshots)
    good = pipeline.run(reference_date=date(2026, 7, 30))
    assert good.promoted
    good_version = snapshots.current_version()

    (source_root / "cw" / "CFPT2601.dat").unlink()
    partial = pipeline.run(reference_date=date(2026, 7, 30))

    assert not partial.promoted
    assert "missing_or_empty_category:cw" in partial.blocking_reasons
    assert snapshots.current_version() == good_version
