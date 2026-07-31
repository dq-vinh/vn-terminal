"""CSV export for a screener run (Section 15: "Export results to CSV").

Two properties matter more than convenience here.

**Excluded securities are exported too.** A CSV of only the passing rows
answers "what passed" but cannot answer "why is FPT missing", which is the
question a screener user actually asks. Every candidate appears with a
`status` column of `included` or `excluded` and its failed criteria, so the
file is a complete account of the run rather than a filtered view of it.

**The file is byte-reproducible.** Columns are fixed and ordered, rows are
emitted in rank order then symbol order, floats are formatted with an
explicit repr rather than a locale-dependent one, and the newline is written
as `\\n` explicitly so the same run exports identically on Windows and Linux.
The run header rows carry the run id, data version, and strategy versions, so
a CSV separated from its run record still identifies what produced it.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any

from .runner import ScreenRun

COLUMNS = (
    "run_id",
    "run_date",
    "data_version",
    "status",
    "rank",
    "symbol",
    "total_score",
    "max_score",
    "signals",
    "passed_criteria",
    "failed_criteria",
    "last_positive_volume_date",
    "sessions_since_last_positive_volume",
    "median_20d_trading_value",
    "usable_bars",
    "traded_on_run_date",
)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return "|".join(f"{key}={value[key]}" for key in sorted(value))
    return str(value)


def rows(run: ScreenRun) -> Iterable[dict[str, Any]]:
    for item in run.results:
        metrics = item.universe.metrics
        yield {
            "run_id": run.run_id,
            "run_date": run.run_date.isoformat(),
            "data_version": run.data_version,
            "status": "included",
            "rank": item.rank,
            "symbol": item.symbol,
            "total_score": item.total_score,
            "max_score": item.max_score,
            "signals": item.signals,
            "passed_criteria": item.passed_criteria,
            "failed_criteria": item.failed_criteria,
            "last_positive_volume_date": metrics.get("last_positive_volume_date"),
            "sessions_since_last_positive_volume": metrics.get(
                "sessions_since_last_positive_volume"
            ),
            "median_20d_trading_value": metrics.get("median_20d_trading_value"),
            "usable_bars": metrics.get("usable_bars"),
            "traded_on_run_date": metrics.get("traded_on_run_date"),
        }
    for assessment in sorted(run.excluded, key=lambda item: item.symbol):
        metrics = assessment.metrics
        yield {
            "run_id": run.run_id,
            "run_date": run.run_date.isoformat(),
            "data_version": run.data_version,
            "status": "excluded",
            "rank": None,
            "symbol": assessment.symbol,
            "total_score": None,
            "max_score": None,
            "signals": None,
            "passed_criteria": assessment.passed_criteria,
            "failed_criteria": assessment.failed_criteria,
            "last_positive_volume_date": metrics.get("last_positive_volume_date"),
            "sessions_since_last_positive_volume": metrics.get(
                "sessions_since_last_positive_volume"
            ),
            "median_20d_trading_value": metrics.get("median_20d_trading_value"),
            "usable_bars": metrics.get("usable_bars"),
            "traded_on_run_date": metrics.get("traded_on_run_date"),
        }


def to_csv(run: ScreenRun) -> str:
    """The whole run as CSV text. Writing it to disk is the caller's job."""

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(COLUMNS), lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    for row in rows(run):
        writer.writerow({key: _cell(row.get(key)) for key in COLUMNS})
    return buffer.getvalue()
