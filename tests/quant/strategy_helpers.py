"""Builders and instruments shared by the WP6, WP7, and WP8 tests.

Kept separate from the WP5 `helpers.py` so neither workstream's tests can
break the other's imports.

The interesting part of this module is `recording_history`. Most no-look-ahead
tests assert that a *result* does not change when the future changes, which is
strong evidence but indirect. `recording_history` is direct: it replaces a
history's numpy arrays and tuples with subclasses that record the highest
index anyone asked for, so a test can state the invariant literally, as "while
processing session `d`, no index above `d` was read, for any symbol, for any
purpose". `test_lookahead_adversarial.py` carries a meta-test proving the
instrument catches a deliberate cheat, so its assertions cannot pass
vacuously.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import numpy as np

from backend.app.quant.strategies import SecurityView, SymbolHistory

START = date(2024, 1, 1)


def sessions(count: int, start: date = START) -> tuple[date, ...]:
    """A synthetic session calendar: consecutive days, no weekends modeled.

    The strategy specification indexes by chronological row rather than by
    calendar date ("`t-1` is the immediately preceding chronological daily
    row, not the preceding calendar date"), so a synthetic calendar with no
    gaps tests exactly what the specification says. Gap behavior is tested
    separately by removing rows.
    """

    return tuple(start + timedelta(days=offset) for offset in range(count))


def make_history(
    *,
    symbol: str = "TEST",
    closes: Sequence[float],
    volumes: Sequence[float] | None = None,
    opens: Sequence[float] | None = None,
    quality: Sequence[str] | None = None,
    dates: Sequence[date] | None = None,
    adjustment_status: str = "back_adjusted",
    data_version: str = "fdata-2026-07-30",
) -> SymbolHistory:
    count = len(closes)
    resolved_dates = tuple(dates) if dates is not None else sessions(count)
    resolved_volumes = list(volumes) if volumes is not None else [1_000_000.0] * count
    resolved_opens = list(opens) if opens is not None else list(closes)
    return SymbolHistory(
        symbol=symbol,
        trading_dates=resolved_dates,
        open=resolved_opens,
        high=[value + 1.0 for value in closes],
        low=[value - 1.0 for value in closes],
        close=list(closes),
        volume=resolved_volumes,
        quality_status=tuple(quality) if quality is not None else ("valid",) * count,
        adjustment_status=adjustment_status,
        data_version=data_version,
    )


def crossover_closes(count: int = 120, *, trough: int = 60) -> list[float]:
    """A V-shaped close series producing one clean bullish crossover.

    Falling then rising, so the fast SMA crosses the slow SMA upward exactly
    once well after warm-up. Deterministic and hand-checkable; it makes no
    market claim.
    """

    return [
        100.0 - 0.5 * index if index < trough else 100.0 - 0.5 * trough + 1.5 * (index - trough)
        for index in range(count)
    ]


def round_trip_closes(count: int = 160) -> list[float]:
    """Falls, rises, then falls again: one bullish and one bearish crossover."""

    values: list[float] = []
    for index in range(count):
        if index < 40:
            values.append(100.0 - 0.4 * index)
        elif index < 100:
            values.append(84.0 + 1.2 * (index - 40))
        else:
            values.append(156.0 - 1.2 * (index - 100))
    return [max(1.0, value) for value in values]


def active_equity(symbol: str = "TEST") -> Any:
    def resolver(requested: str, day: date) -> SecurityView:
        return SecurityView(
            symbol=requested,
            as_of_date=day,
            exchange="HOSE",
            security_type="ordinary_equity",
            trading_status="active",
        )

    return resolver


def security_view(symbol: str, day: date) -> SecurityView:
    return SecurityView(
        symbol=symbol,
        as_of_date=day,
        exchange="HOSE",
        security_type="ordinary_equity",
        trading_status="active",
    )


def corrupt_after(history: SymbolHistory, index: int) -> SymbolHistory:
    """A copy whose bars strictly after `index` are replaced with garbage.

    The corruption is deliberately violent and varied: prices are scaled by a
    large factor and sign-flipped in places, volumes are zeroed, and quality
    statuses are invalidated. Anything that reads a future bar for any purpose
    will produce a different answer. Bars up to and including `index` are
    untouched, so a correct implementation produces a bit-identical result.
    """

    closes = list(history.close)
    opens = list(history.open)
    volumes = list(history.volume)
    quality = list(history.quality_status)
    for position in range(index + 1, len(history)):
        closes[position] = 10_000.0 + 137.0 * position
        opens[position] = 9_999.0 - 41.0 * position
        volumes[position] = 0.0
        quality[position] = "critical"
    return SymbolHistory(
        symbol=history.symbol,
        trading_dates=history.trading_dates,
        open=opens,
        high=[value + 1.0 for value in closes],
        low=[value - 1.0 for value in closes],
        close=closes,
        volume=volumes,
        quality_status=tuple(quality),
        adjustment_status=history.adjustment_status,
        data_version=history.data_version,
    )


def truncate(history: SymbolHistory, index: int) -> SymbolHistory:
    """A copy containing only bars up to and including `index`."""

    stop = index + 1
    return SymbolHistory(
        symbol=history.symbol,
        trading_dates=history.trading_dates[:stop],
        open=list(history.open[:stop]),
        high=list(history.high[:stop]),
        low=list(history.low[:stop]),
        close=list(history.close[:stop]),
        volume=list(history.volume[:stop]),
        quality_status=history.quality_status[:stop],
        adjustment_status=history.adjustment_status,
        data_version=history.data_version,
    )


class _Ledger:
    """Shared record of the highest index anyone asked any array for."""

    def __init__(self) -> None:
        self.highest = -1

    def note(self, index: Any) -> None:
        if isinstance(index, (int, np.integer)) and int(index) > self.highest:
            self.highest = int(index)
        elif isinstance(index, slice):
            stop = index.stop
            if isinstance(stop, (int, np.integer)) and int(stop) - 1 > self.highest:
                self.highest = int(stop) - 1


class RecordingArray(np.ndarray):
    """A float array that records the highest index read from it."""

    def __new__(cls, values: np.ndarray, ledger: _Ledger) -> RecordingArray:  # noqa: PYI034
        obj = np.asarray(values, dtype=np.float64).view(cls)
        obj._ledger = ledger  # type: ignore[attr-defined]
        return obj

    def __array_finalize__(self, obj: Any) -> None:
        if obj is not None:
            self._ledger = getattr(obj, "_ledger", None)

    def __getitem__(self, item: Any) -> Any:
        ledger = getattr(self, "_ledger", None)
        if ledger is not None:
            ledger.note(item)
        return super().__getitem__(item)


class RecordingTuple(tuple):
    """A tuple that records the highest index read from it."""

    _ledger: _Ledger

    def __new__(cls, values: Sequence[Any], ledger: _Ledger) -> RecordingTuple:  # noqa: PYI034
        obj = super().__new__(cls, values)
        obj._ledger = ledger
        return obj

    def __getitem__(self, item: Any) -> Any:
        self._ledger.note(item)
        return super().__getitem__(item)


def recording_history(history: SymbolHistory) -> tuple[SymbolHistory, _Ledger]:
    """A history that reports the highest bar index anything reads from it.

    The returned history behaves identically to the original. Its arrays and
    its `quality_status` tuple are instrumented; `trading_dates` is left as a
    plain tuple because the engine builds a date-to-index map from it once, up
    front, which is not a bar read.
    """

    ledger = _Ledger()
    instrumented = SymbolHistory(
        symbol=history.symbol,
        trading_dates=history.trading_dates,
        open=list(history.open),
        high=list(history.high),
        low=list(history.low),
        close=list(history.close),
        volume=list(history.volume),
        quality_status=history.quality_status,
        adjustment_status=history.adjustment_status,
        data_version=history.data_version,
    )
    for name in ("open", "high", "low", "close", "volume"):
        object.__setattr__(
            instrumented, name, RecordingArray(getattr(instrumented, name), ledger)
        )
    object.__setattr__(
        instrumented, "quality_status", RecordingTuple(instrumented.quality_status, ledger)
    )
    return instrumented, ledger


def comparable(evaluation: Any) -> dict[str, Any]:
    """A hashable, comparable projection of a `StrategyEvaluation`.

    Includes the full evidence, so a difference anywhere in the reported
    facts, not merely in the signal, fails an invariance test.
    """

    return {
        "signal": evaluation.signal.value,
        "order_status": evaluation.order_status.value,
        "score": evaluation.score,
        "max_score": evaluation.max_score,
        "passed": list(evaluation.passed_criteria),
        "failed": list(evaluation.failed_criteria),
        "warnings": list(evaluation.warnings),
        "evidence": {
            key: (
                None
                if isinstance(value, float) and math.isnan(value)
                else value
            )
            for key, value in sorted(evaluation.evidence.items())
        },
        "order": None if evaluation.order is None else evaluation.order.reason,
    }
