"""WP5 indicator engine (Section 14).

Deterministic, pure, and independent of the AI layer. Importing this package
registers every indicator listed in Section 14; see `NUMERICS.md` in this
directory for the per-indicator numerical documentation the section
requires, and `registry.documentation()` for the same content as data.

Typical use:

    from backend.app.quant.indicators import OHLCVSeries, build_indicators_payload

    series = OHLCVSeries.from_bars(bars)          # bars loaded by the caller
    payload = build_indicators_payload(series)    # add provenance, return

Purity contract, enforced by `tests/quant/test_purity.py`: no indicator
opens a file, a socket, or a database connection, reads the clock, reads the
environment, or draws a random number. Inputs are copied and marked
read-only on the way in, so an indicator cannot mutate its caller's data
either.
"""

from __future__ import annotations

from . import (  # noqa: F401  (imported for registration side effects)
    levels,
    momentum,
    money_flow,
    relative_strength,
    trend,
    volatility,
    volume,
)
from .engine import (
    DEFAULT_INDICATOR_SET,
    IndicatorRequest,
    build_indicators_payload,
    compute_many,
    series_key,
    to_indicator_series,
)
from .levels import build_levels
from .money_flow import MoneyFlowUndefined, build_money_flow_block
from .registry import all_ids, all_indicators, compute, documentation, get, spec
from .relative_strength import (
    MISSING_MAPPING_REASON,
    IndexCodeMapping,
    align_benchmark,
    mapping_from_security_master,
    resolve_market_index_code,
    resolve_sector_index_code,
)
from .types import (
    BenchmarkMappingUnavailable,
    BenchmarkSeries,
    IndicatorError,
    IndicatorResult,
    IndicatorSpec,
    OHLCVSeries,
    Tolerance,
)

__all__ = [
    "DEFAULT_INDICATOR_SET",
    "MISSING_MAPPING_REASON",
    "BenchmarkMappingUnavailable",
    "BenchmarkSeries",
    "IndexCodeMapping",
    "IndicatorError",
    "IndicatorRequest",
    "IndicatorResult",
    "IndicatorSpec",
    "MoneyFlowUndefined",
    "OHLCVSeries",
    "Tolerance",
    "align_benchmark",
    "all_ids",
    "all_indicators",
    "build_indicators_payload",
    "build_levels",
    "build_money_flow_block",
    "compute",
    "compute_many",
    "documentation",
    "get",
    "mapping_from_security_master",
    "resolve_market_index_code",
    "resolve_sector_index_code",
    "series_key",
    "spec",
    "to_indicator_series",
]
