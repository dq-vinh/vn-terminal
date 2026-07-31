"""Strategy registry (WP6 deliverable 1).

Mirrors the WP5 indicator registry: an import-time-populated mapping from
`strategy_id` to the registered strategy, so that the screener (WP7), the
backtester (WP8), and the API layer can name a strategy by id without
importing its module.

Two rules distinguish this from the indicator registry:

- Registration is keyed on `(strategy_id, version)` as a pair, and re-
  registering the same pair is an error. Section 10.4 requires a version on
  every strategy and the approved catalogue states that "Any change that can
  alter a signal, order, reported criterion, or evidence value requires a
  strategy-version change". Recording the version in the key is what lets a
  screener run store "which version produced this result" and mean it.
- The registry refuses a strategy whose metadata fails validation, so an
  incompletely declared strategy cannot reach a screener run at all.

The registry contains exactly the strategies with an approved written
specification in `docs/strategy_catalogue.md`. As of 31 July 2026 that is
one. Nothing here is padded to reach the Section 13.1 family count or the
v1.0 target of ten to fifteen; see `HANDOFF_WP6_WP7_WP8.md`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .protocol import Strategy, StrategyMetadata
from .types import (
    AsOfWindow,
    PositionState,
    SecurityView,
    StrategyError,
    StrategyEvaluation,
)


@dataclass(frozen=True, slots=True)
class RegisteredStrategy:
    strategy: Strategy

    @property
    def metadata(self) -> StrategyMetadata:
        return self.strategy.metadata

    @property
    def strategy_id(self) -> str:
        return self.metadata.strategy_id

    @property
    def version(self) -> str:
        return self.metadata.version


_REGISTRY: dict[str, RegisteredStrategy] = {}
_VERSIONS: dict[tuple[str, str], str] = {}


def register(strategy: Strategy) -> Strategy:
    """Register one strategy instance. Returns it, so it can decorate."""

    metadata = strategy.metadata
    if not isinstance(metadata, StrategyMetadata):
        raise StrategyError(
            f"{strategy!r} does not expose a StrategyMetadata; Section 10.4 "
            "requires every declared field."
        )
    key = (metadata.strategy_id, metadata.version)
    if key in _VERSIONS:
        raise StrategyError(
            f"strategy {metadata.strategy_id!r} version {metadata.version!r} is "
            "already registered"
        )
    if metadata.strategy_id in _REGISTRY:
        raise StrategyError(
            f"strategy {metadata.strategy_id!r} is already registered at version "
            f"{_REGISTRY[metadata.strategy_id].version!r}. Two versions of one "
            "strategy cannot be active at once in v1.0; bump the id or retire the "
            "old version."
        )
    _VERSIONS[key] = metadata.version
    _REGISTRY[metadata.strategy_id] = RegisteredStrategy(strategy=strategy)
    return strategy


def get(strategy_id: str) -> RegisteredStrategy:
    try:
        return _REGISTRY[strategy_id]
    except KeyError as error:
        raise StrategyError(
            f"unknown strategy {strategy_id!r}; registered strategies are "
            f"{sorted(_REGISTRY)}"
        ) from error


def metadata(strategy_id: str) -> StrategyMetadata:
    return get(strategy_id).metadata


def all_strategies() -> tuple[RegisteredStrategy, ...]:
    """Every registered strategy, ordered by id for deterministic output."""

    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def all_ids() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def versions() -> dict[str, str]:
    """`strategy_id` to `version`, for a screener or backtest run record."""

    return {key: _REGISTRY[key].version for key in sorted(_REGISTRY)}


def __iter__() -> Iterator[RegisteredStrategy]:  # pragma: no cover - convenience
    return iter(all_strategies())


def resolve_parameters(
    strategy_id: str, overrides: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    entry = get(strategy_id)
    resolved = entry.metadata.resolve_parameters(overrides)
    entry.strategy.validate_parameters(resolved)
    return resolved


def warmup_bars(strategy_id: str, parameters: Mapping[str, Any] | None = None) -> int:
    entry = get(strategy_id)
    resolved = resolve_parameters(strategy_id, parameters)
    return entry.strategy.warmup_bars(resolved)


def evaluate(
    strategy_id: str,
    window: AsOfWindow,
    *,
    security: SecurityView | None = None,
    position_state: PositionState = PositionState.FLAT,
    parameters: Mapping[str, Any] | None = None,
    exit_pending: bool = False,
    entry_price: float | None = None,
) -> StrategyEvaluation:
    """Run one registered strategy against one as-of window.

    Parameters are validated before the strategy sees them, so a rule never
    has to defend itself against an out-of-range period. `exit_pending` and
    `entry_price` are caller-owned position facts; see `Strategy.evaluate`.
    """

    entry = get(strategy_id)
    resolved = resolve_parameters(strategy_id, parameters)
    result = entry.strategy.evaluate(
        window,
        security=security,
        position_state=position_state,
        parameters=resolved,
        exit_pending=exit_pending,
        entry_price=entry_price,
    )
    if result.strategy_id != strategy_id:
        raise StrategyError(
            f"{strategy_id} returned a result labelled {result.strategy_id!r}"
        )
    if result.strategy_version != entry.version:
        raise StrategyError(
            f"{strategy_id} returned version {result.strategy_version!r}, registered "
            f"as {entry.version!r}"
        )
    expected = set(entry.metadata.criterion_names)
    produced = {item.name for item in result.criteria}
    if produced != expected:
        raise StrategyError(
            f"{strategy_id} declares criteria {sorted(expected)} but produced "
            f"{sorted(produced)}; max_score would not be comparable across symbols."
        )
    return result


def _reset_for_tests() -> None:
    """Clear the registry. Test-only; never called by production code."""

    _REGISTRY.clear()
    _VERSIONS.clear()
