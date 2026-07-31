"""Read-only parser for the verified 40-byte FData EOD layout."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..models import DataIssue, ParsedFDataFile, RawFDataRecord, Severity

HEADER_SIZE = 40
RECORD_SIZE = 40
RECORD_STRUCT = struct.Struct("<I9f")
CATEGORIES = ("cw", "der", "index", "stock")


@dataclass(frozen=True, slots=True)
class DiscoveredFDataFile:
    category: str
    path: Path


def discover_eod_files(root: Path) -> list[DiscoveredFDataFile]:
    """Return only .dat files from the four authoritative EOD categories."""

    discovered: list[DiscoveredFDataFile] = []
    for category in CATEGORIES:
        directory = root / category
        if not directory.is_dir():
            continue
        discovered.extend(
            DiscoveredFDataFile(category=category, path=path)
            for path in sorted(directory.glob("*.dat"), key=lambda item: item.name)
        )
    return discovered


def _valid_date_code(value: int) -> bool:
    year, remainder = divmod(value, 10_000)
    month, day = divmod(remainder, 100)
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


class FDataParser:
    """Parse an FData file without ever acquiring write access to it."""

    def parse_file(self, path: Path, category: str) -> ParsedFDataFile:
        source = Path(path)
        with source.open("rb") as handle:
            payload = handle.read()

        issues: list[DataIssue] = []
        size = len(payload)
        if size < HEADER_SIZE or size % RECORD_SIZE != 0:
            issues.append(
                DataIssue(
                    check_id=1,
                    code="file_size_layout_mismatch",
                    severity=Severity.CRITICAL,
                    message=(
                        f"File size {size} is not a valid header plus "
                        f"{RECORD_SIZE}-byte records."
                    ),
                    symbol=source.stem,
                    source_file=str(source),
                )
            )

        header_count = (
            struct.unpack_from("<I", payload, 0)[0] if size >= HEADER_SIZE else 0
        )
        record_payload = payload[HEADER_SIZE:]
        complete_bytes = len(record_payload) - (len(record_payload) % RECORD_SIZE)
        records = tuple(
            RawFDataRecord(*values)
            for values in RECORD_STRUCT.iter_unpack(record_payload[:complete_bytes])
        )
        actual_count = len(records)

        if header_count != actual_count:
            issues.append(
                DataIssue(
                    check_id=2,
                    code="header_count_mismatch",
                    severity=Severity.CRITICAL,
                    message=(
                        f"Header claims {header_count} records but "
                        f"{actual_count} complete records exist."
                    ),
                    symbol=source.stem,
                    source_file=str(source),
                )
            )

        invalid_date_index = next(
            (
                index
                for index, record in enumerate(records)
                if not _valid_date_code(record.date_code)
            ),
            None,
        )
        if invalid_date_index is not None:
            issues.append(
                DataIssue(
                    check_id=3,
                    code="invalid_date",
                    severity=Severity.CRITICAL,
                    message="Record contains a date outside the calendar.",
                    symbol=source.stem,
                    source_file=str(source),
                    record_index=invalid_date_index,
                )
            )

        duplicate_index = next(
            (
                index
                for index in range(1, actual_count)
                if records[index].date_code == records[index - 1].date_code
            ),
            None,
        )
        if duplicate_index is not None:
            issues.append(
                DataIssue(
                    check_id=5,
                    code="duplicate_date",
                    severity=Severity.HIGH,
                    message="Consecutive records contain the same date.",
                    symbol=source.stem,
                    source_file=str(source),
                    record_index=duplicate_index,
                )
            )

        non_increasing_index = next(
            (
                index
                for index in range(1, actual_count)
                if records[index].date_code <= records[index - 1].date_code
            ),
            None,
        )
        if non_increasing_index is not None:
            issues.append(
                DataIssue(
                    check_id=4,
                    code="date_not_strictly_increasing",
                    severity=Severity.HIGH,
                    message="Record dates are not strictly increasing.",
                    symbol=source.stem,
                    source_file=str(source),
                    record_index=non_increasing_index,
                )
            )

        quarantine_codes = {
            "file_size_layout_mismatch",
            "header_count_mismatch",
            "invalid_date",
            "duplicate_date",
            "date_not_strictly_increasing",
        }
        return ParsedFDataFile(
            source_file=source.resolve(),
            category=category,
            symbol=source.stem.upper(),
            header_count=header_count,
            actual_count=actual_count,
            records=records,
            source_sha256=hashlib.sha256(payload).hexdigest(),
            issues=tuple(issues),
            quarantined=any(issue.code in quarantine_codes for issue in issues),
        )

    def parse_repository(self, root: Path) -> list[ParsedFDataFile]:
        return [
            self.parse_file(item.path, item.category)
            for item in discover_eod_files(root)
        ]
