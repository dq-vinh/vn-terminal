"""Request/response envelopes for the Section 11 API surface.

Every endpoint in this module maps to one row of the Section 11 table.
Every response envelope embeds a `provenance` object (see common.Provenance)
to satisfy Section 11's blanket requirement that "All endpoints must have
... as_of_date ... data_version ... source ... Quality and freshness
warnings where applicable." See docs/decision_log.md, WP0 entry, for why
this is nested rather than four repeated flat fields.

Fields whose shape is not given by the plan are typed as open strings or
open objects and logged in contracts/OPEN_ITEMS.md, following the same
policy as the five canonical contracts.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import ConfigDict, Field

from .ai_fact_bundle import AIFactBundle
from .ai_response import StructuredAIResponse
from .common import (
    AIProviderType,
    ExecutionConvention,
    Provenance,
    StrictModel,
    Timeframe,
)
from .financial_observation import FinancialObservation
from .money_flow import MoneyFlowBlock
from .security_master import SecurityMaster
from .strategy_definition import StrategyDefinition
from .strategy_evaluation_result import StrategyEvaluationResult
from .price_bar import PriceBar


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


class DatabaseStatus(StrictModel):
    connected: bool
    latest_snapshot_date: date | None = None


class ProviderStatus(StrictModel):
    name: str = Field(examples=["openrouter", "ollama"])
    provider_type: AIProviderType
    available: bool


class HealthResponse(StrictModel):
    status: str = Field(
        examples=["ok"],
        description=(
            "OPEN ITEM: Section 11 requires an 'Application, database, and "
            "provider status' but does not give a closed vocabulary. See "
            "contracts/OPEN_ITEMS.md, 'Job/health status vocabulary.'"
        ),
    )
    database: DatabaseStatus
    providers: list[ProviderStatus] = Field(default_factory=list)
    provenance: Provenance


# ---------------------------------------------------------------------------
# POST /api/data/refresh, GET /api/data/status
# ---------------------------------------------------------------------------


class DataRefreshRequest(StrictModel):
    force: bool = Field(
        default=False,
        description=(
            "OPEN ITEM: not named by the plan. Added so a caller can "
            "request a refresh even if one recently succeeded. See "
            "contracts/OPEN_ITEMS.md."
        ),
    )


class DataRefreshResponse(StrictModel):
    run_id: str
    status: str = Field(
        examples=["queued", "running"],
        description="OPEN ITEM: see contracts/OPEN_ITEMS.md, 'Job/health status vocabulary.'",
    )
    started_at: datetime
    provenance: Provenance


class SnapshotInfo(StrictModel):
    data_version: str
    as_of_date: date
    promoted_at: datetime


class DataStatusResponse(StrictModel):
    run_id: str | None = None
    status: str = Field(
        examples=["queued", "running", "completed", "failed"],
        description="OPEN ITEM: see contracts/OPEN_ITEMS.md, 'Job/health status vocabulary.'",
    )
    progress_pct: float | None = Field(default=None, ge=0, le=100)
    latest_good_snapshot: SnapshotInfo | None = Field(
        default=None,
        description=(
            "Section 3.4: 'The previous validated data snapshot remains "
            "available if a refresh fails.'"
        ),
    )
    issues: list[str] = Field(default_factory=list)
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/symbols
# ---------------------------------------------------------------------------


class SymbolsResponse(StrictModel):
    items: list[SecurityMaster]
    total: int = Field(ge=0)
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/bars/{symbol}
# ---------------------------------------------------------------------------


class BarsResponse(StrictModel):
    symbol: str
    timeframe: Timeframe
    bars: list[PriceBar]
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/fundamentals/{symbol}
# ---------------------------------------------------------------------------


class DerivedMetric(StrictModel):
    """Section 17: 'Calculate growth and margins deterministically.'

    OPEN ITEM: the plan lists panel content (Section 17, "Initial panels")
    but not a literal derived-metric record shape. This mirrors
    FinancialObservation's shape closely so both can be rendered the same
    way in the fundamentals panel (Section 12.3).
    """

    symbol: str
    period_end: date
    metric_code: str = Field(
        examples=["revenue_yoy_growth", "gross_margin", "roe", "roa", "pe", "pb"]
    )
    metric_label_vi: str
    value: float
    unit: str


class FundamentalsResponse(StrictModel):
    symbol: str
    observations: list[FinancialObservation]
    derived_metrics: list[DerivedMetric] = Field(default_factory=list)
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/indicators/{symbol}
# ---------------------------------------------------------------------------


class IndicatorPoint(StrictModel):
    trading_date: date
    value: float | None = Field(
        default=None,
        description="Section 14: 'Missing-value behaviour' must be documented per indicator; null during warm-up.",
    )


class IndicatorSeries(StrictModel):
    indicator_id: str = Field(
        examples=[
            "sma",
            "ema",
            "rsi",
            "macd",
            "atr",
            "bollinger_bands",
            "rolling_high",
            "rolling_low",
            "rate_of_change",
            "relative_strength_vnindex",
            "relative_strength_sector",
            "volume_sma",
            "volume_price_trend",
            "pivot_levels",
            "rolling_volatility",
            "drawdown",
        ],
        description="Section 14 initial indicator list, given as machine-readable ids.",
    )
    values: list[IndicatorPoint]


class IndicatorsResponse(StrictModel):
    symbol: str
    timeframe: Timeframe
    indicators: list[IndicatorSeries]
    money_flow: MoneyFlowBlock
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/strategies, POST /api/strategies/evaluate
# ---------------------------------------------------------------------------


class StrategiesResponse(StrictModel):
    strategies: list[StrategyDefinition]
    provenance: Provenance


class StrategyEvaluateRequest(StrictModel):
    symbol: str
    strategy_ids: list[str]
    as_of_date: date | None = Field(
        default=None,
        description="Defaults to the latest snapshot date when omitted.",
    )


class StrategyEvaluateResponse(StrictModel):
    results: list[StrategyEvaluationResult]
    provenance: Provenance


# ---------------------------------------------------------------------------
# POST /api/screen, GET /api/screen/{run_id}
# ---------------------------------------------------------------------------


class ScreenUniverseFilters(StrictModel):
    """Section 15 'Default filters' list."""

    active_equity_only: bool = Field(default=True)
    last_positive_volume_within_days: int = Field(
        default=5,
        description=(
            "Section 15: 'Last positive-volume date within a configurable "
            "range.' OPEN ITEM: the plan does not give a default value; "
            "5 sessions is chosen here to match the terminal zero-volume "
            "run length used in Section 19.2's baseline scan ('terminal "
            "zero-volume runs of five or more sessions'). See "
            "contracts/OPEN_ITEMS.md."
        ),
    )
    min_20d_median_trading_value: float = Field(
        description="Section 15: 'Minimum 20-day median trading value.'"
    )
    min_history_days: int = Field(
        description="Section 15: 'Minimum history length.'"
    )
    exclude_unresolved_critical_issues: bool = Field(
        default=True,
        description="Section 15: 'No unresolved critical data-quality issue.'",
    )


class ScreenRequest(StrictModel):
    strategy_ids: list[str]
    universe_filters: ScreenUniverseFilters | None = None


class ScreenStartResponse(StrictModel):
    run_id: str
    status: str = Field(
        examples=["queued", "running"],
        description="OPEN ITEM: see contracts/OPEN_ITEMS.md, 'Job/health status vocabulary.'",
    )
    provenance: Provenance


class ScreenResultItem(StrictModel):
    symbol: str
    score: float
    rank: int
    passed_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)


class ScreenResultsResponse(StrictModel):
    run_id: str
    status: str = Field(examples=["completed", "failed"])
    run_date: date = Field(
        description="Section 15: 'Store run date, strategy versions, parameters, and data version.'"
    )
    strategy_versions: dict[str, str] = Field(
        description="Mapping of strategy_id to the version evaluated in this run."
    )
    parameters: dict = Field(
        description="Effective universe_filters and any per-strategy parameters used for this run."
    )
    results: list[ScreenResultItem]
    provenance: Provenance


# ---------------------------------------------------------------------------
# POST /api/backtest, GET /api/backtest/{run_id}
# ---------------------------------------------------------------------------


class BacktestPeriod(StrictModel):
    start_date: date
    end_date: date


class BacktestRequest(StrictModel):
    """Section 16 'Required controls' list."""

    strategy_id: str
    symbol_universe: list[str] = Field(
        description=(
            "OPEN ITEM: the plan does not say whether a backtest targets "
            "an explicit symbol list, a named universe, or the full "
            "market. Modeled as an explicit list of symbols; a full-market "
            "run is expressed by passing every eligible symbol from "
            "/api/symbols. See contracts/OPEN_ITEMS.md."
        )
    )
    entry_convention: ExecutionConvention
    exit_convention: str = Field(
        description=(
            "OPEN ITEM: Section 16 requires an 'Exit convention' but, "
            "unlike entry convention, does not give a closed list. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    transaction_cost: float = Field(ge=0)
    slippage: float = Field(ge=0)
    position_size: dict = Field(
        description=(
            "OPEN ITEM: Section 16 requires 'Position size' without "
            "specifying whether it is a fixed amount, a percentage of "
            "equity, or a volatility-scaled rule. Typed as an open "
            "object. See contracts/OPEN_ITEMS.md."
        )
    )
    max_concurrent_positions: int = Field(ge=1)
    liquidity_constraint: dict = Field(
        description=(
            "OPEN ITEM: Section 16 requires a 'Liquidity constraint' "
            "without a defined shape. Typed as an open object. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    price_adjustment_convention: str = Field(
        description=(
            "OPEN ITEM: Section 16 requires a 'Price-adjustment "
            "convention' without an enumerated set of conventions. See "
            "contracts/OPEN_ITEMS.md."
        )
    )
    benchmark: str = Field(
        description="Section 16: 'Benchmark.' Typically a security_master symbol/index_code."
    )
    in_sample_period: BacktestPeriod
    out_of_sample_period: BacktestPeriod | None = Field(
        default=None, description="Section 16: 'In-sample and out-of-sample periods.'"
    )


class BacktestStartResponse(StrictModel):
    run_id: str
    status: str = Field(
        examples=["queued", "running"],
        description="OPEN ITEM: see contracts/OPEN_ITEMS.md, 'Job/health status vocabulary.'",
    )
    provenance: Provenance


class Trade(StrictModel):
    """Section 16: 'Trade list.'

    OPEN ITEM: the plan requires trade-list output but does not give a
    per-trade field list. This shape follows standard backtest trade
    records and the fields the plan does specify elsewhere (symbol,
    entry/exit convention, transaction cost, slippage).
    """

    symbol: str
    entry_date: date
    exit_date: date | None = None
    entry_price: float
    exit_price: float | None = None
    quantity: float
    transaction_cost_paid: float
    slippage_paid: float
    pnl: float | None = None


class BacktestMetrics(StrictModel):
    """Section 16 'Required outputs' list, excluding trade/equity/drawdown series."""

    cagr: float | None = None
    annualized_return: float | None = None
    volatility: float
    sharpe: float = Field(description="Section 16 requires this 'with definitions.'")
    sortino: float = Field(description="Section 16 requires this 'with definitions.'")
    max_drawdown: float
    win_rate: float
    profit_factor: float
    average_holding_period_days: float
    turnover: float
    exposure: float
    benchmark_comparison: dict = Field(
        description=(
            "OPEN ITEM: Section 16 requires 'Benchmark comparison' "
            "without a defined shape. Typed as an open object. See "
            "contracts/OPEN_ITEMS.md."
        )
    )


class EquityCurvePoint(StrictModel):
    trading_date: date
    equity: float


class DrawdownCurvePoint(StrictModel):
    trading_date: date
    drawdown: float


class BacktestResultsResponse(StrictModel):
    run_id: str
    status: str = Field(examples=["completed", "failed"])
    trades: list[Trade]
    equity_curve: list[EquityCurvePoint]
    drawdown_curve: list[DrawdownCurvePoint]
    metrics: BacktestMetrics
    warnings: list[str] = Field(default_factory=list)
    data_version: str
    strategy_version: str
    provenance: Provenance


# ---------------------------------------------------------------------------
# POST /api/ai/analyze
# ---------------------------------------------------------------------------


class AIModelConfig(StrictModel):
    provider: AIProviderType
    model: str = Field(examples=["deepseek/deepseek-v4-flash"])


class AIAnalyzeRequest(StrictModel):
    symbol: str
    question: str | None = None
    ai_model_config: AIModelConfig = Field(
        alias="model_config",
        serialization_alias="model_config",
        description=(
            "Section 18.2 provider interface: "
            "'analyze(fact_bundle, prompt_template, model_config) -> "
            "structured_response.' Python attribute named ai_model_config "
            "to avoid Pydantic's reserved `model_` attribute-name "
            "namespace; the wire (JSON) field name is `model_config`, "
            "matching the plan's own name for this argument. See "
            "contracts/OPEN_ITEMS.md."
        ),
    )

    model_config = ConfigDict(
        extra="forbid", use_enum_values=True, populate_by_name=True
    )


class AIAnalyzeResponse(StrictModel):
    analysis: StructuredAIResponse
    fact_bundle: AIFactBundle = Field(
        description=(
            "Included so the frontend AI panel (Section 12.5, WP11 "
            "acceptance criteria: 'User can inspect facts behind the "
            "response') can show the underlying facts without a second "
            "round trip. Not explicitly named as a response field by "
            "Section 11; see contracts/OPEN_ITEMS.md."
        )
    )
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/watchlists, PUT /api/watchlists/{id}
# ---------------------------------------------------------------------------


class WatchlistItem(StrictModel):
    """Section 12.4 'Watchlist' tab; WP12 deliverable 'Watchlists.'

    OPEN ITEM: the plan does not give a Watchlist field list. This is a
    minimal shape covering what Section 12.4/WP12 imply a watchlist needs.
    See contracts/OPEN_ITEMS.md.
    """

    id: str
    name: str
    symbols: list[str]
    created_at: datetime
    updated_at: datetime


class WatchlistsResponse(StrictModel):
    watchlists: list[WatchlistItem]
    provenance: Provenance


class WatchlistUpsertRequest(StrictModel):
    name: str
    symbols: list[str]


class WatchlistResponse(StrictModel):
    watchlist: WatchlistItem
    provenance: Provenance


# ---------------------------------------------------------------------------
# GET /api/settings, PUT /api/settings
# ---------------------------------------------------------------------------


class SettingsResponse(StrictModel):
    settings: dict = Field(
        description=(
            "OPEN ITEM: Section 12.1/18.2 and WP12 scatter individual "
            "settings (model selection, data source, saved layout, ...) "
            "without a single enumerated settings object. Typed as an "
            "open object. See contracts/OPEN_ITEMS.md."
        )
    )
    provenance: Provenance


class SettingsUpdateRequest(StrictModel):
    settings: dict
