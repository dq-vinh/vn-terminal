"""WP7 screener (Section 15).

Runs one or many registered strategies across a filtered security universe,
shows the passed and failed criteria for every security, ranks by a
deterministic score, records everything needed to reproduce the run, runs in
the background, and exports to CSV.

The rule that shapes this package is Section 15's prohibition: "The screener
must not treat a current file date as proof that a security remains actively
traded." Nothing in `backend/app/quant/**` reads a file timestamp; recency is
measured in market sessions since the last positive-volume bar, against a
trading calendar built from the snapshot. See `universe.py`.
"""

from __future__ import annotations

from .export import COLUMNS, to_csv
from .jobs import COMPLETED, FAILED, QUEUED, RUNNING, JobRecord, ScreenerJobs
from .runner import (
    ScreenRun,
    SymbolResult,
    compute_run_id,
    contract_results,
    run_screen,
    strategy_result_rows,
)
from .universe import (
    CRITICAL_QUALITY_VALUES,
    TRADING_VALUE_LOOKBACK,
    Candidate,
    TradingCalendar,
    UniverseAssessment,
    UniverseFilters,
    assess,
    assess_all,
)

__all__ = [
    "COLUMNS",
    "COMPLETED",
    "CRITICAL_QUALITY_VALUES",
    "FAILED",
    "QUEUED",
    "RUNNING",
    "TRADING_VALUE_LOOKBACK",
    "Candidate",
    "JobRecord",
    "ScreenRun",
    "ScreenerJobs",
    "SymbolResult",
    "TradingCalendar",
    "UniverseAssessment",
    "UniverseFilters",
    "assess",
    "assess_all",
    "compute_run_id",
    "contract_results",
    "run_screen",
    "strategy_result_rows",
    "to_csv",
]
