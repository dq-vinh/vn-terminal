"""Loading and call helpers shared by the WP5 tests.

Kept out of `conftest.py` so that test modules can import them directly
without importing pytest's own conftest module a second time under a
different name.

Every loader reads from `contracts/fixtures/`, which is the only data source
this workstream develops against. Reading a fixture happens in the test, not
in the indicator: that separation is the point of the purity constraint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.quant.indicators import BenchmarkSeries, IndicatorSpec, OHLCVSeries

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "contracts" / "fixtures"
GOLDEN = Path(__file__).resolve().parent / "golden"


def load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_series(symbol: str) -> OHLCVSeries:
    return OHLCVSeries.from_bars(load_fixture(f"bars_{symbol}.json")["bars"])


def synthetic_benchmark(series: OHLCVSeries, *, code: str = "TEST-INDEX") -> BenchmarkSeries:
    """A deterministic stand-in index covering the same trading calendar.

    Used wherever a relative-strength indicator has to be exercised without
    the Section 10.2 index mapping. It is a smooth, strictly positive series
    built from the bar position alone, so it makes no market claim of any
    kind: it exists to test arithmetic, not to represent VN-Index.
    """

    closes = [1000.0 * (1.0 + 0.0004 * index) for index in range(len(series))]
    return BenchmarkSeries(code=code, trading_dates=series.trading_dates, close=closes)


def call_kwargs(spec: IndicatorSpec, series: OHLCVSeries) -> dict[str, Any]:
    """Default parameters for `spec`, with a benchmark filled in when needed."""

    kwargs = dict(spec.parameters)
    if spec.requires_benchmark:
        kwargs["benchmark"] = synthetic_benchmark(series)
    return kwargs
