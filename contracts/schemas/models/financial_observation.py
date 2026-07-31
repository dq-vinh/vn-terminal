"""Canonical contract 10.3: financial observation.

Field list is taken verbatim from the "Required fields" list in Section 10.3.
The degraded-mode rule for publication_date is from Section 17: "Fundamentals
without publication dates remain available for display and current screening
but are excluded from historical backtests, with an explicit warning."
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from .common import PeriodType, StrictModel


class FinancialObservation(StrictModel):
    symbol: str
    period_end: date
    period_type: PeriodType
    statement_type: str = Field(
        examples=["income_statement", "balance_sheet", "cash_flow_statement"],
        description=(
            "OPEN ITEM: Section 10.3 names the field but does not "
            "enumerate statement types. Examples given here follow "
            "standard financial-statement categories implied by Section "
            "17 ('Financial statements') but are not a plan-given closed "
            "list. See contracts/OPEN_ITEMS.md."
        ),
    )
    metric_code: str
    metric_label_vi: str
    value: float
    currency: str = Field(examples=["VND"])
    unit: str = Field(
        description=(
            "OPEN ITEM: Section 17 requires recording 'currency and units' "
            "but the plan does not give a unit vocabulary (for example "
            "whether values are in VND, thousand VND, or million VND). "
            "See contracts/OPEN_ITEMS.md."
        )
    )
    consolidated: bool = Field(
        description="Section 17: 'Distinguish consolidated and separate statements.'"
    )
    restatement_version: int = Field(
        ge=1,
        description=(
            "OPEN ITEM: Section 10.3 names 'restatement_version' and "
            "Section 17 requires 'Preserve restatements' but the plan "
            "does not say whether this is an incrementing integer or a "
            "string tag. Modeled as an integer counter starting at 1 in "
            "this session. See contracts/OPEN_ITEMS.md."
        ),
    )
    publication_date: date | None = Field(
        default=None,
        description=(
            "Section 17 degraded mode: nullable. When null, this "
            "observation must be excluded from historical backtests "
            "(Section 16: 'No use of later financial-publication "
            "information... affected fundamental inputs are excluded from "
            "backtests rather than assumed') and must carry an explicit "
            "warning at the point of use."
        ),
    )
    source_url: str
    ingested_at: datetime
