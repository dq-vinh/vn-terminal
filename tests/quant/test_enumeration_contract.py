"""Defect 2 (docs/pre_integration_fixes.md, Blocker 3): enumeration mismatch
with the canonical contract.

`dual_sma_trend_crossover.py` and `screener/universe.py` used to declare
`accepted_exchanges=frozenset({"HOSE", "HNX", "UPCOM"})` and
`accepted_security_types=frozenset({"ordinary_equity"})`. The frozen
contract (`contracts/schemas/models/security_master.py`,
`contracts/schemas/models/price_bar.py`) and the plan's own fixtures
(`contracts/fixtures/bars_FPT.json`) use `"UPCoM"` and `"equity"`. The quant
module therefore rejected every security the data module emits, and the
screener returned zero rows with no error and no exception: a silent
integration failure, not a loud one.

This file tests two things: that both modules now accept the exact contract
values, and that the old values can never silently reappear.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from strategy_helpers import make_history, round_trip_closes

from backend.app.quant.screener.universe import UniverseFilters
from backend.app.quant.strategies import (
    PositionState,
    SecurityView,
    evaluate,
    metadata,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
QUANT_ROOT = REPO_ROOT / "backend" / "app" / "quant"
STRATEGY = "dual_sma_trend_crossover"

#: The exact values contracts/schemas/models/security_master.py and
#: price_bar.py document as evidenced ("examples") for exchange and
#: security_type. These are the values the data layer is contracted to
#: emit; a quant-side accepted-value set that does not equal these silently
#: rejects everything, as it did before this fix.
CANONICAL_EXCHANGES = frozenset({"HOSE", "HNX", "UPCoM"})
CANONICAL_SECURITY_TYPES = frozenset({"equity"})

#: Enumeration values that must never reappear anywhere in the quant module.
#: "UPCOM" (all caps) is distinct from the canonical "UPCoM"; "ordinary_equity"
#: has never been a contract value at all.
BANNED_LITERALS = ("UPCOM", "ordinary_equity")


def _all_quant_source_files() -> list[Path]:
    return sorted(
        path
        for path in QUANT_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _string_literals(path: Path) -> set[str]:
    """Every string literal in `path`'s AST, so a match inside a comment
    (which the fix's own explanatory notes deliberately contain) does not
    produce a false positive."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return literals


# ------------------------------------------------------- acceptance, defect 2


def test_dual_sma_accepts_the_exact_canonical_enumeration_values():
    meta = metadata(STRATEGY)
    assert meta.accepted_exchanges == CANONICAL_EXCHANGES
    assert meta.accepted_security_types == CANONICAL_SECURITY_TYPES


def test_screener_universe_filters_accept_the_exact_canonical_enumeration_values():
    filters = UniverseFilters()
    assert filters.accepted_exchanges == CANONICAL_EXCHANGES
    assert filters.accepted_security_types == CANONICAL_SECURITY_TYPES


def test_a_security_carrying_the_canonical_values_is_not_silently_rejected():
    """The end-to-end symptom: a real "equity" on "UPCoM" must be admitted.

    Before the fix this screened out with no error and no exception,
    because "equity" != "ordinary_equity" and "UPCoM" != "UPCOM".
    """

    history = make_history(closes=round_trip_closes(count=160))
    security = SecurityView(
        "TEST", history.trading_dates[119], "UPCoM", "equity", "active"
    )
    result = evaluate(
        STRATEGY,
        history.window(119),
        security=security,
        position_state=PositionState.FLAT,
    )
    assert result.evidence["universe_pass"] is True


# ------------------------------------------------------------ regression, all


@pytest.mark.parametrize("banned", BANNED_LITERALS)
def test_the_old_enumeration_values_never_reappear_in_quant_source(banned):
    """Regression: fails immediately if "UPCOM" or "ordinary_equity"
    reappears anywhere in backend/app/quant, as a string literal, not merely
    absent from a docstring's prose recounting the fix."""

    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(
            literal for literal in _string_literals(path) if banned in literal
        )
        for path in _all_quant_source_files()
    }
    offenders = {path: hits for path, hits in offenders.items() if hits}
    assert not offenders, (
        f"{banned!r} reappeared as a string literal in backend/app/quant: {offenders}"
    )


# --------------------------------------------------- reconciliation inventory
#
# Every other hardcoded enumeration value found in backend/app/quant/**,
# checked against contracts/schemas/, per the handoff instruction to report
# every instance including ones that were already correct.


def test_quality_status_accepted_values_match_the_price_bar_contract():
    """price_bar.schema.json documents only "valid" as evidenced for
    quality_status; dual_sma_trend_crossover.py's accepted_quality_statuses
    already matched this before the fix and still does."""

    assert metadata(STRATEGY).accepted_quality_statuses == frozenset({"valid"})


def test_trading_status_accepted_values_match_the_security_master_contract():
    """security_master.py documents "active", "suspended", "delisted" as
    examples for trading_status; both modules gate entry on "active" alone,
    which was already correct and is unchanged by this fix."""

    assert metadata(STRATEGY).accepted_trading_statuses == frozenset({"active"})
    assert UniverseFilters().accepted_trading_statuses == frozenset({"active"})


def test_critical_quality_severity_matches_the_quality_issue_contract():
    """quality_issue.schema.json's Severity enum is
    {critical, high, medium, low}; screener/universe.py's
    CRITICAL_QUALITY_VALUES = {"critical"} names one of those four and was
    already correct."""

    from backend.app.quant.screener.universe import CRITICAL_QUALITY_VALUES

    assert CRITICAL_QUALITY_VALUES == frozenset({"critical"})
    assert CRITICAL_QUALITY_VALUES <= frozenset({"critical", "high", "medium", "low"})


def test_index_security_type_matches_the_documented_security_master_convention():
    """relative_strength.py's mapping_from_security_master() matches entries
    on security_type == "index" (case-insensitively). security_master.py's
    own index_code field documents "security_type=index entries" as the
    source of that mapping, so this was already correct; it is not the
    "equity" value this fix touches, since an index is not an equity."""

    from backend.app.quant.indicators.relative_strength import (
        mapping_from_security_master,
    )

    mapping = mapping_from_security_master(
        [
            {
                "security_type": "index",
                "index_code": "0001",
                "company_name": "VN-Index",
                "sector": None,
            }
        ]
    )
    assert mapping.index_name_by_code == {"0001": "VN-Index"}
