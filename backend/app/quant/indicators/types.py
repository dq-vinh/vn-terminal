"""Immutable input and output types for the WP5 indicator engine.

Design constraints, from Section 14 and the WP5 acceptance criteria:

- Indicator functions are pure. They receive already-materialized arrays and
  return new arrays. Nothing here opens a file, a socket, or a database
  connection, and nothing here reads process state that could vary between
  runs (no clock, no environment, no random source).
- Every indicator carries machine-readable numerical documentation. Section
  14 requires seven attributes per indicator: formula, input price,
  adjustment convention, warm-up period, missing-value behaviour,
  comparison reference, and numerical tolerance. `IndicatorSpec` has one
  required field per attribute, and `tests/quant/test_documentation.py`
  fails if any registered indicator leaves one empty.

Missing values are represented as NaN inside this package, never as None,
so that a single float64 array can carry both warm-up and gap positions.
The contract's `IndicatorPoint.value` is `number | null`; conversion happens
once, in `serialization.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np


class IndicatorError(ValueError):
    """Raised for malformed indicator input or parameters."""


class BenchmarkMappingUnavailable(IndicatorError):
    """Raised when a relative-strength benchmark cannot be resolved.

    Section 10.2: "The security master must include an index code-to-name
    mapping from an external source before relative-strength calculations
    against VN-Index or sector indices are enabled." That mapping is owned
    by the data stream (WP2). Until it is supplied, relative-strength
    resolution raises this error rather than guessing an index code.
    """


def _readonly_float_array(values: Sequence[float] | np.ndarray, name: str) -> np.ndarray:
    """Copy `values` into an immutable float64 array.

    The copy is deliberate: it guarantees an indicator can never observe a
    caller mutating its input midway, and it lets the array be marked
    read-only so an indicator cannot mutate the input in place either
    (`tests/quant/test_purity.py` relies on both).
    """

    array = np.array(values, dtype=np.float64, copy=True)
    if array.ndim != 1:
        raise IndicatorError(f"{name} must be one-dimensional, got {array.ndim} dimensions")
    array.setflags(write=False)
    return array


def _parse_date(value: Any, name: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise IndicatorError(f"{name} must be a date or an ISO-8601 date string, got {value!r}")


@dataclass(frozen=True, slots=True, eq=False)
class OHLCVSeries:
    """One security's daily bars, already loaded into memory by the caller.

    Equality is disabled (`eq=False`) because numpy arrays do not produce a
    scalar truth value; use `numpy.testing` helpers in tests instead.

    Adjustment convention: whatever the data layer supplied. Section 19.1
    reports FData OHLC as back-adjusted and expressed in thousands of VND,
    and Section 10.1 carries `adjustment_status` on every bar. This class
    records that status verbatim in `adjustment_status` and never
    re-adjusts, re-scales, or splits-adjusts anything. Every indicator that
    consumes prices therefore inherits the caller's adjustment convention,
    which is what each `IndicatorSpec.adjustment_convention` states.
    """

    symbol: str
    trading_dates: tuple[date, ...]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    adjustment_status: str = "unknown"

    def __post_init__(self) -> None:
        setattr_ = object.__setattr__
        setattr_(self, "trading_dates", tuple(self.trading_dates))
        for name in ("open", "high", "low", "close", "volume"):
            setattr_(self, name, _readonly_float_array(getattr(self, name), name))

        length = len(self.trading_dates)
        for name in ("open", "high", "low", "close", "volume"):
            actual = len(getattr(self, name))
            if actual != length:
                raise IndicatorError(
                    f"{name} has {actual} values but there are {length} trading dates"
                )
        for earlier, later in zip(self.trading_dates, self.trading_dates[1:]):
            if later <= earlier:
                raise IndicatorError(
                    "trading_dates must be strictly increasing; "
                    f"found {earlier.isoformat()} followed by {later.isoformat()}"
                )

    def __len__(self) -> int:
        return len(self.trading_dates)

    @classmethod
    def from_bars(
        cls,
        bars: Sequence[Mapping[str, Any]],
        *,
        symbol: str | None = None,
    ) -> OHLCVSeries:
        """Build a series from contract-shaped `PriceBar` mappings.

        Accepts the exact field names of `contracts/schemas/json/price_bar.schema.json`
        so a caller can pass `json.load(...)["bars"]` straight through. This
        is in-memory parsing only; the caller does the reading.
        """

        if not bars:
            raise IndicatorError("at least one bar is required")

        symbols = {bar.get("symbol") for bar in bars if bar.get("symbol") is not None}
        if symbol is None:
            if len(symbols) != 1:
                raise IndicatorError(
                    "symbol must be given explicitly when bars do not carry exactly "
                    f"one symbol; found {sorted(str(item) for item in symbols)}"
                )
            symbol = str(next(iter(symbols)))
        elif symbols and symbols != {symbol}:
            raise IndicatorError(
                f"bars contain symbols {sorted(str(item) for item in symbols)}, "
                f"which does not match the requested symbol {symbol!r}"
            )

        statuses = {
            str(bar["adjustment_status"])
            for bar in bars
            if bar.get("adjustment_status") is not None
        }
        adjustment_status = statuses.pop() if len(statuses) == 1 else "mixed_or_unknown"

        return cls(
            symbol=symbol,
            trading_dates=tuple(
                _parse_date(bar["trading_date"], "trading_date") for bar in bars
            ),
            open=[float(bar["open"]) for bar in bars],
            high=[float(bar["high"]) for bar in bars],
            low=[float(bar["low"]) for bar in bars],
            close=[float(bar["close"]) for bar in bars],
            volume=[float(bar["volume"]) for bar in bars],
            adjustment_status=adjustment_status,
        )


@dataclass(frozen=True, slots=True, eq=False)
class BenchmarkSeries:
    """A comparison series for relative strength (VN-Index or a sector index).

    Held separately from `OHLCVSeries` because a benchmark only needs a
    close, and because its trading calendar may differ from the security's;
    `relative_strength.py` aligns the two by trading date rather than by
    position.
    """

    code: str
    trading_dates: tuple[date, ...]
    close: np.ndarray
    name: str | None = None

    def __post_init__(self) -> None:
        setattr_ = object.__setattr__
        setattr_(self, "trading_dates", tuple(self.trading_dates))
        setattr_(self, "close", _readonly_float_array(self.close, "close"))
        if len(self.close) != len(self.trading_dates):
            raise IndicatorError(
                f"close has {len(self.close)} values but there are "
                f"{len(self.trading_dates)} trading dates"
            )
        for earlier, later in zip(self.trading_dates, self.trading_dates[1:]):
            if later <= earlier:
                raise IndicatorError("trading_dates must be strictly increasing")

    def __len__(self) -> int:
        return len(self.trading_dates)

    @classmethod
    def from_ohlcv(cls, series: OHLCVSeries, *, code: str | None = None) -> BenchmarkSeries:
        return cls(
            code=code or series.symbol,
            trading_dates=series.trading_dates,
            close=series.close,
        )


@dataclass(frozen=True, slots=True)
class Tolerance:
    """Section 14: "Numerical tolerance" documented per indicator.

    `absolute` and `relative` are the two arms of a numpy-style
    `abs(a - b) <= absolute + relative * abs(b)` comparison. `basis` records
    what the tolerance is a tolerance *against*, since a tolerance is
    meaningless without naming the reference it applies to.
    """

    absolute: float
    relative: float
    basis: str


@dataclass(frozen=True, slots=True)
class IndicatorSpec:
    """Registry entry and the Section 14 documentation record for one indicator.

    The seven Section 14 attributes map one-to-one onto `formula`,
    `input_price`, `adjustment_convention`, `warm_up`, `missing_value_behavior`,
    `comparison_reference`, and `tolerance`.
    """

    indicator_id: str
    title: str
    block: str
    outputs: tuple[str, ...]
    parameters: Mapping[str, Any]
    formula: str
    input_price: str
    adjustment_convention: str
    warm_up: str
    missing_value_behavior: str
    comparison_reference: str
    tolerance: Tolerance
    warm_up_bars: Callable[..., int]
    scalar_outputs: tuple[str, ...] = ()
    requires_benchmark: bool = False

    def resolved_parameters(self, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Merge caller overrides onto the documented defaults.

        Unknown parameter names are rejected rather than ignored, so a typo
        in a strategy definition surfaces immediately instead of silently
        running the indicator at its default setting.
        """

        resolved = dict(self.parameters)
        for key, value in (overrides or {}).items():
            if key not in resolved:
                raise IndicatorError(
                    f"{self.indicator_id} has no parameter {key!r}; "
                    f"known parameters are {sorted(resolved)}"
                )
            resolved[key] = value
        return resolved


@dataclass(frozen=True, slots=True, eq=False)
class IndicatorResult:
    """Output of one indicator run.

    `series` holds one full-length float64 array per output name, NaN where
    the value is undefined (warm-up or a propagated gap). `scalars` holds
    values that are not per-bar, such as a maximum drawdown or a
    volume-at-price concentration summary.
    """

    indicator_id: str
    parameters: Mapping[str, Any]
    series: Mapping[str, np.ndarray]
    scalars: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", dict(self.parameters))
        frozen_series: dict[str, np.ndarray] = {}
        for name, values in self.series.items():
            array = np.asarray(values, dtype=np.float64)
            array = array if not array.flags.writeable else array.view()
            array.setflags(write=False)
            frozen_series[name] = array
        object.__setattr__(self, "series", frozen_series)
        object.__setattr__(self, "scalars", dict(self.scalars))

    def __getitem__(self, output: str) -> np.ndarray:
        try:
            return self.series[output]
        except KeyError as error:
            raise IndicatorError(
                f"{self.indicator_id} has no output {output!r}; "
                f"available outputs are {sorted(self.series)}"
            ) from error

    def last(self, output: str) -> float:
        """Most recent value of `output`, NaN if the series ends undefined."""

        values = self[output]
        return float(values[-1]) if len(values) else float("nan")
