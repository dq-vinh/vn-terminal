"""Canonical contract 10.4: strategy definition.

Field list is taken verbatim from the "Every strategy declares" list in
Section 10.4. Category candidates come from the families listed in Section
13.1, which the plan explicitly says "describes categories, not the final
strategy catalogue" (Section 13.1, closing sentence).

This module intentionally contains no example strategy content (no real
entry/exit rules). Section 13.2 and the P7 prompt in
vn_terminal_ai_execution_playbook.md assign strategy specification to the
user (Stream F), not to any coding agent. Inventing example rule text here,
even as a schema example, would cross that boundary.
"""

from __future__ import annotations

from .common import ExecutionConvention, StrictModel
from pydantic import Field


class StrategyDefinition(StrictModel):
    strategy_id: str
    version: str = Field(examples=["1.0.0"])
    title_vi: str
    title_en: str
    category: str = Field(
        examples=[
            "trend_following",
            "moving_average_alignment",
            "breakout",
            "momentum",
            "relative_strength",
            "volume_liquidity",
            "mean_reversion",
            "sideways_range",
            "weinstein_stage_analysis",
            "minervini_template",
            "wyckoff_derived",
            "pivot_support_resistance",
            "composite_scorecard",
        ],
        description=(
            "OPEN ITEM: examples are machine-readable slugs derived from "
            "the Section 13.1 family list, which the plan explicitly "
            "calls categories rather than a final catalogue. Left as an "
            "open string, not a closed enum. See contracts/OPEN_ITEMS.md."
        ),
    )
    timeframe: str = Field(
        description=(
            "See Timeframe enum in common.py for the same 1D/1W/1M open "
            "item; kept as a plain string here since a strategy's stated "
            "timeframe could in principle combine several (e.g. weekly "
            "trend filter plus daily trigger), which the plan does not "
            "resolve. See contracts/OPEN_ITEMS.md."
        )
    )
    required_fields: list[str] = Field(
        description="Section 10.4: input fields (e.g. price/volume series) the strategy needs."
    )
    warmup_bars: int = Field(ge=0)
    parameter_schema: dict = Field(
        description=(
            "OPEN ITEM: the plan requires a 'parameter_schema' field but "
            "does not define its structure (e.g. JSON Schema for "
            "parameters vs. a simpler name-to-spec mapping). Typed as an "
            "open object. See contracts/OPEN_ITEMS.md."
        )
    )
    entry_rule: str = Field(
        description=(
            "OPEN ITEM: the plan does not specify whether rule fields are "
            "free text, a structured condition tree, or a small DSL. "
            "Typed as a string (human-readable specification) here, "
            "consistent with docs/strategy_catalogue.md being written in "
            "prose by the user per the P7 workflow. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    exit_rule: str
    invalidation_rule: str
    liquidity_rule: str
    execution_convention: ExecutionConvention
    evidence_fields: list[str] = Field(
        description="Section 10.4: fields this strategy must report into the AI fact bundle."
    )
    reference: str = Field(
        description=(
            "Section 13.3: source of the rule, e.g. an AFL file path, a "
            "book citation, or the user's own judgment."
        )
    )
