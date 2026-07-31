"""Narrowing quant results into the frozen 0.1.0 contract shapes.

`contracts/**` belongs to the lead integrator (Section 24.1) and is frozen at
0.1.0, so nothing here edits a schema. This module converts what WP6 produces
into what the contract accepts, and it is the single place where information
is deliberately dropped.

Two mismatches are worth stating plainly, because both are load-bearing.

**Evidence does not fit.** `StrategyEvaluationResult` is
`additionalProperties: false` with twelve fields. The approved
`dual_sma_trend_crossover` specification names thirty-seven evidence fields
and requires that "The AI layer must consume these values as facts and must
not recalculate them". Those two statements cannot both hold through this
contract. `to_contract_result()` therefore emits the twelve-field object for
the API, and `evaluation_payload()` emits the full evidence for WP10's fact
bundle, which is where the specification's requirement actually lands. A
contract-change proposal is recorded in `HANDOFF_WP6_WP7_WP8.md` per Section
24.2 rather than applied unilaterally.

**`warmup_bars` is parameter-dependent.** The contract types it as a single
integer; the specification defines it as `max(slow_period + 1, 20)`.
`to_contract_definition()` evaluates it at the approved defaults and the
handoff says so. Publishing a fixed number that silently goes stale when a
user raises `slow_period` would be the worse failure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .protocol import StrategyMetadata
from .registry import RegisteredStrategy, all_strategies, get
from .types import StrategyEvaluation


def to_contract_definition(
    entry: RegisteredStrategy, parameters: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """A `StrategyDefinition` (contract 10.4) as a plain JSON-ready dict.

    Returned as a dict rather than a pydantic instance so this package keeps
    no import dependency on the contracts package at runtime; the API layer
    can validate it against `strategy_definition.schema.json` directly, and
    `tests/quant/test_strategy_contract.py` does exactly that.
    """

    metadata: StrategyMetadata = entry.metadata
    resolved = metadata.resolve_parameters(parameters)
    return {
        "strategy_id": metadata.strategy_id,
        "version": metadata.version,
        "title_vi": metadata.title_vi,
        "title_en": metadata.title_en,
        "category": metadata.category,
        "timeframe": metadata.timeframe,
        "required_fields": list(metadata.required_fields),
        "warmup_bars": entry.strategy.warmup_bars(resolved),
        "parameter_schema": metadata.parameter_schema(),
        "entry_rule": metadata.entry_rule,
        "exit_rule": metadata.exit_rule,
        "invalidation_rule": metadata.invalidation_rule,
        "liquidity_rule": metadata.liquidity_rule,
        "execution_convention": metadata.execution_convention,
        "evidence_fields": list(metadata.evidence_fields),
        "reference": metadata.reference,
    }


def catalogue(parameters: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every registered strategy, in contract shape, ordered by id."""

    overrides = parameters or {}
    return [
        to_contract_definition(entry, overrides.get(entry.strategy_id))
        for entry in all_strategies()
    ]


def to_contract_result(evaluation: StrategyEvaluation) -> dict[str, Any]:
    """A `StrategyEvaluationResult` (contract 10.5) as a plain dict.

    `score` and `max_score` follow the decision of 31 July 2026: score is the
    number of named criteria that passed and max_score is the number the
    strategy names. See `StrategyEvaluation.score` for why.
    """

    return {
        "symbol": evaluation.symbol,
        "as_of_date": evaluation.as_of_date.isoformat(),
        "strategy_id": evaluation.strategy_id,
        "strategy_version": evaluation.strategy_version,
        "signal": evaluation.signal.value,
        "score": evaluation.score,
        "max_score": evaluation.max_score,
        "passed_criteria": list(evaluation.passed_criteria),
        "failed_criteria": list(evaluation.failed_criteria),
        "levels": {
            "support": list(evaluation.support),
            "resistance": list(evaluation.resistance),
            "invalidation": evaluation.invalidation,
        },
        "data_version": evaluation.data_version,
        "warnings": list(evaluation.warnings),
    }


def evaluation_payload(evaluation: StrategyEvaluation) -> dict[str, Any]:
    """The contract result plus the full evidence the contract cannot hold.

    This is the object WP10 should build its fact bundle from. `result` is
    exactly what the API may return today; `evidence` is what the approved
    specification requires the AI layer to consume as facts.
    """

    return {
        "result": to_contract_result(evaluation),
        "evidence": dict(evaluation.evidence),
        "criteria": [
            {
                "name": item.name,
                "passed": item.passed,
                "computable": item.computable,
                "detail": item.detail,
            }
            for item in evaluation.criteria
        ],
        "order": (
            None
            if evaluation.order is None
            else {
                "symbol": evaluation.order.symbol,
                "side": evaluation.order.side.value,
                "decision_date": evaluation.order.decision_date.isoformat(),
                "execution_convention": evaluation.order.execution_convention,
                "reason": evaluation.order.reason,
                "full_exit": evaluation.order.full_exit,
                "immediate": evaluation.order.immediate,
                "fill_price": evaluation.order.fill_price,
                "fill_date": (
                    evaluation.order.fill_date.isoformat()
                    if evaluation.order.fill_date is not None
                    else None
                ),
            }
        ),
        "order_status": evaluation.order_status.value,
        "position_state": evaluation.position_state.value,
        "parameters": dict(evaluation.parameters),
    }


def definition_for(strategy_id: str, parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return to_contract_definition(get(strategy_id), parameters)
