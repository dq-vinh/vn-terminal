"""Independent reference implementations of every Section 14 indicator.

These exist to satisfy the Section 14 acceptance criterion, "Results match
an independent reference or AmiBroker export within a documented tolerance."
No AmiBroker export has been supplied to this workstream, so the primary
reference is this module plus the hand-computed cases in the test files.

To be worth anything as a reference, this code is written to be obviously
correct rather than fast or elegant, and to share nothing with the
implementation under test:

- plain Python lists and floats, no numpy, no sliding-window views, no
  vectorization,
- the textbook formula transcribed literally, including the O(n * window)
  recomputation of every window from scratch,
- no import from `backend.app.quant.indicators` except the types needed to
  read a series, so a bug in `windows.py` cannot hide itself here.

The known and deliberate exception is that the reference reproduces the same
documented *conventions* as the implementation (SMA-seeded EMA, gap re-seed,
population standard deviation, zero multiplier on a zero-range bar). A
reference cannot detect a wrong convention, only a wrong implementation of
the chosen one; the conventions themselves are argued in each indicator's
`comparison_reference` text and in NUMERICS.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

NAN = float("nan")


def _defined(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def _window(values: Sequence[float], index: int, window: int) -> list[float] | None:
    """The `window` values ending at `index`, or None if unusable."""

    start = index - window + 1
    if start < 0:
        return None
    chunk = [float(values[position]) for position in range(start, index + 1)]
    if any(not _defined(value) for value in chunk):
        return None
    return chunk


def sma(values: Sequence[float], window: int) -> list[float]:
    out = []
    for index in range(len(values)):
        chunk = _window(values, index, window)
        out.append(NAN if chunk is None else sum(chunk) / len(chunk))
    return out


def rolling_max(values: Sequence[float], window: int) -> list[float]:
    out = []
    for index in range(len(values)):
        chunk = _window(values, index, window)
        out.append(NAN if chunk is None else max(chunk))
    return out


def rolling_min(values: Sequence[float], window: int) -> list[float]:
    out = []
    for index in range(len(values)):
        chunk = _window(values, index, window)
        out.append(NAN if chunk is None else min(chunk))
    return out


def rolling_sum(values: Sequence[float], window: int) -> list[float]:
    out = []
    for index in range(len(values)):
        chunk = _window(values, index, window)
        out.append(NAN if chunk is None else sum(chunk))
    return out


def rolling_median(values: Sequence[float], window: int) -> list[float]:
    out = []
    for index in range(len(values)):
        chunk = _window(values, index, window)
        if chunk is None:
            out.append(NAN)
            continue
        ordered = sorted(chunk)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            out.append(ordered[middle])
        else:
            out.append((ordered[middle - 1] + ordered[middle]) / 2.0)
    return out


def rolling_std(values: Sequence[float], window: int, ddof: int = 0) -> list[float]:
    out = []
    for index in range(len(values)):
        chunk = _window(values, index, window)
        if chunk is None:
            out.append(NAN)
            continue
        mean = sum(chunk) / len(chunk)
        squared = sum((value - mean) ** 2 for value in chunk)
        out.append(math.sqrt(squared / (len(chunk) - ddof)))
    return out


def runs(values: Sequence[float]) -> list[tuple[int, int]]:
    found = []
    start = None
    for index, value in enumerate(values):
        if _defined(float(value)):
            if start is None:
                start = index
        elif start is not None:
            found.append((start, index))
            start = None
    if start is not None:
        found.append((start, len(values)))
    return found


def ema(values: Sequence[float], period: int) -> list[float]:
    out = [NAN] * len(values)
    alpha = 2.0 / (period + 1.0)
    for start, stop in runs(values):
        if stop - start < period:
            continue
        seed = start + period - 1
        current = sum(float(values[position]) for position in range(start, seed + 1)) / period
        out[seed] = current
        for index in range(seed + 1, stop):
            current = alpha * float(values[index]) + (1.0 - alpha) * current
            out[index] = current
    return out


def wilder(values: Sequence[float], period: int) -> list[float]:
    out = [NAN] * len(values)
    for start, stop in runs(values):
        if stop - start < period:
            continue
        seed = start + period - 1
        current = sum(float(values[position]) for position in range(start, seed + 1)) / period
        out[seed] = current
        for index in range(seed + 1, stop):
            current = current + (float(values[index]) - current) / period
            out[index] = current
    return out


def rsi(close: Sequence[float], period: int) -> list[float]:
    gains: list[float] = [NAN]
    losses: list[float] = [NAN]
    for index in range(1, len(close)):
        earlier = float(close[index - 1])
        later = float(close[index])
        if not _defined(earlier) or not _defined(later):
            gains.append(NAN)
            losses.append(NAN)
            continue
        change = later - earlier
        gains.append(change if change > 0 else 0.0)
        losses.append(-change if change < 0 else 0.0)

    average_gain = wilder(gains, period)
    average_loss = wilder(losses, period)
    out = []
    for gain, loss in zip(average_gain, average_loss):
        if not _defined(gain) or not _defined(loss) or (gain + loss) == 0.0:
            out.append(NAN)
        else:
            out.append(100.0 * gain / (gain + loss))
    return out


def true_range(
    high: Sequence[float], low: Sequence[float], close: Sequence[float]
) -> list[float]:
    out = [NAN]
    for index in range(1, len(close)):
        previous_close = float(close[index - 1])
        current_high = float(high[index])
        current_low = float(low[index])
        if not all(_defined(value) for value in (previous_close, current_high, current_low)):
            out.append(NAN)
            continue
        out.append(
            max(
                current_high - current_low,
                abs(current_high - previous_close),
                abs(current_low - previous_close),
            )
        )
    return out


def atr(
    high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int
) -> list[float]:
    return wilder(true_range(high, low, close), period)


def bollinger(
    close: Sequence[float], period: int, num_std: float
) -> tuple[list[float], list[float], list[float]]:
    middle = sma(close, period)
    sigma = rolling_std(close, period, ddof=0)
    upper = [
        m + num_std * s if _defined(m) and _defined(s) else NAN for m, s in zip(middle, sigma)
    ]
    lower = [
        m - num_std * s if _defined(m) and _defined(s) else NAN for m, s in zip(middle, sigma)
    ]
    return middle, upper, lower


def rate_of_change(close: Sequence[float], period: int) -> list[float]:
    out = []
    for index in range(len(close)):
        if index < period:
            out.append(NAN)
            continue
        earlier = float(close[index - period])
        later = float(close[index])
        if not _defined(earlier) or not _defined(later) or earlier == 0.0:
            out.append(NAN)
        else:
            out.append(100.0 * (later / earlier - 1.0))
    return out


def rolling_volatility(
    close: Sequence[float], period: int, trading_days: int
) -> tuple[list[float], list[float]]:
    log_returns: list[float] = [NAN]
    for index in range(1, len(close)):
        earlier = float(close[index - 1])
        later = float(close[index])
        if not _defined(earlier) or not _defined(later) or earlier <= 0.0 or later <= 0.0:
            log_returns.append(NAN)
        else:
            log_returns.append(math.log(later / earlier))
    daily = rolling_std(log_returns, period, ddof=1)
    annual = [
        100.0 * value * math.sqrt(trading_days) if _defined(value) else NAN for value in daily
    ]
    return annual, daily


def drawdown(close: Sequence[float]) -> tuple[list[float], list[float]]:
    peaks: list[float] = []
    values: list[float] = []
    running = NAN
    for value in close:
        current = float(value)
        if _defined(current):
            running = current if not _defined(running) else max(running, current)
            peaks.append(running)
            values.append(100.0 * (current / running - 1.0) if running != 0.0 else NAN)
        else:
            peaks.append(NAN)
            values.append(NAN)
    return values, peaks


def volume_price_trend(close: Sequence[float], volume: Sequence[float]) -> list[float]:
    out = []
    total = 0.0
    for index in range(len(close)):
        if index == 0:
            out.append(NAN)
            continue
        earlier = float(close[index - 1])
        later = float(close[index])
        traded = float(volume[index])
        if not all(_defined(value) for value in (earlier, later, traded)) or earlier == 0.0:
            out.append(NAN)
            continue
        total += traded * (later - earlier) / earlier
        out.append(total)
    return out


def accumulation_distribution(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
) -> list[float]:
    out = []
    total = 0.0
    for index in range(len(close)):
        current_high = float(high[index])
        current_low = float(low[index])
        current_close = float(close[index])
        traded = float(volume[index])
        if not all(
            _defined(value)
            for value in (current_high, current_low, current_close, traded)
        ):
            out.append(NAN)
            continue
        span = current_high - current_low
        if span == 0.0:
            multiplier = 0.0
        else:
            multiplier = ((current_close - current_low) - (current_high - current_close)) / span
        total += multiplier * traded
        out.append(total)
    return out


def on_balance_volume(close: Sequence[float], volume: Sequence[float]) -> list[float]:
    out = []
    total = 0.0
    for index in range(len(close)):
        if index == 0:
            out.append(NAN)
            continue
        earlier = float(close[index - 1])
        later = float(close[index])
        traded = float(volume[index])
        if not all(_defined(value) for value in (earlier, later, traded)):
            out.append(NAN)
            continue
        if later > earlier:
            total += traded
        elif later < earlier:
            total -= traded
        out.append(total)
    return out


def up_down_volume(
    close: Sequence[float], volume: Sequence[float], window: int
) -> tuple[list[float], list[float]]:
    up: list[float] = [NAN]
    down: list[float] = [NAN]
    for index in range(1, len(close)):
        earlier = float(close[index - 1])
        later = float(close[index])
        traded = float(volume[index])
        if not all(_defined(value) for value in (earlier, later, traded)):
            up.append(NAN)
            down.append(NAN)
            continue
        up.append(traded if later > earlier else 0.0)
        down.append(traded if later < earlier else 0.0)
    return rolling_sum(up, window), rolling_sum(down, window)


def unusual_volume(
    volume: Sequence[float], window: int, multiple: float
) -> tuple[list[float], list[float]]:
    medians = rolling_median(volume, window)
    baseline = [NAN] + medians[:-1]
    ratio = []
    flag = []
    for index in range(len(volume)):
        traded = float(volume[index])
        base = baseline[index]
        if not _defined(traded) or not _defined(base) or base == 0.0:
            ratio.append(NAN)
            flag.append(NAN)
        else:
            value = traded / base
            ratio.append(value)
            flag.append(1.0 if value >= multiple else 0.0)
    return flag, ratio


def pivot_levels(
    high: Sequence[float], low: Sequence[float], close: Sequence[float]
) -> dict[str, list[float]]:
    names = ("pivot", "r1", "r2", "r3", "s1", "s2", "s3")
    out: dict[str, list[float]] = {name: [] for name in names}
    for index in range(len(close)):
        if index == 0:
            for name in names:
                out[name].append(NAN)
            continue
        previous_high = float(high[index - 1])
        previous_low = float(low[index - 1])
        previous_close = float(close[index - 1])
        if not all(
            _defined(value) for value in (previous_high, previous_low, previous_close)
        ):
            for name in names:
                out[name].append(NAN)
            continue
        pivot = (previous_high + previous_low + previous_close) / 3.0
        out["pivot"].append(pivot)
        out["r1"].append(2.0 * pivot - previous_low)
        out["r2"].append(pivot + (previous_high - previous_low))
        out["r3"].append(previous_high + 2.0 * (pivot - previous_low))
        out["s1"].append(2.0 * pivot - previous_high)
        out["s2"].append(pivot - (previous_high - previous_low))
        out["s3"].append(previous_low - 2.0 * (previous_high - pivot))
    return out


def relative_strength(
    close: Sequence[float],
    benchmark_close: Sequence[float],
    period: int,
    mansfield_period: int,
) -> dict[str, list[float]]:
    ratio = []
    for own, other in zip(close, benchmark_close):
        own_value = float(own)
        other_value = float(other)
        if not _defined(own_value) or not _defined(other_value) or other_value == 0.0:
            ratio.append(NAN)
        else:
            ratio.append(100.0 * own_value / other_value)

    ratio_average = sma(ratio, mansfield_period)
    mansfield = [
        100.0 * (value / average - 1.0)
        if _defined(value) and _defined(average) and average != 0.0
        else NAN
        for value, average in zip(ratio, ratio_average)
    ]
    own_roc = rate_of_change(close, period)
    other_roc = rate_of_change(benchmark_close, period)
    excess = [
        a - b if _defined(a) and _defined(b) else NAN for a, b in zip(own_roc, other_roc)
    ]
    return {
        "ratio": ratio,
        "roc": rate_of_change(ratio, period),
        "excess_return_pct": excess,
        "mansfield": mansfield,
    }


def volume_at_price(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
    lookback: int,
    bins: int,
) -> dict[str, object]:
    start = max(0, len(close) - lookback)
    typical = []
    traded = []
    for index in range(start, len(close)):
        current = [float(high[index]), float(low[index]), float(close[index])]
        current_volume = float(volume[index])
        if not all(_defined(value) for value in current) or not _defined(current_volume):
            continue
        typical.append(sum(current) / 3.0)
        traded.append(current_volume)

    window_low = min(
        float(low[index]) for index in range(start, len(low)) if _defined(float(low[index]))
    )
    window_high = max(
        float(high[index]) for index in range(start, len(high)) if _defined(float(high[index]))
    )
    width = (window_high - window_low) / bins
    histogram = [0.0] * bins
    for price, current_volume in zip(typical, traded):
        position = int(math.floor((price - window_low) / width))
        position = min(max(position, 0), bins - 1)
        histogram[position] += current_volume

    total = sum(histogram)
    shares = [value / total for value in histogram]
    return {
        "bin_volume": histogram,
        "bin_volume_share": shares,
        "herfindahl": sum(share**2 for share in shares),
        "point_of_control_index": histogram.index(max(histogram)),
        "included_bars": len(typical),
    }
