from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.data.fdata.parser import FDataParser, discover_eod_files

VALID_ROWS = [
    (20260729, 63.0, 65.3, 62.5, 65.1, 8_518_325.0, 63.79, 11.0),
    (20260730, 65.2, 67.2, 64.8, 67.0, 7_571_500.0, 66.565125, 15.0),
]


def test_parser_reads_verified_layout_and_canonicalizes_fpt(tmp_path, fdata_writer):
    source = fdata_writer(tmp_path / "stock" / "FPT.dat", VALID_ROWS)

    parsed = FDataParser().parse_file(source, "stock")

    assert parsed.header_count == 2
    assert parsed.actual_count == 2
    assert parsed.symbol == "FPT"
    assert parsed.category == "stock"
    assert parsed.records[-1].date_code == 20260730
    assert parsed.records[-1].close == pytest.approx(67.0)
    assert parsed.records[-1].volume == pytest.approx(7_571_500)
    assert parsed.records[-1].aux1 == pytest.approx(66.565125)
    assert parsed.records[-1].aux2 == pytest.approx(15)
    assert not parsed.quarantined


def test_parser_never_opens_source_in_write_mode(
    tmp_path, fdata_writer, monkeypatch
):
    source = fdata_writer(tmp_path / "stock" / "FPT.dat", VALID_ROWS)
    observed_modes: list[str] = []
    original_open = Path.open

    def guarded_open(path: Path, mode: str = "r", *args, **kwargs):
        if path == source:
            observed_modes.append(mode)
            assert mode == "rb"
            assert not any(marker in mode for marker in ("w", "a", "+"))
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    FDataParser().parse_file(source, "stock")

    assert observed_modes == ["rb"]


def test_malformed_header_and_out_of_order_dates_are_quarantined(
    tmp_path, fdata_writer
):
    source = fdata_writer(
        tmp_path / "cw" / "CSHB2604.dat",
        [
            (20260729, 1, 2, 1, 2, 100, 1.5, 1),
            (20260728, 1, 2, 1, 2, 100, 1.5, 1),
        ],
        header_count=1,
    )

    parsed = FDataParser().parse_file(source, "cw")

    assert parsed.header_count == 1
    assert parsed.actual_count == 2
    assert parsed.quarantined
    assert {issue.code for issue in parsed.issues} >= {
        "header_count_mismatch",
        "date_not_strictly_increasing",
    }


def test_discovery_includes_four_categories_and_ignores_intraday(
    tmp_path, fdata_writer
):
    for category, symbol in (
        ("stock", "FPT"),
        ("index", "0001"),
        ("der", "VN30F2608"),
        ("cw", "CFPT2601"),
    ):
        fdata_writer(tmp_path / category / f"{symbol}.dat", VALID_ROWS)
    for ignored in ("1m", "5m", "15m", "Tick"):
        (tmp_path / ignored).mkdir()

    discovered = discover_eod_files(tmp_path)

    assert [(item.category, item.path.stem) for item in discovered] == [
        ("cw", "CFPT2601"),
        ("der", "VN30F2608"),
        ("index", "0001"),
        ("stock", "FPT"),
    ]


def test_live_cshb2604_fixture_is_quarantined_when_fdata_is_available():
    source = Path(r"C:\FDATA\AmiBroker\EOD\cw\CSHB2604.dat")
    if not source.exists():
        pytest.skip("Live FData fixture is not installed")

    parsed = FDataParser().parse_file(source, "cw")

    assert parsed.header_count == 43
    assert parsed.actual_count == 44
    assert parsed.quarantined
    assert "date_not_strictly_increasing" in {
        issue.code for issue in parsed.issues
    }
