"""Section 15 universe filters.

Section 15's default filters are implemented one function per filter, each
returning a named `Criterion`, so that the section's requirement to "Show
passed and failed criteria" holds for the universe stage and not only for the
strategy stage. A security that is excluded says which filter excluded it.

The load-bearing rule in this module is the one Section 15 states as a
prohibition: "The screener must not treat a current file date as proof that a
security remains actively traded." The data handoff reports 301 stock files
ending in terminal zero-volume runs of at least five sessions while 2,315
files are current to 30 July 2026. Those two facts together are the reason
`last_positive_volume` is measured in *market sessions since the last bar
that actually traded*, computed from a trading calendar, and never from a
file timestamp, a last-bar date, or a modification time. None of those three
values is read anywhere in this package.

Boundary convention, recorded as an implementation decision because Section
15 gives a range but not its inclusivity: a security passes when the number
of market sessions since its last positive-volume bar is *strictly less than*
`last_positive_volume_within_days`. At the contract's default of five this
excludes exactly the terminal runs of "five or more sessions" that the
baseline scan counted, which is what the work-package instruction requires.
`tests/quant/test_screener.py` pins both sides of that boundary.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..strategies.types import Criterion, SecurityView, SymbolHistory

#: Section 15: "Minimum 20-day median trading value."
TRADING_VALUE_LOOKBACK = 20

#: Severity values from Section 19.2 that block a security by default.
CRITICAL_QUALITY_VALUES = frozenset({"critical"})


@dataclass(frozen=True, slots=True)
class UniverseFilters:
    """Section 15's "Default filters" list.

    Field names match `ScreenUniverseFilters` in
    `contracts/schemas/json/screen_request.schema.json` so a request body maps
    across without translation. `last_positive_volume_within_days` keeps the
    contract's default of five.

    `min_20d_median_trading_value` is expressed in the price unit times the
    volume unit, which for FData bars is thousand VND times shares. The unit
    is carried explicitly in the run record rather than assumed, because a
    threshold whose unit is ambiguous is worse than no threshold.
    """

    active_equity_only: bool = True
    last_positive_volume_within_days: int = 5
    min_20d_median_trading_value: float = 0.0
    min_history_days: int = 0
    exclude_unresolved_critical_issues: bool = True
    # "UPCoM" and "equity" are the frozen canonical contract's enumeration
    # values (contracts/schemas/models/security_master.py, price_bar.py).
    # "UPCOM"/"ordinary_equity" matched nothing the data layer emits and made
    # this filter exclude every security with no error; see
    # docs/strategy_catalogue.md section 1, "Adopt the contract enumerations
    # equity and UPCoM" in the specification decision log.
    accepted_exchanges: frozenset[str] = frozenset({"HOSE", "HNX", "UPCoM"})
    accepted_security_types: frozenset[str] = frozenset({"equity"})
    accepted_trading_statuses: frozenset[str] = frozenset({"active"})
    trading_value_unit: str = "thousand_vnd_times_shares"

    def as_dict(self) -> dict[str, Any]:
        """Run-record form. Sorted sets so the record is byte-reproducible."""

        return {
            "active_equity_only": self.active_equity_only,
            "last_positive_volume_within_days": self.last_positive_volume_within_days,
            "min_20d_median_trading_value": self.min_20d_median_trading_value,
            "min_history_days": self.min_history_days,
            "exclude_unresolved_critical_issues": self.exclude_unresolved_critical_issues,
            "accepted_exchanges": sorted(self.accepted_exchanges),
            "accepted_security_types": sorted(self.accepted_security_types),
            "accepted_trading_statuses": sorted(self.accepted_trading_statuses),
            "trading_value_unit": self.trading_value_unit,
            "trading_value_lookback": TRADING_VALUE_LOOKBACK,
            "last_positive_volume_boundary": "strictly_less_than",
        }


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    """The market's session dates, in order.

    Built from the union of every candidate's bar dates rather than from an
    exchange holiday file, so it needs no external source and is reproducible
    from the snapshot alone. A symbol suspended for a month still has the
    market's sessions counted against it, which is the point: recency is
    measured against the market, not against the symbol's own thin history.
    """

    sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sessions", tuple(sorted(set(self.sessions))))

    @classmethod
    def from_histories(cls, histories: Sequence[SymbolHistory]) -> TradingCalendar:
        dates: set[date] = set()
        for history in histories:
            dates.update(history.trading_dates)
        return cls(sessions=tuple(dates))

    def sessions_between(self, start_exclusive: date, end_inclusive: date) -> int:
        """Market sessions after `start_exclusive`, up to `end_inclusive`."""

        if end_inclusive < start_exclusive:
            return -1
        left = bisect_right(self.sessions, start_exclusive)
        right = bisect_right(self.sessions, end_inclusive)
        return max(0, right - left)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One security offered to the screener.

    `security` is the point-in-time classification resolved for the run date
    by the caller. `critical_issue_codes` is the data layer's unresolved
    critical findings for this symbol; it is supplied rather than inferred,
    because the quant package does not read quality reports.
    """

    history: SymbolHistory
    security: SecurityView | None = None
    critical_issue_codes: tuple[str, ...] = ()

    @property
    def symbol(self) -> str:
        return self.history.symbol


@dataclass(frozen=True, slots=True)
class UniverseAssessment:
    """Per-security filter outcome, with every criterion named."""

    symbol: str
    included: bool
    criteria: tuple[Criterion, ...]
    as_of_index: int | None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed_criteria(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.criteria if item.passed)

    @property
    def failed_criteria(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.criteria if not item.passed)


def _last_positive_volume_date(history: SymbolHistory, upto_index: int) -> date | None:
    for index in range(upto_index, -1, -1):
        if float(history.volume[index]) > 0.0:
            return history.trading_dates[index]
    return None


def _median_trading_value(history: SymbolHistory, upto_index: int) -> float | None:
    """Median of close times volume over the last 20 of the symbol's sessions.

    Median rather than mean, per Section 15, so that one limit-up day with
    exceptional turnover cannot carry an otherwise illiquid security through
    the filter. Fewer than twenty available sessions returns None, which the
    caller treats as a failure rather than as a pass on partial evidence.
    """

    start = upto_index - TRADING_VALUE_LOOKBACK + 1
    if start < 0:
        return None
    values = [
        float(history.close[index]) * float(history.volume[index])
        for index in range(start, upto_index + 1)
    ]
    if any(math.isnan(value) for value in values):
        return None
    return float(statistics.median(values))


def assess(
    candidate: Candidate,
    *,
    filters: UniverseFilters,
    calendar: TradingCalendar,
    as_of_date: date,
) -> UniverseAssessment:
    """Apply every Section 15 default filter to one security."""

    history = candidate.history
    index = history.index_of(as_of_date)
    if index is None:
        # The symbol did not trade on the run date. Section 16 requires
        # explicit handling of suspended securities; falling back to the
        # nearest earlier bar would silently screen a stale price as if it
        # were today's, so the last bar on or before the run date is used and
        # named as such in the metrics.
        position = bisect_right(history.trading_dates, as_of_date) - 1
        index = position if position >= 0 else None

    criteria: list[Criterion] = []
    metrics: dict[str, Any] = {"as_of_date": as_of_date.isoformat()}

    if index is None:
        criteria.append(
            Criterion(
                "has_bar_on_or_before_run_date",
                False,
                True,
                f"no bar on or before {as_of_date.isoformat()}",
            )
        )
        return UniverseAssessment(
            symbol=candidate.symbol,
            included=False,
            criteria=tuple(criteria),
            as_of_index=None,
            metrics=metrics,
        )

    bar_date = history.trading_dates[index]
    metrics["last_bar_date"] = bar_date.isoformat()
    metrics["traded_on_run_date"] = bar_date == as_of_date
    criteria.append(
        Criterion("has_bar_on_or_before_run_date", True, True, bar_date.isoformat())
    )

    # --- Active equity -------------------------------------------------
    if filters.active_equity_only:
        security = candidate.security
        if security is None:
            passed = False
            detail = "no point-in-time classification supplied"
        else:
            passed = security.matches(
                exchanges=filters.accepted_exchanges,
                security_types=filters.accepted_security_types,
                trading_statuses=filters.accepted_trading_statuses,
            )
            detail = (
                f"exchange={security.exchange}, type={security.security_type}, "
                f"status={security.trading_status}"
            )
            metrics["security_as_of_date"] = security.as_of_date.isoformat()
        criteria.append(Criterion("active_equity", passed, True, detail))

    # --- Last positive-volume recency ----------------------------------
    last_positive = _last_positive_volume_date(history, index)
    if last_positive is None:
        criteria.append(
            Criterion(
                "last_positive_volume_recent",
                False,
                True,
                "no positive-volume bar in the available history",
            )
        )
        metrics["sessions_since_last_positive_volume"] = None
    else:
        sessions_since = calendar.sessions_between(last_positive, as_of_date)
        metrics["last_positive_volume_date"] = last_positive.isoformat()
        metrics["sessions_since_last_positive_volume"] = sessions_since
        passed = sessions_since < filters.last_positive_volume_within_days
        criteria.append(
            Criterion(
                "last_positive_volume_recent",
                passed,
                True,
                f"{sessions_since} market sessions since {last_positive.isoformat()}, "
                f"limit {filters.last_positive_volume_within_days} (strictly less than)",
            )
        )

    # --- Minimum 20-day median trading value ---------------------------
    median_value = _median_trading_value(history, index)
    metrics["median_20d_trading_value"] = median_value
    metrics["trading_value_unit"] = filters.trading_value_unit
    if median_value is None:
        criteria.append(
            Criterion(
                "min_20d_median_trading_value",
                False,
                True,
                f"fewer than {TRADING_VALUE_LOOKBACK} sessions, or a non-finite value",
            )
        )
    else:
        criteria.append(
            Criterion(
                "min_20d_median_trading_value",
                median_value >= filters.min_20d_median_trading_value,
                True,
                f"{median_value:.6g} vs minimum "
                f"{filters.min_20d_median_trading_value:.6g} "
                f"({filters.trading_value_unit})",
            )
        )

    # --- Minimum history length ----------------------------------------
    usable = index + 1
    metrics["usable_bars"] = usable
    criteria.append(
        Criterion(
            "min_history_days",
            usable >= filters.min_history_days,
            True,
            f"{usable} bars vs minimum {filters.min_history_days}",
        )
    )

    # --- No unresolved critical data-quality issue ---------------------
    if filters.exclude_unresolved_critical_issues:
        window_statuses = set(history.quality_status[: index + 1])
        flagged = sorted(window_statuses & CRITICAL_QUALITY_VALUES)
        codes = sorted(candidate.critical_issue_codes)
        metrics["critical_issue_codes"] = codes
        metrics["critical_quality_statuses"] = flagged
        criteria.append(
            Criterion(
                "no_unresolved_critical_issue",
                not codes and not flagged,
                True,
                "none" if not codes and not flagged else f"{codes + flagged}",
            )
        )

    return UniverseAssessment(
        symbol=candidate.symbol,
        included=all(item.passed for item in criteria),
        criteria=tuple(criteria),
        as_of_index=index,
        metrics=metrics,
    )


def assess_all(
    candidates: Sequence[Candidate],
    *,
    filters: UniverseFilters,
    as_of_date: date,
    calendar: TradingCalendar | None = None,
) -> tuple[UniverseAssessment, ...]:
    """Assess every candidate, ordered by symbol for a deterministic run."""

    resolved = calendar or TradingCalendar.from_histories(
        [candidate.history for candidate in candidates]
    )
    ordered = sorted(candidates, key=lambda candidate: candidate.symbol)
    return tuple(
        assess(candidate, filters=filters, calendar=resolved, as_of_date=as_of_date)
        for candidate in ordered
    )
