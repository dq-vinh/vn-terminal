#!/usr/bin/env python3
"""Assemble contracts/openapi.yaml from the Pydantic models in
contracts/schemas/models/registry.py.

Usage (from repository root):
    python contracts/build_openapi.py

Owner: Lead integrator (contracts/OWNERSHIP.md). openapi.yaml is generated,
not hand-edited. To change it, change the models in contracts/schemas/models/
or the path table below, then re-run this script and
contracts/schemas/generate_json_schema.py, following the contract-change
process in contracts/OWNERSHIP.md Section 24.2 for anything that is not a
same-session fix.

Endpoint list, methods, and purposes are taken verbatim from the Section 11
table of vn_terminal_multi_ai_development_plan.md v1.1. No endpoint is added
or removed beyond that table.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic.json_schema import models_json_schema


class NoAliasDumper(yaml.SafeDumper):
    """Disable YAML anchors/aliases.

    Several response/error dicts below (STANDARD_ERRORS etc.) are reused by
    reference across multiple paths for brevity in this script. Without
    this, PyYAML emits &id001 / *id001 anchors for the shared objects,
    which is valid YAML but is an unnecessary surprise for downstream
    tooling and human readers expecting plain OpenAPI YAML.
    """

    def ignore_aliases(self, data):
        return True

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(THIS_DIR / "schemas"))

from models.registry import EXPORTS  # noqa: E402

CONTRACT_VERSION = (THIS_DIR / "VERSION").read_text(encoding="utf-8").strip()


def ref(model) -> dict:
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def json_body(model) -> dict:
    return {"content": {"application/json": {"schema": ref(model)}}}


def build_components_schemas() -> dict:
    pairs = [(m, "validation") for m in EXPORTS.values()]
    _key_map, top = models_json_schema(pairs, ref_template="#/components/schemas/{model}")
    schemas = top["$defs"]
    for name, schema in schemas.items():
        schema.setdefault("title", name)
    return dict(sorted(schemas.items()))


COMMON_RESPONSES = {
    "BadRequest": {
        "description": "Malformed request.",
        **json_body(EXPORTS["error_response"]),
    },
    "NotFound": {
        "description": "The requested resource (symbol, run_id, watchlist id) does not exist.",
        **json_body(EXPORTS["error_response"]),
    },
    "ValidationError": {
        "description": "Request failed schema validation (FastAPI default 422 shape, Section 7).",
        **json_body(EXPORTS["http_validation_error"]),
    },
    "ServiceUnavailable": {
        "description": (
            "Required data or an AI provider is unavailable, or the latest "
            "snapshot failed validation (Section 3.4: 'No trading "
            "recommendation is generated when required data is missing or "
            "fails validation.')."
        ),
        **json_body(EXPORTS["error_response"]),
    },
    "ServerError": {
        "description": "Unexpected server error.",
        **json_body(EXPORTS["error_response"]),
    },
}

STANDARD_ERRORS = {
    "400": {"$ref": "#/components/responses/BadRequest"},
    "422": {"$ref": "#/components/responses/ValidationError"},
    "500": {"$ref": "#/components/responses/ServerError"},
}

STANDARD_ERRORS_WITH_404 = {
    **STANDARD_ERRORS,
    "404": {"$ref": "#/components/responses/NotFound"},
}

COMPONENTS_PARAMETERS = {
    "SymbolPath": {
        "name": "symbol",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "FPT",
    },
    "RunIdPath": {
        "name": "run_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    },
    "WatchlistIdPath": {
        "name": "id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    },
    "TimeframeQuery": {
        "name": "timeframe",
        "in": "query",
        "required": False,
        "schema": {"$ref": "#/components/schemas/Timeframe"},
        "description": "Section 12.1/12.2: daily, weekly, or monthly. Defaults to 1D.",
    },
    "StartDateQuery": {
        "name": "start_date",
        "in": "query",
        "required": False,
        "schema": {"type": "string", "format": "date"},
    },
    "EndDateQuery": {
        "name": "end_date",
        "in": "query",
        "required": False,
        "schema": {"type": "string", "format": "date"},
    },
    "SymbolSearchQuery": {
        "name": "q",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": "Section 11: 'Search and filter the security universe.'",
    },
    "ExchangeFilterQuery": {
        "name": "exchange",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
    },
    "SecurityTypeFilterQuery": {
        "name": "security_type",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
    },
    "TradingStatusFilterQuery": {
        "name": "trading_status",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
    },
    "LimitQuery": {
        "name": "limit",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
        "description": (
            "OPEN ITEM: pagination is not specified by Section 11; added "
            "given the full-market universe is 1,500-1,800 securities "
            "(Section 3.3). See contracts/OPEN_ITEMS.md."
        ),
    },
    "OffsetQuery": {
        "name": "offset",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "minimum": 0, "default": 0},
    },
    "IndicatorIdsQuery": {
        "name": "indicator_ids",
        "in": "query",
        "required": False,
        "schema": {"type": "array", "items": {"type": "string"}},
        "style": "form",
        "explode": True,
        "description": "Restrict to specific indicator ids from Section 14. Omit for all.",
    },
    "AsOfDateQuery": {
        "name": "as_of_date",
        "in": "query",
        "required": False,
        "schema": {"type": "string", "format": "date"},
        "description": "Defaults to the latest promoted snapshot date when omitted.",
    },
}


def build_paths() -> dict:
    p = {}

    p["/api/health"] = {
        "get": {
            "operationId": "getHealth",
            "summary": "Application, database, and provider status",
            "tags": ["system"],
            "responses": {
                "200": {"description": "Health status.", **json_body(EXPORTS["health_response"])},
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/data/refresh"] = {
        "post": {
            "operationId": "startDataRefresh",
            "summary": "Start atomic data refresh",
            "tags": ["data"],
            "requestBody": json_body(EXPORTS["data_refresh_request"]),
            "responses": {
                "202": {
                    "description": "Refresh accepted and queued/running.",
                    **json_body(EXPORTS["data_refresh_response"]),
                },
                **STANDARD_ERRORS,
                "503": {"$ref": "#/components/responses/ServiceUnavailable"},
            },
        }
    }

    p["/api/data/status"] = {
        "get": {
            "operationId": "getDataStatus",
            "summary": "Refresh progress and latest good snapshot",
            "tags": ["data"],
            "responses": {
                "200": {"description": "Refresh status.", **json_body(EXPORTS["data_status_response"])},
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/symbols"] = {
        "get": {
            "operationId": "listSymbols",
            "summary": "Search and filter the security universe",
            "tags": ["data"],
            "parameters": [
                {"$ref": "#/components/parameters/SymbolSearchQuery"},
                {"$ref": "#/components/parameters/ExchangeFilterQuery"},
                {"$ref": "#/components/parameters/SecurityTypeFilterQuery"},
                {"$ref": "#/components/parameters/TradingStatusFilterQuery"},
                {"$ref": "#/components/parameters/LimitQuery"},
                {"$ref": "#/components/parameters/OffsetQuery"},
            ],
            "responses": {
                "200": {"description": "Matching securities.", **json_body(EXPORTS["symbols_response"])},
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/bars/{symbol}"] = {
        "get": {
            "operationId": "getBars",
            "summary": "Return validated OHLCV",
            "tags": ["data"],
            "parameters": [
                {"$ref": "#/components/parameters/SymbolPath"},
                {"$ref": "#/components/parameters/TimeframeQuery"},
                {"$ref": "#/components/parameters/StartDateQuery"},
                {"$ref": "#/components/parameters/EndDateQuery"},
            ],
            "responses": {
                "200": {"description": "Validated OHLCV bars.", **json_body(EXPORTS["bars_response"])},
                **STANDARD_ERRORS_WITH_404,
            },
        }
    }

    p["/api/fundamentals/{symbol}"] = {
        "get": {
            "operationId": "getFundamentals",
            "summary": "Financial statements and derived metrics",
            "tags": ["fundamentals"],
            "parameters": [{"$ref": "#/components/parameters/SymbolPath"}],
            "responses": {
                "200": {
                    "description": "Financial observations and derived metrics.",
                    **json_body(EXPORTS["fundamentals_response"]),
                },
                **STANDARD_ERRORS_WITH_404,
            },
        }
    }

    p["/api/indicators/{symbol}"] = {
        "get": {
            "operationId": "getIndicators",
            "summary": "Deterministic indicators",
            "tags": ["quant"],
            "parameters": [
                {"$ref": "#/components/parameters/SymbolPath"},
                {"$ref": "#/components/parameters/TimeframeQuery"},
                {"$ref": "#/components/parameters/StartDateQuery"},
                {"$ref": "#/components/parameters/EndDateQuery"},
                {"$ref": "#/components/parameters/IndicatorIdsQuery"},
            ],
            "responses": {
                "200": {
                    "description": "Indicator series and the Section 14 money-flow block.",
                    **json_body(EXPORTS["indicators_response"]),
                },
                **STANDARD_ERRORS_WITH_404,
            },
        }
    }

    p["/api/strategies"] = {
        "get": {
            "operationId": "listStrategies",
            "summary": "Strategy catalogue and versions",
            "tags": ["quant"],
            "responses": {
                "200": {"description": "Strategy catalogue.", **json_body(EXPORTS["strategies_response"])},
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/strategies/evaluate"] = {
        "post": {
            "operationId": "evaluateStrategies",
            "summary": "Evaluate selected strategies",
            "tags": ["quant"],
            "requestBody": json_body(EXPORTS["strategy_evaluate_request"]),
            "responses": {
                "200": {
                    "description": "Evaluation results.",
                    **json_body(EXPORTS["strategy_evaluate_response"]),
                },
                **STANDARD_ERRORS_WITH_404,
            },
        }
    }

    p["/api/screen"] = {
        "post": {
            "operationId": "startScreen",
            "summary": "Run market-wide screening",
            "tags": ["quant"],
            "requestBody": json_body(EXPORTS["screen_request"]),
            "responses": {
                "202": {
                    "description": "Screen accepted as a background job (Section 15).",
                    **json_body(EXPORTS["screen_start_response"]),
                },
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/screen/{run_id}"] = {
        "get": {
            "operationId": "getScreenResults",
            "summary": "Return background-screen results",
            "tags": ["quant"],
            "parameters": [{"$ref": "#/components/parameters/RunIdPath"}],
            "responses": {
                "200": {
                    "description": "Screen results, reproducible per Section 15.",
                    **json_body(EXPORTS["screen_results_response"]),
                },
                **STANDARD_ERRORS_WITH_404,
            },
        }
    }

    p["/api/backtest"] = {
        "post": {
            "operationId": "startBacktest",
            "summary": "Start a reproducible backtest",
            "tags": ["quant"],
            "requestBody": json_body(EXPORTS["backtest_request"]),
            "responses": {
                "202": {
                    "description": "Backtest accepted (Section 16).",
                    **json_body(EXPORTS["backtest_start_response"]),
                },
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/backtest/{run_id}"] = {
        "get": {
            "operationId": "getBacktestResults",
            "summary": "Return trades, metrics, and warnings",
            "tags": ["quant"],
            "parameters": [{"$ref": "#/components/parameters/RunIdPath"}],
            "responses": {
                "200": {
                    "description": "Trades, equity/drawdown curves, and metrics.",
                    **json_body(EXPORTS["backtest_results_response"]),
                },
                **STANDARD_ERRORS_WITH_404,
            },
        }
    }

    p["/api/ai/analyze"] = {
        "post": {
            "operationId": "analyzeWithAI",
            "summary": "Explain a server-created fact bundle",
            "tags": ["ai"],
            "requestBody": json_body(EXPORTS["ai_analyze_request"]),
            "responses": {
                "200": {
                    "description": (
                        "Structured AI response (Section 18.3) plus the fact "
                        "bundle it was built from."
                    ),
                    **json_body(EXPORTS["ai_analyze_response"]),
                },
                **STANDARD_ERRORS_WITH_404,
                "503": {"$ref": "#/components/responses/ServiceUnavailable"},
            },
        }
    }

    p["/api/watchlists"] = {
        "get": {
            "operationId": "listWatchlists",
            "summary": "Retrieve watchlists",
            "tags": ["workspace"],
            "responses": {
                "200": {"description": "Saved watchlists.", **json_body(EXPORTS["watchlists_response"])},
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/watchlists/{id}"] = {
        "put": {
            "operationId": "saveWatchlist",
            "summary": "Save a watchlist",
            "tags": ["workspace"],
            "parameters": [{"$ref": "#/components/parameters/WatchlistIdPath"}],
            "requestBody": json_body(EXPORTS["watchlist_upsert_request"]),
            "responses": {
                "200": {"description": "Saved watchlist.", **json_body(EXPORTS["watchlist_response"])},
                **STANDARD_ERRORS,
            },
        }
    }

    p["/api/settings"] = {
        "get": {
            "operationId": "getSettings",
            "summary": "Retrieve local settings",
            "tags": ["workspace"],
            "responses": {
                "200": {"description": "Local settings.", **json_body(EXPORTS["settings_response"])},
                **STANDARD_ERRORS,
            },
        },
        "put": {
            "operationId": "saveSettings",
            "summary": "Save local settings",
            "tags": ["workspace"],
            "requestBody": json_body(EXPORTS["settings_update_request"]),
            "responses": {
                "200": {"description": "Saved settings.", **json_body(EXPORTS["settings_response"])},
                **STANDARD_ERRORS,
            },
        },
    }

    return p


def main() -> None:
    doc = {
        "openapi": "3.1.0",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "VN Terminal Pro API",
            "version": CONTRACT_VERSION,
            "description": (
                "Local, single-user API for VN Terminal Pro (Section 11 of "
                "vn_terminal_multi_ai_development_plan.md v1.1). Binds to "
                "127.0.0.1 only (Section 3.1, Section 20); never exposed "
                "publicly. This file is generated by "
                "contracts/build_openapi.py from the Pydantic models in "
                "contracts/schemas/models/. Do not hand-edit."
            ),
        },
        "servers": [
            {
                "url": "http://127.0.0.1:{port}",
                "description": "Local-only backend (Section 3.1).",
                "variables": {"port": {"default": "8000"}},
            }
        ],
        "tags": [
            {"name": "system", "description": "Health and status."},
            {"name": "data", "description": "FData refresh, security universe, and OHLCV (WP1-WP3)."},
            {"name": "fundamentals", "description": "Financial statements and derived metrics (WP9)."},
            {"name": "quant", "description": "Indicators, strategies, screener, backtester (WP5-WP8)."},
            {"name": "ai", "description": "AI fact bundle and analysis gateway (WP10)."},
            {"name": "workspace", "description": "Watchlists and settings (WP12)."},
        ],
        "paths": build_paths(),
        "components": {
            "schemas": build_components_schemas(),
            "responses": COMMON_RESPONSES,
            "parameters": COMPONENTS_PARAMETERS,
        },
    }

    out_path = THIS_DIR / "openapi.yaml"
    header = (
        "# GENERATED FILE. Do not hand-edit.\n"
        "# Produced by contracts/build_openapi.py from "
        "contracts/schemas/models/.\n"
        "# To change this file, change the models or the path table in "
        "build_openapi.py, then re-run:\n"
        "#   python contracts/schemas/generate_json_schema.py\n"
        "#   python contracts/build_openapi.py\n"
        "# Any change here that is not a same-session fix is a contract "
        "change; follow contracts/OWNERSHIP.md Section 24.2.\n"
    )
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        yaml.dump(
            doc, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True, width=100
        )

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
