"""Indicator registry (WP5 deliverable 1).

The registry is a single import-time-populated mapping from `indicator_id`
to `(spec, function)`. It exists so that:

- the screener and strategy registry (WP6, WP7) can name indicators by id
  rather than importing each module,
- `tests/quant/test_documentation.py` can assert that every registered
  indicator carries all seven Section 14 documentation attributes and has a
  golden-fixture test,
- `tests/quant/test_purity.py` can enumerate every indicator and run it
  under a sandbox that fails on network, database, or file access.

Registration happens once, at import of `backend.app.quant.indicators`.
`compute()` never mutates the registry, and indicator functions never see
it, so the module-level dictionary does not compromise indicator purity.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .types import IndicatorError, IndicatorResult, IndicatorSpec, OHLCVSeries

IndicatorFunction = Callable[..., IndicatorResult]


@dataclass(frozen=True, slots=True)
class RegisteredIndicator:
    spec: IndicatorSpec
    function: IndicatorFunction


_REGISTRY: dict[str, RegisteredIndicator] = {}


def register(spec: IndicatorSpec) -> Callable[[IndicatorFunction], IndicatorFunction]:
    """Decorator binding an indicator function to its documentation record."""

    def decorator(function: IndicatorFunction) -> IndicatorFunction:
        if spec.indicator_id in _REGISTRY:
            raise IndicatorError(f"indicator {spec.indicator_id!r} is already registered")
        _REGISTRY[spec.indicator_id] = RegisteredIndicator(spec=spec, function=function)
        return function

    return decorator


def get(indicator_id: str) -> RegisteredIndicator:
    try:
        return _REGISTRY[indicator_id]
    except KeyError as error:
        raise IndicatorError(
            f"unknown indicator {indicator_id!r}; registered indicators are "
            f"{sorted(_REGISTRY)}"
        ) from error


def spec(indicator_id: str) -> IndicatorSpec:
    return get(indicator_id).spec


def all_indicators() -> tuple[RegisteredIndicator, ...]:
    """Every registered indicator, ordered by id for deterministic output."""

    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def all_ids() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def __iter__() -> Iterator[RegisteredIndicator]:  # pragma: no cover - convenience only
    return iter(all_indicators())


def compute(
    indicator_id: str,
    series: OHLCVSeries,
    /,
    **parameters: Any,
) -> IndicatorResult:
    """Run one registered indicator.

    Parameter overrides are validated against the documented defaults
    (`IndicatorSpec.resolved_parameters`), so an unknown keyword raises
    instead of being silently dropped.
    """

    entry = get(indicator_id)
    resolved = entry.spec.resolved_parameters(parameters)
    result = entry.function(series, **resolved)
    if result.indicator_id != indicator_id:
        raise IndicatorError(
            f"{indicator_id} returned a result labelled {result.indicator_id!r}"
        )
    missing = set(entry.spec.outputs) - set(result.series)
    if missing:
        raise IndicatorError(
            f"{indicator_id} declares outputs {sorted(entry.spec.outputs)} but did not "
            f"return {sorted(missing)}"
        )
    return result


def documentation() -> tuple[Mapping[str, Any], ...]:
    """Section 14 documentation for every indicator, as plain dictionaries.

    Used by `tests/quant/test_documentation.py` and available to the API
    layer if the lead integrator wants to expose indicator metadata.
    """

    records: list[Mapping[str, Any]] = []
    for entry in all_indicators():
        item = entry.spec
        records.append(
            {
                "indicator_id": item.indicator_id,
                "title": item.title,
                "block": item.block,
                "outputs": list(item.outputs),
                "scalar_outputs": list(item.scalar_outputs),
                "parameters": dict(item.parameters),
                "formula": item.formula,
                "input_price": item.input_price,
                "adjustment_convention": item.adjustment_convention,
                "warm_up": item.warm_up,
                "missing_value_behavior": item.missing_value_behavior,
                "comparison_reference": item.comparison_reference,
                "tolerance": {
                    "absolute": item.tolerance.absolute,
                    "relative": item.tolerance.relative,
                    "basis": item.tolerance.basis,
                },
                "requires_benchmark": item.requires_benchmark,
            }
        )
    return tuple(records)
