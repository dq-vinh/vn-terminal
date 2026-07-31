"""Canonical contract 10.2: security master.

Field list is taken verbatim from the "Required fields" list in Section 10.2
of vn_terminal_multi_ai_development_plan.md v1.1. The index_code field is
added because Section 10.2's prose (immediately following the required-field
list) states: "The security master must include an index code-to-name
mapping from an external source before relative-strength calculations
against VN-Index or sector indices are enabled." The plan describes this
requirement but does not name it as a field; adding it here is this
session's interpretation and is logged in contracts/OPEN_ITEMS.md.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from .common import StrictModel


class SecurityMaster(StrictModel):
    symbol: str
    isin: str | None = Field(
        default=None, description="Section 10.2: 'isin, when available.'"
    )
    exchange: str = Field(
        examples=["HOSE", "HNX", "UPCoM"],
        description="See OPEN_ITEMS.md; same open-string treatment as PriceBar.exchange.",
    )
    security_type: str = Field(
        examples=["equity"],
        description="See OPEN_ITEMS.md; same open-string treatment as PriceBar.security_type.",
    )
    company_name: str
    sector: str
    industry: str
    listing_date: date
    delisting_date: date | None = Field(
        default=None,
        description="Section 10.2 lists this field; only populated for delisted securities.",
    )
    trading_status: str = Field(
        examples=["active", "suspended", "delisted"],
        description=(
            "OPEN ITEM: Section 3.2 mentions distinguishing 'suspended "
            "securities, and delisted securities'; WP2 (Section 22) speaks "
            "of 'Active/inactive status.' Whether trading_status is a "
            "three-plus-value set (active/suspended/delisted/...) or a "
            "two-value active/inactive flag with suspension detail held "
            "elsewhere is not settled by the plan. See "
            "contracts/OPEN_ITEMS.md."
        ),
    )
    currency: str = Field(examples=["VND"])
    price_unit: str = Field(
        examples=["thousand_vnd"],
        description=(
            "Section 3.2: 'OHLC prices appear to be historically adjusted "
            "and expressed in thousands of VND.'"
        ),
    )
    lot_size: int = Field(ge=1)
    source: str
    valid_from: date
    valid_to: date | None = None
    index_code: str | None = Field(
        default=None,
        description=(
            "Only populated for security_type=index entries sourced from "
            "EOD/index, whose 207 files are named with numeric codes (for "
            "example 0001.dat, 0500.dat) rather than symbols (Section "
            "10.2). Not a literal field name from the plan; see "
            "contracts/OPEN_ITEMS.md."
        ),
    )
