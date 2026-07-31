"""Decimal helpers for specification-mandated quantization.

The approved `dual_sma_trend_crossover` specification does not leave the
arithmetic to the implementation. It states the summation order, the
quantization, and the rounding mode:

    raw_sma_p[t] = sum_oldest_to_newest(close[t-p+1], ..., close[t]) / p
    SMA_p[t]     = quantize(raw_sma_p[t], 6 decimal places, ROUND_HALF_EVEN)

and it requires that "Both SMAs are quantized before relational comparison",
with the stated reason in its decision log: quantization "gives equality and
crossover consistent cross-implementation semantics". Comparing raw float64
means would make the equality cases in the specification's edge-case table
depend on the last bit of a binary mean, which differs between a naive loop,
a pairwise sum, and a SIMD reduction of the same numbers. That is why this
module exists instead of `numpy.mean`.

Conversion from float64 to Decimal is exact: `Decimal(float)` takes the
binary value the float actually holds, not a decimal approximation of it. The
division is performed at a working precision far wider than the six decimal
places the result is quantized to, so the quantization, not the division, is
what determines the last digit.

The liquidity comparison deliberately does *not* use this machinery. The
specification requires it to be implemented as an integer-scale comparison,
`volume_sum_20[t] >= 20 * min_avg_volume_20`, precisely to avoid a division;
see `dual_sma_trend_crossover.py`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

#: Six decimal places, per the specification's `quantize(..., 6, ...)`.
QUANTUM = Decimal("0.000001")

#: Working precision for the division that precedes quantization. Fifty
#: significant digits is far more than the ~17 a float64 can carry, so the
#: division contributes no rounding of its own at six decimal places.
WORKING_PRECISION = 50

ROUNDING_MODE = ROUND_HALF_EVEN


def quantize(value: Decimal) -> Decimal:
    """Round to six decimal places, half to even."""

    return value.quantize(QUANTUM, rounding=ROUNDING_MODE)


def exact(value: float) -> Decimal:
    """Exact Decimal for a finite float, raising on NaN or infinity.

    Raising rather than propagating is deliberate. A NaN close reaching the
    arithmetic means an upstream validation gate failed to run; that should
    surface as an error in a test, not as a NaN that silently makes every
    comparison false and therefore makes every crossover look absent.
    """

    if not math.isfinite(value):
        raise ValueError(f"cannot quantize a non-finite value: {value!r}")
    return Decimal(value)


def mean_quantized(values: Sequence[float]) -> Decimal:
    """Specification-exact moving-average value for one window.

    `values` must already be ordered oldest to newest and must contain
    exactly the window length; both are the caller's responsibility and both
    are checked by the strategy before this is reached.
    """

    if not values:
        raise ValueError("mean of an empty window is undefined")
    with localcontext() as context:
        context.prec = WORKING_PRECISION
        total = Decimal(0)
        for value in values:  # oldest to newest, per the specification
            total += exact(value)
        raw = total / Decimal(len(values))
    return quantize(raw)


def difference_quantized(left: Decimal, right: Decimal) -> Decimal:
    """`quantize(left - right, 6, ROUND_HALF_EVEN)`.

    Both operands are already quantized to six places, so the subtraction is
    exact and this quantization is a formality. It is applied anyway because
    the specification writes it out, and because a later strategy version
    that changed the operand precision would otherwise silently change
    meaning.
    """

    with localcontext() as context:
        context.prec = WORKING_PRECISION
        raw = left - right
    return quantize(raw)


def as_float(value: Decimal) -> float:
    """Convert a quantized Decimal for transport in a JSON payload.

    Used only at the serialization boundary. Comparisons upstream of this
    are performed on Decimals, so the float conversion cannot affect a
    signal; it only affects how the evidence is rendered.
    """

    return float(value)
