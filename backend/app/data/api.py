"""FastAPI router for the WP3 and WP9 operations in OpenAPI 0.1.0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from contracts.schemas.models.api_envelopes import (
    BarsResponse,
    DataRefreshRequest,
    DataRefreshResponse,
    DataStatusResponse,
    FundamentalsResponse,
    HealthResponse,
    SymbolsResponse,
)
from contracts.schemas.models.common import (
    ErrorResponse,
    HTTPValidationError,
    Timeframe,
)


@dataclass(frozen=True, slots=True)
class DataAPIContext:
    service: Any


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    422: {"model": HTTPValidationError},
    500: {"model": ErrorResponse},
}


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error_code=code, message=message)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


def create_data_router(context: DataAPIContext) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/health",
        operation_id="getHealth",
        response_model=HealthResponse,
        responses=ERROR_RESPONSES,
        tags=["system"],
    )
    def get_health() -> HealthResponse:
        return context.service.health()

    @router.post(
        "/api/data/refresh",
        operation_id="startDataRefresh",
        status_code=202,
        response_model=DataRefreshResponse,
        responses={
            **ERROR_RESPONSES,
            503: {"model": ErrorResponse},
        },
        tags=["data"],
    )
    def start_data_refresh(
        request: DataRefreshRequest | None = None,
    ) -> DataRefreshResponse:
        return context.service.start_refresh(
            force=request.force if request is not None else False
        )

    @router.get(
        "/api/data/status",
        operation_id="getDataStatus",
        response_model=DataStatusResponse,
        responses=ERROR_RESPONSES,
        tags=["data"],
    )
    def get_data_status() -> DataStatusResponse:
        return context.service.data_status()

    @router.get(
        "/api/symbols",
        operation_id="listSymbols",
        response_model=SymbolsResponse,
        responses=ERROR_RESPONSES,
        tags=["data"],
    )
    def list_symbols(
        q: str | None = None,
        exchange: str | None = None,
        security_type: str | None = None,
        trading_status: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> SymbolsResponse:
        return context.service.list_symbols(
            q=q,
            exchange=exchange,
            security_type=security_type,
            trading_status=trading_status,
            limit=limit,
            offset=offset,
        )

    @router.get(
        "/api/bars/{symbol}",
        operation_id="getBars",
        response_model=BarsResponse,
        responses={
            **ERROR_RESPONSES,
            404: {"model": ErrorResponse},
        },
        tags=["data"],
    )
    def get_bars(
        symbol: str,
        timeframe: Timeframe = Timeframe.D1,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> BarsResponse | JSONResponse:
        response = context.service.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )
        if response is None:
            return _error(404, "symbol_not_found", f"No bars found for {symbol}.")
        return response

    @router.get(
        "/api/fundamentals/{symbol}",
        operation_id="getFundamentals",
        response_model=FundamentalsResponse,
        responses={
            **ERROR_RESPONSES,
            404: {"model": ErrorResponse},
        },
        tags=["fundamentals"],
    )
    def get_fundamentals(
        symbol: str,
    ) -> FundamentalsResponse | JSONResponse:
        response = context.service.get_fundamentals(symbol)
        if response is None:
            return _error(
                404,
                "symbol_not_found",
                f"No fundamentals found for {symbol}.",
            )
        return response

    return router
