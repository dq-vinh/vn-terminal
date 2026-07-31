"""Shared types reused across the canonical contracts and the API layer.

Traceability:
- Provenance: Section 3.4 ("Every analytical output includes an as_of_date,
  data source, and freshness status") and Section 11 ("All endpoints must
  have as_of_date, data_version, source, quality and freshness warnings
  where applicable"). Consolidated into one reusable object rather than
  repeated flat fields on 18 endpoints; see docs/decision_log.md, WP0 entry.
- Error / HTTPValidationError: Section 11 ("Explicit error responses").
  HTTPValidationError mirrors FastAPI's own default 422 envelope shape,
  since Section 7 mandates FastAPI as the backend framework.
- Severity: Section 19.2 ("Severity levels: Critical, High, Medium, Low").
  This is one of the few fields the plan gives as an explicit closed list.
- PeriodType: Section 10.3 ("period_type, quarter or year"), explicit closed
  list.
- ExecutionConvention: Section 16 ("Entry at next open or next close,
  explicitly selected"), explicit closed list.
- AIProviderType: Section 18.2 ("OpenRouter-compatible cloud adapter",
  "Ollama local adapter", "Optional direct OpenAI-compatible adapter"),
  explicit closed list of three adapter kinds.
- Levels: Section 10.5 ("levels": {"support": [], "resistance": [],
  "invalidation": null}), reused verbatim in the AI fact bundle (Section
  10.6, "Support, resistance, and invalidation candidates").
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base class for all canonical contracts.

    additionalProperties is set to false (extra="forbid") on every canonical
    contract as a deliberate strictness choice to catch contract drift
    early (Section 21.1, Section 28 risk register: "Contract drift").
    See docs/decision_log.md, WP0 entry, for why this is stricter than the
    plan literally requires.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Severity(str, Enum):
    """Section 19.2: "Severity levels: Critical, High, Medium, Low."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PeriodType(str, Enum):
    """Section 10.3: "period_type, quarter or year."""

    QUARTER = "quarter"
    YEAR = "year"


class ExecutionConvention(str, Enum):
    """Section 16: "Entry at next open or next close, explicitly selected."""

    NEXT_OPEN = "next_open"
    NEXT_CLOSE = "next_close"


class AIProviderType(str, Enum):
    """Section 18.2 adapters list."""

    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class Timeframe(str, Enum):
    """Daily, weekly, monthly per Section 12.1 and Section 12.2.

    OPEN ITEM: the plan never gives literal timeframe codes. "1D" appears
    once, as an example value in the Section 10.1 price-bar JSON sample.
    "1W" and "1M" are inferred by this session to cover the weekly and
    monthly views required by Section 12.1/12.2. See contracts/OPEN_ITEMS.md.
    """

    D1 = "1D"
    W1 = "1W"
    M1 = "1M"


class QualityIssue(StrictModel):
    """One data-quality finding, per the checks enumerated in Section 19.2.

    OPEN ITEM: the plan lists fourteen automated checks and four severity
    levels (Section 19.2) but does not give a literal issue-record schema.
    This shape is this session's proposal for representing one finding; see
    contracts/OPEN_ITEMS.md.
    """

    code: str = Field(
        description=(
            "Identifier for which of the fourteen Section 19.2 checks "
            "produced this issue, for example 'header_count_mismatch' or "
            "'ohlc_violation'. Exact vocabulary is an open item."
        )
    )
    severity: Severity
    message: str
    symbol: str | None = Field(
        default=None, description="Affected symbol, when the issue is symbol-scoped."
    )
    source_file: str | None = Field(
        default=None,
        description=(
            "Affected source file path, when applicable "
            "(Section 19.2 example: EOD/cw/CSHB2604.dat)."
        ),
    )


class Provenance(StrictModel):
    """Attached to every API response envelope (Section 11, Section 3.4)."""

    as_of_date: date = Field(
        description="Section 11: 'as_of_date' required on every endpoint."
    )
    data_version: str = Field(
        description=(
            "Section 11: 'data_version' required on every endpoint. "
            "Example form from Section 10.5: 'fdata-2026-07-30'."
        )
    )
    source: str = Field(
        description="Section 11: 'source' required on every endpoint."
    )
    freshness_status: str = Field(
        description=(
            "Section 3.4: 'freshness status'. OPEN ITEM: the plan does not "
            "enumerate allowed values. See contracts/OPEN_ITEMS.md."
        )
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Section 11: 'Quality and freshness warnings where applicable.'"
        ),
    )


class Levels(StrictModel):
    """Section 10.5 'levels' object, reused by the AI fact bundle (10.6)."""

    support: list[float] = Field(default_factory=list)
    resistance: list[float] = Field(default_factory=list)
    invalidation: float | None = None


class ErrorResponse(StrictModel):
    """Explicit error response (Section 11) for non-validation errors."""

    error_code: str = Field(
        description=(
            "OPEN ITEM: the plan requires 'explicit error responses' "
            "(Section 11) but does not name an error vocabulary. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    message: str
    details: dict[str, Any] | None = None


class HTTPValidationErrorItem(StrictModel):
    loc: list[str | int]
    msg: str
    type: str


class HTTPValidationError(StrictModel):
    """FastAPI's standard 422 request-validation error envelope.

    Traceable to Section 7 ('Backend: Python FastAPI'); this is FastAPI's
    own documented default shape, not an invented one.
    """

    detail: list[HTTPValidationErrorItem]


class ContractMeta(StrictModel):
    """Embedded in every fixture file for provenance of the fixture itself."""

    contract_version: str
    generated_at: datetime
    generator: str
