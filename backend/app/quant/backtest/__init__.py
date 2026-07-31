"""WP8 backtester (Section 16), daily bars.

Implements every Section 16 required control and produces every Section 16
required output, each output carrying its own definition.

The bias controls are not a feature of this package; they are its shape. See
`engine.py` for the three-phase session loop that makes "evaluate at `t`,
execute at `t+1`" structurally true, `config.py` for the survivorship,
corporate-action, and publication-date guards that run before any bar is
read, and `tests/quant/test_lookahead_adversarial.py` for the suite whose
only purpose is to try to break all of it.
"""

from __future__ import annotations

from .config import (
    EXECUTION_CONVENTIONS,
    FIXED_CASH_AMOUNT,
    FIXED_FRACTION_OF_EQUITY,
    FIXED_SHARES,
    NEXT_CLOSE,
    NEXT_OPEN,
    POSITION_SIZE_MODES,
    BacktestConfig,
    BacktestConfigError,
    LiquidityConstraint,
    Period,
    PositionSizing,
)
from .engine import (
    AdjustmentConventionError,
    BacktestEngine,
    BacktestError,
    BacktestResult,
    Fill,
    FundamentalObservation,
    OrderEvent,
    PublicationDateError,
    SurvivorshipBiasError,
    Trade,
    compute_run_id,
    run_backtest,
)
from .metrics import (
    DEFINITIONS,
    MetricSet,
    compute_metrics,
    contract_payload,
    drawdown_curve,
    summarize,
)

__all__ = [
    "DEFINITIONS",
    "EXECUTION_CONVENTIONS",
    "FIXED_CASH_AMOUNT",
    "FIXED_FRACTION_OF_EQUITY",
    "FIXED_SHARES",
    "NEXT_CLOSE",
    "NEXT_OPEN",
    "POSITION_SIZE_MODES",
    "AdjustmentConventionError",
    "BacktestConfig",
    "BacktestConfigError",
    "BacktestEngine",
    "BacktestError",
    "BacktestResult",
    "Fill",
    "FundamentalObservation",
    "LiquidityConstraint",
    "MetricSet",
    "OrderEvent",
    "Period",
    "PositionSizing",
    "PublicationDateError",
    "SurvivorshipBiasError",
    "Trade",
    "compute_metrics",
    "compute_run_id",
    "contract_payload",
    "drawdown_curve",
    "run_backtest",
    "summarize",
]
