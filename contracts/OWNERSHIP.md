# Ownership and contract-change process

Reproduces Section 24.1 and Section 24.2 of
`vn_terminal_multi_ai_development_plan.md` v1.1, as instructed by WP0
deliverable 6.

## 24.1 Ownership rules

- Lead owns `contracts/**`.
- Data AI owns `backend/app/data/**`.
- Quant AI owns `backend/app/quant/**`.
- Frontend AI owns `frontend/**`.
- Lead owns `backend/app/ai/**`, integration tests, and release files.
- QA AI is read-only except for assigned test and report paths.

Applied to this repository (Section 9 tree), that means:

| Path | Owner |
|---|---|
| `contracts/**` | Lead integrator |
| `backend/app/data/**` | Data/backend specialist |
| `backend/app/quant/**` | Quantitative specialist |
| `backend/app/ai/**` | Lead integrator |
| `backend/app/api/**`, `backend/app/config/**`, `backend/app/main.py` | Data/backend specialist and Lead integrator jointly, per Section 21.2 (WP3 owner is the data/backend specialist; WP10/WP13 mounting is the lead's) |
| `frontend/**` | Frontend specialist |
| `tests/backend/**` | Data/backend specialist |
| `tests/quant/**` | Quantitative specialist |
| `tests/contracts/**` | Lead integrator |
| `tests/integration/**` | Lead integrator |
| `tests/e2e/**` | Lead integrator, then QA AI (Section 25.6, WP14) |
| `docs/strategy_catalogue.md` | The user (Vinh), via Stream F specification sessions (Section 21.2, the P7 prompt in `vn_terminal_ai_execution_playbook.md`). No coding agent should write strategy rules into this file. |
| `docs/data_dictionary.md` | Lead integrator authored the WP0 baseline; the data/backend specialist appends the Aux1 verification result (WP1) in the marked section only |
| `data/**` | Data/backend specialist (runtime output; never source-controlled content, see `.gitignore`) |
| Everything else under `docs/`, `scripts/**` | Lead integrator |
| Read-only review paths (adversarial QA, Section 21.2, WP14) | Independent QA AI tool; read-only elsewhere |

No two tools should own the same files. Shared contracts are changed only
by the lead integrator (Section 21.1).

## 24.2 Contract-change process

1. Specialist identifies a contract gap.
2. Specialist submits a short change proposal.
3. Lead assesses downstream effects.
4. Lead changes the contract and fixtures.
5. All specialists update against the same contract version.

### How to submit a change proposal (implementation detail, not in the plan)

The plan states the five-step process above but does not specify a
submission mechanism. Until the team adopts a tracker, submit a change
proposal as a short markdown note (symptom, proposed field/endpoint change,
which downstream module needs it, and whether it is backward compatible)
and hand it to the lead integrator directly. The lead integrator then:

- Edits the relevant Pydantic model(s) in `contracts/schemas/models/`.
- Re-runs `python contracts/schemas/generate_json_schema.py` and
  `python contracts/build_openapi.py`.
- Regenerates or hand-updates the affected fixtures in `contracts/fixtures/`
  (`python contracts/fixtures/generate_fixtures.py` where applicable).
- Re-runs the contract tests (`pytest tests/contracts`) and confirms they
  pass.
- Bumps `contracts/VERSION` (see "Versioning" below) and records the change
  in `docs/decision_log.md`.
- Notifies every specialist that a new contract version is available.

No specialist edits `contracts/**` directly. If a specialist's local
experiment requires a contract change to keep developing, they still submit
the proposal above rather than committing a workaround against their own
copy of the schema.

### Versioning

`contracts/VERSION` currently reads `0.1.0`, the WP0 contract freeze
(Section 31, Step 4: "Freeze OpenAPI v0.1"). This session's convention,
not stated in the plan and therefore recorded here as an implementation
decision (see `docs/decision_log.md`):

- Patch (`0.1.x`): fixes that do not change any schema shape (typos,
  fixture regeneration, documentation).
- Minor (`0.x.0`): additive, backward-compatible schema or endpoint
  changes (new optional field, new endpoint).
- `1.0.0` is reserved for the accepted v1.0 release (Section 26,
  Definition of Done), not used before then.
