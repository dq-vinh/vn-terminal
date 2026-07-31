"""Input and output types for the WP6 strategy registry.

The central design decision in this module is `AsOfWindow`. Section 16 makes
"No future bars" a mandatory bias control, and the WP8 acceptance criterion
is "No look-ahead". Those are properties of the code, so they are enforced by
the shape of the code rather than by reviewer discipline: a strategy is never
handed the full history plus an index it is trusted to respect. It is handed
a window that physically refuses to return anything after bar `t`.

Every accessor takes a non-negative `lag` counted backwards from `t`. A
negative lag raises `LookAheadError`. There is no accessor that takes an
absolute index, and no attribute that exposes the underlying arrays, so a
strategy cannot reach past `t` even by accident.

Execution is deliberately not the strategy's job. A strategy observes bar `t`
and *schedules* an order; the caller (the screener for point-in-time
evaluation, the backtester for simulation) executes it against a later bar.
That separation is what makes "evaluate at `t`, execute at `t+1`" checkable
rather than assumed.

Purity: nothing in this package opens a file, a socket, or a database
connection, reads the clock, reads the environment, or draws a random
number. `tests/quant/test_strategy_purity.py` enforces this statically and at
runtime, in the same way `tests/quant/test_purity.py` does for WP5.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import numpy as np


class StrategyError(ValueError):
    """Raised for malformed strategy input, parameters, or registration."""


class LookAheadError(StrategyError):
    """Raised when a caller asks a window for data at or after a future bar.

    This is not a defensive nicety. Section 16 lists "No future bars" first
    among the mandatory bias controls, and this exception is the mechanism
    that makes the control enforceable. It is deliberately a hard error
    rather than a returned NaN, so a look-ahead bug fails a test loudly
    instead of quietly producing a slightly optimistic equity curve.
    """


class InsufficientHistory(StrategyError):
    """Raised when a window cannot supply the number of bars requested.

    Distinct from `LookAheadError`: this one means the history is too short
    at its *old* end, which is a warm-up condition and a legitimate
    `unavailable` result, not a bias defect.
    """


class Signal(str, Enum):
    """Signal vocabulary.

    OPEN ITEM in `contracts/OPEN_ITEMS.md` records that the plan evidences
    only `watch` for `StrategyEvaluationResult.signal`. These five values are
    not invented here: they are taken verbatim from the "Signal
    classification" table of the approved `dual_sma_trend_crossover`
    specification in `docs/strategy_catalogue.md`. A strategy whose approved
    specification defines a different vocabulary would need its own type and
    a contract-change proposal; see `HANDOFF_WP6_WP7_WP8.md`.
    """

    UNAVAILABLE = "unavailable"
    ENTRY = "entry"
    ENTRY_BLOCKED = "entry_blocked"
    EXIT = "exit"
    NONE = "none"


class OrderStatus(str, Enum):
    """Order-status vocabulary, verbatim from the approved specification."""

    NONE = "none"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    PENDING_EXIT = "pending_exit"


class PositionState(str, Enum):
    """Whether the caller currently holds a position in this symbol.

    Supplied *to* the strategy rather than tracked inside it. A strategy is a
    pure function of (window, position state, parameters); the caller owns
    portfolio state. The screener evaluates from `FLAT`, which is the correct
    semantic for "what would I do about this symbol today"; the backtester
    supplies the simulated state.
    """

    FLAT = "flat"
    LONG = "long"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class SecurityView:
    """Point-in-time security-master facts for one symbol on one date.

    Deliberately a separate object from the bar history. `as_of_date` is
    carried so that a caller resolving a `valid_from`/`valid_to` interval has
    to state which date it resolved for, which is what makes the
    classification point-in-time rather than "whatever the master says
    today". A backtest that reused today's listing status for a 2015 bar
    would be a survivorship defect; `SecurityView.as_of_date` is the field a
    test can assert against.

    `trading_status`, `security_type`, and `exchange` are carried verbatim
    from the data layer. Nothing here normalizes, maps, or guesses them. The
    data handoff (`backend/app/data/HANDOFF.md`, limitation 1) states that no
    authoritative security master exists yet and that every symbol currently
    carries `UNKNOWN`/`unknown`; a strategy gate against those values
    therefore fails, which is the intended and reported behavior.
    """

    symbol: str
    as_of_date: date
    exchange: str
    security_type: str
    trading_status: str
    source: str = "unspecified"

    def matches(
        self,
        *,
        exchanges: frozenset[str],
        security_types: frozenset[str],
        trading_statuses: frozenset[str],
    ) -> bool:
        return (
            self.exchange in exchanges
            and self.security_type in security_types
            and self.trading_status in trading_statuses
        )


@dataclass(frozen=True, slots=True)
class BarView:
    """One bar, as seen by a strategy. Read-only and self-describing."""

    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    quality_status: str


def _readonly(values: Sequence[float] | np.ndarray, name: str, length: int) -> np.ndarray:
    array = np.array(values, dtype=np.float64, copy=True)
    if array.ndim != 1:
        raise StrategyError(f"{name} must be one-dimensional")
    if len(array) != length:
        raise StrategyError(f"{name} has {len(array)} values but {length} trading dates")
    array.setflags(write=False)
    return array


@dataclass(frozen=True, slots=True, eq=False)
class SymbolHistory:
    """One symbol's complete daily history, loaded by the caller.

    Carries the fields the approved specification lists under
    `required_fields`, including the per-bar `quality_status` the
    specification gates on. `adjustment_status` is carried once for the whole
    series because the corporate-action-consistency control in Section 16 is
    a property of the series, not of a bar.

    This object holds the *full* history. Strategies never receive it; they
    receive `AsOfWindow` slices of it.
    """

    symbol: str
    trading_dates: tuple[date, ...]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    quality_status: tuple[str, ...]
    adjustment_status: str = "unknown"
    price_unit: str = "thousand_vnd"
    volume_unit: str = "shares"
    source: str = "unspecified"
    data_version: str = "unspecified"

    def __post_init__(self) -> None:
        set_ = object.__setattr__
        set_(self, "trading_dates", tuple(self.trading_dates))
        set_(self, "quality_status", tuple(str(item) for item in self.quality_status))
        length = len(self.trading_dates)
        if length == 0:
            raise StrategyError("a history needs at least one bar")
        for name in ("open", "high", "low", "close", "volume"):
            set_(self, name, _readonly(getattr(self, name), name, length))
        if len(self.quality_status) != length:
            raise StrategyError("quality_status length does not match trading_dates")
        for earlier, later in zip(self.trading_dates, self.trading_dates[1:]):
            if later <= earlier:
                raise StrategyError(
                    "trading_dates must be unique and strictly increasing; found "
                    f"{earlier.isoformat()} followed by {later.isoformat()}"
                )

    def __len__(self) -> int:
        return len(self.trading_dates)

    def index_of(self, trading_date: date) -> int | None:
        """Position of `trading_date`, or None when the symbol did not trade.

        A missing date is a real condition, not an error: a suspended symbol
        has no bar on a day the rest of the market traded. Section 16
        requires "Explicit handling of suspended and zero-volume securities",
        and returning None rather than the nearest neighbour is that explicit
        handling. Nothing here synthesizes a missing calendar date, which the
        approved specification prohibits.
        """

        low, high = 0, len(self.trading_dates) - 1
        while low <= high:
            middle = (low + high) // 2
            candidate = self.trading_dates[middle]
            if candidate == trading_date:
                return middle
            if candidate < trading_date:
                low = middle + 1
            else:
                high = middle - 1
        return None

    def bar(self, index: int) -> BarView:
        if index < 0 or index >= len(self.trading_dates):
            raise IndexError(f"bar index {index} out of range for {self.symbol}")
        return BarView(
            trading_date=self.trading_dates[index],
            open=float(self.open[index]),
            high=float(self.high[index]),
            low=float(self.low[index]),
            close=float(self.close[index]),
            volume=float(self.volume[index]),
            quality_status=self.quality_status[index],
        )

    def window(self, index: int) -> AsOfWindow:
        """A view of this history up to and including `index`."""

        return AsOfWindow(self, index)

    @classmethod
    def from_bars(
        cls,
        bars: Sequence[Mapping[str, Any]],
        *,
        symbol: str | None = None,
        data_version: str = "unspecified",
    ) -> SymbolHistory:
        """Build from contract-shaped `PriceBar` mappings.

        Field names are exactly those of
        `contracts/schemas/json/price_bar.schema.json`, so a caller can hand
        over `json.load(...)["bars"]` unchanged. Reading is the caller's job;
        this only parses what is already in memory.
        """

        if not bars:
            raise StrategyError("at least one bar is required")
        symbols = {str(bar["symbol"]) for bar in bars if bar.get("symbol") is not None}
        if symbol is None:
            if len(symbols) != 1:
                raise StrategyError(
                    "symbol must be given explicitly when bars do not carry exactly "
                    f"one symbol; found {sorted(symbols)}"
                )
            symbol = next(iter(symbols))
        elif symbols and symbols != {symbol}:
            raise StrategyError(f"bars carry {sorted(symbols)}, not {symbol!r}")

        statuses = {
            str(bar["adjustment_status"])
            for bar in bars
            if bar.get("adjustment_status") is not None
        }
        adjustment = statuses.pop() if len(statuses) == 1 else "mixed_or_unknown"
        sources = {str(bar["source"]) for bar in bars if bar.get("source") is not None}

        def parsed_date(value: Any) -> date:
            return value if isinstance(value, date) else date.fromisoformat(str(value))

        return cls(
            symbol=symbol,
            trading_dates=tuple(parsed_date(bar["trading_date"]) for bar in bars),
            # `__post_init__` accepts any sequence and copies it, but the
            # declared field type is an array, so the conversion happens here
            # rather than relying on the coercion for typing purposes.
            open=np.array([float(bar["open"]) for bar in bars], dtype=np.float64),
            high=np.array([float(bar["high"]) for bar in bars], dtype=np.float64),
            low=np.array([float(bar["low"]) for bar in bars], dtype=np.float64),
            close=np.array([float(bar["close"]) for bar in bars], dtype=np.float64),
            volume=np.array([float(bar["volume"]) for bar in bars], dtype=np.float64),
            quality_status=tuple(str(bar.get("quality_status", "unknown")) for bar in bars),
            adjustment_status=adjustment,
            source=sources.pop() if len(sources) == 1 else "mixed_or_unknown",
            data_version=data_version,
        )


class AsOfWindow:
    """A strategy's entire view of the world at bar `t`.

    Refuses, by construction, to return anything dated after `t`. Every
    accessor counts backwards: `lag=0` is bar `t`, `lag=1` is the previous
    chronological row, and so on. There is no forward accessor and no
    absolute-index accessor.

    `lag` is *chronological rows*, never calendar days. The approved
    specification states this explicitly: "`t-1` is the immediately preceding
    chronological daily row, not the preceding calendar date."

    `highest_index_read` records the largest underlying array index this
    window has been asked for. It exists so that
    `tests/quant/test_lookahead_adversarial.py` can assert, empirically and
    per evaluation, that a strategy never touched a bar after `t`. That test
    carries its own negative control, so the assertion cannot pass vacuously.
    """

    __slots__ = ("_highest_index_read", "_history", "_index")

    def __init__(self, history: SymbolHistory, index: int) -> None:
        if index < 0:
            raise StrategyError(f"window index must be non-negative, got {index}")
        if index >= len(history):
            raise LookAheadError(
                f"window index {index} is past the end of {history.symbol}'s "
                f"{len(history)} bars"
            )
        self._history = history
        self._index = index
        self._highest_index_read = -1

    @property
    def symbol(self) -> str:
        return self._history.symbol

    @property
    def as_of_date(self) -> date:
        return self._history.trading_dates[self._index]

    @property
    def usable_bars(self) -> int:
        """How many chronological rows exist up to and including `t`."""

        return self._index + 1

    @property
    def adjustment_status(self) -> str:
        return self._history.adjustment_status

    @property
    def price_unit(self) -> str:
        return self._history.price_unit

    @property
    def volume_unit(self) -> str:
        return self._history.volume_unit

    @property
    def data_version(self) -> str:
        return self._history.data_version

    @property
    def highest_index_read(self) -> int:
        return self._highest_index_read

    def _resolve(self, lag: int) -> int:
        if lag < 0:
            raise LookAheadError(
                f"{self._history.symbol}: a strategy asked for lag {lag}, which is bar "
                f"t+{-lag}. Section 16 forbids future bars. Evaluate at t and let the "
                "caller execute at t+1."
            )
        index = self._index - lag
        if index < 0:
            raise InsufficientHistory(
                f"{self._history.symbol}: lag {lag} needs {lag + 1} rows but only "
                f"{self.usable_bars} exist at {self.as_of_date.isoformat()}"
            )
        self._highest_index_read = max(self._highest_index_read, index)
        return index

    def bar(self, lag: int = 0) -> BarView:
        return self._history.bar(self._resolve(lag))

    def trading_date(self, lag: int = 0) -> date:
        return self._history.trading_dates[self._resolve(lag)]

    def close(self, lag: int = 0) -> float:
        return float(self._history.close[self._resolve(lag)])

    def volume(self, lag: int = 0) -> float:
        return float(self._history.volume[self._resolve(lag)])

    def quality_status(self, lag: int = 0) -> str:
        return self._history.quality_status[self._resolve(lag)]

    def closes(self, count: int, *, ending_lag: int = 0) -> tuple[float, ...]:
        """`count` closes, oldest first, ending at `t - ending_lag`."""

        return tuple(
            float(self._history.close[index])
            for index in self._span(count, ending_lag)
        )

    def volumes(self, count: int, *, ending_lag: int = 0) -> tuple[float, ...]:
        return tuple(
            float(self._history.volume[index])
            for index in self._span(count, ending_lag)
        )

    def quality_statuses(self, count: int, *, ending_lag: int = 0) -> tuple[str, ...]:
        return tuple(
            self._history.quality_status[index]
            for index in self._span(count, ending_lag)
        )

    def _span(self, count: int, ending_lag: int) -> range:
        if count <= 0:
            raise StrategyError(f"count must be positive, got {count}")
        newest = self._resolve(ending_lag)
        oldest_lag = ending_lag + count - 1
        oldest = self._resolve(oldest_lag)
        return range(oldest, newest + 1)


@dataclass(frozen=True, slots=True)
class Criterion:
    """One named, evaluated condition.

    `passed` is tri-state by way of `computable`. A criterion that could not
    be computed is neither passed nor failed, which is what lets the approved
    specification distinguish `entry_blocked` ("a gate failed") from
    `unavailable` ("the calculation could not be performed"). Collapsing the
    two would violate the specification's explicit instruction that
    "`entry_blocked` must not be used when the crossover itself is
    indeterminate."
    """

    name: str
    passed: bool
    computable: bool = True
    detail: str = ""


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """An order a strategy scheduled at `t`, for a caller to execute later.

    Carries no price. The strategy does not know, and must not know, the
    price at which the order will fill; supplying one here would be exactly
    the look-ahead the design is built to prevent.
    """

    symbol: str
    side: OrderSide
    decision_date: date
    execution_convention: str
    reason: str
    full_exit: bool = False


@dataclass(frozen=True, slots=True)
class StrategyEvaluation:
    """The full, rich result of evaluating one strategy for one symbol/date.

    This is the quant-internal result. It carries every field the approved
    specification lists under `evidence_fields`, which is roughly three times
    what the frozen `StrategyEvaluationResult` contract can hold
    (`additionalProperties: false`, twelve fields). `to_contract_result()` in
    `serialization.py` narrows it to the contract shape; the full object is
    what WP10's fact bundle should consume. A contract-change proposal is
    recorded in `HANDOFF_WP6_WP7_WP8.md` rather than applied here, since
    `contracts/**` belongs to the lead integrator.
    """

    symbol: str
    as_of_date: date
    strategy_id: str
    strategy_version: str
    signal: Signal
    position_state: PositionState
    order_status: OrderStatus
    criteria: tuple[Criterion, ...]
    evidence: Mapping[str, Any]
    warnings: tuple[str, ...] = ()
    order: OrderIntent | None = None
    data_version: str = "unspecified"
    support: tuple[float, ...] = ()
    resistance: tuple[float, ...] = ()
    invalidation: float | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "evidence", dict(self.evidence))
        object.__setattr__(self, "parameters", dict(self.parameters))

    @property
    def passed_criteria(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.criteria if item.computable and item.passed)

    @property
    def failed_criteria(self) -> tuple[str, ...]:
        return tuple(
            item.name for item in self.criteria if item.computable and not item.passed
        )

    @property
    def score(self) -> int:
        """Number of named criteria that passed.

        Decision of 31 July 2026, recorded in `HANDOFF_WP6_WP7_WP8.md`: the
        approved specification defines a `signal` vocabulary but no score,
        while the frozen contract requires integer `score`/`max_score` and
        Section 15 requires the screener to "rank using deterministic
        scores". Counting passed criteria derives the score from values the
        specification already defines, rather than inventing a weighting the
        user never approved. An uncomputable criterion counts as not passed,
        so a symbol that cannot be evaluated never outranks one that can.
        """

        return len(self.passed_criteria)

    @property
    def max_score(self) -> int:
        """Total number of criteria this strategy names.

        Constant for a given strategy and independent of the outcome, which
        is what makes scores comparable across symbols in a screener ranking.
        """

        return len(self.criteria)
