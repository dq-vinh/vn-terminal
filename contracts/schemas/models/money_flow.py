"""Money-flow and accumulation block, Section 14.

"Initial members are the accumulation/distribution line, on-balance volume,
up-day versus down-day volume ratio, volume-at-price concentration, and
unusual-volume flags. Once Aux1 is confirmed as unadjusted VWAP,
close-versus-VWAP positioning joins this block."
"""

from __future__ import annotations

from pydantic import Field

from .common import StrictModel


class MoneyFlowBlock(StrictModel):
    accumulation_distribution_line: float = Field(
        description="Section 14: accumulation/distribution line, latest value."
    )
    on_balance_volume: float = Field(
        description="Section 14: on-balance volume, latest value."
    )
    up_down_volume_ratio: float = Field(
        description="Section 14: up-day versus down-day volume ratio."
    )
    volume_at_price_concentration: dict = Field(
        description=(
            "OPEN ITEM: Section 14 names 'volume-at-price concentration' "
            "as a member of this block but does not define its shape "
            "(for example a price-to-volume histogram, or a single "
            "concentration score). Typed as an open object. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    unusual_volume_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Section 14: 'unusual-volume flags' (plural). Modeled as a "
            "list of ISO dates on which unusual volume was flagged. "
            "OPEN ITEM: the plan does not define the detection threshold "
            "or the exact record shape. See contracts/OPEN_ITEMS.md."
        ),
    )
    close_vs_vwap: float | None = Field(
        default=None,
        description=(
            "Section 14: 'Once Aux1 is confirmed as unadjusted VWAP, "
            "close-versus-VWAP positioning joins this block.' Null until "
            "WP1's Aux1 confirmation task (Section 19.1, WP1 acceptance "
            "criteria) concludes. Do not populate before that "
            "confirmation is recorded in docs/data_dictionary.md."
        ),
    )
