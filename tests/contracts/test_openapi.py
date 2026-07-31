"""Structural checks on contracts/openapi.yaml.

WP0 deliverable 2 requires OpenAPI 3.1 with typed request/response schemas,
explicit error responses, and as_of_date/data_version/source on every
endpoint (via the shared Provenance component; see docs/decision_log.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate

# Section 11 table of vn_terminal_multi_ai_development_plan.md v1.1: 18
# operations across 17 distinct paths (GET/PUT /api/settings share one path).
EXPECTED_PATHS = {
    "/api/health",
    "/api/data/refresh",
    "/api/data/status",
    "/api/symbols",
    "/api/bars/{symbol}",
    "/api/fundamentals/{symbol}",
    "/api/indicators/{symbol}",
    "/api/strategies",
    "/api/strategies/evaluate",
    "/api/screen",
    "/api/screen/{run_id}",
    "/api/backtest",
    "/api/backtest/{run_id}",
    "/api/ai/analyze",
    "/api/watchlists",
    "/api/watchlists/{id}",
    "/api/settings",
}


@pytest.fixture(scope="module")
def openapi_doc(repo_root: Path) -> dict:
    text = (repo_root / "contracts" / "openapi.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_openapi_is_version_3_1(openapi_doc: dict):
    assert openapi_doc["openapi"].startswith("3.1"), (
        "WP0 constraint: 'Output OpenAPI 3.1.'"
    )


def test_openapi_passes_spec_validation(openapi_doc: dict):
    validate(openapi_doc)


def test_openapi_paths_match_section_11(openapi_doc: dict):
    assert set(openapi_doc["paths"]) == EXPECTED_PATHS, (
        "contracts/openapi.yaml paths must match Section 11 of "
        "vn_terminal_multi_ai_development_plan.md v1.1 exactly. Do not add "
        "or remove endpoints without a contract-change proposal "
        "(contracts/OWNERSHIP.md Section 24.2)."
    )


def test_openapi_version_matches_contracts_version(openapi_doc: dict, repo_root: Path):
    contract_version = (repo_root / "contracts" / "VERSION").read_text().strip()
    assert openapi_doc["info"]["version"] == contract_version


def test_openapi_binds_localhost_only(openapi_doc: dict):
    urls = [s["url"] for s in openapi_doc["servers"]]
    assert all("127.0.0.1" in u for u in urls), (
        "Section 3.1: 'The application binds to 127.0.0.1 and is not "
        "exposed publicly.'"
    )


@pytest.mark.parametrize("path", sorted(EXPECTED_PATHS))
def test_every_operation_has_explicit_error_responses(openapi_doc: dict, path: str):
    """Section 11: 'All endpoints must have... Explicit error responses.'"""

    item = openapi_doc["paths"][path]
    for method in ("get", "post", "put", "delete", "patch"):
        if method not in item:
            continue
        responses = item[method]["responses"]
        error_codes = {code for code in responses if code not in ("200", "201", "202")}
        assert error_codes, f"{method.upper()} {path} declares no error responses"
        assert any(code.startswith(("4", "5")) for code in error_codes), (
            f"{method.upper()} {path} error responses are not 4xx/5xx: {error_codes}"
        )


@pytest.mark.parametrize("path", sorted(EXPECTED_PATHS))
def test_every_success_response_references_a_schema_with_provenance(
    openapi_doc: dict, path: str
):
    """Section 11: 'All endpoints must have as_of_date, data_version,
    source.' Enforced here via the shared Provenance component embedded in
    every response schema (docs/decision_log.md, WP0 entry). Request-only
    operations without a body response schema are exempt.
    """

    schemas = openapi_doc["components"]["schemas"]
    item = openapi_doc["paths"][path]
    for method in ("get", "post", "put"):
        if method not in item:
            continue
        for code, resp in item[method]["responses"].items():
            if not code.startswith("2"):
                continue
            schema_ref = resp["content"]["application/json"]["schema"]["$ref"]
            schema_name = schema_ref.rsplit("/", 1)[-1]
            props = schemas[schema_name].get("properties", {})
            assert "provenance" in props, (
                f"{method.upper()} {path} {code} response schema "
                f"'{schema_name}' has no 'provenance' field."
            )
            prov_ref = props["provenance"]["$ref"].rsplit("/", 1)[-1]
            prov_props = schemas[prov_ref]["properties"]
            for required_field in ("as_of_date", "data_version", "source"):
                assert required_field in prov_props, (
                    f"Provenance component is missing '{required_field}' "
                    f"(Section 11 requirement)."
                )
