from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pyarrow.parquet as pq

from backend.app.data.fdata.parser import FDataParser
from backend.app.data.storage.snapshots import SnapshotManager


def test_snapshot_hash_is_reproducible_and_parquet_has_provenance(
    tmp_path, fdata_writer
):
    source = fdata_writer(
        tmp_path / "source" / "stock" / "FPT.dat",
        [(20260730, 65.2, 67.2, 64.8, 67.0, 7_571_500, 66.565, 15)],
    )
    parsed = FDataParser().parse_file(source, "stock")
    manager = SnapshotManager(tmp_path / "snapshots")

    first = manager.stage(
        [parsed],
        data_version="fdata-test",
        as_of_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
    )
    second = manager.stage(
        [parsed],
        data_version="fdata-test",
        as_of_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 23, 0, tzinfo=UTC),
    )

    assert first.content_sha256 == second.content_sha256
    metadata = pq.read_metadata(first.bars_files[0]).metadata or {}
    assert metadata[b"data_version"] == b"fdata-test"
    assert metadata[b"snapshot_format_version"] == b"1.0.0"
    assert metadata[b"source"] == b"Fialda FData"
    assert metadata[b"content_sha256"] == first.content_sha256.encode()


def test_invalid_candidate_never_replaces_last_good_snapshot(
    tmp_path, fdata_writer
):
    source = fdata_writer(
        tmp_path / "source" / "stock" / "FPT.dat",
        [(20260730, 65.2, 67.2, 64.8, 67.0, 100, 66.5, 1)],
    )
    parsed = FDataParser().parse_file(source, "stock")
    manager = SnapshotManager(tmp_path / "snapshots")
    good = manager.stage(
        [parsed],
        data_version="good",
        as_of_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
    )
    manager.promote(good, valid=True)

    bad = manager.stage(
        [parsed],
        data_version="bad",
        as_of_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 23, 0, tzinfo=UTC),
    )
    promoted = manager.promote(bad, valid=False)

    assert promoted is False
    assert manager.current_version() == "good"


def test_promotion_atomically_swaps_pointer_without_renaming_directory(
    tmp_path, fdata_writer, monkeypatch
):
    source = fdata_writer(
        tmp_path / "source" / "stock" / "FPT.dat",
        [(20260730, 1, 1, 1, 1, 100, 1, 1)],
    )
    parsed = FDataParser().parse_file(source, "stock")
    manager = SnapshotManager(tmp_path / "snapshots")
    candidate = manager.stage(
        [parsed],
        data_version="pointer-only",
        as_of_date=date(2026, 7, 30),
        generated_at=datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
    )
    original_replace = os.replace

    def reject_directory_rename(source_path, destination_path):
        assert not type(candidate.path)(source_path).is_dir()
        return original_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", reject_directory_rename)

    assert manager.promote(candidate, valid=True)
    assert candidate.path.exists()
    assert manager.current_snapshot_path() == candidate.path
