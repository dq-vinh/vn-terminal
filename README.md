# VN Terminal Pro

Local, single-user research workstation for Vietnamese listed equities
(HOSE, HNX, UPCoM). Full product context lives in
`vn_terminal_multi_ai_development_plan.md` v1.1 (the development plan) and
`vn_terminal_ai_execution_playbook.md` v1.0 (the multi-agent execution
playbook), both kept alongside this repository.

## Status

Contracts are frozen at version `0.1.0` (WP0, this session). No backend,
quantitative, or frontend logic has been implemented yet; see
`contracts/OWNERSHIP.md` for who builds what next, and
`docs/decision_log.md` / `contracts/OPEN_ITEMS.md` for the decisions and
open questions this freeze produced.

## Repository layout

Matches Section 9 of the development plan exactly:

- `contracts/` — the frozen API contract. Owned exclusively by the lead
  integrator. See `contracts/OWNERSHIP.md`.
- `backend/app/` — FastAPI backend, empty scaffold. `data/**` (data and
  backend specialist), `quant/**` (quantitative specialist), `ai/**` (lead
  integrator).
- `frontend/` — HTML/TypeScript workstation, empty scaffold. Frontend
  specialist.
- `data/` — runtime output (snapshots, canonical store, quality reports).
  Never source-controlled content.
- `tests/` — `contracts/` (lead integrator, populated), everything else
  empty scaffold owned by the relevant specialist.
- `scripts/` — Windows PowerShell operations scripts, placeholders pending
  WP15/WP16.
- `docs/` — `data_dictionary.md` and `decision_log.md` are populated;
  `architecture.md`, `strategy_catalogue.md`, and `user_guide.md` are
  placeholders for later work packages.

## Getting started (once implementation begins)

```powershell
# Backend (Python >= 3.11)
pip install -e ".[dev]"
pytest

# Frontend (Node)
npm install
npm run test:unit
```

## Validating the contracts

```bash
python contracts/schemas/generate_json_schema.py   # regenerate contracts/schemas/json/*.schema.json
python contracts/build_openapi.py                   # regenerate contracts/openapi.yaml
python contracts/fixtures/generate_fixtures.py       # regenerate contracts/fixtures/*.json
pip install -e ".[dev]"
pytest tests/contracts -v
```

All three generators are deterministic; re-running them against an
unmodified checkout must produce byte-identical output
(`tests/contracts/test_generators_reproducible.py` enforces this).

## Key documents

- `contracts/openapi.yaml` — OpenAPI 3.1 contract for the full API surface
  (Section 11 of the plan).
- `contracts/schemas/models/` — Pydantic source of truth; everything else
  under `contracts/` is generated from these.
- `contracts/schemas/json/` — standalone JSON Schema files, one per
  contract/component.
- `contracts/fixtures/` — synthetic FPT/KDH fixtures for frontend and
  quantitative development with no backend present. See
  `contracts/fixtures/README.md` before using any number in them.
- `contracts/OWNERSHIP.md` — path ownership and the contract-change
  process.
- `contracts/OPEN_ITEMS.md` — every field or design choice this session
  could not resolve from the plan text, logged instead of guessed.
- `docs/data_dictionary.md` — verified Fialda FData binary format (Section
  19.1 of the plan).
