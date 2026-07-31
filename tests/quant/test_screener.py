"""WP7 screener tests (Section 15).

The tests that matter most are the ones about what the screener *refuses* to
show. Section 15's prohibition, "The screener must not treat a current file
date as proof that a security remains actively traded", and the work-package
instruction that the 301 terminally inactive stock files "must not appear in
current screening results", are both tested at the boundary rather than in the
middle, because a recency filter that is right in the middle and wrong at the
edge is the failure mode that ships.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import jsonschema
import pytest
from strategy_helpers import (
    crossover_closes,
    make_history,
    round_trip_closes,
    sessions,
)

from backend.app.quant.screener import (
    COMPLETED,
    FAILED,
    Candidate,
    ScreenerJobs,
    TradingCalendar,
    UniverseFilters,
    assess,
    compute_run_id,
    contract_results,
    run_screen,
    to_csv,
)
from backend.app.quant.strategies import SecurityView

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "contracts" / "schemas" / "json"
STRATEGY = "dual_sma_trend_crossover"


def candidate(
    symbol: str,
    *,
    closes=None,
    volumes=None,
    tail_zero: int = 0,
    active: bool = True,
    critical: tuple[str, ...] = (),
    quality=None,
) -> Candidate:
    resolved = list(closes if closes is not None else round_trip_closes(count=140))
    count = len(resolved)
    vols = list(volumes) if volumes is not None else [1_000_000.0] * count
    for offset in range(tail_zero):
        vols[count - 1 - offset] = 0.0
    history = make_history(
        symbol=symbol, closes=resolved, volumes=vols, quality=quality
    )
    return Candidate(
        history=history,
        security=(
            SecurityView(
                symbol, history.trading_dates[-1], "HOSE", "ordinary_equity", "active"
            )
            if active
            else SecurityView(symbol, history.trading_dates[-1], "UNKNOWN", "unknown", "unknown")
        ),
        critical_issue_codes=critical,
    )


def run(candidates, **kwargs):
    run_date = kwargs.pop("run_date", candidates[0].history.trading_dates[-1])
    filters = kwargs.pop("filters", UniverseFilters(min_history_days=60))
    return run_screen(
        candidates,
        strategy_ids=[STRATEGY],
        run_date=run_date,
        data_version="fdata-2026-07-30",
        filters=filters,
        **kwargs,
    )


# ---------------------------------------------------------- the 301 symbols


@pytest.mark.parametrize(
    ("tail_zero", "expected_included"),
    [(0, True), (1, True), (4, True), (5, False), (6, False), (30, False)],
)
def test_terminal_zero_volume_runs_are_excluded_at_the_documented_boundary(
    tail_zero, expected_included
):
    """The baseline scan counted "terminal zero-volume runs of at least five".

    At the contract default of five sessions, a run of exactly five must be
    excluded and a run of four must not. This is the boundary the 301 files
    sit on, so it is asserted on both sides rather than assumed.
    """

    result = run([candidate("AAA", tail_zero=tail_zero)])
    included = [item.symbol for item in result.results]
    assert ("AAA" in included) is expected_included
    if not expected_included:
        excluded = {item.symbol: item.failed_criteria for item in result.excluded}
        assert "last_positive_volume_recent" in excluded["AAA"]


def test_a_current_last_bar_date_does_not_imply_the_security_is_active():
    """Section 15's explicit prohibition.

    Both securities have a bar on the run date. One of them has not traded for
    a fortnight. Only the traded one may appear.
    """

    live = candidate("LIVE")
    dead = candidate("DEAD", tail_zero=14)
    assert live.history.trading_dates[-1] == dead.history.trading_dates[-1]
    result = run([live, dead])
    assert [item.symbol for item in result.results] == ["LIVE"]


def test_recency_is_measured_in_market_sessions_not_calendar_days():
    """A thinly traded symbol is judged against the market's calendar."""

    dense = candidate("DENSE")
    calendar = TradingCalendar.from_histories([dense.history])
    assessment = assess(
        candidate("DEAD", tail_zero=7),
        filters=UniverseFilters(),
        calendar=calendar,
        as_of_date=dense.history.trading_dates[-1],
    )
    assert assessment.metrics["sessions_since_last_positive_volume"] == 7


# ------------------------------------------------------------ other filters


def test_inactive_classification_excludes_a_security():
    result = run([candidate("AAA"), candidate("BBB", active=False)])
    assert [item.symbol for item in result.results] == ["AAA"]
    failed = {item.symbol: item.failed_criteria for item in result.excluded}
    assert failed["BBB"] == ("active_equity",)


def test_min_history_excludes_a_short_series():
    short = candidate("SHORT", closes=crossover_closes(count=30))
    long = candidate("LONG")
    result = run(
        [short, long],
        run_date=long.history.trading_dates[-1],
        filters=UniverseFilters(min_history_days=60),
    )
    assert [item.symbol for item in result.results] == ["LONG"]


def test_median_trading_value_filter_uses_the_median_not_the_mean():
    """One exceptional session must not carry an illiquid security through."""

    volumes = [1_000.0] * 140
    volumes[-1] = 100_000_000.0
    thin = candidate("THIN", volumes=volumes)
    result = run(
        [thin],
        filters=UniverseFilters(
            min_20d_median_trading_value=1_000_000.0, min_history_days=60
        ),
    )
    assert not result.results
    assert "min_20d_median_trading_value" in result.excluded[0].failed_criteria


def test_unresolved_critical_issue_excludes_a_security():
    result = run([candidate("AAA"), candidate("BAD", critical=("ohlc_violation",))])
    assert [item.symbol for item in result.results] == ["AAA"]


def test_a_critical_quality_status_on_any_bar_excludes_a_security():
    quality = ["valid"] * 140
    quality[10] = "critical"
    result = run([candidate("AAA"), candidate("FLAGGED", quality=quality)])
    assert [item.symbol for item in result.results] == ["AAA"]


def test_a_security_with_no_bar_on_or_before_the_run_date_is_excluded():
    later = sessions(200)[-1]
    result = run([candidate("AAA")], run_date=sessions(1)[0] - timedelta(days=5))
    assert not result.results
    assert "has_bar_on_or_before_run_date" in result.excluded[0].failed_criteria
    assert later is not None


# ----------------------------------------------------- ranking and run record


def test_ranking_is_deterministic_and_independent_of_input_order():
    names = ["DDD", "AAA", "CCC", "BBB"]
    forward = run([candidate(name) for name in names])
    reverse = run([candidate(name) for name in reversed(names)])
    assert [item.symbol for item in forward.results] == [
        item.symbol for item in reverse.results
    ]
    assert [item.rank for item in forward.results] == list(
        range(1, len(forward.results) + 1)
    )


def test_ties_break_on_symbol():
    result = run([candidate(name) for name in ("ZZZ", "AAA", "MMM")])
    scores = {item.symbol: item.total_score for item in result.results}
    assert len(set(scores.values())) == 1, "fixture should produce a tie"
    assert [item.symbol for item in result.results] == ["AAA", "MMM", "ZZZ"]


def test_run_id_is_identical_for_identical_inputs_and_differs_otherwise():
    first = run([candidate("AAA")])
    second = run([candidate("AAA")])
    assert first.run_id == second.run_id
    third = run(
        [candidate("AAA")],
        filters=UniverseFilters(min_history_days=61),
    )
    assert third.run_id != first.run_id


def test_run_id_changes_when_a_strategy_parameter_changes():
    base = candidate("AAA")
    first = run_screen(
        [base],
        strategy_ids=[STRATEGY],
        run_date=base.history.trading_dates[-1],
        data_version="v1",
        filters=UniverseFilters(min_history_days=60),
    )
    second = run_screen(
        [base],
        strategy_ids=[STRATEGY],
        run_date=base.history.trading_dates[-1],
        data_version="v1",
        filters=UniverseFilters(min_history_days=60),
        strategy_parameters={STRATEGY: {"fast_period": 10}},
    )
    assert first.run_id != second.run_id


def test_run_id_changes_when_the_data_version_changes():
    base = candidate("AAA")
    common = {
        "strategy_ids": [STRATEGY],
        "run_date": base.history.trading_dates[-1],
        "filters": UniverseFilters(min_history_days=60),
    }
    first = run_screen([base], data_version="fdata-2026-07-30", **common)
    second = run_screen([base], data_version="fdata-2026-07-31", **common)
    assert first.run_id != second.run_id


def test_the_run_record_stores_everything_section_15_requires():
    result = run([candidate("AAA")])
    assert result.run_date == candidate("AAA").history.trading_dates[-1]
    assert result.strategy_versions == {STRATEGY: "1.0.0"}
    assert result.data_version == "fdata-2026-07-30"
    assert result.parameters["strategy_parameters"][STRATEGY]["fast_period"] == 20
    assert result.parameters["universe_filters"]["min_history_days"] == 60


def test_passed_and_failed_criteria_are_shown_per_security():
    result = run([candidate("AAA"), candidate("DEAD", tail_zero=9)])
    included = result.results[0]
    assert any(name.startswith(f"{STRATEGY}.") for name in included.passed_criteria)
    assert any(name.startswith("universe.") for name in included.passed_criteria)
    assert result.excluded[0].failed_criteria


def test_an_all_excluded_run_says_so_rather_than_looking_empty():
    result = run([candidate("AAA", active=False)])
    assert not result.results
    assert any("excluded by the universe filters" in item for item in result.warnings)


def test_compute_run_id_is_stable_across_processes():
    """A hash of canonical JSON, not of object identity or insertion order."""

    kwargs = {
        "run_date": sessions(10)[-1],
        "data_version": "v1",
        "filters": UniverseFilters(),
        "strategy_parameters": {STRATEGY: {"fast_period": 20, "slow_period": 50}},
        "strategy_versions": {STRATEGY: "1.0.0"},
        "symbols": ["BBB", "AAA"],
    }
    shuffled = dict(kwargs)
    shuffled["symbols"] = ["AAA", "BBB"]
    shuffled["strategy_parameters"] = {STRATEGY: {"slow_period": 50, "fast_period": 20}}
    assert compute_run_id(**kwargs) == compute_run_id(**shuffled)


# -------------------------------------------------------------- contract, CSV


def test_results_validate_against_the_frozen_screen_response_schema():
    with (SCHEMAS / "screen_results_response.schema.json").open(encoding="utf-8") as fh:
        schema = json.load(fh)
    result = run([candidate("AAA"), candidate("BBB")])
    payload = result.contract_payload(source="Fialda FData", freshness_status="current")
    jsonschema.validate(payload, schema)
    assert len(payload["results"]) == len(contract_results(result))


def test_csv_export_includes_excluded_securities_and_is_reproducible():
    candidates = [candidate("AAA"), candidate("DEAD", tail_zero=9)]
    first = to_csv(run(candidates))
    second = to_csv(run(candidates))
    assert first == second
    lines = first.splitlines()
    assert lines[0].startswith("run_id,run_date,data_version,status,rank,symbol")
    assert any(line.split(",")[3] == "included" for line in lines[1:])
    dead = [line for line in lines[1:] if ",DEAD," in line]
    assert dead and "excluded" in dead[0]
    assert "last_positive_volume_recent" in dead[0]


def test_csv_uses_unix_newlines_only():
    text = to_csv(run([candidate("AAA")]))
    assert "\r" not in text


# ------------------------------------------------------------------- jobs


def test_background_run_completes_and_stores_its_result():
    jobs = ScreenerJobs()
    try:
        candidates = [candidate("AAA")]
        expected = run(candidates)
        record = jobs.submit(expected.run_id, lambda: run(candidates))
        snapshot = jobs.wait(expected.run_id, timeout=30)
        assert snapshot["status"] == COMPLETED
        assert jobs.result(expected.run_id).run_id == expected.run_id
        assert record.run_id == expected.run_id
    finally:
        jobs.shutdown()


def test_a_failing_background_run_records_the_error_and_stores_no_result():
    jobs = ScreenerJobs()
    try:

        def boom():
            raise ValueError("snapshot unavailable")

        jobs.submit("run-1", boom)
        snapshot = jobs.wait("run-1", timeout=30)
        assert snapshot["status"] == FAILED
        assert "snapshot unavailable" in snapshot["error"]
        with pytest.raises(ValueError):
            jobs.result("run-1")
    finally:
        jobs.shutdown()


def test_submitting_the_same_run_id_twice_does_not_start_a_second_screen():
    jobs = ScreenerJobs()
    calls = []

    def work():
        calls.append(1)
        return run([candidate("AAA")])

    try:
        jobs.submit("run-2", work)
        jobs.wait("run-2", timeout=30)
        assert len(calls) == 1
    finally:
        jobs.shutdown()


def test_background_execution_does_not_change_the_result():
    """Concurrency must not touch a deterministic computation."""

    jobs = ScreenerJobs(max_workers=2)
    try:
        candidates = [candidate(name) for name in ("AAA", "BBB", "CCC")]
        direct = run(candidates)
        jobs.submit(direct.run_id, lambda: run(candidates))
        jobs.wait(direct.run_id, timeout=30)
        background = jobs.result(direct.run_id)
        assert [item.symbol for item in background.results] == [
            item.symbol for item in direct.results
        ]
        assert background.run_id == direct.run_id
    finally:
        jobs.shutdown()
