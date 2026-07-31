"""Command-line tasks for scanning, refreshing, and validating Aux1."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .aux1_validation import (
    Aux1ValidationReport,
    PublishedAveragePrice,
    compare_aux1_to_published_average,
)
from .fdata.parser import FDataParser
from .pipeline import RefreshPipeline, RefreshResult
from .quality.checks import scan_repository
from .storage.snapshots import SnapshotManager

CURATED_AUX1_OBSERVATIONS = (
    PublishedAveragePrice(
        symbol="FPT",
        trading_date=date(2026, 7, 21),
        average_price=65.98,
        source_url="https://web.stockbiz.vn/Stocks/FPT/HistoricalQuotes.aspx",
    ),
    PublishedAveragePrice(
        symbol="HPG",
        trading_date=date(2026, 7, 21),
        average_price=20.86,
        source_url="https://web.stockbiz.vn/Stocks/HPG/HistoricalQuotes.aspx",
    ),
    PublishedAveragePrice(
        symbol="SSI",
        trading_date=date(2026, 7, 21),
        average_price=23.21,
        source_url="https://web.stockbiz.vn/Stocks/SSI/HistoricalQuotes.aspx",
    ),
    PublishedAveragePrice(
        symbol="MBB",
        trading_date=date(2026, 7, 21),
        average_price=22.81,
        source_url="https://web.stockbiz.vn/Stocks/MBB/HistoricalQuotes.aspx",
    ),
    PublishedAveragePrice(
        symbol="VNM",
        trading_date=date(2026, 7, 21),
        average_price=58.45,
        source_url="https://web.stockbiz.vn/Stocks/VNM/HistoricalQuotes.aspx",
    ),
)


def run_curated_aux1_validation(source_root: Path) -> Aux1ValidationReport:
    parser = FDataParser()
    parsed = {
        observation.symbol: parser.parse_file(
            Path(source_root) / "stock" / f"{observation.symbol}.dat",
            "stock",
        )
        for observation in CURATED_AUX1_OBSERVATIONS
    }
    return compare_aux1_to_published_average(
        parsed,
        CURATED_AUX1_OBSERVATIONS,
        tolerance_thousand_vnd=0.051,
    )


def write_json_report(payload: object, output: Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output.resolve()


def write_refresh_report(result: RefreshResult, output: Path) -> Path:
    return write_json_report(asdict(result), output)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vn-terminal-data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan")
    scan.add_argument("--source-root", type=Path, required=True)
    scan.add_argument("--reference-date", type=date.fromisoformat, required=True)
    scan.add_argument("--output", type=Path, required=True)

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--source-root", type=Path, required=True)
    refresh.add_argument("--snapshots-root", type=Path, required=True)
    refresh.add_argument("--reference-date", type=date.fromisoformat, required=True)
    refresh.add_argument("--output", type=Path, required=True)

    aux1 = subparsers.add_parser("aux1")
    aux1.add_argument("--source-root", type=Path, required=True)
    aux1.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "scan":
        summary = scan_repository(
            args.source_root, reference_date=args.reference_date
        )
        output = write_json_report(asdict(summary), args.output)
    elif args.command == "refresh":
        snapshots = SnapshotManager(args.snapshots_root)
        result = RefreshPipeline(
            source_root=args.source_root, snapshots=snapshots
        ).run(reference_date=args.reference_date)
        output = write_refresh_report(result, args.output)
    else:
        report = run_curated_aux1_validation(args.source_root)
        output = write_json_report(asdict(report), args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
