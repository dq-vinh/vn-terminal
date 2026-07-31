"""WP6 strategy registry (Sections 10.4 and 13).

Importing this package registers every strategy with an approved written
specification in `docs/strategy_catalogue.md`.

**The catalogue holds one strategy.** As of 31 July 2026, section 1 of
`docs/strategy_catalogue.md` ("Dual-SMA Trend Crossover", approved
2026-07-30) is the only entry with `Specification status: Approved`. Section
13.2 scopes v1.0 at ten to fifteen strategies and the plan is explicit that
"Specification writing is the user's work, not the agents' work, and is the
true critical path". Nothing here is invented to close that gap and nothing
is added to reach a count; see `HANDOFF_WP6_WP7_WP8.md`.

Typical use:

    from backend.app.quant.strategies import SymbolHistory, evaluate

    history = SymbolHistory.from_bars(bars)     # bars loaded by the caller
    result = evaluate("dual_sma_trend_crossover", history.window(index))

Purity, enforced by `tests/quant/test_strategy_purity.py`: no module in this
package opens a file, a socket, or a database connection, reads the clock,
reads the environment, or draws a random number. Bars are copied and marked
read-only on the way in.

No-look-ahead, enforced by `tests/quant/test_lookahead_adversarial.py`: a
strategy sees an `AsOfWindow`, which refuses any request for a bar after `t`.
"""

from __future__ import annotations

from . import (
    dual_sma_trend_crossover,  # noqa: F401  (registration side effect)
    numerics,
)
from .protocol import ParameterSpec, Strategy, StrategyMetadata
from .registry import (
    RegisteredStrategy,
    all_ids,
    all_strategies,
    evaluate,
    get,
    metadata,
    register,
    resolve_parameters,
    versions,
    warmup_bars,
)
from .serialization import (
    catalogue,
    definition_for,
    evaluation_payload,
    to_contract_definition,
    to_contract_result,
)
from .types import (
    AsOfWindow,
    BarView,
    Criterion,
    InsufficientHistory,
    LookAheadError,
    OrderIntent,
    OrderSide,
    OrderStatus,
    PositionState,
    SecurityView,
    Signal,
    StrategyError,
    StrategyEvaluation,
    SymbolHistory,
)

__all__ = [
    "AsOfWindow",
    "BarView",
    "Criterion",
    "InsufficientHistory",
    "LookAheadError",
    "OrderIntent",
    "OrderSide",
    "OrderStatus",
    "ParameterSpec",
    "PositionState",
    "RegisteredStrategy",
    "SecurityView",
    "Signal",
    "Strategy",
    "StrategyError",
    "StrategyEvaluation",
    "StrategyMetadata",
    "SymbolHistory",
    "all_ids",
    "all_strategies",
    "catalogue",
    "definition_for",
    "evaluate",
    "evaluation_payload",
    "get",
    "metadata",
    "numerics",
    "register",
    "resolve_parameters",
    "to_contract_definition",
    "to_contract_result",
    "versions",
    "warmup_bars",
]
