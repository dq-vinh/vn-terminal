from __future__ import annotations

from datetime import date

from backend.app.data.fdata.parser import FDataParser
from backend.app.data.security_master.service import (
    SecurityMasterBuilder,
    SecurityReference,
)


def test_reference_controls_security_type_and_status_not_file_mtime(
    tmp_path, fdata_writer
):
    source = fdata_writer(
        tmp_path / "stock" / "FPT.dat",
        [
            (20260729, 63, 65, 62, 64, 100, 64, 1),
            (20260730, 64, 67, 64, 67, 0, 66, 1),
        ],
    )
    source.touch()
    parsed = FDataParser().parse_file(source, "stock")
    reference = SecurityReference(
        symbol="FPT",
        exchange="HOSE",
        security_type="equity",
        company_name="CTCP FPT",
        sector="Technology",
        industry="IT services",
        listing_date=date(2006, 12, 13),
        delisting_date=None,
        trading_status="suspended",
        lot_size=100,
        source="authoritative_test_reference",
    )

    profile = SecurityMasterBuilder({"FPT": reference}).build(parsed)

    assert profile.contract.trading_status == "suspended"
    assert profile.contract.security_type == "equity"
    assert profile.last_positive_volume_date == date(2026, 7, 29)


def test_numeric_index_without_mapping_is_blocked_not_guessed(
    tmp_path, fdata_writer
):
    source = fdata_writer(
        tmp_path / "index" / "0001.dat",
        [(20260730, 100, 101, 99, 100, 1000, 100, 1)],
    )
    parsed = FDataParser().parse_file(source, "index")

    profile = SecurityMasterBuilder({}).build(parsed)

    assert profile.contract.index_code == "0001"
    assert profile.contract.company_name == "UNMAPPED"
    assert profile.contract.trading_status == "blocked_missing_index_mapping"
    assert profile.blocked_reason == "index_code_mapping_unavailable"
