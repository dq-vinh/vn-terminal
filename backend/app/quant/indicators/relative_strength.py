"""Relative strength versus VN-Index and versus sector (Section 14).

This is the one indicator family in WP5 with an external dependency. Section
10.2 is explicit:

> The security master must include an index code-to-name mapping from an
> external source before relative-strength calculations against VN-Index or
> sector indices are enabled.

That mapping is owned by the data stream (WP2). The 207 files under
`EOD/index` are named with numeric codes rather than symbols, so without the
mapping there is no way to know which file is VN-Index and which is a given
sector index. This module therefore separates two things:

- The **mathematics**, which is implemented, tested, and complete. Given any
  benchmark series, relative strength is computed here.
- The **resolution** of which benchmark to use, which raises
  `BenchmarkMappingUnavailable` until the data stream supplies a mapping.
  Nothing here guesses a code, hard-codes "VNINDEX", or infers a sector
  index from a sector name.

`tests/quant/test_relative_strength.py` runs the mathematics against a
synthetic benchmark and skips the end-to-end resolution tests with an
explicit reason while the mapping is absent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .registry import register
from .trend import ADJUSTMENT
from .types import (
    BenchmarkMappingUnavailable,
    BenchmarkSeries,
    IndicatorError,
    IndicatorResult,
    IndicatorSpec,
    OHLCVSeries,
    Tolerance,
)
from .windows import rolling_mean, safe_divide

MISSING_MAPPING_REASON = (
    "Index code-to-name mapping is not available. Section 10.2 requires the security "
    "master to carry an index code-to-name mapping from an external source before "
    "relative-strength calculations against VN-Index or sector indices are enabled, "
    "and the 207 files under EOD/index are named with numeric codes. The mapping is "
    "owned by the data stream (WP2); no security_master entry with "
    "security_type='index' and a populated index_code exists yet."
)


@dataclass(frozen=True, slots=True)
class IndexCodeMapping:
    """The data stream's index code-to-name mapping, once it exists.

    `market_index_code` identifies VN-Index. `sector_index_code_by_sector`
    maps a security master `sector` value onto the index code that tracks
    it. `index_name_by_code` is the human-readable half of the Section 10.2
    mapping and is carried so a caller can label a chart without a second
    lookup.
    """

    market_index_code: str | None = None
    sector_index_code_by_sector: Mapping[str, str] = None  # type: ignore[assignment]
    index_name_by_code: Mapping[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        setattr_ = object.__setattr__
        setattr_(self, "sector_index_code_by_sector", dict(self.sector_index_code_by_sector or {}))
        setattr_(self, "index_name_by_code", dict(self.index_name_by_code or {}))

    @property
    def is_usable(self) -> bool:
        return bool(self.market_index_code) or bool(self.sector_index_code_by_sector)


def mapping_from_security_master(
    entries: Sequence[Mapping[str, Any]],
) -> IndexCodeMapping:
    """Derive the mapping from already-loaded security master records.

    Pure: the caller loads the records; this function only reads the
    in-memory sequence. An entry contributes to the mapping when it has
    `security_type == "index"` and a populated `index_code`. Nothing is
    inferred for equities whose sector has no index entry, so a partial
    mapping stays partial rather than silently falling back to the market
    index.
    """

    market_code: str | None = None
    by_sector: dict[str, str] = {}
    by_code: dict[str, str] = {}

    for entry in entries:
        if str(entry.get("security_type", "")).lower() != "index":
            continue
        code = entry.get("index_code")
        if not code:
            continue
        code = str(code)
        name = str(entry.get("company_name") or entry.get("symbol") or code)
        by_code[code] = name
        sector = entry.get("sector")
        if sector:
            by_sector.setdefault(str(sector), code)

    return IndexCodeMapping(
        market_index_code=market_code,
        sector_index_code_by_sector=by_sector,
        index_name_by_code=by_code,
    )


def resolve_market_index_code(mapping: IndexCodeMapping | None) -> str:
    """Index code for VN-Index, or raise with the documented reason."""

    if mapping is None or not mapping.market_index_code:
        raise BenchmarkMappingUnavailable(MISSING_MAPPING_REASON)
    return mapping.market_index_code


def resolve_sector_index_code(sector: str | None, mapping: IndexCodeMapping | None) -> str:
    """Index code for a sector, or raise with the documented reason."""

    if mapping is None or not mapping.sector_index_code_by_sector:
        raise BenchmarkMappingUnavailable(MISSING_MAPPING_REASON)
    if not sector:
        raise BenchmarkMappingUnavailable(
            "the security has no sector recorded in the security master, so no "
            "sector index can be resolved. " + MISSING_MAPPING_REASON
        )
    try:
        return mapping.sector_index_code_by_sector[str(sector)]
    except KeyError as error:
        raise BenchmarkMappingUnavailable(
            f"sector {sector!r} has no index code in the mapping. "
            + MISSING_MAPPING_REASON
        ) from error


def align_benchmark(series: OHLCVSeries, benchmark: BenchmarkSeries) -> np.ndarray:
    """Benchmark closes aligned onto the security's trading dates.

    Alignment is by trading date, never by position: the two calendars can
    differ, since an index prints on days a thinly traded security does not,
    and vice versa. Dates the benchmark does not cover become NaN, which
    then propagates through the missing-value rules of whatever consumes
    them. Nothing is forward-filled.
    """

    by_date = dict(zip(benchmark.trading_dates, benchmark.close))
    return np.array(
        [by_date.get(day, np.nan) for day in series.trading_dates], dtype=np.float64
    )


def _relative_strength(
    indicator_id: str,
    series: OHLCVSeries,
    benchmark: BenchmarkSeries | None,
    period: int,
    mansfield_period: int,
) -> IndicatorResult:
    if benchmark is None:
        raise IndicatorError(
            f"{indicator_id} requires a benchmark series. Resolve the index code via "
            "resolve_market_index_code() or resolve_sector_index_code(), load that "
            "index's bars, and pass them as benchmark=BenchmarkSeries(...)."
        )
    if int(period) < 1:
        raise IndicatorError("period must be >= 1")
    if int(mansfield_period) < 2:
        raise IndicatorError("mansfield_period must be >= 2")

    benchmark_close = align_benchmark(series, benchmark)
    ratio = 100.0 * safe_divide(series.close, benchmark_close)

    def _roc(values: np.ndarray, lag: int) -> np.ndarray:
        lagged = np.full(len(values), np.nan, dtype=np.float64)
        if len(values) > lag:
            lagged[lag:] = values[:-lag]
        return 100.0 * (safe_divide(values, lagged) - 1.0)

    ratio_average = rolling_mean(ratio, int(mansfield_period))
    return IndicatorResult(
        indicator_id=indicator_id,
        parameters={
            "period": period,
            "mansfield_period": mansfield_period,
            "benchmark": benchmark.code,
        },
        series={
            "ratio": ratio,
            "roc": _roc(ratio, int(period)),
            "excess_return_pct": _roc(series.close, int(period))
            - _roc(benchmark_close, int(period)),
            "mansfield": 100.0 * (safe_divide(ratio, ratio_average) - 1.0),
        },
    )


_RS_FORMULA = (
    "ratio[i] = 100 * close[i] / benchmark_close[i], where benchmark_close is the "
    "benchmark aligned onto the security's trading dates; "
    "roc[i] = 100 * (ratio[i] / ratio[i - period] - 1); "
    "excess_return_pct[i] = ROC(close, period) - ROC(benchmark_close, period); "
    "mansfield[i] = 100 * (ratio[i] / SMA(ratio, mansfield_period) - 1), the "
    "Mansfield relative-strength form used in Weinstein stage analysis."
)

_RS_INPUT = (
    "Close of the security and close of the benchmark index. The ratio's LEVEL is "
    "arbitrary, being a price in thousands of VND divided by an index level, so it "
    "must never be compared across securities. It is deliberately not re-based to "
    "100 at the start of the loaded window, because that would make every value "
    "depend on how much history the caller happened to request. Compare securities "
    "using roc, excess_return_pct, or mansfield, all three of which are invariant to "
    "the ratio's scale."
)

_RS_MISSING = (
    "NaN on any date the benchmark does not cover, on any date the security's close "
    "is missing, and wherever the benchmark close is zero. Alignment is by trading "
    "date and nothing is forward-filled, so a benchmark holiday shows as a gap "
    "rather than as a flat day. mansfield additionally follows the windowed rule "
    "over mansfield_period."
)

_RS_TOLERANCE = Tolerance(
    absolute=1e-9,
    relative=1e-9,
    basis=(
        "Against the naive reference implementation, on a synthetic benchmark. No "
        "external cross-check is possible until the index mapping and real index "
        "bars exist; the AmiBroker comparison for this family is blocked on the same "
        "dependency, not merely on an export."
    ),
)


@register(
    IndicatorSpec(
        indicator_id="relative_strength_vnindex",
        title="Relative strength versus VN-Index",
        block="relative_strength",
        outputs=("ratio", "roc", "excess_return_pct", "mansfield"),
        parameters={"period": 63, "mansfield_period": 200, "benchmark": None},
        formula=_RS_FORMULA,
        input_price=_RS_INPUT,
        adjustment_convention=(
            ADJUSTMENT
            + " Both legs must be on the same adjustment basis. A back-adjusted "
            "security close divided by a price index that is not back-adjusted "
            "produces a ratio that drifts at every corporate action; confirming that "
            "the index series in EOD/index is on a comparable basis is part of the "
            "outstanding data-stream dependency."
        ),
        warm_up=(
            "ratio: none beyond the first date both series cover. roc and "
            "excess_return_pct: `period` bars. mansfield: mansfield_period - 1 bars, "
            "so the default of 200 needs roughly ten months of overlapping history."
        ),
        missing_value_behavior=_RS_MISSING,
        comparison_reference=(
            "Naive reference implementation on a synthetic benchmark. BLOCKED for "
            "any real comparison: the benchmark cannot be identified until the data "
            "stream supplies the Section 10.2 index code-to-name mapping. The "
            "default period of 63 bars is a quarter of trading sessions and the "
            "Mansfield period of 200 follows Weinstein's published convention; "
            "neither is prescribed by Section 14."
        ),
        tolerance=_RS_TOLERANCE,
        warm_up_bars=lambda period=63, mansfield_period=200, benchmark=None: max(
            int(period), int(mansfield_period) - 1
        ),
        requires_benchmark=True,
    )
)
def relative_strength_vnindex(
    series: OHLCVSeries,
    *,
    period: int = 63,
    mansfield_period: int = 200,
    benchmark: BenchmarkSeries | None = None,
) -> IndicatorResult:
    return _relative_strength(
        "relative_strength_vnindex", series, benchmark, period, mansfield_period
    )


@register(
    IndicatorSpec(
        indicator_id="relative_strength_sector",
        title="Relative strength versus sector index",
        block="relative_strength",
        outputs=("ratio", "roc", "excess_return_pct", "mansfield"),
        parameters={"period": 63, "mansfield_period": 200, "benchmark": None},
        formula=_RS_FORMULA,
        input_price=_RS_INPUT,
        adjustment_convention=(
            ADJUSTMENT
            + " The same basis requirement as relative strength versus VN-Index "
            "applies, and additionally the sector index must be the one the security "
            "master assigns to this security's sector, not a sector chosen by "
            "resemblance."
        ),
        warm_up=(
            "ratio: none beyond the first date both series cover. roc and "
            "excess_return_pct: `period` bars. mansfield: mansfield_period - 1 bars."
        ),
        missing_value_behavior=(
            _RS_MISSING
            + " A sector index typically has a shorter history than a long-listed "
            "security, so the overlap window, not the security's own history, sets "
            "the first usable date."
        ),
        comparison_reference=(
            "Naive reference implementation on a synthetic benchmark. BLOCKED for "
            "any real comparison on the same Section 10.2 mapping dependency, and "
            "additionally on the sector taxonomy: the security master's `sector` "
            "field must use the same vocabulary as whatever the sector indices are "
            "built from, which is not yet established."
        ),
        tolerance=_RS_TOLERANCE,
        warm_up_bars=lambda period=63, mansfield_period=200, benchmark=None: max(
            int(period), int(mansfield_period) - 1
        ),
        requires_benchmark=True,
    )
)
def relative_strength_sector(
    series: OHLCVSeries,
    *,
    period: int = 63,
    mansfield_period: int = 200,
    benchmark: BenchmarkSeries | None = None,
) -> IndicatorResult:
    return _relative_strength(
        "relative_strength_sector", series, benchmark, period, mansfield_period
    )
