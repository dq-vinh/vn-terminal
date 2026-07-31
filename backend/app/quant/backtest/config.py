"""Section 16 backtest controls, one field per required control.

Section 16 lists ten required controls. Every one of them is a field here,
none has a silently permissive default, and the two the plan calls out as
requiring explicit selection (`entry_convention`, and by symmetry
`exit_convention`) have no default at all: a caller must state them.

`contracts/OPEN_ITEMS.md` section B records `position_size`,
`liquidity_constraint`, `price_adjustment_convention`, and `exit_convention`
as shapes the plan does not define. This module gives each a concrete, named
shape and the handoff carries the corresponding change proposals. Where a
shape had to be chosen, the choice is the one that makes the assumption
visible: `PositionSizing` names its mode rather than overloading a bare
number, and `price_adjustment_convention` is verified against the bars rather
than recorded as a label.

Three fields exist only to make a bias control enforceable and would be
pointless in a backtester that took bias on trust:

- `universe_is_survivorship_filtered` makes the caller state whether the
  symbol list was built from currently-active securities. The engine refuses
  to run when it is true. Section 16 requires "No survivorship-only
  universe", and the data handoff records 301 stock files ending in terminal
  zero-volume runs that must stay in the historical universe.
- `price_adjustment_convention` is checked against every history's
  `adjustment_status`. Section 16 requires "Corporate-action consistency";
  mixing an adjusted and an unadjusted series in one simulation produces
  returns that are arithmetically fine and economically meaningless.
- `require_fundamental_publication_dates` cannot be set to False. Section 16
  and Section 17 require that fundamentals without a publication date be
  excluded from backtests rather than assumed; the field exists so the rule
  is visible in the configuration, not so it can be turned off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


class BacktestConfigError(ValueError):
    """Raised for an internally inconsistent backtest configuration."""


NEXT_OPEN = "next_open"
NEXT_CLOSE = "next_close"
EXECUTION_CONVENTIONS = frozenset({NEXT_OPEN, NEXT_CLOSE})

FIXED_FRACTION_OF_EQUITY = "fixed_fraction_of_equity"
FIXED_CASH_AMOUNT = "fixed_cash_amount"
FIXED_SHARES = "fixed_shares"
POSITION_SIZE_MODES = frozenset(
    {FIXED_FRACTION_OF_EQUITY, FIXED_CASH_AMOUNT, FIXED_SHARES}
)


@dataclass(frozen=True, slots=True)
class PositionSizing:
    """How much to buy.

    `equity_reference` records *when* the equity used for sizing is measured.
    The only value implemented is `previous_close`, and that is deliberate: an
    entry that fills at the open of session `d` sized from equity marked at
    the close of `d` would be sized from a number that did not exist when the
    order was placed. Naming the field rather than hard-coding the behavior
    means a future convention has to be declared rather than slipped in.

    `lot_size` defaults to one share. The approved specification's non-goals
    put position sizing outside the strategy, and no lot-rounding rule has
    been specified in writing, so none is imposed. A caller with an
    authoritative lot size can supply it.
    """

    mode: str
    value: float
    lot_size: int = 1
    equity_reference: str = "previous_close"

    def __post_init__(self) -> None:
        if self.mode not in POSITION_SIZE_MODES:
            raise BacktestConfigError(
                f"position size mode must be one of {sorted(POSITION_SIZE_MODES)}, "
                f"got {self.mode!r}"
            )
        if self.value <= 0:
            raise BacktestConfigError("position size value must be positive")
        if self.mode == FIXED_FRACTION_OF_EQUITY and self.value > 1:
            raise BacktestConfigError(
                "a fixed fraction of equity above 1.0 implies leverage, which v1.0 "
                "does not model"
            )
        if self.lot_size < 1:
            raise BacktestConfigError("lot_size must be at least 1")
        if self.equity_reference != "previous_close":
            raise BacktestConfigError(
                "only the 'previous_close' equity reference is implemented; any "
                "other reference would size an order from a price that postdates "
                "the decision"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "value": self.value,
            "lot_size": self.lot_size,
            "equity_reference": self.equity_reference,
        }


@dataclass(frozen=True, slots=True)
class LiquidityConstraint:
    """How much of an execution bar the simulation is allowed to take.

    Both limits are evaluated against the *execution* bar, which the engine
    has already reached when it applies them. That is not look-ahead: on the
    session the order fills, that session's volume is present information.
    Sizing the order from it a day earlier would be look-ahead, and the
    engine does not do that.
    """

    max_participation_of_bar_volume: float | None = None
    min_execution_bar_volume: float = 0.0
    reject_partial_fills: bool = False

    def __post_init__(self) -> None:
        participation = self.max_participation_of_bar_volume
        if participation is not None and not 0 < participation <= 1:
            raise BacktestConfigError(
                "max_participation_of_bar_volume must be within (0, 1]"
            )
        if self.min_execution_bar_volume < 0:
            raise BacktestConfigError("min_execution_bar_volume cannot be negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_participation_of_bar_volume": self.max_participation_of_bar_volume,
            "min_execution_bar_volume": self.min_execution_bar_volume,
            "reject_partial_fills": self.reject_partial_fills,
        }


@dataclass(frozen=True, slots=True)
class Period:
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise BacktestConfigError(
                f"period end {self.end_date} precedes start {self.start_date}"
            )

    def contains(self, value: date) -> bool:
        return self.start_date <= value <= self.end_date

    def as_dict(self) -> dict[str, str]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Every Section 16 required control."""

    strategy_id: str
    symbol_universe: tuple[str, ...]
    entry_convention: str
    exit_convention: str
    transaction_cost_rate: float
    slippage_rate: float
    position_size: PositionSizing
    max_concurrent_positions: int
    liquidity_constraint: LiquidityConstraint
    price_adjustment_convention: str
    benchmark: str | None
    in_sample_period: Period
    out_of_sample_period: Period | None = None
    initial_capital: float = 1_000_000.0
    strategy_parameters: dict[str, Any] = field(default_factory=dict)
    risk_free_rate_annual: float = 0.0
    trading_days_per_year: int = 252
    universe_is_survivorship_filtered: bool = False
    require_fundamental_publication_dates: bool = True

    def __post_init__(self) -> None:
        for name in ("entry_convention", "exit_convention"):
            value = getattr(self, name)
            if value not in EXECUTION_CONVENTIONS:
                raise BacktestConfigError(
                    f"{name} must be explicitly selected from "
                    f"{sorted(EXECUTION_CONVENTIONS)}, got {value!r}"
                )
        if self.transaction_cost_rate < 0 or self.slippage_rate < 0:
            raise BacktestConfigError("costs and slippage cannot be negative")
        if self.transaction_cost_rate >= 1 or self.slippage_rate >= 1:
            raise BacktestConfigError(
                "transaction_cost_rate and slippage_rate are fractions of notional "
                "and must be below 1.0"
            )
        if self.max_concurrent_positions < 1:
            raise BacktestConfigError("max_concurrent_positions must be at least 1")
        if self.initial_capital <= 0:
            raise BacktestConfigError("initial_capital must be positive")
        if self.trading_days_per_year < 1:
            raise BacktestConfigError("trading_days_per_year must be positive")
        if not self.symbol_universe:
            raise BacktestConfigError("symbol_universe cannot be empty")
        if not self.require_fundamental_publication_dates:
            raise BacktestConfigError(
                "fundamental publication dates cannot be made optional. Section 16 "
                "requires 'No use of later financial-publication information' and "
                "Section 17 requires that inputs lacking a publication date be "
                "excluded rather than assumed."
            )
        if (
            self.out_of_sample_period is not None
            and self.out_of_sample_period.start_date <= self.in_sample_period.end_date
        ):
            raise BacktestConfigError(
                    "the out-of-sample period must begin after the in-sample period "
                    "ends; overlapping windows are not an out-of-sample test"
                )

    @property
    def full_period(self) -> Period:
        end = (
            self.out_of_sample_period.end_date
            if self.out_of_sample_period is not None
            else self.in_sample_period.end_date
        )
        return Period(start_date=self.in_sample_period.start_date, end_date=end)

    def as_dict(self) -> dict[str, Any]:
        """Canonical record. A run reproduces from exactly this."""

        return {
            "strategy_id": self.strategy_id,
            "strategy_parameters": dict(self.strategy_parameters),
            "symbol_universe": sorted(self.symbol_universe),
            "entry_convention": self.entry_convention,
            "exit_convention": self.exit_convention,
            "transaction_cost_rate": self.transaction_cost_rate,
            "slippage_rate": self.slippage_rate,
            "position_size": self.position_size.as_dict(),
            "max_concurrent_positions": self.max_concurrent_positions,
            "liquidity_constraint": self.liquidity_constraint.as_dict(),
            "price_adjustment_convention": self.price_adjustment_convention,
            "benchmark": self.benchmark,
            "in_sample_period": self.in_sample_period.as_dict(),
            "out_of_sample_period": (
                None
                if self.out_of_sample_period is None
                else self.out_of_sample_period.as_dict()
            ),
            "initial_capital": self.initial_capital,
            "risk_free_rate_annual": self.risk_free_rate_annual,
            "trading_days_per_year": self.trading_days_per_year,
            "universe_is_survivorship_filtered": self.universe_is_survivorship_filtered,
            "require_fundamental_publication_dates": (
                self.require_fundamental_publication_dates
            ),
        }
