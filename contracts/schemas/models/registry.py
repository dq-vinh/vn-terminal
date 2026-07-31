"""Single source of truth for which Pydantic models are exported as
contracts, used by both generate_json_schema.py (standalone
*.schema.json files) and contracts/build_openapi.py (components.schemas in
openapi.yaml). Keeping one dict avoids the two outputs drifting apart.
"""

from __future__ import annotations

from . import (
    ai_fact_bundle,
    ai_response,
    api_envelopes,
    common,
    financial_observation,
    money_flow,
    price_bar,
    security_master,
    strategy_definition,
    strategy_evaluation_result,
)

EXPORTS: dict[str, type] = {
    # Canonical contracts, Section 10
    "price_bar": price_bar.PriceBar,
    "security_master": security_master.SecurityMaster,
    "financial_observation": financial_observation.FinancialObservation,
    "strategy_definition": strategy_definition.StrategyDefinition,
    "strategy_evaluation_result": strategy_evaluation_result.StrategyEvaluationResult,
    "money_flow_block": money_flow.MoneyFlowBlock,
    "ai_fact_bundle": ai_fact_bundle.AIFactBundle,
    "structured_ai_response": ai_response.StructuredAIResponse,
    # Shared components
    "provenance": common.Provenance,
    "levels": common.Levels,
    "quality_issue": common.QualityIssue,
    "error_response": common.ErrorResponse,
    "http_validation_error": common.HTTPValidationError,
    # API envelopes, one entry per Section 11 request/response body
    "health_response": api_envelopes.HealthResponse,
    "data_refresh_request": api_envelopes.DataRefreshRequest,
    "data_refresh_response": api_envelopes.DataRefreshResponse,
    "data_status_response": api_envelopes.DataStatusResponse,
    "symbols_response": api_envelopes.SymbolsResponse,
    "bars_response": api_envelopes.BarsResponse,
    "fundamentals_response": api_envelopes.FundamentalsResponse,
    "indicators_response": api_envelopes.IndicatorsResponse,
    "strategies_response": api_envelopes.StrategiesResponse,
    "strategy_evaluate_request": api_envelopes.StrategyEvaluateRequest,
    "strategy_evaluate_response": api_envelopes.StrategyEvaluateResponse,
    "screen_request": api_envelopes.ScreenRequest,
    "screen_start_response": api_envelopes.ScreenStartResponse,
    "screen_results_response": api_envelopes.ScreenResultsResponse,
    "backtest_request": api_envelopes.BacktestRequest,
    "backtest_start_response": api_envelopes.BacktestStartResponse,
    "backtest_results_response": api_envelopes.BacktestResultsResponse,
    "ai_analyze_request": api_envelopes.AIAnalyzeRequest,
    "ai_analyze_response": api_envelopes.AIAnalyzeResponse,
    "watchlists_response": api_envelopes.WatchlistsResponse,
    "watchlist_upsert_request": api_envelopes.WatchlistUpsertRequest,
    "watchlist_response": api_envelopes.WatchlistResponse,
    "settings_response": api_envelopes.SettingsResponse,
    "settings_update_request": api_envelopes.SettingsUpdateRequest,
}
