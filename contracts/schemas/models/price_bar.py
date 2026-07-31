"""Canonical contract 10.1: price bar.

Field set and example values are taken directly from the JSON example in
Section 10.1 of vn_terminal_multi_ai_development_plan.md v1.1, plus the
verified binary format in Section 19.1 (OHLC in thousands of VND,
back-adjusted; volume in shares).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from .common import StrictModel, Timeframe


class PriceBar(StrictModel):
    symbol: str = Field(examples=["FPT"])
    exchange: str = Field(
        examples=["HOSE", "HNX", "UPCoM"],
        description=(
            "Section 1/10.1: evidenced values are HOSE, HNX, UPCoM. Left as "
            "an open string rather than a closed enum; see "
            "contracts/OPEN_ITEMS.md."
        ),
    )
    security_type: str = Field(
        examples=["equity"],
        description=(
            "OPEN ITEM: candidate values inferred from WP1's four FData "
            "category directories (stock, index, der, cw) mapping to "
            "equity/index/derivative/warrant, plus 'bond' per the Section "
            "3.2 assumption text, which has no confirmed FData source "
            "directory. Section 19.2 also notes 'Mixed security types in "
            "the stock directory,' so directory alone does not determine "
            "this value. Left as an open string; see "
            "contracts/OPEN_ITEMS.md."
        ),
    )
    timeframe: Timeframe = Field(examples=["1D"])
    trading_date: date
    timezone: str = Field(
        default="Asia/Ho_Chi_Minh",
        description="Section 10.1 example value; VN Terminal Pro is single-market.",
    )
    open: float = Field(description="Thousands of VND, back-adjusted (Section 19.1).")
    high: float = Field(description="Thousands of VND, back-adjusted (Section 19.1).")
    low: float = Field(description="Thousands of VND, back-adjusted (Section 19.1).")
    close: float = Field(description="Thousands of VND, back-adjusted (Section 19.1).")
    volume: int = Field(ge=0, description="Shares (Section 19.1).")
    adjustment_status: str = Field(
        examples=["adjusted_unknown_method"],
        description=(
            "OPEN ITEM: only 'adjusted_unknown_method' is evidenced "
            "(Section 10.1 example). The plan does not enumerate the full "
            "set of possible values. See contracts/OPEN_ITEMS.md."
        ),
    )
    source: str = Field(examples=["Fialda FData"])
    source_file: str = Field(
        examples=["C:\\FDATA\\AmiBroker\\EOD\\stock\\FPT.dat"]
    )
    ingested_at: datetime
    quality_status: str = Field(
        examples=["valid"],
        description=(
            "OPEN ITEM: only 'valid' is evidenced (Section 10.1 example). "
            "See contracts/OPEN_ITEMS.md."
        ),
    )
