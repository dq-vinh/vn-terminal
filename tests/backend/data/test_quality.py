from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.app.data.fdata.parser import FDataParser
from backend.app.data.quality.checks import (
    ALL_CHECK_IDS,
    CriticalDataQualityError,
    assert_strategy_safe,
    assess_file,
    build_repository_summary,
    detect_historical_revisions,
    scan_repository,
)


def test_all_fourteen_quality_checks_are_registered():
    assert ALL_CHECK_IDS == set(range(1, 15))


def test_quality_checks_flag_values_and_calculate_liquidity_metrics(
    tmp_path, fdata_writer
):
    source = fdata_writer(
        tmp_path / "stock" / "BAD.dat",
        [
            (20260724, 10, 9, 11, 8, 100, 9, 1),
            (20260727, 0, 10, 1, 9, 0, 9, 1),
            (20260728, 9, 10, 8, 9, 0, 9, 1),
            (20260729, 9, 10, 8, 9, 0, 9, 1),
            (20260730, 9, 10, 8, 9, 0, 9, 1),
            (20260731, 9, 10, 8, 9, 0, 9, 1),
        ],
    )
    parsed = FDataParser().parse_file(source, "stock")

    result = assess_file(
        parsed,
        reference_date=date(2026, 7, 31),
        security_type="unknown",
        freshness_days=0,
    )

    codes = {issue.code for issue in result.issues}
    assert "nonpositive_price" in codes
    assert "ohlc_violation" in codes
    assert "terminal_zero_volume_run" in codes
    assert "unknown_security_type" in codes
    assert result.last_positive_volume_date == date(2026, 7, 24)
    assert result.terminal_zero_volume_run == 5
    assert result.zero_volume_records == 5
    assert result.blocks_strategy_execution

    with pytest.raises(CriticalDataQualityError):
        assert_strategy_safe(result)


def test_repository_summary_counts_files_not_individual_bad_rows(
    tmp_path, fdata_writer
):
    bad = fdata_writer(
        tmp_path / "stock" / "BAD.dat",
        [
            (20260729, 10, 9, 11, 8, 0, 9, 1),
            (20260730, 10, 9, 11, 8, 0, 9, 1),
        ],
    )
    good = fdata_writer(
        tmp_path / "stock" / "GOOD.dat",
        [(20260730, 8, 10, 7, 9, 100, 9, 1)],
    )
    parsed = [
        FDataParser().parse_file(bad, "stock"),
        FDataParser().parse_file(good, "stock"),
    ]

    summary = build_repository_summary(parsed, reference_date=date(2026, 7, 30))

    assert summary.file_count == 2
    assert summary.record_count == 3
    assert summary.ohlc_violation_files == 1
    assert summary.zero_volume_records == 2
    assert summary.zero_volume_records_all_categories == 2
    assert summary.current_files == 2


def test_zero_volume_baseline_is_stock_only_but_all_categories_are_reported(
    tmp_path, fdata_writer
):
    fdata_writer(
        tmp_path / "stock" / "AAA.dat",
        [(20260730, 1, 1, 1, 1, 0, 1, 1)],
    )
    fdata_writer(
        tmp_path / "index" / "0001.dat",
        [(20260730, 1, 1, 1, 1, 0, 1, 1)],
    )

    summary = scan_repository(tmp_path, reference_date=date(2026, 7, 30))

    assert summary.zero_volume_records == 1
    assert summary.zero_volume_records_all_categories == 2


def test_historical_revisions_compare_only_overlapping_dates(
    tmp_path, fdata_writer
):
    previous_path = fdata_writer(
        tmp_path / "previous" / "FPT.dat",
        [(20260729, 63, 65, 62, 64, 100, 64, 1)],
    )
    current_path = fdata_writer(
        tmp_path / "current" / "FPT.dat",
        [
            (20260729, 63, 65, 62, 64.5, 100, 64, 1),
            (20260730, 64, 67, 64, 67, 200, 66, 1),
        ],
    )
    parser = FDataParser()

    revisions = detect_historical_revisions(
        parser.parse_file(previous_path, "stock"),
        parser.parse_file(current_path, "stock"),
    )

    assert revisions == (20260729,)


def test_live_repository_reproduces_30_july_baseline_when_available():
    source_root = Path(r"C:\FDATA\AmiBroker\EOD")
    if not source_root.exists():
        pytest.skip("Live FData repository is not installed")

    summary = scan_repository(
        source_root, reference_date=date(2026, 7, 30)
    )

    assert summary.file_count == 2_471
    assert summary.record_count == 3_632_818
    assert summary.ohlc_violation_files == 505
    assert summary.nonpositive_price_files == 34
    assert summary.zero_volume_records == 11_020
    assert summary.terminal_zero_volume_stock_files == 301
    assert summary.current_files == 2_315
    assert summary.malformed_files == 1
