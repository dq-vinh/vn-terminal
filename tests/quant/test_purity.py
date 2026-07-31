"""Enforcement of the WP5 purity constraint.

The acceptance criteria for WP5 are "No network or database access inside
indicator functions" and "Pure functions produce repeatable results". Those
are properties of the code, so they are tested as properties of the code
rather than asserted in a docstring:

1. A static scan of every module in the indicator package for imports and
   attribute names associated with I/O, nondeterminism, or clock access.
2. A runtime sandbox that replaces `open`, the socket constructors, the
   process-spawning entry points, and `__import__` itself with functions
   that fail the test, and then runs every registered indicator inside it.
   This catches a lazy import that a static scan would miss.
3. Repeatability, cross-input independence, and input immutability checks.
"""

from __future__ import annotations

import ast
import builtins
import datetime
import os
import socket
import subprocess
from pathlib import Path

import numpy as np
import pytest
from helpers import call_kwargs

from backend.app.quant.indicators import (
    OHLCVSeries,
    all_indicators,
    build_indicators_payload,
    build_money_flow_block,
    compute,
)

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[2] / "backend" / "app" / "quant" / "indicators"
)

#: Modules an indicator has no legitimate reason to touch. `datetime` is
#: absent because `types.py` needs the `date` type to parse a contract bar;
#: the clock functions on it are caught by FORBIDDEN_ATTRIBUTES instead.
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
        "psycopg",
        "psycopg2",
        "random",
        "requests",
        "shutil",
        "smtplib",
        "socket",
        "sqlalchemy",
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

#: Attribute names that imply a clock read, a random draw, a connection, or
#: an environment lookup, whatever module they are reached through.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "connect",
        "environ",
        "getenv",
        "now",
        "popen",
        "putenv",
        "rand",
        "randint",
        "randn",
        "random",
        "seed",
        "system",
        "today",
        "urlopen",
        "utcnow",
    }
)

#: Builtins that reach outside the process.
FORBIDDEN_BUILTINS = frozenset({"open", "eval", "exec", "compile", "input", "__import__"})


def package_modules() -> list[Path]:
    return sorted(PACKAGE_ROOT.glob("*.py"))


def test_the_scan_actually_sees_the_package():
    """Guard against the scan silently passing because it found no files."""

    modules = package_modules()
    assert len(modules) >= 8, f"expected the indicator package, found {modules}"


@pytest.mark.parametrize("module_path", package_modules(), ids=lambda path: path.name)
def test_module_imports_nothing_that_reaches_outside_the_process(module_path: Path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])

    offending = sorted(imported & FORBIDDEN_IMPORTS)
    assert not offending, (
        f"{module_path.name} imports {offending}, which an indicator must not touch. "
        "Indicator functions receive already-loaded arrays; loading is the caller's job."
    )


@pytest.mark.parametrize("module_path", package_modules(), ids=lambda path: path.name)
def test_module_calls_nothing_nondeterministic(module_path: Path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            findings.append(f"line {node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_BUILTINS:
                findings.append(f"line {node.lineno}: {node.func.id}()")
    assert not findings, f"{module_path.name} contains {findings}"


class _Sandbox:
    """Replaces every escape hatch with a recorder that fails the test."""

    def __init__(self) -> None:
        self.violations: list[str] = []
        self._saved: dict[str, object] = {}
        self._allowed_modules: set[str] = set()

    def _trip(self, description: str):
        def blocked(*args, **kwargs):
            self.violations.append(f"{description} args={args!r}")
            raise AssertionError(f"indicator attempted {description}")

        return blocked

    def _guarded_import(self, real_import):
        def guard(name, globals=None, locals=None, fromlist=(), level=0):
            if level and globals:
                # A relative import resolves inside a package that is already
                # loaded, so judge it by the importing package's root.
                origin = globals.get("__package__") or globals.get("__name__") or ""
                root = origin.split(".")[0]
            else:
                root = name.split(".")[0]
            if root not in self._allowed_modules:
                self.violations.append(f"import of {name!r} during execution")
                raise AssertionError(f"indicator imported {name!r} at call time")
            return real_import(name, globals, locals, fromlist, level)

        return guard

    def __enter__(self) -> _Sandbox:
        import sys

        self._allowed_modules = {name.split(".")[0] for name in sys.modules}
        self._saved = {
            "open": builtins.open,
            "__import__": builtins.__import__,
            "socket": socket.socket,
            "create_connection": socket.create_connection,
            "system": os.system,
            "popen": os.popen,
            "run": subprocess.run,
            "Popen": subprocess.Popen,
        }
        builtins.open = self._trip("open()")
        builtins.__import__ = self._guarded_import(self._saved["__import__"])
        socket.socket = self._trip("socket.socket()")
        socket.create_connection = self._trip("socket.create_connection()")
        os.system = self._trip("os.system()")
        os.popen = self._trip("os.popen()")
        subprocess.run = self._trip("subprocess.run()")
        subprocess.Popen = self._trip("subprocess.Popen()")
        return self

    def __exit__(self, *exc_info) -> None:
        builtins.open = self._saved["open"]
        builtins.__import__ = self._saved["__import__"]
        socket.socket = self._saved["socket"]
        socket.create_connection = self._saved["create_connection"]
        os.system = self._saved["system"]
        os.popen = self._saved["popen"]
        subprocess.run = self._saved["run"]
        subprocess.Popen = self._saved["Popen"]


def test_sandbox_itself_works():
    """A sandbox that blocks nothing would make every test below vacuous."""

    with _Sandbox() as sandbox:
        with pytest.raises(AssertionError):
            builtins.open("/etc/hostname")
        with pytest.raises(AssertionError):
            socket.socket()
    assert len(sandbox.violations) == 2


def test_every_indicator_runs_with_all_io_blocked(fpt: OHLCVSeries):
    # Warm-up pass outside the sandbox. numpy resolves a few of its own
    # submodules lazily on first use (numpy.ma, reached through np.median),
    # and blocking those would fail the test for numpy's internals rather
    # than for anything an indicator did. After this pass every module the
    # computation needs is already in sys.modules, so any import seen inside
    # the sandbox genuinely originates from indicator code.
    for entry in all_indicators():
        compute(entry.spec.indicator_id, fpt, **call_kwargs(entry.spec, fpt))
    build_money_flow_block(fpt)
    build_indicators_payload(fpt)

    with _Sandbox() as sandbox:
        for entry in all_indicators():
            compute(entry.spec.indicator_id, fpt, **call_kwargs(entry.spec, fpt))
        build_money_flow_block(fpt)
        build_indicators_payload(fpt)
    assert sandbox.violations == []


def test_results_are_repeatable(fpt: OHLCVSeries):
    for entry in all_indicators():
        kwargs = call_kwargs(entry.spec, fpt)
        first = compute(entry.spec.indicator_id, fpt, **kwargs)
        second = compute(entry.spec.indicator_id, fpt, **kwargs)
        for output in entry.spec.outputs:
            np.testing.assert_array_equal(
                first[output],
                second[output],
                err_msg=f"{entry.spec.indicator_id}.{output} is not repeatable",
            )
        assert first.scalars == second.scalars


def test_no_state_carries_between_securities(fpt: OHLCVSeries, kdh: OHLCVSeries):
    """Running a different security in between must change nothing."""

    for entry in all_indicators():
        baseline = compute(entry.spec.indicator_id, fpt, **call_kwargs(entry.spec, fpt))
        compute(entry.spec.indicator_id, kdh, **call_kwargs(entry.spec, kdh))
        repeat = compute(entry.spec.indicator_id, fpt, **call_kwargs(entry.spec, fpt))
        for output in entry.spec.outputs:
            np.testing.assert_array_equal(
                baseline[output],
                repeat[output],
                err_msg=f"{entry.spec.indicator_id}.{output} depends on call order",
            )


def test_inputs_are_immutable_and_unmodified(fpt: OHLCVSeries):
    before = {
        name: np.array(getattr(fpt, name), copy=True)
        for name in ("open", "high", "low", "close", "volume")
    }
    for name in before:
        assert not getattr(fpt, name).flags.writeable, f"{name} must be read-only"

    for entry in all_indicators():
        compute(entry.spec.indicator_id, fpt, **call_kwargs(entry.spec, fpt))

    for name, original in before.items():
        np.testing.assert_array_equal(
            original, getattr(fpt, name), err_msg=f"an indicator mutated {name}"
        )


def test_outputs_are_immutable(fpt: OHLCVSeries):
    result = compute("sma", fpt, period=20)
    with pytest.raises(ValueError):
        result["value"][0] = 1.0


def test_constructor_copies_caller_data():
    """A caller mutating its own list afterwards must not change the series."""

    closes = [1.0, 2.0, 3.0]
    series = OHLCVSeries(
        symbol="TEST",
        trading_dates=(
            datetime.date(2026, 1, 5),
            datetime.date(2026, 1, 6),
            datetime.date(2026, 1, 7),
        ),
        open=closes,
        high=closes,
        low=closes,
        close=closes,
        volume=[1.0, 1.0, 1.0],
    )
    closes[0] = 999.0
    assert series.close[0] == 1.0


def test_registry_is_not_mutated_by_computation(fpt: OHLCVSeries):
    from backend.app.quant.indicators import all_ids

    before = all_ids()
    for entry in all_indicators():
        compute(entry.spec.indicator_id, fpt, **call_kwargs(entry.spec, fpt))
    assert all_ids() == before
