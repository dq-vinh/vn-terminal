"""End-to-end read-only refresh with quarantine and atomic promotion."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from .fdata.parser import CATEGORIES, FDataParser, discover_eod_files
from .models import DataIssue, ParsedFDataFile
from .quality.checks import (
    RepositoryQualitySummary,
    assess_file,
    scan_repository,
)
from .security_master.service import (
    SecurityMasterBuilder,
    SecurityProfile,
    SecurityReference,
)
from .storage.snapshots import (
    SNAPSHOT_FORMAT_VERSION,
    SnapshotManager,
    content_hash_from_fingerprints,
)

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

BASELINE_2026_07_30 = {
    "file_count": 2471,
    "record_count": 3_632_818,
    "ohlc_violation_files": 505,
    "nonpositive_price_files": 34,
    "zero_volume_records": 11_020,
    "terminal_zero_volume_stock_files": 301,
    "current_files": 2315,
}


@dataclass(frozen=True, slots=True)
class RefreshResult:
    data_version: str
    content_sha256: str
    summary: RepositoryQualitySummary
    promoted: bool
    blocking_reasons: tuple[str, ...]
    quarantined_files: tuple[str, ...]
    index_mapping_status: str
    snapshot_path: Path | None


def _count_historical_revisions(
    parsed: ParsedFDataFile, previous_snapshot: Path | None
) -> int:
    if previous_snapshot is None:
        return 0
    previous_file = (
        previous_snapshot
        / "bars"
        / parsed.category
        / f"{parsed.symbol}.parquet"
    )
    if not previous_file.exists():
        return 0
    previous_rows = pq.read_table(
        previous_file,
        columns=["trading_date", "open", "high", "low", "close", "volume"],
    ).to_pylist()
    previous = {
        row["trading_date"]: (
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
        )
        for row in previous_rows
    }
    revisions = 0
    for record in parsed.records:
        year, remainder = divmod(record.date_code, 10_000)
        month, day = divmod(remainder, 100)
        try:
            trading_date = date(year, month, day)
        except ValueError:
            continue
        current = (
            record.open,
            record.high,
            record.low,
            record.close,
            round(record.volume),
        )
        if trading_date in previous and current != previous[trading_date]:
            revisions += 1
    return revisions


def _quality_rows(
    issues: list[DataIssue],
) -> pa.Table:
    schema = pa.schema(
        [
            ("check_id", pa.int16()),
            ("code", pa.string()),
            ("severity", pa.string()),
            ("message", pa.string()),
            ("symbol", pa.string()),
            ("source_file", pa.string()),
            ("record_index", pa.int32()),
        ]
    )
    return pa.Table.from_pylist([asdict(issue) for issue in issues], schema=schema)


def _security_rows(profiles: list[SecurityProfile]) -> pa.Table:
    rows = []
    for profile in profiles:
        row = profile.contract.model_dump(mode="python")
        row["last_positive_volume_date"] = profile.last_positive_volume_date
        row["blocked_reason"] = profile.blocked_reason
        rows.append(row)
    return pa.Table.from_pylist(rows)


class RefreshPipeline:
    def __init__(
        self,
        *,
        source_root: Path,
        snapshots: SnapshotManager,
        references: dict[str, SecurityReference] | None = None,
    ):
        self.source_root = Path(source_root)
        self.snapshots = snapshots
        self.references = references or {}
        self.parser = FDataParser()

    def run(
        self,
        *,
        reference_date: date,
        generated_at: datetime | None = None,
    ) -> RefreshResult:
        generated_at = generated_at or datetime.now(
            ZoneInfo("Asia/Ho_Chi_Minh")
        )
        discovered = discover_eod_files(self.source_root)
        category_counts = {
            category: sum(item.category == category for item in discovered)
            for category in CATEGORIES
        }
        blocking_reasons = [
            f"missing_or_empty_category:{category}"
            for category, count in category_counts.items()
            if count == 0
        ]
        builder = SecurityMasterBuilder(self.references)
        previous_snapshot = self.snapshots.current_snapshot_path()
        profiles: list[SecurityProfile] = []
        issues: list[DataIssue] = []
        critical_source_files: set[str] = set()
        quality_status_by_source: dict[str, str] = {}
        fingerprints: list[tuple[str, str, str]] = []

        for item in discovered:
            parsed = self.parser.parse_file(item.path, item.category)
            profile = builder.build(parsed)
            revision_count = _count_historical_revisions(
                parsed, previous_snapshot
            )
            quality = assess_file(
                parsed,
                reference_date=reference_date,
                security_type=profile.contract.security_type,
                historical_revision_count=revision_count,
            )
            profiles.append(profile)
            issues.extend(quality.issues)
            quality_status_by_source[str(parsed.source_file)] = max(
                (issue.severity for issue in quality.issues),
                key=lambda severity: SEVERITY_RANK[severity],
                default="valid",
            )
            fingerprints.append(
                (parsed.category, parsed.symbol, parsed.source_sha256)
            )
            if quality.blocks_strategy_execution:
                critical_source_files.add(str(parsed.source_file))

        summary = scan_repository(
            self.source_root, reference_date=reference_date
        )
        content_sha256 = content_hash_from_fingerprints(fingerprints)
        data_version = f"fdata-{reference_date.isoformat()}"

        if reference_date == date(2026, 7, 30) and summary.file_count >= 2000:
            for field, expected in BASELINE_2026_07_30.items():
                observed = getattr(summary, field)
                if observed != expected:
                    blocking_reasons.append(
                        f"baseline_deviation:{field}:{observed}:expected:{expected}"
                    )

        def parsed_stream():
            for item in discovered:
                yield self.parser.parse_file(item.path, item.category)

        candidate = self.snapshots.stage_prehashed(
            parsed_stream(),
            source_file_count=len(discovered),
            content_sha256=content_sha256,
            data_version=data_version,
            as_of_date=reference_date,
            generated_at=generated_at,
            excluded_source_files=frozenset(critical_source_files),
            quality_status_by_source=quality_status_by_source,
        )
        metadata = {
            b"data_version": data_version.encode(),
            b"snapshot_format_version": SNAPSHOT_FORMAT_VERSION.encode(),
            b"source": b"Fialda FData",
            b"content_sha256": content_sha256.encode(),
        }
        security_table = _security_rows(profiles).replace_schema_metadata(metadata)
        quality_table = _quality_rows(issues).replace_schema_metadata(metadata)
        pq.write_table(
            security_table,
            candidate.path / "security_master.parquet",
            compression="zstd",
        )
        pq.write_table(
            quality_table,
            candidate.path / "quality_issues.parquet",
            compression="zstd",
        )

        unmapped_indices = sum(
            profile.blocked_reason == "index_code_mapping_unavailable"
            for profile in profiles
        )
        index_mapping_status = (
            "blocked_no_authoritative_source"
            if unmapped_indices
            else "available"
        )
        manifest_path = candidate.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(
            {
                "quality_summary": asdict(summary),
                "quality_issue_count": len(issues),
                "critical_quarantined_file_count": len(
                    critical_source_files
                ),
                "index_mapping_status": index_mapping_status,
                "unmapped_numeric_index_count": unmapped_indices,
                "blocking_reasons": blocking_reasons,
                "historical_revision_count": sum(
                    issue.code == "historical_revision" for issue in issues
                ),
            }
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        promoted = self.snapshots.promote(
            candidate, valid=not blocking_reasons
        )
        return RefreshResult(
            data_version=data_version,
            content_sha256=content_sha256,
            summary=summary,
            promoted=promoted,
            blocking_reasons=tuple(blocking_reasons),
            quarantined_files=candidate.quarantined_files,
            index_mapping_status=index_mapping_status,
            snapshot_path=(
                self.snapshots.current_snapshot_path() if promoted else None
            ),
        )
