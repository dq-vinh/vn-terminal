"""The fourteen Section 19 automated quality controls."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..fdata.parser import FDataParser, discover_eod_files
from ..models import DataIssue, ParsedFDataFile, RawFDataRecord, Severity

ALL_CHECK_IDS = set(range(1, 15))
KNOWN_SECURITY_TYPES = {"equity", "index", "derivative", "warrant", "bond"}


class CriticalDataQualityError(RuntimeError):
    """Raised when check 14 prevents analytical execution."""


@dataclass(frozen=True, slots=True)
class FileQualityResult:
    symbol: str
    issues: tuple[DataIssue, ...]
    last_positive_volume_date: date | None
    terminal_zero_volume_run: int
    zero_volume_records: int
    revision_count: int
    blocks_strategy_execution: bool


@dataclass(frozen=True, slots=True)
class RepositoryQualitySummary:
    file_count: int
    record_count: int
    ohlc_violation_files: int
    nonpositive_price_files: int
    # Section 19.2's 11,020 baseline is the stock-category count.
    zero_volume_records: int
    zero_volume_records_all_categories: int
    terminal_zero_volume_stock_files: int
    current_files: int
    malformed_files: int


def date_from_code(value: int) -> date | None:
    year, remainder = divmod(value, 10_000)
    month, day = divmod(remainder, 100)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _has_nonpositive_price(record: RawFDataRecord) -> bool:
    prices = (record.open, record.high, record.low, record.close)
    return any(not math.isfinite(value) or value <= 0 for value in prices)


def _has_ohlc_violation(record: RawFDataRecord) -> bool:
    prices = (record.open, record.high, record.low, record.close)
    if not all(math.isfinite(value) for value in prices):
        return False
    return not (
        record.low <= record.open <= record.high
        and record.low <= record.close <= record.high
    )


def _terminal_zero_run(records: tuple[RawFDataRecord, ...]) -> int:
    count = 0
    for record in reversed(records):
        if record.volume != 0:
            break
        count += 1
    return count


def assess_file(
    parsed: ParsedFDataFile,
    *,
    reference_date: date,
    security_type: str,
    freshness_days: int = 0,
    historical_revision_count: int = 0,
) -> FileQualityResult:
    issues = list(parsed.issues)
    source_file = str(parsed.source_file)

    if any(_has_nonpositive_price(record) for record in parsed.records):
        issues.append(
            DataIssue(
                check_id=6,
                code="nonpositive_price",
                severity=Severity.CRITICAL,
                message="At least one OHLC value is non-finite or non-positive.",
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )
    if any(_has_ohlc_violation(record) for record in parsed.records):
        issues.append(
            DataIssue(
                check_id=7,
                code="ohlc_violation",
                severity=Severity.HIGH,
                message="At least one bar violates low <= open, close <= high.",
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )
    if any(
        not math.isfinite(record.volume) or record.volume < 0
        for record in parsed.records
    ):
        issues.append(
            DataIssue(
                check_id=8,
                code="invalid_volume",
                severity=Severity.CRITICAL,
                message="At least one volume is non-finite or negative.",
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )

    positive_dates = [
        trading_date
        for record in parsed.records
        if record.volume > 0
        and (trading_date := date_from_code(record.date_code)) is not None
    ]
    last_positive = max(positive_dates, default=None)
    terminal_run = _terminal_zero_run(parsed.records)
    if terminal_run >= 5:
        issues.append(
            DataIssue(
                check_id=10,
                code="terminal_zero_volume_run",
                severity=Severity.MEDIUM,
                message=f"File ends with {terminal_run} zero-volume records.",
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )

    if security_type not in KNOWN_SECURITY_TYPES:
        issues.append(
            DataIssue(
                check_id=11,
                code="unknown_security_type",
                severity=Severity.HIGH,
                message="No authoritative security type is available.",
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )

    valid_dates = [
        trading_date
        for record in parsed.records
        if (trading_date := date_from_code(record.date_code)) is not None
    ]
    last_date = max(valid_dates, default=None)
    freshness_cutoff = reference_date - timedelta(days=freshness_days)
    if last_date is None or last_date < freshness_cutoff:
        issues.append(
            DataIssue(
                check_id=12,
                code="stale_data",
                severity=Severity.MEDIUM,
                message=(
                    "Latest valid record is outside the configured freshness "
                    f"threshold ending {freshness_cutoff.isoformat()}."
                ),
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )

    if historical_revision_count:
        issues.append(
            DataIssue(
                check_id=13,
                code="historical_revision",
                severity=Severity.LOW,
                message=(
                    f"{historical_revision_count} historical records changed "
                    "relative to the previous snapshot."
                ),
                symbol=parsed.symbol,
                source_file=source_file,
            )
        )

    blocks = any(issue.severity == Severity.CRITICAL for issue in issues)
    return FileQualityResult(
        symbol=parsed.symbol,
        issues=tuple(issues),
        last_positive_volume_date=last_positive,
        terminal_zero_volume_run=terminal_run,
        zero_volume_records=sum(
            1 for record in parsed.records if record.volume == 0
        ),
        revision_count=historical_revision_count,
        blocks_strategy_execution=blocks,
    )


def assert_strategy_safe(result: FileQualityResult) -> None:
    if result.blocks_strategy_execution:
        raise CriticalDataQualityError(
            f"{result.symbol} has unresolved critical data-quality issues."
        )


def build_repository_summary(
    parsed_files: Iterable[ParsedFDataFile], *, reference_date: date
) -> RepositoryQualitySummary:
    files = list(parsed_files)
    return RepositoryQualitySummary(
        file_count=len(files),
        record_count=sum(item.actual_count for item in files),
        ohlc_violation_files=sum(
            any(_has_ohlc_violation(record) for record in item.records)
            for item in files
        ),
        nonpositive_price_files=sum(
            any(_has_nonpositive_price(record) for record in item.records)
            for item in files
        ),
        zero_volume_records=sum(
            item.category == "stock" and record.volume == 0
            for item in files
            for record in item.records
        ),
        zero_volume_records_all_categories=sum(
            record.volume == 0 for item in files for record in item.records
        ),
        terminal_zero_volume_stock_files=sum(
            item.category == "stock" and _terminal_zero_run(item.records) >= 5
            for item in files
        ),
        current_files=sum(
            bool(item.records)
            and date_from_code(item.records[-1].date_code) == reference_date
            for item in files
        ),
        malformed_files=sum(item.quarantined for item in files),
    )


def scan_repository(
    root: Path, *, reference_date: date
) -> RepositoryQualitySummary:
    """Scan the complete repository while retaining one source file at a time."""

    parser = FDataParser()
    discovered = discover_eod_files(Path(root))
    file_count = 0
    record_count = 0
    ohlc_violation_files = 0
    nonpositive_price_files = 0
    stock_zero_records = 0
    all_zero_records = 0
    terminal_zero_stock_files = 0
    current_files = 0
    malformed_files = 0
    for item in discovered:
        parsed = parser.parse_file(item.path, item.category)
        file_count += 1
        record_count += parsed.actual_count
        ohlc_violation_files += any(
            _has_ohlc_violation(record) for record in parsed.records
        )
        nonpositive_price_files += any(
            _has_nonpositive_price(record) for record in parsed.records
        )
        zero_count = sum(record.volume == 0 for record in parsed.records)
        all_zero_records += zero_count
        if item.category == "stock":
            stock_zero_records += zero_count
            terminal_zero_stock_files += _terminal_zero_run(parsed.records) >= 5
        current_files += (
            bool(parsed.records)
            and date_from_code(parsed.records[-1].date_code) == reference_date
        )
        malformed_files += parsed.quarantined
    return RepositoryQualitySummary(
        file_count=file_count,
        record_count=record_count,
        ohlc_violation_files=ohlc_violation_files,
        nonpositive_price_files=nonpositive_price_files,
        zero_volume_records=stock_zero_records,
        zero_volume_records_all_categories=all_zero_records,
        terminal_zero_volume_stock_files=terminal_zero_stock_files,
        current_files=current_files,
        malformed_files=malformed_files,
    )


def detect_historical_revisions(
    previous: ParsedFDataFile, current: ParsedFDataFile
) -> tuple[int, ...]:
    """Return overlapping dates whose raw 40-byte field values changed."""

    previous_by_date = {
        record.date_code: record for record in previous.records
    }
    return tuple(
        record.date_code
        for record in current.records
        if record.date_code in previous_by_date
        and record != previous_by_date[record.date_code]
    )
