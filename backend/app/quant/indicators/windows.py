"""Numeric primitives shared by the indicators.

Two families of primitive appear throughout Section 14's indicator list,
and each has a different, explicitly documented missing-value rule. Both
rules are deliberately conservative: a missing bar is never imputed,
interpolated, or forward-filled, because a research terminal that silently
invents a price is worse than one that reports "undefined here".

**Windowed primitives** (`rolling_mean`, `rolling_std`, `rolling_max`,
`rolling_min`, `rolling_sum`, `rolling_median`). Output at index `i` is
defined only when the full window `[i - window + 1, i]` exists and contains
no NaN. Any NaN inside the window makes that one output NaN; the indicator
recovers automatically once the gap falls out of the window, so a single
missing bar costs exactly `window` outputs.

**Recursive primitives** (`exponential_moving_average`, `wilder_smoothing`).
These have infinite memory, so a naive implementation would let one missing
bar poison every later value. The rule here is "gap re-seed": the input is
split into maximal runs of consecutive non-NaN values, each run is seeded
independently with a simple mean of its first `period` values, and the
recursion runs only inside the run. A gap therefore costs one full warm-up
period and nothing more, and no value is ever computed across a gap as
though the gap were not there.

**Cumulative primitives** (`cumulative_with_gaps`). On-balance volume, the
accumulation/distribution line, and volume-price trend are all cumulative
sums whose origin is arbitrary. A bar whose contribution is undefined
yields NaN at that index and contributes zero to the running total, so the
series resumes at the same level rather than restarting at an unrelated
origin. This is the one place where a missing bar is treated as "no
information" rather than "unknown information"; it is safe only because the
level of these three series has no absolute meaning, and it is called out
in each indicator's `missing_value_behavior`.
"""

from __future__ import annotations

import numpy as np

from .types import IndicatorError


def validate_window(window: int, name: str = "window") -> int:
    if not isinstance(window, (int, np.integer)) or isinstance(window, bool):
        raise IndicatorError(f"{name} must be an integer, got {window!r}")
    window = int(window)
    if window < 1:
        raise IndicatorError(f"{name} must be >= 1, got {window}")
    return window


def _sliding(values: np.ndarray, window: int) -> np.ndarray | None:
    """Read-only sliding window view, or None when the series is too short."""

    if len(values) < window:
        return None
    return np.lib.stride_tricks.sliding_window_view(values, window)


def _rolling_reduce(values: np.ndarray, window: int, reducer) -> np.ndarray:
    window = validate_window(window)
    values = np.asarray(values, dtype=np.float64)
    out = np.full(len(values), np.nan, dtype=np.float64)
    view = _sliding(values, window)
    if view is None:
        return out
    out[window - 1 :] = reducer(view, axis=1)
    return out


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    return _rolling_reduce(values, window, np.mean)


def rolling_sum(values: np.ndarray, window: int) -> np.ndarray:
    return _rolling_reduce(values, window, np.sum)


def rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    return _rolling_reduce(values, window, np.max)


def rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    return _rolling_reduce(values, window, np.min)


def rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    return _rolling_reduce(values, window, np.median)


def rolling_std(values: np.ndarray, window: int, *, ddof: int = 0) -> np.ndarray:
    """Rolling standard deviation.

    `ddof=0` (population) is the default because Bollinger Bands as
    originally published use the population standard deviation, and because
    it is the convention AmiBroker's `StDev` uses. Callers wanting the
    sample standard deviation pass `ddof=1`; the choice is recorded in each
    consuming indicator's documented formula.
    """

    window = validate_window(window)
    if ddof >= window:
        raise IndicatorError(f"ddof={ddof} is not valid for window={window}")
    return _rolling_reduce(values, window, lambda view, axis: np.std(view, axis=axis, ddof=ddof))


def valid_runs(values: np.ndarray) -> list[tuple[int, int]]:
    """Maximal `[start, stop)` index ranges over which `values` is non-NaN."""

    finite = np.isfinite(np.asarray(values, dtype=np.float64))
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, is_finite in enumerate(finite):
        if is_finite and start is None:
            start = index
        elif not is_finite and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(finite)))
    return runs


def exponential_moving_average(
    values: np.ndarray,
    period: int,
    *,
    smoothing: float = 2.0,
) -> np.ndarray:
    """EMA with an SMA seed and the gap re-seed rule.

    alpha = smoothing / (period + 1); the first output of each run is the
    simple mean of that run's first `period` values, placed at the run's
    `period`-th bar, and thereafter
    `ema[i] = alpha * value[i] + (1 - alpha) * ema[i - 1]`.

    Seeding with an SMA rather than with the first observation is the
    convention used by AmiBroker's `EMA` and by most charting packages, and
    it removes the dependence on how much history the caller happened to
    load.
    """

    period = validate_window(period, "period")
    if smoothing <= 0:
        raise IndicatorError(f"smoothing must be > 0, got {smoothing}")
    values = np.asarray(values, dtype=np.float64)
    out = np.full(len(values), np.nan, dtype=np.float64)
    alpha = smoothing / (period + 1.0)

    for start, stop in valid_runs(values):
        if stop - start < period:
            continue
        seed_index = start + period - 1
        current = float(np.mean(values[start : seed_index + 1]))
        out[seed_index] = current
        for index in range(seed_index + 1, stop):
            current = alpha * float(values[index]) + (1.0 - alpha) * current
            out[index] = current
    return out


def wilder_smoothing(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (a.k.a. RMA, or EMA with alpha = 1 / period).

    Wilder's original recursion is `s[i] = s[i-1] + (x[i] - s[i-1]) / period`
    seeded with the simple mean of the first `period` values. It is
    implemented separately from `exponential_moving_average` rather than as
    `smoothing=1.0` so that the seeding and the alpha are visibly Wilder's
    in the code that RSI and ATR read.
    """

    period = validate_window(period, "period")
    values = np.asarray(values, dtype=np.float64)
    out = np.full(len(values), np.nan, dtype=np.float64)

    for start, stop in valid_runs(values):
        if stop - start < period:
            continue
        seed_index = start + period - 1
        current = float(np.mean(values[start : seed_index + 1]))
        out[seed_index] = current
        for index in range(seed_index + 1, stop):
            current = current + (float(values[index]) - current) / period
            out[index] = current
    return out


def cumulative_with_gaps(contributions: np.ndarray, *, start_value: float = 0.0) -> np.ndarray:
    """Running total that skips, rather than propagates, undefined bars.

    Output is NaN wherever `contributions` is NaN; elsewhere it is
    `start_value` plus the sum of every defined contribution up to and
    including that bar.
    """

    contributions = np.asarray(contributions, dtype=np.float64)
    out = np.full(len(contributions), np.nan, dtype=np.float64)
    total = float(start_value)
    for index, contribution in enumerate(contributions):
        if not np.isfinite(contribution):
            continue
        total += float(contribution)
        out[index] = total
    return out


def previous(values: np.ndarray) -> np.ndarray:
    """`values` shifted forward one bar, with NaN in the first position."""

    values = np.asarray(values, dtype=np.float64)
    out = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) > 1:
        out[1:] = values[:-1]
    return out


def safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Element-wise division where a zero denominator yields NaN, not inf.

    Every ratio in this package uses this helper so that a degenerate bar
    (a zero previous close, a zero-range bar, a window with no down-volume)
    produces an honestly undefined value rather than an infinity that would
    silently survive into a strategy comparison.
    """

    numerator = np.asarray(numerator, dtype=np.float64)
    denominator = np.asarray(denominator, dtype=np.float64)
    out = np.full(np.broadcast(numerator, denominator).shape, np.nan, dtype=np.float64)
    usable = np.isfinite(numerator) & np.isfinite(denominator) & (denominator != 0.0)
    np.divide(numerator, denominator, out=out, where=usable)
    return out
