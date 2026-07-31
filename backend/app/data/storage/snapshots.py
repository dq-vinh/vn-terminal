"""Immutable Parquet snapshot staging and atomic promotion."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..models import ParsedFDataFile
from ..quality.checks import date_from_code

SNAPSHOT_FORMAT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class SnapshotCandidate:
    path: Path
    data_version: str
    as_of_date: date
    generated_at: datetime
    content_sha256: str
    bars_files: tuple[Path, ...]
    source_file_count: int
    record_count: int
    quarantined_files: tuple[str, ...]


def content_hash_from_fingerprints(
    fingerprints: Iterable[tuple[str, str, str]],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        f"vn-terminal-snapshot-{SNAPSHOT_FORMAT_VERSION}\n".encode()
    )
    for category, symbol, source_sha256 in sorted(fingerprints):
        digest.update(category.encode())
        digest.update(b"\0")
        digest.update(symbol.encode())
        digest.update(b"\0")
        digest.update(source_sha256.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _content_hash(parsed_files: Iterable[ParsedFDataFile]) -> str:
    return content_hash_from_fingerprints(
        (item.category, item.symbol, item.source_sha256)
        for item in parsed_files
    )


def _security_type(category: str) -> str:
    return {
        "index": "index",
        "der": "derivative",
        "cw": "warrant",
        "stock": "unknown",
    }.get(category, "unknown")


class SnapshotManager:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.staging_root = self.root / ".staging"
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def stage(
        self,
        parsed_files: Iterable[ParsedFDataFile],
        *,
        data_version: str,
        as_of_date: date,
        generated_at: datetime,
    ) -> SnapshotCandidate:
        files = list(parsed_files)
        return self.stage_prehashed(
            files,
            source_file_count=len(files),
            content_sha256=_content_hash(files),
            data_version=data_version,
            as_of_date=as_of_date,
            generated_at=generated_at,
        )

    def stage_prehashed(
        self,
        parsed_files: Iterable[ParsedFDataFile],
        *,
        source_file_count: int,
        content_sha256: str,
        data_version: str,
        as_of_date: date,
        generated_at: datetime,
        excluded_source_files: frozenset[str] = frozenset(),
        quality_status_by_source: Mapping[str, str] | None = None,
    ) -> SnapshotCandidate:
        quality_status_by_source = quality_status_by_source or {}
        stage_path = self.staging_root / (
            f"{data_version}-{content_sha256[:12]}-{uuid.uuid4().hex}"
        )
        bars_root = stage_path / "bars"
        bars_root.mkdir(parents=True)
        bars_files: list[Path] = []
        record_count = 0
        quarantined: list[str] = []

        metadata = {
            b"data_version": data_version.encode(),
            b"snapshot_format_version": SNAPSHOT_FORMAT_VERSION.encode(),
            b"source": b"Fialda FData",
            b"record_layout": b"header-40-byte;record-<I9f-40-byte",
            b"content_sha256": content_sha256.encode(),
            b"as_of_date": as_of_date.isoformat().encode(),
        }
        for parsed in parsed_files:
            if parsed.quarantined or str(parsed.source_file) in excluded_source_files:
                quarantined.append(str(parsed.source_file))
                continue
            rows = []
            for record in parsed.records:
                trading_date = date_from_code(record.date_code)
                if trading_date is None:
                    continue
                rows.append(
                    {
                        "symbol": parsed.symbol,
                        "exchange": "UNKNOWN",
                        "security_type": _security_type(parsed.category),
                        "timeframe": "1D",
                        "trading_date": trading_date,
                        "timezone": "Asia/Ho_Chi_Minh",
                        "open": float(record.open),
                        "high": float(record.high),
                        "low": float(record.low),
                        "close": float(record.close),
                        "volume": round(record.volume),
                        "adjustment_status": "adjusted_unknown_method",
                        "source": "Fialda FData",
                        "source_file": str(parsed.source_file),
                        "ingested_at": generated_at.isoformat(),
                        "quality_status": quality_status_by_source.get(
                            str(parsed.source_file), "valid"
                        ),
                    }
                )
            table = pa.Table.from_pylist(rows)
            table = table.replace_schema_metadata(metadata)
            category_root = bars_root / parsed.category
            category_root.mkdir(exist_ok=True)
            output = category_root / f"{parsed.symbol}.parquet"
            pq.write_table(
                table,
                output,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
            )
            bars_files.append(output)
            record_count += len(rows)

        manifest = {
            "data_version": data_version,
            "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
            "as_of_date": as_of_date.isoformat(),
            "generated_at": generated_at.isoformat(),
            "content_sha256": content_sha256,
            "source": "Fialda FData",
            "record_layout": "header-40-byte;record-<I9f-40-byte",
            "source_file_count": source_file_count,
            "record_count": record_count,
            "quarantined_files": sorted(quarantined),
        }
        (stage_path / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return SnapshotCandidate(
            path=stage_path,
            data_version=data_version,
            as_of_date=as_of_date,
            generated_at=generated_at,
            content_sha256=content_sha256,
            bars_files=tuple(bars_files),
            source_file_count=source_file_count,
            record_count=record_count,
            quarantined_files=tuple(sorted(quarantined)),
        )

    def promote(self, candidate: SnapshotCandidate, *, valid: bool) -> bool:
        if not valid:
            return False
        candidate_path = candidate.path.resolve()
        if candidate_path.parent != self.staging_root.resolve():
            raise ValueError("Candidate is outside this manager's staging directory")
        ready = {
            "data_version": candidate.data_version,
            "content_sha256": candidate.content_sha256,
            "validated_at": candidate.generated_at.isoformat(),
        }
        (candidate_path / "READY").write_text(
            json.dumps(ready, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        pointer = {
            "data_version": candidate.data_version,
            "snapshot_dir": candidate_path.relative_to(self.root).as_posix(),
            "as_of_date": candidate.as_of_date.isoformat(),
            "promoted_at": candidate.generated_at.isoformat(),
            "content_sha256": candidate.content_sha256,
        }
        temp_pointer = self.root / f".CURRENT-{uuid.uuid4().hex}.tmp"
        temp_pointer.write_text(
            json.dumps(pointer, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp_pointer, self.root / "CURRENT")
        return True

    def current_info(self) -> dict[str, str] | None:
        pointer = self.root / "CURRENT"
        if not pointer.exists():
            return None
        return json.loads(pointer.read_text(encoding="utf-8"))

    def current_version(self) -> str | None:
        info = self.current_info()
        return info["data_version"] if info else None

    def current_snapshot_path(self) -> Path | None:
        info = self.current_info()
        if not info:
            return None
        path = (self.root / info["snapshot_dir"]).resolve()
        if (
            not path.is_relative_to(self.root)
            or path == self.root
            or not (path / "READY").is_file()
        ):
            raise ValueError("CURRENT points outside the snapshot root")
        return path
