"""Registry, Section 10.4 completeness, contract conformance, and purity.

Three separable claims are tested here.

1. **Every Section 10.4 field is populated, with substance.** WP6's acceptance
   criterion is that "Every strategy has version, parameters, rules, and
   tests". A field containing `PLACEHOLDER`, `TODO`, or a one-word stub would
   satisfy a non-empty check while satisfying nothing else, so the tests
   reject those explicitly.
2. **What the registry emits validates against the frozen contract.** The
   contract is version 0.1.0 and belongs to the lead integrator; the tests
   validate against the JSON Schema on disk rather than against a copy.
3. **The package is pure.** Same static and runtime enforcement WP5 applies to
   the indicator package, extended to the strategy package, with the same
   meta-test proving the sandbox is not vacuous.

The catalogue-size test is deliberately an equality, not a lower bound. The
work-package instruction is "Never invent a rule to fill a gap, and never add
a strategy to reach a target count", and an assertion that the registry holds
exactly the approved specifications is the mechanical form of that
instruction.
"""

from __future__ import annotations

import ast
import builtins
import json
import socket
import subprocess
from pathlib import Path

import jsonschema
import pytest
from strategy_helpers import crossover_closes, make_history, security_view

from backend.app.quant.strategies import (
    PositionState,
    all_ids,
    all_strategies,
    catalogue,
    evaluate,
    metadata,
    registry,
    to_contract_definition,
    to_contract_result,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "contracts" / "schemas" / "json"
PACKAGE_ROOT = REPO_ROOT / "backend" / "app" / "quant" / "strategies"

#: Every strategy with `Specification status: Approved` in
#: docs/strategy_catalogue.md as of 31 July 2026.
APPROVED_STRATEGIES = ("dual_sma_trend_crossover",)

PLACEHOLDER_MARKERS = ("placeholder", "todo", "tbd", "fixme", "xxx", "not yet")


def load_schema(name: str) -> dict:
    with (SCHEMAS / name).open(encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------------ registry


def test_the_registry_holds_exactly_the_approved_specifications():
    assert all_ids() == APPROVED_STRATEGIES, (
        "the registry must contain exactly the strategies with an approved "
        "written specification. Adding one without a specification, or to reach "
        "the v1.0 count of ten to fifteen, is prohibited by the work package."
    )


def test_registering_the_same_strategy_twice_is_refused():
    entry = registry.get("dual_sma_trend_crossover")
    with pytest.raises(Exception, match="already registered"):
        registry.register(entry.strategy)


def test_an_unknown_strategy_id_names_the_known_ones():
    with pytest.raises(Exception, match="dual_sma_trend_crossover"):
        registry.get("no_such_strategy")


def test_versions_map_is_reported_for_run_records():
    assert registry.versions() == {"dual_sma_trend_crossover": "1.1.0"}


# ------------------------------------------------------------- Section 10.4


@pytest.mark.parametrize("entry", all_strategies(), ids=lambda item: item.strategy_id)
def test_every_section_10_4_field_is_populated(entry):
    definition = to_contract_definition(entry)
    required = [
        "strategy_id",
        "version",
        "title_vi",
        "title_en",
        "category",
        "timeframe",
        "required_fields",
        "warmup_bars",
        "parameter_schema",
        "entry_rule",
        "exit_rule",
        "invalidation_rule",
        "liquidity_rule",
        "execution_convention",
        "evidence_fields",
        "reference",
    ]
    for field in required:
        assert field in definition, f"Section 10.4 requires {field}"
        value = definition[field]
        assert value not in (None, "", [], {}), f"{field} is empty"


@pytest.mark.parametrize("entry", all_strategies(), ids=lambda item: item.strategy_id)
def test_rule_fields_are_substantive_not_stubs(entry):
    definition = to_contract_definition(entry)
    for field in ("entry_rule", "exit_rule", "invalidation_rule", "liquidity_rule"):
        text = definition[field]
        lowered = text.lower()
        assert len(text) > 80, f"{field} is too short to be a specification"
        assert not any(marker in lowered for marker in PLACEHOLDER_MARKERS), (
            f"{field} contains placeholder text: {text[:80]!r}"
        )


@pytest.mark.parametrize("entry", all_strategies(), ids=lambda item: item.strategy_id)
def test_reference_names_its_source(entry):
    reference = to_contract_definition(entry)["reference"]
    assert "docs/strategy_catalogue.md" in reference or "owner_judgment" in reference


@pytest.mark.parametrize("entry", all_strategies(), ids=lambda item: item.strategy_id)
def test_parameter_schema_describes_every_parameter(entry):
    schema = to_contract_definition(entry)["parameter_schema"]
    assert schema["kind"] == "vn_terminal_parameter_table_v1"
    names = {item["name"] for item in schema["parameters"]}
    assert names == set(entry.metadata.defaults)
    for item in schema["parameters"]:
        assert item["minimum"] <= item["default"] <= item["maximum"]
        assert item["type"] in {"integer", "number"}
        assert item["unit"]


def test_warmup_bars_in_the_contract_definition_tracks_the_parameters():
    """The contract holds one integer; the specification holds a formula.

    The published value must be the one for the parameters it was generated
    with, so a caller who changes `slow_period` and reads the definition back
    is not told 51.
    """

    entry = registry.get("dual_sma_trend_crossover")
    assert to_contract_definition(entry)["warmup_bars"] == 51
    assert to_contract_definition(entry, {"slow_period": 120})["warmup_bars"] == 121


# ------------------------------------------------------------------ contract


def test_catalogue_validates_against_the_frozen_strategy_definition_schema():
    schema = load_schema("strategy_definition.schema.json")
    for definition in catalogue():
        jsonschema.validate(definition, schema)


def test_strategies_response_shape_validates():
    schema = load_schema("strategies_response.schema.json")
    payload = {
        "strategies": catalogue(),
        "provenance": {
            "as_of_date": "2026-07-31",
            "data_version": "fdata-2026-07-30",
            "source": "Fialda FData",
            "freshness_status": "current",
            "warnings": [],
        },
    }
    jsonschema.validate(payload, schema)


def test_evaluation_result_validates_against_the_frozen_schema():
    schema = load_schema("strategy_evaluation_result.schema.json")
    history = make_history(closes=crossover_closes(count=120))
    result = evaluate(
        "dual_sma_trend_crossover",
        history.window(119),
        security=security_view("TEST", history.trading_dates[119]),
        position_state=PositionState.FLAT,
    )
    jsonschema.validate(to_contract_result(result), schema)


def test_evaluate_response_envelope_validates():
    schema = load_schema("strategy_evaluate_response.schema.json")
    history = make_history(closes=crossover_closes(count=120))
    result = evaluate(
        "dual_sma_trend_crossover",
        history.window(119),
        security=security_view("TEST", history.trading_dates[119]),
        position_state=PositionState.FLAT,
    )
    payload = {
        "results": [to_contract_result(result)],
        "provenance": {
            "as_of_date": "2026-07-31",
            "data_version": "fdata-2026-07-30",
            "source": "Fialda FData",
            "freshness_status": "current",
            "warnings": [],
        },
    }
    jsonschema.validate(payload, schema)


def test_the_contract_cannot_carry_the_specified_evidence_fields():
    """Documents the gap rather than papering over it.

    The approved specification names thirty-seven evidence fields and requires
    the AI layer to consume them as facts. `StrategyEvaluationResult` is
    `additionalProperties: false` with twelve. This test asserts the mismatch
    is real, so that if the lead integrator later extends the contract, the
    test fails and the handoff's change proposal gets revisited rather than
    quietly going stale.
    """

    schema = load_schema("strategy_evaluation_result.schema.json")
    contract_fields = set(schema["properties"])
    specified = set(metadata("dual_sma_trend_crossover").evidence_fields)
    assert schema.get("additionalProperties") is False
    missing = specified - contract_fields
    assert missing, "the contract now carries every evidence field; update the handoff"
    assert "order_status" in missing
    assert "execution_price" in missing


# -------------------------------------------------------------------- purity

FORBIDDEN_IMPORTS = frozenset(
    {
        "aiohttp",
        "asyncio",
        "duckdb",
        "ftplib",
        "http",
        "httpx",
        "io",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "random",
        "requests",
        "shutil",
        "socket",
        "sqlite3",
        "ssl",
        "subprocess",
        "tempfile",
        "threading",
        "time",
        "urllib",
        "webbrowser",
    }
)

FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "connect",
        "environ",
        "getenv",
        "now",
        "popen",
        "seed",
        "system",
        "today",
        "urlopen",
        "utcnow",
    }
)


def package_modules() -> list[Path]:
    return sorted(PACKAGE_ROOT.glob("*.py"))


def test_the_scan_actually_sees_the_package():
    modules = package_modules()
    assert len(modules) >= 6, f"expected the strategy package, found {modules}"


@pytest.mark.parametrize("module_path", package_modules(), ids=lambda path: path.name)
def test_no_forbidden_import(module_path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in FORBIDDEN_IMPORTS, f"{module_path.name} imports {root}"
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            root = node.module.split(".")[0]
            assert root not in FORBIDDEN_IMPORTS, f"{module_path.name} imports {root}"


@pytest.mark.parametrize("module_path", package_modules(), ids=lambda path: path.name)
def test_no_forbidden_attribute_or_dynamic_execution(module_path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in FORBIDDEN_ATTRIBUTES, (
                f"{module_path.name} touches .{node.attr}"
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"eval", "exec", "compile", "open"}, (
                f"{module_path.name} calls {node.func.id}"
            )


def test_evaluation_runs_inside_a_sandbox_that_blocks_io(monkeypatch):
    """Runtime enforcement, to catch a lazy import a static scan would miss."""

    def blocked(*args, **kwargs):
        raise AssertionError("strategy evaluation attempted I/O")

    monkeypatch.setattr(builtins, "open", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)

    history = make_history(closes=crossover_closes(count=120))
    for strategy_id in all_ids():
        evaluate(
            strategy_id,
            history.window(119),
            security=security_view("TEST", history.trading_dates[119]),
            position_state=PositionState.FLAT,
        )


def test_the_sandbox_itself_blocks(monkeypatch):
    """Meta-test: the sandbox above must not pass vacuously."""

    def blocked(*args, **kwargs):
        raise AssertionError("blocked")

    monkeypatch.setattr(builtins, "open", blocked)
    with pytest.raises(AssertionError, match="blocked"):
        open(__file__)  # noqa: SIM115


def test_evaluation_is_repeatable_and_does_not_mutate_its_input():
    history = make_history(closes=crossover_closes(count=120))
    before = (list(history.close), list(history.volume), list(history.open))
    first = to_contract_result(
        evaluate(
            "dual_sma_trend_crossover",
            history.window(119),
            security=security_view("TEST", history.trading_dates[119]),
            position_state=PositionState.FLAT,
        )
    )
    second = to_contract_result(
        evaluate(
            "dual_sma_trend_crossover",
            history.window(119),
            security=security_view("TEST", history.trading_dates[119]),
            position_state=PositionState.FLAT,
        )
    )
    assert first == second
    assert (list(history.close), list(history.volume), list(history.open)) == before
