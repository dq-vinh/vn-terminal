"""Internal immutable models for the data workstream."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class Severity:
    """The four severity values frozen in contract version 0.1.0."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class DataIssue:
    check_id: int
    code: str
    severity: str
    message: str
    symbol: str | None = None
    source_file: str | None = None
    record_index: int | None = None


@dataclass(frozen=True, slots=True)
class RawFDataRecord:
    date_code: int
    unused_1: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    unused_2: float
    aux1: float
    aux2: float


@dataclass(frozen=True, slots=True)
class ParsedFDataFile:
    source_file: Path
    category: str
    symbol: str
    header_count: int
    actual_count: int
    records: tuple[RawFDataRecord, ...]
    source_sha256: str
    issues: tuple[DataIssue, ...] = field(default_factory=tuple)
    quarantined: bool = False
