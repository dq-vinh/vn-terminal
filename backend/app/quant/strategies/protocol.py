"""The WP6 strategy protocol and its Section 10.4 metadata record.

Section 10.4 lists sixteen fields that "every strategy declares". WP6's
acceptance criterion is that every strategy has version, parameters, rules,
and tests. `StrategyMetadata` has one required field per Section 10.4 entry
and no defaults for any of them, so a strategy cannot be registered with a
field left blank; `tests/quant/test_strategy_metadata.py` additionally
rejects placeholder text and empty collections.

Two Section 10.4 fields need a shape the plan does not give, and
`contracts/OPEN_ITEMS.md` section B records both as open:

- `parameter_schema` is modeled here as an ordered tuple of `ParameterSpec`
  records, one per row of the approved specification's parameter table
  (type, default, minimum, maximum, increment, additional constraint). It
  serializes to the contract's open JSON object. This is a transcription of
  the approved table, not a design invented for the contract.
- `warmup_bars` is a plain integer in the contract, but the approved
  specification defines it as a function of the parameters,
  `max(slow_period + 1, 20)`. The protocol therefore exposes a callable, and
  the contract serialization evaluates it at the default parameters and says
  so in the handoff. Publishing a single number that silently goes stale when
  a user changes `slow_period` would be worse than either option.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .types import (
    AsOfWindow,
    PositionState,
    SecurityView,
    StrategyError,
    StrategyEvaluation,
)


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """One row of a strategy's approved parameter table."""

    name: str
    kind: str
    default: int | float
    minimum: int | float
    maximum: int | float
    increment: int | float
    unit: str
    constraint: str = ""

    def validate(self, value: Any) -> int | float:
        """Range- and type-check one supplied value.

        Cross-parameter constraints (for example `fast_period <
        slow_period`) are not checked here, because they are relations
        between rows rather than properties of one row. `StrategyMetadata`
        delegates those to the strategy's own `validate_parameters`.
        """

        if self.kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise StrategyError(f"{self.name} must be an integer, got {value!r}")
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            raise StrategyError(f"{self.name} must be numeric, got {value!r}")
        if value < self.minimum or value > self.maximum:
            raise StrategyError(
                f"{self.name} must be between {self.minimum} and {self.maximum}, "
                f"got {value}"
            )
        if self.increment:
            offset = value - self.minimum
            steps = offset / self.increment
            if abs(steps - round(steps)) > 1e-9:
                raise StrategyError(
                    f"{self.name} must advance from {self.minimum} in steps of "
                    f"{self.increment}, got {value}"
                )
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.kind,
            "unit": self.unit,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "increment": self.increment,
            "constraint": self.constraint,
        }


@dataclass(frozen=True, slots=True)
class StrategyMetadata:
    """Section 10.4, one field per declared item, none optional."""

    strategy_id: str
    version: str
    title_vi: str
    title_en: str
    category: str
    timeframe: str
    required_fields: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    entry_rule: str
    exit_rule: str
    invalidation_rule: str
    liquidity_rule: str
    execution_convention: str
    evidence_fields: tuple[str, ...]
    reference: str
    #: Universe gate vocabulary, verbatim from the approved specification.
    #: Held as data rather than as literals inside the rule so that a test
    #: can assert what a strategy accepts without executing it, and so that
    #: the screener can pre-filter on the same values the strategy gates on.
    accepted_exchanges: frozenset[str]
    accepted_security_types: frozenset[str]
    accepted_trading_statuses: frozenset[str]
    #: The exact per-bar quality status the specification permits.
    accepted_quality_statuses: frozenset[str]
    #: Ordered criterion names. Fixes `max_score` for this strategy and makes
    #: screener ranking comparable across symbols.
    criterion_names: tuple[str, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        for name in (
            "strategy_id",
            "version",
            "title_vi",
            "title_en",
            "category",
            "timeframe",
            "entry_rule",
            "exit_rule",
            "invalidation_rule",
            "liquidity_rule",
            "execution_convention",
            "reference",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise StrategyError(f"{self.strategy_id}: {name} must be non-empty")
        for name in ("required_fields", "evidence_fields", "criterion_names"):
            if not getattr(self, name):
                raise StrategyError(f"{self.strategy_id}: {name} must be non-empty")
        if not self.parameters:
            raise StrategyError(f"{self.strategy_id}: parameters must be non-empty")
        seen = {item.name for item in self.parameters}
        if len(seen) != len(self.parameters):
            raise StrategyError(f"{self.strategy_id}: duplicate parameter names")

    @property
    def defaults(self) -> dict[str, int | float]:
        return {item.name: item.default for item in self.parameters}

    def parameter(self, name: str) -> ParameterSpec:
        for item in self.parameters:
            if item.name == name:
                return item
        raise StrategyError(
            f"{self.strategy_id} has no parameter {name!r}; known parameters are "
            f"{sorted(item.name for item in self.parameters)}"
        )

    def resolve_parameters(self, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Merge overrides onto the approved defaults and range-check them.

        Unknown names are rejected rather than ignored, matching the WP5
        registry's behavior, so a typo in a screener or backtest request
        surfaces immediately instead of silently running at a default.
        """

        resolved: dict[str, Any] = dict(self.defaults)
        for key, value in (overrides or {}).items():
            if key not in resolved:
                raise StrategyError(
                    f"{self.strategy_id} has no parameter {key!r}; known parameters "
                    f"are {sorted(resolved)}"
                )
            resolved[key] = self.parameter(key).validate(value)
        return resolved

    def parameter_schema(self) -> dict[str, Any]:
        """The Section 10.4 `parameter_schema` value, as a JSON object."""

        return {
            "kind": "vn_terminal_parameter_table_v1",
            "parameters": [item.as_dict() for item in self.parameters],
        }


@runtime_checkable
class Strategy(Protocol):
    """What every registered strategy must provide.

    `evaluate` is a pure function of an as-of window, a point-in-time
    security view, the caller's position state, and validated parameters. It
    returns a `StrategyEvaluation`; it does not execute, does not mutate
    anything, and cannot see past bar `t` because `AsOfWindow` will not let
    it.
    """

    metadata: StrategyMetadata

    def warmup_bars(self, parameters: Mapping[str, Any]) -> int:
        """Chronological rows required through and including bar `t`."""

    def validate_parameters(self, parameters: Mapping[str, Any]) -> None:
        """Check cross-parameter constraints; raise `StrategyError` if broken."""

    def evaluate(
        self,
        window: AsOfWindow,
        *,
        security: SecurityView | None,
        position_state: PositionState,
        parameters: Mapping[str, Any],
    ) -> StrategyEvaluation:
        """Evaluate one completed bar."""


def required_field_names(metadata: StrategyMetadata) -> Sequence[str]:
    return metadata.required_fields
