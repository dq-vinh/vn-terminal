"""Shared fixtures for the WP5 indicator tests.

Every test in this directory develops against `contracts/fixtures/`, never
against a live database, per the WP5 instruction. The fixtures are synthetic
(see `contracts/fixtures/README.md`); the tests use them for shape, warm-up,
and regression purposes and never quote a value from them as a market fact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from helpers import REPO_ROOT, load_fixture, load_series

from backend.app.quant.indicators import (
    IndexCodeMapping,
    OHLCVSeries,
    mapping_from_security_master,
)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fpt() -> OHLCVSeries:
    return load_series("FPT")


@pytest.fixture(scope="session")
def kdh() -> OHLCVSeries:
    return load_series("KDH")


@pytest.fixture(scope="session")
def security_master() -> list[dict[str, Any]]:
    return list(load_fixture("security_master.json")["items"])


@pytest.fixture(scope="session")
def index_mapping(security_master: list[dict[str, Any]]) -> IndexCodeMapping:
    """The Section 10.2 index code-to-name mapping, as far as it exists.

    Derived from the security master rather than hard-coded. While no
    `security_type: "index"` entry with an `index_code` exists, the mapping
    comes back unusable and the relative-strength resolution tests skip
    themselves with `MISSING_MAPPING_REASON`.
    """

    return mapping_from_security_master(security_master)
