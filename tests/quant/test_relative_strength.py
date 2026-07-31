"""Relative strength versus VN-Index and sector (Section 14).

Split deliberately into two groups.

The **mathematics** is tested unconditionally against a synthetic benchmark.
Those tests must pass today and will keep passing when the real index bars
arrive; nothing about them depends on the data stream.

The **resolution** tests, which ask "which index is VN-Index" and "which
index tracks this security's sector", are skipped with an explicit reason
while the Section 10.2 index code-to-name mapping does not exist. Per the
WP5 instruction they are skipped rather than deleted, stubbed, or passed
against a fabricated mapping, so that they turn themselves back on the day
the security master gains index entries.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
import reference
from helpers import synthetic_benchmark
from test_indicator_math import assert_close, build

from backend.app.quant.indicators import (
    MISSING_MAPPING_REASON,
    BenchmarkMappingUnavailable,
    BenchmarkSeries,
    IndexCodeMapping,
    IndicatorError,
    OHLCVSeries,
    align_benchmark,
    compute,
    mapping_from_security_master,
    resolve_market_index_code,
    resolve_sector_index_code,
)

RS_IDS = ("relative_strength_vnindex", "relative_strength_sector")


# ---------------------------------------------------------------------------
# Mathematics, tested against a synthetic benchmark
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("indicator_id", RS_IDS)
def test_matches_reference(indicator_id: str, fpt: OHLCVSeries):
    benchmark = synthetic_benchmark(fpt)
    expected = reference.relative_strength(
        list(fpt.close), list(benchmark.close), 63, 200
    )
    result = compute(indicator_id, fpt, benchmark=benchmark)
    for output, values in expected.items():
        assert_close(result[output], values, indicator_id, output)


@pytest.mark.parametrize("indicator_id", RS_IDS)
def test_a_security_tracking_its_benchmark_exactly_has_flat_relative_strength(
    indicator_id: str,
):
    """A security that moves with the index must show zero excess return."""

    closes = [100.0 * (1.001**index) for index in range(80)]
    series = build(closes)
    benchmark = BenchmarkSeries(
        code="TEST",
        trading_dates=series.trading_dates,
        close=[value * 7.0 for value in closes],  # same path, different scale
    )
    result = compute(indicator_id, series, benchmark=benchmark, period=20, mansfield_period=30)
    ratio = result["ratio"]
    assert np.allclose(ratio, ratio[0]), "a proportional benchmark gives a flat ratio"

    excess = result["excess_return_pct"]
    defined = excess[np.isfinite(excess)]
    assert defined.size > 0
    assert np.all(np.abs(defined) < 1e-9)

    mansfield = result["mansfield"]
    defined_mansfield = mansfield[np.isfinite(mansfield)]
    assert np.all(np.abs(defined_mansfield) < 1e-9)


@pytest.mark.parametrize("indicator_id", RS_IDS)
def test_an_outperforming_security_has_positive_excess_return(indicator_id: str):
    series = build([100.0 * (1.004**index) for index in range(60)])
    benchmark = BenchmarkSeries(
        code="TEST",
        trading_dates=series.trading_dates,
        close=[1000.0 * (1.001**index) for index in range(60)],
    )
    result = compute(indicator_id, series, benchmark=benchmark, period=20, mansfield_period=30)
    excess = result["excess_return_pct"]
    defined = excess[np.isfinite(excess)]
    assert defined.size > 0
    assert np.all(defined > 0)


def test_alignment_is_by_trading_date_not_by_position():
    """A benchmark holiday must show as a gap, not shift every later value."""

    series = build([10.0, 11.0, 12.0, 13.0])
    dates = series.trading_dates
    benchmark = BenchmarkSeries(
        code="TEST",
        trading_dates=(dates[0], dates[1], dates[3]),  # bar 2 missing
        close=[100.0, 110.0, 130.0],
    )
    aligned = align_benchmark(series, benchmark)
    assert aligned[0] == 100.0
    assert aligned[1] == 110.0
    assert np.isnan(aligned[2]), "the missing session is a hole, not a shift"
    assert aligned[3] == 130.0, "later values stay on their own dates"


def test_a_benchmark_gap_is_not_forward_filled():
    series = build([10.0, 11.0, 12.0, 13.0])
    dates = series.trading_dates
    benchmark = BenchmarkSeries(
        code="TEST",
        trading_dates=(dates[0], dates[1], dates[3]),
        close=[100.0, 110.0, 130.0],
    )
    ratio = compute(
        "relative_strength_vnindex", series, benchmark=benchmark, period=1, mansfield_period=2
    )["ratio"]
    assert np.isnan(ratio[2])


def test_a_benchmark_with_no_overlapping_dates_gives_nothing():
    series = build([10.0, 11.0, 12.0])
    benchmark = BenchmarkSeries(
        code="TEST",
        trading_dates=(dt.date(2020, 1, 6), dt.date(2020, 1, 7), dt.date(2020, 1, 8)),
        close=[100.0, 110.0, 120.0],
    )
    ratio = compute(
        "relative_strength_vnindex", series, benchmark=benchmark, period=1, mansfield_period=2
    )["ratio"]
    assert np.all(np.isnan(ratio))


@pytest.mark.parametrize("indicator_id", RS_IDS)
def test_omitting_the_benchmark_raises_a_directive_error(
    indicator_id: str, fpt: OHLCVSeries
):
    with pytest.raises(IndicatorError, match="requires a benchmark"):
        compute(indicator_id, fpt)


@pytest.mark.parametrize("indicator_id", RS_IDS)
def test_the_ratio_level_is_not_rebased_to_the_loaded_window(
    indicator_id: str, fpt: OHLCVSeries
):
    """Loading more history must not change the values already computed.

    Re-basing the ratio to 100 at the start of the window would make every
    number depend on how much history the caller happened to request. This
    test is the guard on that documented decision.
    """

    benchmark = synthetic_benchmark(fpt)
    full = compute(indicator_id, fpt, benchmark=benchmark)["ratio"]

    tail_length = 100
    tail = OHLCVSeries(
        symbol=fpt.symbol,
        trading_dates=fpt.trading_dates[-tail_length:],
        open=fpt.open[-tail_length:],
        high=fpt.high[-tail_length:],
        low=fpt.low[-tail_length:],
        close=fpt.close[-tail_length:],
        volume=fpt.volume[-tail_length:],
    )
    tail_benchmark = BenchmarkSeries(
        code=benchmark.code,
        trading_dates=benchmark.trading_dates[-tail_length:],
        close=benchmark.close[-tail_length:],
    )
    partial = compute(indicator_id, tail, benchmark=tail_benchmark)["ratio"]
    np.testing.assert_allclose(full[-tail_length:], partial, rtol=1e-12, atol=1e-12)


# ---------------------------------------------------------------------------
# Benchmark resolution: the blocked dependency
# ---------------------------------------------------------------------------


def test_the_mapping_is_derived_from_the_security_master_not_hard_coded(
    security_master,
):
    """Whatever the mapping's state, it must come from the data, not from us."""

    mapping = mapping_from_security_master(security_master)
    assert isinstance(mapping, IndexCodeMapping)
    index_entries = [
        entry
        for entry in security_master
        if str(entry.get("security_type", "")).lower() == "index" and entry.get("index_code")
    ]
    assert bool(mapping.index_name_by_code) == bool(index_entries)


def test_resolution_fails_loudly_rather_than_guessing_a_code():
    """With no mapping at all, resolution must raise, never fall back."""

    with pytest.raises(BenchmarkMappingUnavailable):
        resolve_market_index_code(None)
    with pytest.raises(BenchmarkMappingUnavailable):
        resolve_sector_index_code("Information Technology", None)
    with pytest.raises(BenchmarkMappingUnavailable):
        resolve_market_index_code(IndexCodeMapping())


def test_resolution_of_an_unmapped_sector_does_not_fall_back_to_the_market():
    """A partial mapping must stay partial; silence is safer than a wrong index."""

    mapping = IndexCodeMapping(
        market_index_code="0001",
        sector_index_code_by_sector={"Real Estate": "0042"},
    )
    assert resolve_sector_index_code("Real Estate", mapping) == "0042"
    with pytest.raises(BenchmarkMappingUnavailable, match="no index code"):
        resolve_sector_index_code("Information Technology", mapping)


def test_resolution_requires_a_sector_on_the_security():
    mapping = IndexCodeMapping(sector_index_code_by_sector={"Real Estate": "0042"})
    with pytest.raises(BenchmarkMappingUnavailable, match="no sector recorded"):
        resolve_sector_index_code(None, mapping)


def test_vnindex_benchmark_resolves_from_the_security_master(index_mapping, fpt):
    """SKIPPED while the data stream has not supplied the index mapping."""

    if not index_mapping.market_index_code:
        pytest.skip(MISSING_MAPPING_REASON)

    code = resolve_market_index_code(index_mapping)
    assert code in index_mapping.index_name_by_code
    pytest.skip(
        "Mapping exists but this test still needs real VN-Index bars from the data "
        "stream to compute an end-to-end relative-strength series. Wire "
        "contracts/fixtures/bars_<VN-Index>.json in and remove this skip."
    )


def test_sector_benchmark_resolves_from_the_security_master(
    index_mapping, security_master
):
    """SKIPPED while the data stream has not supplied the index mapping."""

    if not index_mapping.sector_index_code_by_sector:
        pytest.skip(MISSING_MAPPING_REASON)

    equities = [
        entry
        for entry in security_master
        if str(entry.get("security_type", "")).lower() == "equity"
    ]
    assert equities, "the security master fixture holds no equities to resolve"
    for entry in equities:
        code = resolve_sector_index_code(entry.get("sector"), index_mapping)
        assert code in index_mapping.index_name_by_code


def test_the_skip_reason_names_the_owner_and_the_blocking_artifact():
    """A skip is only acceptable if it says who unblocks it and how."""

    assert "Section 10.2" in MISSING_MAPPING_REASON
    assert "WP2" in MISSING_MAPPING_REASON
    assert "security_master" in MISSING_MAPPING_REASON
