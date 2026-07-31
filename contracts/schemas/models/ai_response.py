"""Structured AI response, Section 18.3, with the Section 18.4 validation
metadata folded in.

Section 18.3 required fields: summary, facts, base_case, bull_case,
bear_case, conditions, risks, invalidation, conflicting_evidence,
confidence, sources, warnings.

Section 18.4 additionally requires: "Preserve the model name and prompt
version," which this module surfaces as model and prompt_version fields on
the same response object, since the plan gives no separate envelope for
that metadata.
"""

from __future__ import annotations

from pydantic import Field

from .common import AIProviderType, StrictModel


class StructuredAIResponse(StrictModel):
    summary: str
    facts: list[str] = Field(
        description=(
            "Section 18.3: 'facts.' OPEN ITEM: the plan does not specify "
            "whether this is a list of fact-bundle references (ids/paths "
            "into the AIFactBundle) or restated fact strings. Modeled as "
            "a list of strings. See contracts/OPEN_ITEMS.md."
        )
    )
    base_case: str
    bull_case: str
    bear_case: str
    conditions: list[str]
    risks: list[str]
    invalidation: str | None
    conflicting_evidence: list[str] = Field(default_factory=list)
    confidence: str = Field(
        description=(
            "Section 18.4: 'Require a confidence level.' OPEN ITEM: the "
            "plan does not define the scale (qualitative label such as "
            "low/medium/high, or a numeric 0-1 score). Left as an open "
            "string. See contracts/OPEN_ITEMS.md."
        )
    )
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Section 18.4: "Preserve the model name and prompt version."
    model: str
    provider: AIProviderType
    prompt_version: str
