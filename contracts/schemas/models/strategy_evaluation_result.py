"""Canonical contract 10.5: strategy evaluation result.

Field set and types are taken directly from the JSON example in Section
10.5 of vn_terminal_multi_ai_development_plan.md v1.1.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from .common import Levels, StrictModel


class StrategyEvaluationResult(StrictModel):
    symbol: str = Field(examples=["FPT"])
    as_of_date: date
    strategy_id: str = Field(examples=["minervini_trend_template"])
    strategy_version: str = Field(examples=["1.0.0"])
    signal: str = Field(
        examples=["watch"],
        description=(
            "OPEN ITEM: only 'watch' is evidenced (Section 10.5 example). "
            "The plan does not enumerate the full signal vocabulary (for "
            "example whether 'buy', 'sell', 'hold' also exist). See "
            "contracts/OPEN_ITEMS.md."
        ),
    )
    score: int
    max_score: int
    passed_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)
    levels: Levels
    data_version: str = Field(examples=["fdata-2026-07-30"])
    warnings: list[str] = Field(default_factory=list)
