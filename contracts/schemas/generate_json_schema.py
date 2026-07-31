#!/usr/bin/env python3
"""Generate contracts/schemas/json/*.schema.json from the Pydantic models in
contracts/schemas/models/registry.py.

Usage (from repository root):
    python contracts/schemas/generate_json_schema.py

Owner: Lead integrator (contracts/OWNERSHIP.md). This script is part of the
frozen contract tooling; changing which models it exports is a contract
change and follows Section 24.2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent.parent
sys.path.insert(0, str(THIS_DIR))

from models.registry import EXPORTS  # noqa: E402

OUT_DIR = THIS_DIR / "json"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    contract_version = (REPO_ROOT / "contracts" / "VERSION").read_text(encoding="utf-8").strip()

    written = []
    for name, model in EXPORTS.items():
        schema = model.model_json_schema()
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://vn-terminal.local/contracts/{contract_version}/{name}.schema.json",
            "title": model.__name__,
            **schema,
        }
        out_path = OUT_DIR / f"{name}.schema.json"
        out_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(out_path.name)

    print(f"Wrote {len(written)} schema files to {OUT_DIR}")
    for w in sorted(written):
        print(f"  {w}")


if __name__ == "__main__":
    main()
