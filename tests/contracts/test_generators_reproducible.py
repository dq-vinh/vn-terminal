"""Guards against committed generated files drifting from their generators.

contracts/schemas/json/*.schema.json, contracts/openapi.yaml, and
contracts/fixtures/*.json are all produced by scripts in this repository
and must never be hand-edited (see the header comment in each generator).
This test re-runs each generator and confirms the files on disk do not
change, which would mean someone edited a generated file directly, or
edited a model without regenerating.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


def _hash_files(paths: list[Path]) -> dict[Path, str]:
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}


def test_json_schema_generator_is_idempotent(repo_root: Path):
    schema_dir = repo_root / "contracts" / "schemas" / "json"
    before = _hash_files(sorted(schema_dir.glob("*.schema.json")))

    result = subprocess.run(
        [sys.executable, str(repo_root / "contracts" / "schemas" / "generate_json_schema.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    after = _hash_files(sorted(schema_dir.glob("*.schema.json")))
    assert before == after, (
        "contracts/schemas/json/*.schema.json changed after re-running "
        "generate_json_schema.py. Either a schema file was hand-edited, or "
        "a model changed without the schema files being regenerated and "
        "committed. Run 'python contracts/schemas/generate_json_schema.py' "
        "and commit the result."
    )


def test_openapi_builder_is_idempotent(repo_root: Path):
    openapi_path = repo_root / "contracts" / "openapi.yaml"
    before = openapi_path.read_bytes()

    result = subprocess.run(
        [sys.executable, str(repo_root / "contracts" / "build_openapi.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    after = openapi_path.read_bytes()
    assert before == after, (
        "contracts/openapi.yaml changed after re-running build_openapi.py. "
        "Either the file was hand-edited, or a model/path table change was "
        "made without regenerating and committing the result. Run "
        "'python contracts/build_openapi.py' and commit the result."
    )


def test_fixtures_generator_is_idempotent(repo_root: Path):
    fixtures_dir = repo_root / "contracts" / "fixtures"
    before = _hash_files(sorted(fixtures_dir.glob("*.json")))

    result = subprocess.run(
        [sys.executable, str(fixtures_dir / "generate_fixtures.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    after = _hash_files(sorted(fixtures_dir.glob("*.json")))
    assert before == after, (
        "contracts/fixtures/*.json changed after re-running "
        "generate_fixtures.py. The generator uses fixed random seeds and "
        "should be fully deterministic; investigate before committing."
    )
