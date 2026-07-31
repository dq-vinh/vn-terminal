"""Daily-bar backtest engine (WP8).

The whole design is organized around one invariant, stated once here and
tested in `tests/quant/test_lookahead_adversarial.py`:

    While the engine is processing session `d`, it never reads a bar dated
    after `d`, for any symbol, for any purpose.

Everything else follows from it. Each session is processed in three phases,
in this order:

1. **Execute.** Orders placed on an earlier session are filled against
   *this* session's bar. The engine is standing on `d`, so reading `open[d]`
   or `close[d]` is present information, not future information.
2. **Mark.** Open positions are marked at `close[d]`, producing the equity
   point for `d`.
3. **Decide.** Strategies are evaluated on an `AsOfWindow` ending at `d` and
   may place orders for the *next* session.

The ordering is what makes "evaluate at `t`, execute at `t+1`" true rather
than merely intended: a decision made in phase 3 of session `d` cannot be
executed until phase 1 of session `d+1`, and by then the engine has advanced.
There is no code path in which a decision and its own fill happen on the same
bar, and no code path in which a fill price is known to the decision that
produced it.

Position sizing uses equity marked at the *previous* close, for the same
reason. Sizing an order from equity that includes the execution bar's own
close would import a price the decision could not have known.

Three further Section 16 bias controls are enforced at construction, before
any bar is read: a survivorship-filtered universe is refused, a mixed
price-adjustment convention is refused, and fundamentals without a
publication date are excluded from the run rather than assumed.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..strategies import registry as strategy_registry
from ..strategies.types import (
    OrderIntent,
    OrderSide,
    OrderStatus,
    PositionState,
    SecurityView,
    StrategyEvaluation,
    SymbolHistory,
)
from .config import (
    FIXED_CASH_AMOUNT,
    FIXED_FRACTION_OF_EQUITY,
    FIXED_SHARES,
    NEXT_OPEN,
    BacktestConfig,
)


class BacktestError(RuntimeError):
    """Base class for refusals that protect a result's validity."""


class SurvivorshipBiasError(BacktestError):
    """Raised when the universe was built from currently-active securities."""


class AdjustmentConventionError(BacktestError):
    """Raised when histories disagree about their price-adjustment status."""


class PublicationDateError(BacktestError):
    """Raised when a fundamental input lacks a publication date."""


@dataclass(frozen=True, slots=True)
class FundamentalObservation:
    """A fundamental input, admissible only with a publication date.

    Section 17 and Section 16 agree on this: an observation whose publication
    date is unknown cannot be placed on a timeline, and placing it at its
    period end instead would hand the simulation figures months before the
    market saw them. `publication_date` is therefore `date | None` and a
    `None` is a hard exclusion, never a fallback to `period_end`.
    """

    symbol: str
    period_end: date
    metric_code: str
    value: float
    publication_date: date | None = None


@dataclass(frozen=True, slots=True)
class PendingOrder:
    intent: OrderIntent
    decision_session: int
    earliest_session: int
    convention: str

    @property
    def is_exit(self) -> bool:
        return self.intent.side is OrderSide.SELL


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: str
    trading_date: date
    reference_price: float
    fill_price: float
    quantity: int
    notional: float
    transaction_cost: float
    slippage_cost: float
    convention: str
    reason: str


@dataclass(frozen=True, slots=True)
class Trade:
    """One completed round trip.

    Field set follows `contracts/OPEN_ITEMS.md` section B's note that the
    plan requires a "Trade list" without giving a per-trade field list, and
    extends the interim shape with the holding period and the reasons, both
    of which Section 16 requires as metrics or evidence elsewhere.
    """

    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    quantity: int
    gross_pnl: float
    costs: float
    net_pnl: float
    return_pct: float
    holding_sessions: int
    entry_reason: str
    exit_reason: str
    transaction_cost_paid: float = 0.0
    slippage_paid: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date.isoformat(),
            "entry_price": self.entry_price,
            "exit_date": self.exit_date.isoformat(),
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "gross_pnl": self.gross_pnl,
            "costs": self.costs,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "holding_sessions": self.holding_sessions,
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
            "transaction_cost_paid": self.transaction_cost_paid,
            "slippage_paid": self.slippage_paid,
        }

    def contract_dict(self) -> dict[str, Any]:
        """The frozen 0.1.0 `Trade` shape, which is narrower than this one.

        `additionalProperties: false` on nine fields, none of which is the
        holding period, the entry and exit reasons, or the split between gross
        and net profit. Those are dropped here and kept in `as_dict()`; a
        change proposal to widen the contract is in the handoff. `pnl` is
        mapped from `net_pnl`, because a profit figure that excluded the costs
        the same record reports would be the more misleading of the two.
        """

        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date.isoformat(),
            "entry_price": self.entry_price,
            "exit_date": self.exit_date.isoformat(),
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.net_pnl,
            "transaction_cost_paid": self.transaction_cost_paid,
            "slippage_paid": self.slippage_paid,
        }


@dataclass
class OpenPosition:
    symbol: str
    quantity: int
    entry_date: date
    entry_price: float
    entry_session: int
    entry_costs: float
    entry_reason: str
    last_mark: float
    entry_slippage: float = 0.0


@dataclass(frozen=True, slots=True)
class OrderEvent:
    """Every order decision and its outcome, for audit and for bias tests."""

    trading_date: date
    symbol: str
    side: str
    status: str
    detail: str
    decision_date: date


@dataclass(frozen=True, slots=True)
class BacktestResult:
    run_id: str
    config: Mapping[str, Any]
    strategy_version: str
    data_version: str
    calendar: tuple[date, ...]
    equity_curve: tuple[float, ...]
    cash_curve: tuple[float, ...]
    exposure_curve: tuple[float, ...]
    traded_notional_curve: tuple[float, ...]
    trades: tuple[Trade, ...]
    open_positions: tuple[Mapping[str, Any], ...]
    fills: tuple[Fill, ...]
    order_events: tuple[OrderEvent, ...]
    warnings: tuple[str, ...] = ()
    excluded_fundamentals: tuple[Mapping[str, Any], ...] = ()
    evaluations: tuple[StrategyEvaluation, ...] = ()
    max_history_index_read: Mapping[str, int] = field(default_factory=dict)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_run_id(config: BacktestConfig, data_version: str) -> str:
    material = {
        "schema": "vn_terminal_backtest_run_v1",
        "config": config.as_dict(),
        "data_version": data_version,
    }
    digest = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    return f"backtest-{config.strategy_id}-{digest[:16]}"


SecurityResolver = Callable[[str, date], SecurityView | None]


class BacktestEngine:
    """Runs one strategy over a daily-bar universe."""

    def __init__(
        self,
        config: BacktestConfig,
        histories: Mapping[str, SymbolHistory],
        *,
        data_version: str = "unspecified",
        security_resolver: SecurityResolver | None = None,
        benchmark_history: SymbolHistory | None = None,
        fundamentals: Sequence[FundamentalObservation] = (),
    ) -> None:
        self.config = config
        self.data_version = data_version
        self.security_resolver = security_resolver
        self.benchmark_history = benchmark_history
        self._warnings: list[str] = []
        self._excluded_fundamentals: list[dict[str, Any]] = []

        self._guard_survivorship()
        self.histories = self._guard_universe(histories)
        self._guard_adjustment_convention()
        self.admissible_fundamentals = self._guard_fundamentals(fundamentals)

        self.parameters = strategy_registry.resolve_parameters(
            config.strategy_id, config.strategy_parameters
        )
        self.strategy_version = strategy_registry.get(config.strategy_id).version
        self.warmup = strategy_registry.warmup_bars(config.strategy_id, self.parameters)

    # ------------------------------------------------------------- guards

    def _guard_survivorship(self) -> None:
        if self.config.universe_is_survivorship_filtered:
            raise SurvivorshipBiasError(
                "The symbol universe was built from currently-active securities. "
                "Section 16 requires 'No survivorship-only universe', and the data "
                "handoff records 301 stock files ending in terminal zero-volume runs "
                "that must remain in the historical universe. Pass the full "
                "historical universe, including delisted and terminally inactive "
                "symbols, and set universe_is_survivorship_filtered=False."
            )

    def _guard_universe(
        self, histories: Mapping[str, SymbolHistory]
    ) -> dict[str, SymbolHistory]:
        missing = sorted(set(self.config.symbol_universe) - set(histories))
        if missing:
            raise BacktestError(
                f"no history supplied for {missing}. A symbol named in the universe "
                "but silently dropped would reintroduce survivorship bias through "
                "the back door."
            )
        return {symbol: histories[symbol] for symbol in sorted(self.config.symbol_universe)}

    def _guard_adjustment_convention(self) -> None:
        declared = self.config.price_adjustment_convention
        mismatched = sorted(
            symbol
            for symbol, history in self.histories.items()
            if history.adjustment_status != declared
        )
        if mismatched:
            observed = sorted(
                {self.histories[symbol].adjustment_status for symbol in mismatched}
            )
            raise AdjustmentConventionError(
                f"the run declares price_adjustment_convention={declared!r} but "
                f"{len(mismatched)} symbols carry {observed}. Section 16 requires "
                "corporate-action consistency; mixing adjusted and unadjusted series "
                "produces returns that are arithmetically valid and economically "
                f"meaningless. First mismatches: {mismatched[:10]}."
            )
        if self.benchmark_history is not None and (
            self.benchmark_history.adjustment_status != declared
        ):
            raise AdjustmentConventionError(
                f"the benchmark carries adjustment_status="
                f"{self.benchmark_history.adjustment_status!r}, not {declared!r}"
            )

    def _guard_fundamentals(
        self, fundamentals: Sequence[FundamentalObservation]
    ) -> tuple[FundamentalObservation, ...]:
        admissible: list[FundamentalObservation] = []
        for item in fundamentals:
            if item.publication_date is None:
                self._excluded_fundamentals.append(
                    {
                        "symbol": item.symbol,
                        "period_end": item.period_end.isoformat(),
                        "metric_code": item.metric_code,
                        "reason": "missing_publication_date",
                    }
                )
                continue
            admissible.append(item)
        if self._excluded_fundamentals:
            self._warnings.append(
                f"{len(self._excluded_fundamentals)} fundamental observations were "
                "excluded because they carry no publication date. Section 16 forbids "
                "using financial information published after the simulated decision "
                "date, and Section 17 requires exclusion rather than assumption when "
                "the publication date is unavailable."
            )
        required = set(strategy_registry.metadata(self.config.strategy_id).required_fields)
        if any(name.startswith("fundamentals.") for name in required) and (
            self._excluded_fundamentals
        ):
            raise PublicationDateError(
                f"{self.config.strategy_id} requires fundamental inputs, but "
                f"{len(self._excluded_fundamentals)} observations lack a publication "
                "date and were excluded. The backtest cannot proceed on a partial "
                "fundamental history without silently changing what the strategy sees."
            )
        return tuple(admissible)

    # ------------------------------------------------------------- helpers

    def _calendar(self) -> list[date]:
        period = self.config.full_period
        sessions: set[date] = set()
        for history in self.histories.values():
            sessions.update(history.trading_dates)
        return sorted(day for day in sessions if period.contains(day))

    def _price_for(self, symbol: str, index: int, convention: str) -> float:
        history = self.histories[symbol]
        return float(
            history.open[index] if convention == NEXT_OPEN else history.close[index]
        )

    def _executable(self, symbol: str, index: int, convention: str) -> tuple[bool, str]:
        """The approved specification's executable-bar checks.

        "The entry executes at open[t+1] only if quality_status[t+1] ==
        'valid'; open[t+1] is finite and greater than zero; and volume[t+1] >
        0." The same checks apply to exits. A suspended symbol has no bar at
        all and is handled by the caller before this is reached.
        """

        history = self.histories[symbol]
        if history.quality_status[index] != "valid":
            return False, f"quality_status={history.quality_status[index]!r}"
        price = self._price_for(symbol, index, convention)
        if not math.isfinite(price) or price <= 0:
            return False, f"{convention} price {price!r} is not finite and positive"
        volume = float(history.volume[index])
        if not (volume > 0):
            return False, "zero volume on the execution bar"
        if volume < self.config.liquidity_constraint.min_execution_bar_volume:
            return False, (
                f"execution bar volume {volume:g} below the configured minimum "
                f"{self.config.liquidity_constraint.min_execution_bar_volume:g}"
            )
        return True, "executable"

    def _size_order(self, symbol: str, price: float, equity: float, cash: float) -> int:
        sizing = self.config.position_size
        if sizing.mode == FIXED_SHARES:
            target = int(sizing.value)
        elif sizing.mode == FIXED_CASH_AMOUNT:
            target = int(sizing.value // price)
        elif sizing.mode == FIXED_FRACTION_OF_EQUITY:
            target = int((equity * sizing.value) // price)
        else:  # pragma: no cover - guarded in PositionSizing
            raise BacktestError(f"unsupported position size mode {sizing.mode!r}")
        gross_rate = 1.0 + self.config.transaction_cost_rate + self.config.slippage_rate
        affordable = int(cash // (price * gross_rate)) if price > 0 else 0
        target = min(target, affordable)
        if sizing.lot_size > 1:
            target -= target % sizing.lot_size
        return max(0, target)

    def _apply_liquidity_cap(self, symbol: str, index: int, quantity: int) -> tuple[int, str]:
        participation = self.config.liquidity_constraint.max_participation_of_bar_volume
        if participation is None or quantity <= 0:
            return quantity, ""
        volume = float(self.histories[symbol].volume[index])
        cap = int(volume * participation)
        if self.config.position_size.lot_size > 1:
            cap -= cap % self.config.position_size.lot_size
        if quantity <= cap:
            return quantity, ""
        if self.config.liquidity_constraint.reject_partial_fills:
            return 0, (
                f"rejected: {quantity} shares exceed the {participation:.0%} "
                f"participation cap of {cap} shares"
            )
        return max(0, cap), (
            f"capped from {quantity} to {max(0, cap)} shares by the "
            f"{participation:.0%} participation limit"
        )

    # ----------------------------------------------------------------- run

    def run(self) -> BacktestResult:
        config = self.config
        calendar = self._calendar()
        if not calendar:
            raise BacktestError(
                "no trading sessions fall inside the configured periods"
            )

        cash = config.initial_capital
        positions: dict[str, OpenPosition] = {}
        pending: list[PendingOrder] = []
        trades: list[Trade] = []
        fills: list[Fill] = []
        events: list[OrderEvent] = []
        evaluations: list[StrategyEvaluation] = []
        equity_curve: list[float] = []
        cash_curve: list[float] = []
        exposure_curve: list[float] = []
        traded_notional: list[float] = []
        highest_index_read: dict[str, int] = {}
        previous_equity = config.initial_capital

        # Index of each symbol's bars by session, resolved once. Only lookups
        # are performed during the loop; no scan can drift forward.
        session_index: dict[str, dict[date, int]] = {
            symbol: {day: position for position, day in enumerate(history.trading_dates)}
            for symbol, history in self.histories.items()
        }

        def note_read(symbol: str, index: int) -> None:
            if index > highest_index_read.get(symbol, -1):
                highest_index_read[symbol] = index

        for session, day in enumerate(calendar):
            session_notional = 0.0

            # ---------------------------------------------------- 1. execute
            still_pending: list[PendingOrder] = []
            for order in sorted(
                pending, key=lambda item: (not item.is_exit, item.intent.symbol)
            ):
                symbol = order.intent.symbol
                if order.earliest_session > session:
                    still_pending.append(order)
                    continue
                index = session_index[symbol].get(day)
                if index is None:
                    detail = "no bar on this session (suspended or not listed)"
                    if order.is_exit:
                        still_pending.append(order)
                        events.append(
                            OrderEvent(
                                day,
                                symbol,
                                order.intent.side.value,
                                OrderStatus.PENDING_EXIT.value,
                                detail,
                                order.intent.decision_date,
                            )
                        )
                    else:
                        events.append(
                            OrderEvent(
                                day,
                                symbol,
                                order.intent.side.value,
                                OrderStatus.CANCELLED.value,
                                detail,
                                order.intent.decision_date,
                            )
                        )
                    continue

                note_read(symbol, index)
                ok, reason = self._executable(symbol, index, order.convention)
                if not ok:
                    if order.is_exit:
                        still_pending.append(order)
                        events.append(
                            OrderEvent(
                                day,
                                symbol,
                                order.intent.side.value,
                                OrderStatus.PENDING_EXIT.value,
                                reason,
                                order.intent.decision_date,
                            )
                        )
                    else:
                        events.append(
                            OrderEvent(
                                day,
                                symbol,
                                order.intent.side.value,
                                OrderStatus.CANCELLED.value,
                                reason,
                                order.intent.decision_date,
                            )
                        )
                    continue

                reference = self._price_for(symbol, index, order.convention)
                if order.is_exit:
                    position = positions.get(symbol)
                    if position is None:
                        events.append(
                            OrderEvent(
                                day,
                                symbol,
                                order.intent.side.value,
                                OrderStatus.CANCELLED.value,
                                "position already closed",
                                order.intent.decision_date,
                            )
                        )
                        continue
                    fill_price = reference * (1.0 - config.slippage_rate)
                    notional = fill_price * position.quantity
                    cost = notional * config.transaction_cost_rate
                    slip = reference * config.slippage_rate * position.quantity
                    cash += notional - cost
                    session_notional += notional
                    fills.append(
                        Fill(
                            symbol,
                            "sell",
                            day,
                            reference,
                            fill_price,
                            position.quantity,
                            notional,
                            cost,
                            slip,
                            order.convention,
                            order.intent.reason,
                        )
                    )
                    gross = (fill_price - position.entry_price) * position.quantity
                    total_costs = position.entry_costs + cost
                    invested = position.entry_price * position.quantity
                    trades.append(
                        Trade(
                            symbol=symbol,
                            entry_date=position.entry_date,
                            entry_price=position.entry_price,
                            exit_date=day,
                            exit_price=fill_price,
                            quantity=position.quantity,
                            gross_pnl=gross,
                            costs=total_costs,
                            net_pnl=gross - cost,
                            return_pct=(gross - cost) / invested if invested else 0.0,
                            holding_sessions=session - position.entry_session,
                            entry_reason=position.entry_reason,
                            exit_reason=order.intent.reason,
                            transaction_cost_paid=total_costs,
                            slippage_paid=position.entry_slippage + slip,
                        )
                    )
                    del positions[symbol]
                    events.append(
                        OrderEvent(
                            day,
                            symbol,
                            "sell",
                            OrderStatus.EXECUTED.value,
                            f"filled {position.quantity} at {fill_price:.6f}",
                            order.intent.decision_date,
                        )
                    )
                    continue

                # --- entry
                if symbol in positions:
                    events.append(
                        OrderEvent(
                            day,
                            symbol,
                            "buy",
                            OrderStatus.CANCELLED.value,
                            "already long; pyramiding is prohibited",
                            order.intent.decision_date,
                        )
                    )
                    continue
                if len(positions) >= config.max_concurrent_positions:
                    events.append(
                        OrderEvent(
                            day,
                            symbol,
                            "buy",
                            OrderStatus.CANCELLED.value,
                            f"max_concurrent_positions={config.max_concurrent_positions} "
                            "already held",
                            order.intent.decision_date,
                        )
                    )
                    continue
                fill_price = reference * (1.0 + config.slippage_rate)
                quantity = self._size_order(symbol, fill_price, previous_equity, cash)
                quantity, cap_detail = self._apply_liquidity_cap(symbol, index, quantity)
                if quantity <= 0:
                    events.append(
                        OrderEvent(
                            day,
                            symbol,
                            "buy",
                            OrderStatus.CANCELLED.value,
                            cap_detail or "position size resolved to zero shares",
                            order.intent.decision_date,
                        )
                    )
                    continue
                notional = fill_price * quantity
                cost = notional * config.transaction_cost_rate
                slip = reference * config.slippage_rate * quantity
                cash -= notional + cost
                session_notional += notional
                fills.append(
                    Fill(
                        symbol,
                        "buy",
                        day,
                        reference,
                        fill_price,
                        quantity,
                        notional,
                        cost,
                        slip,
                        order.convention,
                        order.intent.reason,
                    )
                )
                positions[symbol] = OpenPosition(
                    symbol=symbol,
                    quantity=quantity,
                    entry_date=day,
                    entry_price=fill_price,
                    entry_session=session,
                    entry_costs=cost,
                    entry_reason=order.intent.reason,
                    last_mark=fill_price,
                    entry_slippage=slip,
                )
                events.append(
                    OrderEvent(
                        day,
                        symbol,
                        "buy",
                        OrderStatus.EXECUTED.value,
                        f"filled {quantity} at {fill_price:.6f}"
                        + (f"; {cap_detail}" if cap_detail else ""),
                        order.intent.decision_date,
                    )
                )
            pending = still_pending

            # ------------------------------------------------------- 2. mark
            market_value = 0.0
            for position in positions.values():
                index = session_index[position.symbol].get(day)
                if index is not None:
                    note_read(position.symbol, index)
                    close = float(self.histories[position.symbol].close[index])
                    if math.isfinite(close) and close > 0:
                        position.last_mark = close
                # A suspended symbol keeps its last observed mark. Carrying the
                # previous close is the explicit handling Section 16 asks for;
                # the alternative, marking to zero, would invent a loss.
                market_value += position.last_mark * position.quantity
            equity = cash + market_value
            equity_curve.append(equity)
            cash_curve.append(cash)
            exposure_curve.append(market_value / equity if equity > 0 else 0.0)
            traded_notional.append(session_notional)

            # ----------------------------------------------------- 3. decide
            # `exit_pending_symbols` is a snapshot of what is still
            # outstanding after phase 1 ran for this session; it is what lets
            # the strategy honor "Order semantics while an exit is pending"
            # (no duplicate exit order; a suppressed bullish crossover is
            # reported rather than silently dropped) without tracking any
            # book of its own.
            exit_pending_symbols = {order.intent.symbol for order in pending if order.is_exit}
            for symbol in self.histories:
                index = session_index[symbol].get(day)
                if index is None:
                    continue
                window = self.histories[symbol].window(index)
                security = (
                    self.security_resolver(symbol, day)
                    if self.security_resolver is not None
                    else None
                )
                position = positions.get(symbol)
                evaluation = strategy_registry.evaluate(
                    config.strategy_id,
                    window,
                    security=security,
                    position_state=(
                        PositionState.LONG if position is not None else PositionState.FLAT
                    ),
                    parameters=self.parameters,
                    exit_pending=symbol in exit_pending_symbols,
                    entry_price=position.entry_price if position is not None else None,
                )
                evaluations.append(evaluation)
                note_read(symbol, window.highest_index_read)
                if evaluation.order is not None and evaluation.order.immediate:
                    # `halt_exit_rule` (specification version 1.1.0): the fill
                    # price is already known (a row at or before today, or the
                    # entry price), so this executes now rather than being
                    # scheduled for a future bar. It supersedes any order this
                    # symbol still has outstanding.
                    assert evaluation.order.fill_price is not None
                    assert evaluation.order.fill_date is not None
                    fill_price = evaluation.order.fill_price
                    fill_date = evaluation.order.fill_date
                    still_outstanding = [
                        order for order in pending if order.intent.symbol == symbol
                    ]
                    if still_outstanding:
                        pending = [
                            order for order in pending if order.intent.symbol != symbol
                        ]
                        for order in still_outstanding:
                            events.append(
                                OrderEvent(
                                    day,
                                    symbol,
                                    order.intent.side.value,
                                    OrderStatus.CANCELLED.value,
                                    "superseded by a halt exit",
                                    order.intent.decision_date,
                                )
                            )
                    if position is not None:
                        notional = fill_price * position.quantity
                        cost = notional * config.transaction_cost_rate
                        cash += notional - cost
                        session_notional += notional
                        fills.append(
                            Fill(
                                symbol,
                                "sell",
                                day,
                                fill_price,
                                fill_price,
                                position.quantity,
                                notional,
                                cost,
                                0.0,
                                "immediate_last_trade",
                                evaluation.order.reason,
                            )
                        )
                        gross = (fill_price - position.entry_price) * position.quantity
                        total_costs = position.entry_costs + cost
                        invested = position.entry_price * position.quantity
                        trades.append(
                            Trade(
                                symbol=symbol,
                                entry_date=position.entry_date,
                                entry_price=position.entry_price,
                                exit_date=day,
                                exit_price=fill_price,
                                quantity=position.quantity,
                                gross_pnl=gross,
                                costs=total_costs,
                                net_pnl=gross - cost,
                                return_pct=(gross - cost) / invested if invested else 0.0,
                                holding_sessions=session - position.entry_session,
                                entry_reason=position.entry_reason,
                                exit_reason=evaluation.order.reason,
                                transaction_cost_paid=total_costs,
                                slippage_paid=position.entry_slippage,
                            )
                        )
                        del positions[symbol]
                        events.append(
                            OrderEvent(
                                day,
                                symbol,
                                "sell",
                                OrderStatus.EXECUTED.value,
                                f"halt exit filled {position.quantity} at "
                                f"{fill_price:.6f} (row dated "
                                f"{fill_date.isoformat()})",
                                evaluation.order.decision_date,
                            )
                        )
                    continue
                if evaluation.order is not None:
                    convention = (
                        config.entry_convention
                        if evaluation.order.side is OrderSide.BUY
                        else config.exit_convention
                    )
                    pending.append(
                        PendingOrder(
                            intent=evaluation.order,
                            decision_session=session,
                            earliest_session=session + 1,
                            convention=convention,
                        )
                    )
                    events.append(
                        OrderEvent(
                            day,
                            symbol,
                            evaluation.order.side.value,
                            OrderStatus.SCHEDULED.value,
                            f"scheduled for the next session at {convention}",
                            evaluation.order.decision_date,
                        )
                    )

            previous_equity = equity

        for order in pending:
            events.append(
                OrderEvent(
                    calendar[-1],
                    order.intent.symbol,
                    order.intent.side.value,
                    (
                        OrderStatus.PENDING_EXIT.value
                        if order.is_exit
                        else OrderStatus.CANCELLED.value
                    ),
                    "still outstanding when the backtest period ended",
                    order.intent.decision_date,
                )
            )
        if any(order.is_exit for order in pending):
            self._warnings.append(
                "One or more exit orders were still pending when the period ended. "
                "A pending exit does not expire, so it is reported rather than "
                "force-filled at a price the simulation never observed."
            )
        if positions:
            self._warnings.append(
                f"{len(positions)} positions were still open at the end of the "
                "period. They are marked to their last observed close and are "
                "excluded from closed-trade statistics; no synthetic closing trade "
                "was created, because the approved specification defines no such rule."
            )

        return BacktestResult(
            run_id=compute_run_id(config, self.data_version),
            config=config.as_dict(),
            strategy_version=self.strategy_version,
            data_version=self.data_version,
            calendar=tuple(calendar),
            equity_curve=tuple(equity_curve),
            cash_curve=tuple(cash_curve),
            exposure_curve=tuple(exposure_curve),
            traded_notional_curve=tuple(traded_notional),
            trades=tuple(trades),
            open_positions=tuple(
                {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "entry_date": position.entry_date.isoformat(),
                    "entry_price": position.entry_price,
                    "last_mark": position.last_mark,
                }
                for position in sorted(positions.values(), key=lambda item: item.symbol)
            ),
            fills=tuple(fills),
            order_events=tuple(events),
            warnings=tuple(dict.fromkeys(self._warnings)),
            excluded_fundamentals=tuple(self._excluded_fundamentals),
            evaluations=tuple(evaluations),
            max_history_index_read=dict(highest_index_read),
        )


def run_backtest(
    config: BacktestConfig,
    histories: Mapping[str, SymbolHistory],
    **kwargs: Any,
) -> BacktestResult:
    return BacktestEngine(config, histories, **kwargs).run()
