"""Section 16 required outputs, each with its definition recorded.

Section 16 lists sixteen required outputs and says of two of them, Sharpe and
Sortino, "with definitions". That qualifier is treated here as applying to all
of them, because every one of these metrics has more than one defensible
convention and a number without its convention is not a result. `DEFINITIONS`
carries a prose definition for every metric this module produces, it travels
with the metrics in `MetricSet.as_dict()`, and
`tests/quant/test_backtest_metrics.py` fails if a metric is produced without
one.

The conventions chosen, stated once so they are arguable rather than hidden:

- Returns are simple daily returns of the equity curve, not log returns.
- Volatility, Sharpe, and Sortino annualize by the square root of
  `trading_days_per_year`, default 252.
- Sharpe and Sortino use the *sample* standard deviation (ddof=1). With a
  short backtest the difference from the population form is not negligible.
- Sortino's downside deviation is computed over *all* observations, with
  upside deviations entered as zero, rather than over the subset of negative
  observations. Both are in use; averaging over only the negative days
  inflates the ratio for a strategy that is rarely in the market, which is
  exactly the kind of strategy this system will screen for.
- Maximum drawdown is reported as a negative fraction.
- Profit factor is `None`, never infinity, when there are no losing trades.
  An infinity would survive into a fact bundle as an apparently enormous
  number; `None` says "undefined" and stays undefined.
- Win rate, profit factor, and average holding period are computed over
  *closed* trades. Positions still open at the end of the period are excluded
  and counted separately, because scoring an unrealized position as a win
  would be a result the simulation never observed.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from .config import BacktestConfig, Period
from .engine import BacktestResult, Trade

DEFINITIONS: dict[str, str] = {
    "total_return": (
        "final_equity / initial_equity - 1, over the sessions in the window. "
        "Simple, not annualized."
    ),
    "cagr": (
        "(final_equity / initial_equity) ** (1 / years) - 1, where years = "
        "sessions / trading_days_per_year. Null when the window is shorter than "
        "one session or the final equity is not positive."
    ),
    "annualized_return": (
        "mean(daily simple returns) * trading_days_per_year. The arithmetic "
        "annualization, reported alongside the geometric CAGR because the two "
        "differ whenever returns are volatile and the difference is informative."
    ),
    "volatility": (
        "sample standard deviation (ddof=1) of daily simple returns, multiplied "
        "by sqrt(trading_days_per_year)."
    ),
    "sharpe": (
        "mean(daily excess return) / sample standard deviation (ddof=1) of daily "
        "excess return, multiplied by sqrt(trading_days_per_year), where excess = "
        "daily return - risk_free_rate_annual / trading_days_per_year. Null when "
        "fewer than two return observations exist or the deviation is zero."
    ),
    "sortino": (
        "mean(daily excess return) / downside deviation, multiplied by "
        "sqrt(trading_days_per_year). Downside deviation is "
        "sqrt(mean(min(excess, 0) ** 2)) taken over ALL observations, not only "
        "negative ones, with the minimum acceptable return set to the daily "
        "risk-free rate. Null when there is no downside deviation."
    ),
    "max_drawdown": (
        "min over sessions of (equity / running_peak_equity - 1). Reported as a "
        "negative fraction; 0.0 means the equity curve never fell below a prior "
        "peak."
    ),
    "max_drawdown_date": "Session on which the maximum drawdown was reached.",
    "win_rate": (
        "closed trades with net_pnl > 0, divided by the number of closed trades. "
        "A trade with exactly zero net profit and loss counts as neither a win "
        "nor a loss in the numerator. Null when no trade closed."
    ),
    "profit_factor": (
        "sum of net_pnl over profitable closed trades divided by the absolute sum "
        "of net_pnl over losing closed trades. Null, never infinity, when there "
        "are no losing trades or no closed trades."
    ),
    "average_holding_period_days": (
        "mean number of trading sessions between entry fill and exit fill over "
        "closed trades, counted on the backtest calendar rather than in calendar "
        "days. Null when no trade closed."
    ),
    "turnover": (
        "total traded notional across both sides divided by mean equity, then "
        "divided by years, giving an annualized turnover multiple. Both a buy and "
        "the matching sell count toward the numerator."
    ),
    "exposure": (
        "mean over sessions of (market value of open positions / total equity). "
        "1.0 means fully invested every session; 0.0 means never invested."
    ),
    "trade_count": "Number of closed round trips in the window.",
    "open_position_count": (
        "Positions still open at the end of the window. Excluded from win rate, "
        "profit factor, and average holding period."
    ),
    "benchmark_total_return": "Benchmark close-to-close simple return over the window.",
    "benchmark_cagr": "CAGR of the benchmark over the same sessions, same formula.",
    "excess_return_vs_benchmark": "total_return - benchmark_total_return.",
    "beta": (
        "covariance(strategy daily returns, benchmark daily returns) / "
        "variance(benchmark daily returns), both sample estimates (ddof=1), over "
        "sessions where both series have a return."
    ),
    "alpha_annualized": (
        "(mean strategy daily excess return - beta * mean benchmark daily excess "
        "return) * trading_days_per_year, with excess measured against the daily "
        "risk-free rate."
    ),
    "correlation": "Pearson correlation of daily returns with the benchmark.",
    "tracking_error": (
        "sample standard deviation (ddof=1) of (strategy daily return - benchmark "
        "daily return), annualized by sqrt(trading_days_per_year)."
    ),
    "information_ratio": (
        "mean(strategy daily return - benchmark daily return) * "
        "trading_days_per_year / tracking_error. Null when tracking error is zero."
    ),
}


def _returns(values: Sequence[float]) -> list[float]:
    out: list[float] = []
    for previous, current in itertools.pairwise(values):
        out.append(current / previous - 1.0 if previous else 0.0)
    return out


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sample_stdev(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


@dataclass(frozen=True, slots=True)
class MetricSet:
    """One window's metrics, always accompanied by their definitions."""

    label: str
    period: Mapping[str, str]
    sessions: int
    values: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "period": dict(self.period),
            "sessions": self.sessions,
            "metrics": dict(self.values),
            "definitions": {
                name: DEFINITIONS[name] for name in sorted(self.values) if name in DEFINITIONS
            },
        }

    def contract_metrics(self) -> dict[str, Any]:
        """`BacktestMetrics` shape from `backtest_results_response.schema.json`.

        The contract requires non-null `volatility`, `sharpe`, `sortino`,
        `max_drawdown`, `win_rate`, `profit_factor`,
        `average_holding_period_days`, `turnover`, and `exposure`. Any of
        those can be genuinely undefined on a short or trade-free window, so
        an undefined value is emitted as 0.0 and the reason is recorded in
        `benchmark_comparison["undefined_metrics"]` rather than a null being
        smuggled past a required field. A consumer that needs to know the
        difference between "zero" and "undefined" must read that list; this
        is raised as a contract-change proposal in the handoff.
        """

        undefined = sorted(
            name
            for name in (
                "volatility",
                "sharpe",
                "sortino",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "average_holding_period_days",
                "turnover",
                "exposure",
            )
            if self.values.get(name) is None
        )
        comparison = dict(self.values.get("benchmark_comparison") or {})
        comparison["undefined_metrics"] = undefined
        comparison["definitions"] = {
            name: DEFINITIONS[name]
            for name in sorted(comparison)
            if name in DEFINITIONS
        }
        return {
            "cagr": self.values.get("cagr"),
            "annualized_return": self.values.get("annualized_return"),
            "volatility": float(self.values.get("volatility") or 0.0),
            "sharpe": float(self.values.get("sharpe") or 0.0),
            "sortino": float(self.values.get("sortino") or 0.0),
            "max_drawdown": float(self.values.get("max_drawdown") or 0.0),
            "win_rate": float(self.values.get("win_rate") or 0.0),
            "profit_factor": float(self.values.get("profit_factor") or 0.0),
            "average_holding_period_days": float(
                self.values.get("average_holding_period_days") or 0.0
            ),
            "turnover": float(self.values.get("turnover") or 0.0),
            "exposure": float(self.values.get("exposure") or 0.0),
            "benchmark_comparison": comparison,
        }


def _benchmark_returns(
    result: BacktestResult, sessions: Sequence[date], benchmark_closes: Mapping[date, float]
) -> list[float] | None:
    closes = [benchmark_closes.get(day) for day in sessions]
    if any(value is None or value <= 0 for value in closes):
        return None
    return _returns([float(value) for value in closes])  # type: ignore[arg-type]


def compute_metrics(
    result: BacktestResult,
    config: BacktestConfig,
    *,
    label: str,
    period: Period,
    benchmark_closes: Mapping[date, float] | None = None,
) -> MetricSet:
    """Every Section 16 output metric for one window of the run."""

    indices = [
        position
        for position, day in enumerate(result.calendar)
        if period.contains(day)
    ]
    if not indices:
        return MetricSet(label=label, period=period.as_dict(), sessions=0, values={})

    first, last = indices[0], indices[-1]
    sessions = result.calendar[first : last + 1]
    equity = list(result.equity_curve[first : last + 1])
    exposure = list(result.exposure_curve[first : last + 1])
    notional = list(result.traded_notional_curve[first : last + 1])

    # The opening equity of a window is the closing equity of the session
    # before it, so a mid-period window is not credited with the jump into it.
    opening_equity = (
        result.equity_curve[first - 1] if first > 0 else config.initial_capital
    )
    series = [opening_equity, *equity]
    returns = _returns(series)
    year_length = config.trading_days_per_year
    years = len(sessions) / year_length
    daily_rf = config.risk_free_rate_annual / year_length
    excess = [value - daily_rf for value in returns]

    total_return = equity[-1] / opening_equity - 1.0 if opening_equity else None
    cagr = (
        (equity[-1] / opening_equity) ** (1.0 / years) - 1.0
        if opening_equity > 0 and equity[-1] > 0 and years > 0
        else None
    )
    mean_return = _mean(returns)
    stdev = _sample_stdev(returns)
    excess_mean = _mean(excess)
    excess_stdev = _sample_stdev(excess)
    downside = (
        math.sqrt(sum(min(value, 0.0) ** 2 for value in excess) / len(excess))
        if excess
        else None
    )

    peak = -math.inf
    max_drawdown = 0.0
    max_drawdown_date: date | None = None
    for day, value in zip(sessions, equity):
        peak = max(peak, value)
        if peak > 0:
            drawdown = value / peak - 1.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown
                max_drawdown_date = day

    closed = [trade for trade in result.trades if period.contains(trade.exit_date)]
    wins = [trade for trade in closed if trade.net_pnl > 0]
    losses = [trade for trade in closed if trade.net_pnl < 0]
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))

    mean_equity = _mean(equity) or 0.0
    values: dict[str, Any] = {
        "total_return": total_return,
        "cagr": cagr,
        "annualized_return": None if mean_return is None else mean_return * year_length,
        "volatility": None if stdev is None else stdev * math.sqrt(year_length),
        "sharpe": (
            None
            if excess_mean is None or not excess_stdev
            else excess_mean / excess_stdev * math.sqrt(year_length)
        ),
        "sortino": (
            None
            if excess_mean is None or not downside
            else excess_mean / downside * math.sqrt(year_length)
        ),
        "max_drawdown": max_drawdown,
        "max_drawdown_date": None if max_drawdown_date is None else max_drawdown_date.isoformat(),
        "win_rate": len(wins) / len(closed) if closed else None,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "average_holding_period_days": (
            sum(trade.holding_sessions for trade in closed) / len(closed)
            if closed
            else None
        ),
        "turnover": (
            sum(notional) / mean_equity / years if mean_equity and years else None
        ),
        "exposure": _mean(exposure),
        "trade_count": len(closed),
        "open_position_count": len(result.open_positions),
    }

    comparison: dict[str, Any] = {"benchmark": config.benchmark}
    if benchmark_closes:
        benchmark_series = _benchmark_returns(result, sessions, benchmark_closes)
        if benchmark_series is None:
            comparison["status"] = "unavailable"
            comparison["reason"] = (
                "the benchmark has no positive close on at least one session of this "
                "window; no value was interpolated"
            )
        else:
            opening = benchmark_closes.get(
                result.calendar[first - 1] if first > 0 else sessions[0]
            )
            closing = benchmark_closes[sessions[-1]]
            benchmark_total = (
                closing / opening - 1.0 if opening and opening > 0 else None
            )
            paired = list(zip(returns, benchmark_series))
            comparison["status"] = "available"
            comparison["benchmark_total_return"] = benchmark_total
            comparison["benchmark_cagr"] = (
                (closing / opening) ** (1.0 / years) - 1.0
                if opening and opening > 0 and closing > 0 and years > 0
                else None
            )
            comparison["excess_return_vs_benchmark"] = (
                None
                if total_return is None or benchmark_total is None
                else total_return - benchmark_total
            )
            if len(paired) >= 2:
                strategy_returns = [item[0] for item in paired]
                bench_returns = [item[1] for item in paired]
                bench_mean = _mean(bench_returns) or 0.0
                strat_mean = _mean(strategy_returns) or 0.0
                covariance = sum(
                    (a - strat_mean) * (b - bench_mean) for a, b in paired
                ) / (len(paired) - 1)
                bench_variance = sum((b - bench_mean) ** 2 for b in bench_returns) / (
                    len(paired) - 1
                )
                beta = covariance / bench_variance if bench_variance else None
                comparison["beta"] = beta
                comparison["alpha_annualized"] = (
                    None
                    if beta is None
                    else ((strat_mean - daily_rf) - beta * (bench_mean - daily_rf))
                    * year_length
                )
                strat_stdev = _sample_stdev(strategy_returns)
                bench_stdev = _sample_stdev(bench_returns)
                comparison["correlation"] = (
                    covariance / (strat_stdev * bench_stdev)
                    if strat_stdev and bench_stdev
                    else None
                )
                differences = [a - b for a, b in paired]
                diff_stdev = _sample_stdev(differences)
                tracking = None if diff_stdev is None else diff_stdev * math.sqrt(year_length)
                comparison["tracking_error"] = tracking
                comparison["information_ratio"] = (
                    None
                    if not tracking
                    else (_mean(differences) or 0.0) * year_length / tracking
                )
    else:
        comparison["status"] = "not_configured" if config.benchmark is None else "no_data"
        comparison["reason"] = (
            "no benchmark was configured"
            if config.benchmark is None
            else "a benchmark was configured but no benchmark series was supplied"
        )
    values["benchmark_comparison"] = comparison

    return MetricSet(
        label=label,
        period=period.as_dict(),
        sessions=len(sessions),
        values=values,
    )


def summarize(
    result: BacktestResult,
    config: BacktestConfig,
    *,
    benchmark_closes: Mapping[date, float] | None = None,
) -> dict[str, Any]:
    """Full, in-sample, and out-of-sample metric sets plus the run record.

    Section 16 requires "In-sample and out-of-sample periods" as a control and
    the whole point of the control is that the two are reported separately. A
    single blended number would hide exactly the degradation an out-of-sample
    test exists to reveal.
    """

    windows = [("full", config.full_period), ("in_sample", config.in_sample_period)]
    if config.out_of_sample_period is not None:
        windows.append(("out_of_sample", config.out_of_sample_period))

    metrics = {
        label: compute_metrics(
            result,
            config,
            label=label,
            period=period,
            benchmark_closes=benchmark_closes,
        ).as_dict()
        for label, period in windows
    }
    return {
        "run_id": result.run_id,
        "strategy_id": config.strategy_id,
        "strategy_version": result.strategy_version,
        "data_version": result.data_version,
        "config": dict(result.config),
        "metrics": metrics,
        "metric_definitions": dict(DEFINITIONS),
        "equity_curve": [
            {"trading_date": day.isoformat(), "equity": value}
            for day, value in zip(result.calendar, result.equity_curve)
        ],
        "drawdown_curve": drawdown_curve(result),
        "trades": [trade.as_dict() for trade in result.trades],
        "open_positions": [dict(item) for item in result.open_positions],
        "warnings": list(result.warnings),
        "excluded_fundamentals": [dict(item) for item in result.excluded_fundamentals],
    }


def contract_payload(
    result: BacktestResult,
    config: BacktestConfig,
    *,
    source: str,
    freshness_status: str,
    status: str = "completed",
    benchmark_closes: Mapping[date, float] | None = None,
) -> dict[str, Any]:
    """`BacktestResultsResponse` shape from the frozen 0.1.0 contract.

    Narrower than `summarize()` in three ways, each a deliberate loss recorded
    as a change proposal in the handoff: the trade records drop the holding
    period and the entry and exit reasons, only the full-period metric set
    fits, and undefined metrics are emitted as 0.0 with their names listed
    under `benchmark_comparison.undefined_metrics`. Use `summarize()` for
    anything that is not an API response.
    """

    metrics = compute_metrics(
        result,
        config,
        label="full",
        period=config.full_period,
        benchmark_closes=benchmark_closes,
    )
    return {
        "run_id": result.run_id,
        "status": status,
        "trades": [trade.contract_dict() for trade in result.trades],
        "equity_curve": [
            {"trading_date": day.isoformat(), "equity": value}
            for day, value in zip(result.calendar, result.equity_curve)
        ],
        "drawdown_curve": drawdown_curve(result),
        "metrics": metrics.contract_metrics(),
        "data_version": result.data_version,
        "strategy_version": result.strategy_version,
        "warnings": list(result.warnings),
        "provenance": {
            "as_of_date": result.calendar[-1].isoformat(),
            "data_version": result.data_version,
            "source": source,
            "freshness_status": freshness_status,
            "warnings": list(result.warnings),
        },
    }


def drawdown_curve(result: BacktestResult) -> list[dict[str, Any]]:
    """`DrawdownCurvePoint` series: equity over its running peak, minus one."""

    points: list[dict[str, Any]] = []
    peak = -math.inf
    for day, value in zip(result.calendar, result.equity_curve):
        peak = max(peak, value)
        points.append(
            {
                "trading_date": day.isoformat(),
                "drawdown": (value / peak - 1.0) if peak > 0 else 0.0,
            }
        )
    return points


def closed_trades(result: BacktestResult) -> tuple[Trade, ...]:
    return result.trades
