"""Internal immutable models for point-in-time financial data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class ValueBasis(str, Enum):
    """How a statement value relates to its reporting period."""

    STANDALONE = "standalone"
    CUMULATIVE = "cumulative"
    ANNUAL = "annual"
    POINT_IN_TIME = "point_in_time"
    RATIO = "ratio"
    UNKNOWN = "unknown"


FLOW_STATEMENTS = frozenset({"income_statement", "cash_flow_statement"})


@dataclass(frozen=True, slots=True)
class RawFinancialObservation:
    """One provider value before canonical validation and code projection."""

    symbol: str
    period_end: date
    period_type: str
    statement_type: str
    metric_code: str
    metric_label_vi: str
    value: Decimal | float | int
    currency: str
    unit: str
    consolidated: bool
    value_basis: ValueBasis
    restatement_version: int
    publication_date: date | None
    source_url: str
    source_name: str
    ingested_at: datetime

    def __post_init__(self) -> None:
        if (
            self.period_type == "quarter"
            and self.statement_type in FLOW_STATEMENTS
            and self.value_basis not in {
                ValueBasis.STANDALONE,
                ValueBasis.CUMULATIVE,
            }
        ):
            raise ValueError(
                "value_basis must explicitly be standalone or cumulative "
                "for quarterly flow observations"
            )


@dataclass(frozen=True, slots=True)
class NormalizedFinancialObservation:
    """Validated append-only observation used by storage and calculations."""

    symbol: str
    period_end: date
    period_type: str
    statement_type: str
    metric_code: str
    base_metric_code: str
    metric_label_vi: str
    value: Decimal
    currency: str
    unit: str
    consolidated: bool
    value_basis: ValueBasis
    restatement_version: int
    publication_date: date | None
    source_url: str
    source_name: str
    ingested_at: datetime
    calculation: str | None = None

    @property
    def backtest_eligible(self) -> bool:
        return self.publication_date is not None

