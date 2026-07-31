from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.data.api import DataAPIContext, create_data_router
from contracts.schemas.models.api_envelopes import (
    BarsResponse,
    DatabaseStatus,
    DataRefreshResponse,
    DataStatusResponse,
    FundamentalsResponse,
    HealthResponse,
    SnapshotInfo,
    SymbolsResponse,
)
from contracts.schemas.models.common import Provenance

PROVENANCE = Provenance(
    as_of_date=date(2026, 7, 30),
    data_version="fdata-test",
    source="Fialda FData",
    freshness_status="current",
    warnings=[],
)


class FakeService:
    def health(self):
        return HealthResponse(
            status="ok",
            database=DatabaseStatus(
                connected=True, latest_snapshot_date=date(2026, 7, 30)
            ),
            providers=[],
            provenance=PROVENANCE,
        )

    def start_refresh(self, force: bool):
        return DataRefreshResponse(
            run_id="run-1",
            status="queued",
            started_at=datetime(2026, 7, 30, 22, 0, tzinfo=UTC),
            provenance=PROVENANCE,
        )

    def data_status(self):
        return DataStatusResponse(
            run_id="run-1",
            status="completed",
            progress_pct=100,
            latest_good_snapshot=SnapshotInfo(
                data_version="fdata-test",
                as_of_date=date(2026, 7, 30),
                promoted_at=datetime(2026, 7, 30, 22, 1, tzinfo=UTC),
            ),
            issues=[],
            provenance=PROVENANCE,
        )

    def list_symbols(self, **kwargs):
        return SymbolsResponse(items=[], total=0, provenance=PROVENANCE)

    def get_bars(self, symbol, timeframe, start_date, end_date):
        if symbol != "FPT":
            return None
        return BarsResponse(
            symbol="FPT", timeframe=timeframe, bars=[], provenance=PROVENANCE
        )

    def get_fundamentals(self, symbol):
        if symbol != "FPT":
            return None
        return FundamentalsResponse(
            symbol="FPT",
            observations=[],
            derived_metrics=[],
            provenance=PROVENANCE,
        )


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_data_router(DataAPIContext(service=FakeService())))
    return TestClient(app)


def test_router_implements_wp3_and_wp9_data_operations():
    app = FastAPI()
    app.include_router(create_data_router(DataAPIContext(service=FakeService())))
    operations = {
        route.operation_id
        for route in app.routes
        if getattr(route, "operation_id", None)
    }
    assert operations == {
        "getHealth",
        "startDataRefresh",
        "getDataStatus",
        "listSymbols",
        "getBars",
        "getFundamentals",
    }


def test_router_response_statuses_match_frozen_openapi():
    app = FastAPI()
    app.include_router(create_data_router(DataAPIContext(service=FakeService())))
    generated = app.openapi()
    frozen = yaml.safe_load(
        Path("contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    data_paths = {
        "/api/health",
        "/api/data/refresh",
        "/api/data/status",
        "/api/symbols",
        "/api/bars/{symbol}",
        "/api/fundamentals/{symbol}",
    }

    for path in data_paths:
        method = next(iter(frozen["paths"][path]))
        assert generated["paths"][path][method]["operationId"] == frozen[
            "paths"
        ][path][method]["operationId"]
        assert set(generated["paths"][path][method]["responses"]) == set(
            frozen["paths"][path][method]["responses"]
        )


def test_data_endpoints_return_contract_envelopes_and_explicit_404():
    client = make_client()

    assert client.get("/api/health").status_code == 200
    assert client.post("/api/data/refresh", json={"force": False}).status_code == 202
    assert client.get("/api/data/status").status_code == 200
    assert client.get("/api/symbols?limit=100&offset=0").status_code == 200
    assert client.get("/api/bars/FPT?timeframe=1D").status_code == 200
    assert client.get("/api/fundamentals/FPT").status_code == 200
    missing = client.get("/api/bars/MISSING?timeframe=1D")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "symbol_not_found"
    missing_financials = client.get("/api/fundamentals/MISSING")
    assert missing_financials.status_code == 404
    assert missing_financials.json()["error_code"] == "symbol_not_found"
