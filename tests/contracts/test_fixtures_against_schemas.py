"""WP0 deliverable 8: "Write contract tests that validate every fixture
against its schema. These must pass before you finish."

Every file in contracts/fixtures/*.json is validated against the JSON
Schema in contracts/schemas/json/ that describes its shape. The mapping
below is the source of truth for which fixture matches which schema; see
contracts/fixtures/README.md for the same mapping in prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

FIXTURE_TO_SCHEMA = {
    "bars_FPT.json": "bars_response.schema.json",
    "bars_KDH.json": "bars_response.schema.json",
    "fundamentals_FPT.json": "fundamentals_response.schema.json",
    "fundamentals_KDH.json": "fundamentals_response.schema.json",
    "strategy_evaluation_FPT.json": "strategy_evaluate_response.schema.json",
    "strategy_evaluation_KDH.json": "strategy_evaluate_response.schema.json",
    "ai_fact_bundle_FPT.json": "ai_fact_bundle.schema.json",
    "ai_fact_bundle_KDH.json": "ai_fact_bundle.schema.json",
    "strategy_definitions.json": "strategies_response.schema.json",
    "security_master.json": "symbols_response.schema.json",
}


def _fixtures_dir(repo_root: Path) -> Path:
    return repo_root / "contracts" / "fixtures"


def _schemas_dir(repo_root: Path) -> Path:
    return repo_root / "contracts" / "schemas" / "json"


def test_every_fixture_file_is_mapped(repo_root: Path):
    """Guard against a new fixture being added without a schema mapping."""

    fixtures_dir = _fixtures_dir(repo_root)
    on_disk = {p.name for p in fixtures_dir.glob("*.json")}
    assert on_disk == set(FIXTURE_TO_SCHEMA), (
        "contracts/fixtures/*.json does not match FIXTURE_TO_SCHEMA in this "
        "test file. Update FIXTURE_TO_SCHEMA (and contracts/fixtures/"
        "README.md) when adding or removing a fixture."
    )


def test_every_referenced_schema_file_exists(repo_root: Path):
    schemas_dir = _schemas_dir(repo_root)
    for schema_name in set(FIXTURE_TO_SCHEMA.values()):
        assert (schemas_dir / schema_name).is_file(), schema_name


@pytest.mark.parametrize("fixture_name,schema_name", sorted(FIXTURE_TO_SCHEMA.items()))
def test_fixture_matches_schema(repo_root: Path, fixture_name: str, schema_name: str):
    fixture_path = _fixtures_dir(repo_root) / fixture_name
    schema_path = _schemas_dir(repo_root) / schema_name

    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # The schema itself must be a well-formed JSON Schema (2020-12).
    Draft202012Validator.check_schema(schema)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(fixture_data), key=lambda e: list(e.path))
    if errors:
        details = "\n".join(
            f"  - {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors
        )
        pytest.fail(
            f"{fixture_name} does not satisfy {schema_name}:\n{details}"
        )


@pytest.mark.parametrize(
    "fixture_name",
    ["bars_FPT.json", "bars_KDH.json"],
)
def test_bars_fixture_has_at_least_500_bars(repo_root: Path, fixture_name: str):
    data = json.loads((_fixtures_dir(repo_root) / fixture_name).read_text(encoding="utf-8"))
    assert len(data["bars"]) >= 500, (
        "WP0 deliverable 4 requires at least 500 daily bars per symbol; "
        f"{fixture_name} has {len(data['bars'])}."
    )


def test_fpt_latest_bar_matches_plan_section_10_1(repo_root: Path):
    """The one real, plan-verified number in any fixture: the FPT bar for
    2026-07-30, from Section 10.1 of vn_terminal_multi_ai_development_plan.md
    v1.1. Every other value in every fixture is synthetic (see
    contracts/fixtures/README.md); this test guards the one exception.
    """

    data = json.loads((_fixtures_dir(repo_root) / "bars_FPT.json").read_text(encoding="utf-8"))
    last = data["bars"][-1]
    assert last["trading_date"] == "2026-07-30"
    assert last["open"] == 65.2
    assert last["high"] == 67.2
    assert last["low"] == 64.8
    assert last["close"] == 67.0
    assert last["volume"] == 7_571_500


@pytest.mark.parametrize(
    "fixture_name",
    sorted(FIXTURE_TO_SCHEMA),
)
def test_fixture_declares_synthetic_data_warning(repo_root: Path, fixture_name: str):
    """Every fixture must be honest about not being real market data
    (Section 18.1: 'AI may not... create missing price data'; the same
    discipline applies to fixtures a human or agent might mistake for a
    live feed).

    Most fixtures are API response envelopes and carry the warning in
    provenance.warnings. ai_fact_bundle_*.json is the canonical
    AIFactBundle contract itself (Section 10.6), which has no top-level
    provenance field; it carries data-freshness warnings in
    data_quality.warnings instead (see contracts/OPEN_ITEMS.md, section B).
    """

    data = json.loads((_fixtures_dir(repo_root) / fixture_name).read_text(encoding="utf-8"))
    if "provenance" in data:
        warnings = data["provenance"].get("warnings", [])
    else:
        warnings = data.get("data_quality", {}).get("warnings", [])
    assert any("SYNTHETIC FIXTURE DATA" in w for w in warnings), fixture_name
