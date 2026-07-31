"""WP8 backtester tests: controls, outputs, and reproducibility.

Bias controls live in `test_lookahead_adversarial.py`. This file covers the
rest of Section 16: that every required control changes the result it is
supposed to change, that every required output is produced with a recorded
definition, and that a run reproduces from its saved configuration.

Each control is tested by varying only that control and asserting the specific
consequence, rather than by asserting the control is stored. A configuration
field that is recorded and then ignored is a common and quiet defect.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import jsonschema
import pytest
from strategy_helpers import (
    make_history,
    round_trip_closes,
    security_view,
)

from backend.app.quant.backtest import (
    DEFINITIONS,
    NEXT_CLOSE,
    NEXT_OPEN,
    BacktestConfig,
    BacktestConfigError,
    LiquidityConstraint,
    Period,
    PositionSizing,
    compute_metrics,
    compute_run_id,
    contract_payload,
    drawdown_curve,
    run_backtest,
    summarize,
)
from backend.app.quant.backtest.config import (
    FIXED_CASH_AMOUNT,
    FIXED_FRACTION_OF_EQUITY,
    FIXED_SHARES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "contracts" / "schemas" / "json"
STRATEGY = "dual_sma_trend_crossover"

CLOSES = round_trip_closes(count=180)
HISTORY = make_history(closes=CLOSES)
FULL = Period(HISTORY.trading_dates[0], HISTORY.trading_dates[-1])


def config(**overrides) -> BacktestConfig:
    defaults: dict = {
        "strategy_id": STRATEGY,
        "symbol_universe": ("TEST",),
        "entry_convention": NEXT_OPEN,
        "exit_convention": NEXT_OPEN,
        "transaction_cost_rate": 0.0,
        "slippage_rate": 0.0,
        "position_size": PositionSizing(FIXED_SHARES, 100),
        "max_concurrent_positions": 1,
        "liquidity_constraint": LiquidityConstraint(),
        "price_adjustment_convention": "back_adjusted",
        "benchmark": None,
        "in_sample_period": FULL,
        "initial_capital": 1_000_000.0,
    }
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def go(cfg=None, histories=None, **kwargs):
    return run_backtest(
        cfg or config(),
        histories or {"TEST": HISTORY},
        data_version="fdata-2026-07-30",
        security_resolver=security_view,
        **kwargs,
    )


# ------------------------------------------------------- required controls


def test_entry_and_exit_conventions_must_be_selected_explicitly():
    with pytest.raises(BacktestConfigError, match="explicitly selected"):
        config(entry_convention="market")
    with pytest.raises(BacktestConfigError, match="explicitly selected"):
        config(exit_convention="")


def test_entry_and_exit_conventions_can_differ():
    result = go(config(entry_convention=NEXT_OPEN, exit_convention=NEXT_CLOSE))
    buys = [fill for fill in result.fills if fill.side == "buy"]
    sells = [fill for fill in result.fills if fill.side == "sell"]
    assert buys and sells
    assert buys[0].convention == NEXT_OPEN
    assert sells[0].convention == NEXT_CLOSE


def test_transaction_cost_reduces_net_profit_and_is_recorded():
    free = go(config(transaction_cost_rate=0.0))
    charged = go(config(transaction_cost_rate=0.01))
    assert charged.equity_curve[-1] < free.equity_curve[-1]
    assert all(fill.transaction_cost > 0 for fill in charged.fills)
    assert charged.trades[0].costs > free.trades[0].costs


def test_slippage_moves_the_fill_against_the_trade_on_both_sides():
    result = go(config(slippage_rate=0.01))
    for fill in result.fills:
        if fill.side == "buy":
            assert fill.fill_price > fill.reference_price
        else:
            assert fill.fill_price < fill.reference_price


def test_slippage_and_cost_are_separately_attributed():
    result = go(config(transaction_cost_rate=0.002, slippage_rate=0.003))
    fill = result.fills[0]
    assert fill.transaction_cost == pytest.approx(
        fill.notional * 0.002
    )
    assert fill.slippage_cost == pytest.approx(
        fill.reference_price * 0.003 * fill.quantity
    )


@pytest.mark.parametrize(
    ("sizing", "check"),
    [
        (PositionSizing(FIXED_SHARES, 250), lambda q, p: q == 250),
        (
            PositionSizing(FIXED_CASH_AMOUNT, 50_000),
            lambda q, p: q == int(50_000 // p),
        ),
        (
            PositionSizing(FIXED_FRACTION_OF_EQUITY, 0.25),
            lambda q, p: q == int((1_000_000.0 * 0.25) // p),
        ),
    ],
)
def test_every_position_size_mode_sizes_as_documented(sizing, check):
    result = go(config(position_size=sizing))
    fill = next(item for item in result.fills if item.side == "buy")
    assert check(fill.quantity, fill.fill_price)


def test_leverage_is_refused():
    with pytest.raises(BacktestConfigError, match="leverage"):
        PositionSizing(FIXED_FRACTION_OF_EQUITY, 1.5)


def test_lot_size_rounds_the_quantity_down():
    result = go(config(position_size=PositionSizing(FIXED_SHARES, 1_007, lot_size=100)))
    fill = next(item for item in result.fills if item.side == "buy")
    assert fill.quantity == 1_000


def test_max_concurrent_positions_caps_simultaneous_holdings():
    others = {
        name: make_history(symbol=name, closes=CLOSES) for name in ("AAA", "BBB", "CCC")
    }
    capped = run_backtest(
        config(symbol_universe=tuple(others), max_concurrent_positions=1),
        others,
        data_version="v",
        security_resolver=security_view,
    )
    uncapped = run_backtest(
        config(symbol_universe=tuple(others), max_concurrent_positions=3),
        others,
        data_version="v",
        security_resolver=security_view,
    )
    assert len([f for f in capped.fills if f.side == "buy"]) < len(
        [f for f in uncapped.fills if f.side == "buy"]
    )
    rejected = [
        event
        for event in capped.order_events
        if event.status == "cancelled" and "max_concurrent_positions" in event.detail
    ]
    assert rejected


def test_liquidity_constraint_can_reject_rather_than_partially_fill():
    """The engine's constraint is separate from the strategy's liquidity rule.

    `min_avg_volume_20` is set to zero so the *strategy* still signals on a
    thin series; what is being tested here is the backtester's own
    participation limit, which is a portfolio control rather than a rule of
    the approved specification.
    """

    thin = make_history(closes=CLOSES, volumes=[500.0] * len(CLOSES))
    capped = run_backtest(
        config(
            strategy_parameters={"min_avg_volume_20": 0},
            position_size=PositionSizing(FIXED_SHARES, 10_000),
            liquidity_constraint=LiquidityConstraint(
                max_participation_of_bar_volume=0.1, reject_partial_fills=True
            ),
        ),
        {"TEST": thin},
        data_version="v",
        security_resolver=security_view,
    )
    assert not [fill for fill in capped.fills if fill.side == "buy"]
    assert any("rejected" in event.detail for event in capped.order_events)


def test_liquidity_constraint_can_partially_fill_instead():
    thin = make_history(closes=CLOSES, volumes=[500.0] * len(CLOSES))
    capped = run_backtest(
        config(
            strategy_parameters={"min_avg_volume_20": 0},
            position_size=PositionSizing(FIXED_SHARES, 10_000),
            liquidity_constraint=LiquidityConstraint(
                max_participation_of_bar_volume=0.1
            ),
        ),
        {"TEST": thin},
        data_version="v",
        security_resolver=security_view,
    )
    buys = [fill for fill in capped.fills if fill.side == "buy"]
    assert buys and buys[0].quantity == 50
    assert any("capped from" in event.detail for event in capped.order_events)


def test_min_execution_bar_volume_blocks_a_fill():
    thin = make_history(closes=CLOSES, volumes=[500.0] * len(CLOSES))
    result = run_backtest(
        config(
            strategy_parameters={"min_avg_volume_20": 0},
            liquidity_constraint=LiquidityConstraint(min_execution_bar_volume=1_000),
        ),
        {"TEST": thin},
        data_version="v",
        security_resolver=security_view,
    )
    assert not result.fills
    assert any("below the configured minimum" in e.detail for e in result.order_events)


def test_benchmark_comparison_is_populated_when_a_series_is_supplied():
    benchmark = {
        day: 100.0 + index * 0.1 for index, day in enumerate(HISTORY.trading_dates)
    }
    result = go(config(benchmark="VNINDEX"))
    metrics = compute_metrics(
        result, config(benchmark="VNINDEX"), label="full", period=FULL,
        benchmark_closes=benchmark,
    )
    comparison = metrics.values["benchmark_comparison"]
    assert comparison["status"] == "available"
    for key in ("beta", "correlation", "tracking_error", "information_ratio"):
        assert key in comparison


def test_benchmark_comparison_says_why_it_is_absent():
    result = go()
    metrics = compute_metrics(result, config(), label="full", period=FULL)
    comparison = metrics.values["benchmark_comparison"]
    assert comparison["status"] == "not_configured"
    assert "reason" in comparison


def test_in_sample_and_out_of_sample_are_reported_separately():
    cfg = config(
        in_sample_period=Period(HISTORY.trading_dates[0], HISTORY.trading_dates[119]),
        out_of_sample_period=Period(
            HISTORY.trading_dates[120], HISTORY.trading_dates[-1]
        ),
    )
    report = summarize(go(cfg), cfg)
    assert set(report["metrics"]) == {"full", "in_sample", "out_of_sample"}
    assert report["metrics"]["in_sample"]["sessions"] == 120
    assert report["metrics"]["out_of_sample"]["sessions"] == 60


def test_overlapping_in_sample_and_out_of_sample_is_refused():
    with pytest.raises(BacktestConfigError, match="out-of-sample"):
        config(
            in_sample_period=Period(date(2024, 1, 1), date(2024, 6, 1)),
            out_of_sample_period=Period(date(2024, 5, 1), date(2024, 12, 1)),
        )


def test_publication_date_requirement_cannot_be_disabled():
    with pytest.raises(BacktestConfigError, match="publication dates"):
        config(require_fundamental_publication_dates=False)


# --------------------------------------------------------- required outputs


REQUIRED_OUTPUTS = (
    "cagr",
    "annualized_return",
    "volatility",
    "sharpe",
    "sortino",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "average_holding_period_days",
    "turnover",
    "exposure",
    "benchmark_comparison",
)


def test_every_section_16_output_metric_is_produced():
    metrics = compute_metrics(go(), config(), label="full", period=FULL)
    for name in REQUIRED_OUTPUTS:
        assert name in metrics.values, f"Section 16 requires {name}"


def test_every_metric_carries_a_definition():
    metrics = compute_metrics(go(), config(), label="full", period=FULL).as_dict()
    for name in metrics["metrics"]:
        if name == "benchmark_comparison":
            continue
        assert name in DEFINITIONS, f"{name} was produced without a definition"
        assert len(DEFINITIONS[name]) > 40, f"{name}'s definition is a stub"


def test_trade_list_equity_curve_and_drawdown_curve_are_produced():
    result = go()
    report = summarize(result, config())
    assert report["trades"]
    assert len(report["equity_curve"]) == len(result.calendar)
    assert len(report["drawdown_curve"]) == len(result.calendar)
    assert all(point["drawdown"] <= 0 for point in drawdown_curve(result))


def test_data_and_strategy_versions_travel_with_the_result():
    report = summarize(go(), config())
    assert report["strategy_version"] == "1.1.0"
    assert report["data_version"] == "fdata-2026-07-30"
    assert report["config"]["strategy_id"] == STRATEGY


def test_profit_factor_is_null_rather_than_infinite_when_nothing_lost():
    result = go()
    metrics = compute_metrics(result, config(), label="full", period=FULL)
    losers = [trade for trade in result.trades if trade.net_pnl < 0]
    if not losers:
        assert metrics.values["profit_factor"] is None
    else:
        assert metrics.values["profit_factor"] > 0


def test_metrics_over_a_trade_free_window_do_not_invent_numbers():
    early = Period(HISTORY.trading_dates[0], HISTORY.trading_dates[40])
    metrics = compute_metrics(go(), config(), label="early", period=early)
    assert metrics.values["trade_count"] == 0
    assert metrics.values["win_rate"] is None
    assert metrics.values["average_holding_period_days"] is None


def test_undefined_metrics_are_named_in_the_contract_payload():
    """The contract requires non-null numbers; undefined must stay visible."""

    early = Period(HISTORY.trading_dates[0], HISTORY.trading_dates[40])
    payload = compute_metrics(go(), config(), label="early", period=early).contract_metrics()
    undefined = payload["benchmark_comparison"]["undefined_metrics"]
    assert "win_rate" in undefined
    assert payload["win_rate"] == 0.0


def test_max_drawdown_is_negative_or_zero_and_dated():
    metrics = compute_metrics(go(), config(), label="full", period=FULL)
    assert metrics.values["max_drawdown"] <= 0
    if metrics.values["max_drawdown"] < 0:
        assert metrics.values["max_drawdown_date"] is not None


def test_exposure_is_between_zero_and_one_for_an_unlevered_run():
    metrics = compute_metrics(go(), config(), label="full", period=FULL)
    assert 0.0 <= metrics.values["exposure"] <= 1.0


def test_open_positions_are_reported_and_excluded_from_trade_statistics():
    truncated = Period(HISTORY.trading_dates[0], HISTORY.trading_dates[95])
    result = go(config(in_sample_period=truncated))
    if result.open_positions:
        assert any("still open" in warning for warning in result.warnings)
        metrics = compute_metrics(result, config(), label="w", period=truncated)
        assert metrics.values["open_position_count"] == len(result.open_positions)


def test_results_validate_against_the_frozen_backtest_schema():
    with (SCHEMAS / "backtest_results_response.schema.json").open(encoding="utf-8") as fh:
        schema = json.load(fh)
    payload = contract_payload(
        go(), config(), source="Fialda FData", freshness_status="current"
    )
    jsonschema.validate(payload, schema)


def test_the_contract_trade_shape_is_narrower_than_the_recorded_one():
    """Documents what the API drops, so the loss is visible and testable.

    If the lead integrator widens the `Trade` contract, this test fails and
    the change proposal in the handoff gets revisited instead of going stale.
    """

    result = go()
    assert result.trades
    trade = result.trades[0]
    full = set(trade.as_dict())
    narrow = set(trade.contract_dict())
    dropped = full - narrow
    assert {"holding_sessions", "entry_reason", "exit_reason", "gross_pnl"} <= dropped
    assert trade.contract_dict()["pnl"] == trade.net_pnl


# --------------------------------------------------------- reproducibility


def test_a_run_reproduces_exactly_from_the_same_configuration():
    first = go()
    second = go()
    assert first.run_id == second.run_id
    assert first.equity_curve == second.equity_curve
    assert [trade.as_dict() for trade in first.trades] == [
        trade.as_dict() for trade in second.trades
    ]


def test_run_id_changes_when_any_control_changes():
    base = compute_run_id(config(), "v1")
    assert base != compute_run_id(config(slippage_rate=0.001), "v1")
    assert base != compute_run_id(config(max_concurrent_positions=2), "v1")
    assert base != compute_run_id(config(exit_convention=NEXT_CLOSE), "v1")
    assert base != compute_run_id(config(), "v2")


def test_the_saved_configuration_is_json_serializable():
    """A run record that cannot be written to disk is not a run record."""

    text = json.dumps(config().as_dict(), sort_keys=True)
    assert json.loads(text)["entry_convention"] == NEXT_OPEN
