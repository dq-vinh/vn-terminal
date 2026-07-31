"""AI fact bundle, Section 10.6.

Section 10.6 gives the bundle's contents as a bullet list, not literal field
names:

- Symbol identity and as-of date.
- Price and volume summary.
- Deterministic indicators.
- Money-flow and accumulation metrics from Section 14.
- Strategy results and failed criteria.
- Financial history and growth metrics.
- Support, resistance, and invalidation candidates.
- Data freshness and quality warnings.
- Source URLs and calculation definitions.
- "The language model must not access raw database tables directly."

Where a bullet already maps to a concrete contract elsewhere in the plan
(money-flow, strategy results, levels), this module reuses that contract
directly. Where a bullet has no defined internal shape (price/volume
summary, indicators, financial summary), this module uses an open object
and records the gap in contracts/OPEN_ITEMS.md, rather than inventing
sub-fields the plan never specified.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from .common import Levels, StrictModel
from .money_flow import MoneyFlowBlock
from .strategy_evaluation_result import StrategyEvaluationResult


class AIFactBundle(StrictModel):
    symbol: str = Field(description="Section 10.6: 'Symbol identity and as-of date.'")
    as_of_date: date

    price_summary: dict = Field(
        description=(
            "Section 10.6: 'Price and volume summary.' OPEN ITEM: no "
            "internal shape given by the plan. Typed as an open object. "
            "See contracts/OPEN_ITEMS.md."
        )
    )
    indicators: dict = Field(
        description=(
            "Section 10.6: 'Deterministic indicators.' OPEN ITEM: Section "
            "14 names the indicator list but not the fact-bundle "
            "serialization shape. Typed as an open object. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    money_flow: MoneyFlowBlock = Field(
        description="Section 10.6: 'Money-flow and accumulation metrics from Section 14.'"
    )
    strategy_results: list[StrategyEvaluationResult] = Field(
        default_factory=list,
        description="Section 10.6: 'Strategy results and failed criteria.'",
    )
    financial_summary: dict = Field(
        description=(
            "Section 10.6: 'Financial history and growth metrics.' OPEN "
            "ITEM: no internal shape given by the plan. Typed as an open "
            "object. See contracts/OPEN_ITEMS.md."
        )
    )
    levels: Levels = Field(
        description="Section 10.6: 'Support, resistance, and invalidation candidates.'"
    )
    data_quality: dict = Field(
        description=(
            "Section 10.6: 'Data freshness and quality warnings.' Expected "
            "to carry a freshness_status and a list of QualityIssue "
            "entries (see common.QualityIssue), but the plan does not fix "
            "an exact shape for this bullet either. Typed as an open "
            "object. See contracts/OPEN_ITEMS.md."
        )
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Section 10.6: 'Source URLs...', modeled as a list of URL strings.",
    )
    calculation_definitions: list[str] = Field(
        default_factory=list,
        description=(
            "Section 10.6: '...and calculation definitions.', modeled as "
            "a list of human-readable definition strings, matching the "
            "per-indicator documentation required by Section 14 (formula, "
            "input price, adjustment convention, warm-up period, "
            "missing-value behavior, comparison reference, numerical "
            "tolerance)."
        ),
    )
