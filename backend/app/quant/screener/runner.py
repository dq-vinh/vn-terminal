"""Screener execution, ranking, and the reproducibility record (Section 15).

Section 15 requires a run to "Store run date, strategy versions, parameters,
and data version" and WP7's acceptance criterion is that a "Full run is
reproducible". `ScreenRun.run_id` is therefore not a UUID. It is the SHA-256
of the canonical JSON of everything that can change an output: the run date,
the data version, the resolved universe filters, each strategy's id, version
and effective parameters, and the sorted candidate symbol list. Two runs with
identical inputs produce an identical `run_id`; a run whose inputs differ in
any respect produces a different one. That turns reproducibility into
something a test can assert rather than something a log claims.

Ranking is deterministic in the strict sense: the sort key is
`(-total_score, symbol)`, so ties never depend on dictionary order, thread
scheduling, or input order. `tests/quant/test_screener.py` shuffles the input
and asserts the ranking is unchanged.

Securities excluded by the universe filters are kept, with their failed
criteria, in `ScreenRun.excluded`. Section 15 asks the screener to "Show
passed and failed criteria"; dropping exclusions silently would answer "why
is this symbol missing" with nothing. Only `ScreenRun.results` is ranked, and
only it maps onto the contract's `results` array.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..strategies import registry as strategy_registry
from ..strategies.serialization import evaluation_payload, to_contract_result
from ..strategies.types import PositionState, StrategyEvaluation
from .universe import (
    Candidate,
    TradingCalendar,
    UniverseAssessment,
    UniverseFilters,
    assess_all,
)


@dataclass(frozen=True, slots=True)
class SymbolResult:
    """One security's outcome across every strategy in the run."""

    symbol: str
    total_score: int
    max_score: int
    rank: int
    passed_criteria: tuple[str, ...]
    failed_criteria: tuple[str, ...]
    signals: Mapping[str, str]
    evaluations: tuple[StrategyEvaluation, ...]
    universe: UniverseAssessment

    def contract_item(self) -> dict[str, Any]:
        """`ScreenResultItem` shape from `screen_results_response.schema.json`."""

        return {
            "symbol": self.symbol,
            "score": float(self.total_score),
            "rank": self.rank,
            "passed_criteria": list(self.passed_criteria),
            "failed_criteria": list(self.failed_criteria),
        }


@dataclass(frozen=True, slots=True)
class ScreenRun:
    """Everything needed to reproduce, audit, and export one screener run."""

    run_id: str
    run_date: date
    data_version: str
    strategy_versions: Mapping[str, str]
    parameters: Mapping[str, Any]
    results: tuple[SymbolResult, ...]
    excluded: tuple[UniverseAssessment, ...]
    warnings: tuple[str, ...] = ()
    status: str = "completed"
    evaluated_symbol_count: int = 0
    candidate_symbol_count: int = 0
    universe_metrics: Mapping[str, Any] = field(default_factory=dict)

    def contract_payload(self, *, source: str, freshness_status: str) -> dict[str, Any]:
        """`ScreenResultsResponse` shape, less nothing.

        `provenance` is assembled here from values the caller supplies rather
        than read from a clock, so a stored run re-serializes identically.
        """

        return {
            "run_id": self.run_id,
            "status": self.status,
            "run_date": self.run_date.isoformat(),
            "strategy_versions": dict(self.strategy_versions),
            "parameters": dict(self.parameters),
            "results": [item.contract_item() for item in self.results],
            "provenance": {
                "as_of_date": self.run_date.isoformat(),
                "data_version": self.data_version,
                "source": source,
                "freshness_status": freshness_status,
                "warnings": list(self.warnings),
            },
        }

    def evidence_payload(self) -> dict[str, Any]:
        """Full evidence for every evaluated symbol, for WP10's fact bundle."""

        return {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "data_version": self.data_version,
            "strategy_versions": dict(self.strategy_versions),
            "parameters": dict(self.parameters),
            "results": [
                {
                    "symbol": item.symbol,
                    "rank": item.rank,
                    "total_score": item.total_score,
                    "max_score": item.max_score,
                    "universe": {
                        "included": item.universe.included,
                        "passed_criteria": list(item.universe.passed_criteria),
                        "failed_criteria": list(item.universe.failed_criteria),
                        "metrics": dict(item.universe.metrics),
                    },
                    "strategies": [
                        evaluation_payload(evaluation) for evaluation in item.evaluations
                    ],
                }
                for item in self.results
            ],
            "excluded": [
                {
                    "symbol": item.symbol,
                    "passed_criteria": list(item.passed_criteria),
                    "failed_criteria": list(item.failed_criteria),
                    "metrics": dict(item.metrics),
                }
                for item in self.excluded
            ],
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_run_id(
    *,
    run_date: date,
    data_version: str,
    filters: UniverseFilters,
    strategy_parameters: Mapping[str, Mapping[str, Any]],
    strategy_versions: Mapping[str, str],
    symbols: Sequence[str],
) -> str:
    """Deterministic run identity. Same inputs, same id."""

    material = {
        "schema": "vn_terminal_screen_run_v1",
        "run_date": run_date.isoformat(),
        "data_version": data_version,
        "filters": filters.as_dict(),
        "strategies": {
            strategy_id: {
                "version": strategy_versions[strategy_id],
                "parameters": dict(strategy_parameters[strategy_id]),
            }
            for strategy_id in sorted(strategy_parameters)
        },
        "symbols": sorted(symbols),
    }
    digest = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    return f"screen-{run_date.isoformat()}-{digest[:16]}"


def run_screen(
    candidates: Sequence[Candidate],
    *,
    strategy_ids: Sequence[str],
    run_date: date,
    data_version: str,
    filters: UniverseFilters | None = None,
    strategy_parameters: Mapping[str, Mapping[str, Any]] | None = None,
    calendar: TradingCalendar | None = None,
) -> ScreenRun:
    """Run one or many strategies across a filtered universe.

    Every strategy is evaluated from `PositionState.FLAT`. That is the
    correct semantic for a screener: the question is "what would I do about
    this symbol today", not "what would I do if I already held it". A
    consequence worth stating is that `exit` can never appear in a screener
    result; exits belong to the backtester and to a position view.
    """

    if not strategy_ids:
        raise ValueError("at least one strategy_id is required")
    resolved_filters = filters or UniverseFilters()
    overrides = strategy_parameters or {}

    effective: dict[str, dict[str, Any]] = {}
    versions: dict[str, str] = {}
    for strategy_id in sorted(set(strategy_ids)):
        entry = strategy_registry.get(strategy_id)
        effective[strategy_id] = strategy_registry.resolve_parameters(
            strategy_id, overrides.get(strategy_id)
        )
        versions[strategy_id] = entry.version

    symbols = [candidate.symbol for candidate in candidates]
    run_id = compute_run_id(
        run_date=run_date,
        data_version=data_version,
        filters=resolved_filters,
        strategy_parameters=effective,
        strategy_versions=versions,
        symbols=symbols,
    )

    resolved_calendar = calendar or TradingCalendar.from_histories(
        [candidate.history for candidate in candidates]
    )
    assessments = assess_all(
        candidates,
        filters=resolved_filters,
        as_of_date=run_date,
        calendar=resolved_calendar,
    )
    by_symbol = {candidate.symbol: candidate for candidate in candidates}

    scored: list[tuple[int, int, str, list[str], list[str], dict[str, str], list[StrategyEvaluation], UniverseAssessment]] = []
    excluded: list[UniverseAssessment] = []
    warnings: list[str] = []

    for assessment in assessments:
        if not assessment.included or assessment.as_of_index is None:
            excluded.append(assessment)
            continue
        candidate = by_symbol[assessment.symbol]
        window_index = assessment.as_of_index
        passed: list[str] = []
        failed: list[str] = []
        signals: dict[str, str] = {}
        evaluations: list[StrategyEvaluation] = []
        total = 0
        maximum = 0
        for strategy_id in sorted(effective):
            evaluation = strategy_registry.evaluate(
                strategy_id,
                candidate.history.window(window_index),
                security=candidate.security,
                position_state=PositionState.FLAT,
                parameters=effective[strategy_id],
            )
            evaluations.append(evaluation)
            signals[strategy_id] = evaluation.signal.value
            total += evaluation.score
            maximum += evaluation.max_score
            passed.extend(f"{strategy_id}.{name}" for name in evaluation.passed_criteria)
            failed.extend(f"{strategy_id}.{name}" for name in evaluation.failed_criteria)
            warnings.extend(
                f"{assessment.symbol}: {message}" for message in evaluation.warnings
            )
        passed.extend(f"universe.{name}" for name in assessment.passed_criteria)
        scored.append(
            (
                total,
                maximum,
                assessment.symbol,
                passed,
                failed,
                signals,
                evaluations,
                assessment,
            )
        )

    scored.sort(key=lambda item: (-item[0], item[2]))
    results = tuple(
        SymbolResult(
            symbol=symbol,
            total_score=total,
            max_score=maximum,
            rank=position + 1,
            passed_criteria=tuple(passed),
            failed_criteria=tuple(failed),
            signals=dict(signals),
            evaluations=tuple(evaluations),
            universe=assessment,
        )
        for position, (
            total,
            maximum,
            symbol,
            passed,
            failed,
            signals,
            evaluations,
            assessment,
        ) in enumerate(scored)
    )

    if not results and candidates:
        warnings.insert(
            0,
            "Every candidate was excluded by the universe filters. This is the "
            "expected outcome while no authoritative security master exists and "
            "active_equity_only is enabled; see backend/app/data/HANDOFF.md, "
            "limitation 1. The run is not empty by accident, and the per-symbol "
            "failed criteria are in ScreenRun.excluded.",
        )

    return ScreenRun(
        run_id=run_id,
        run_date=run_date,
        data_version=data_version,
        strategy_versions=versions,
        parameters={
            "universe_filters": resolved_filters.as_dict(),
            "strategy_parameters": {key: dict(value) for key, value in effective.items()},
            "position_state": PositionState.FLAT.value,
        },
        results=results,
        excluded=tuple(excluded),
        warnings=tuple(dict.fromkeys(warnings)),
        evaluated_symbol_count=len(results),
        candidate_symbol_count=len(candidates),
        universe_metrics={
            "excluded_count": len(excluded),
            "calendar_sessions": len(resolved_calendar.sessions),
        },
    )


def contract_results(run: ScreenRun) -> list[dict[str, Any]]:
    return [item.contract_item() for item in run.results]


def strategy_result_rows(run: ScreenRun) -> list[dict[str, Any]]:
    """One contract `StrategyEvaluationResult` per symbol per strategy."""

    rows: list[dict[str, Any]] = []
    for item in run.results:
        for evaluation in item.evaluations:
            rows.append(to_contract_result(evaluation))
    return rows
