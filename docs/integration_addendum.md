# Integration Addendum

**Date:** 31 July 2026
**Read alongside:** `vn_terminal_ai_execution_playbook.md` Section 7.2, and `vn_terminal_multi_ai_development_plan.md` v1.1
**Purpose:** Three facts that postdate the playbook and that the integrator must know before starting Phase 1.

---

## 1. The reference strategy is at v1.1.0, not v1.0.0

`docs/strategy_catalogue.md` was revised after empirical testing found that positions were held indefinitely on halted securities. On carry-forward zero-volume bars both moving averages freeze, no crossover ever occurs, and no exit is generated. Testing 121 halted symbols left AMD and IBC holding open longs at the final bar.

Version 1.1.0 adds `halt_exit_rule`, a `halt_exit` signal value, the `halt_exit_sessions` parameter defaulting to 5, order semantics while an exit is pending, four evidence fields, and nine edge cases. It also corrects the enumerations to the contract values `equity` and `UPCoM`, replacing the earlier `ordinary_equity` and `UPCOM` which matched nothing the data layer emits.

The implementation in `backend/app/quant/strategies/dual_sma_trend_crossover.py` is current with the specification and is covered by `tests/quant/test_halt_exit_rule.py` and `tests/quant/test_enumeration_contract.py`. Do not regenerate or "modernize" this strategy during integration.

## 2. Generated artifacts must be written as UTF-8 with LF

On Windows, `Path.write_text()` defaults to the cp1252 locale encoding and translates `\n` to `\r\n`. Both defaults corrupt generated artifacts. A UTF-8 em dash was written as the single byte `0x97`, which broke schema loading, and CRLF output made the fixture hashes disagree with the golden baselines.

Every generator now passes both arguments explicitly, and `.gitattributes` enforces `eol=lf`. Any new file-writing code must do the same:

```python
path.write_text(content, encoding="utf-8", newline="\n")
path.open("w", encoding="utf-8", newline="\n")
```

**Six call sites remain unfixed** and are latent rather than failing, because their current content is ASCII. They belong to the data stream, not to the integrator. Do not edit them; file them for the Codex agent.

- `backend/app/data/pipeline.py:269`
- `backend/app/data/storage/snapshots.py:182`
- `backend/app/data/storage/snapshots.py:210`
- `backend/app/data/storage/snapshots.py:224`
- `backend/app/data/tasks.py:75`

A Vietnamese company name written into a manifest would corrupt in exactly the way described above.

## 3. Local environment notes

Run the test suite with an explicit base temp directory, because the default Windows temp path raises `PermissionError` on this machine:

```powershell
python -m pytest -q --basetemp=.pytest_tmp
```

`.pytest_tmp/`, `test-results/`, `.ruff_cache/`, and `.mypy_cache/` are gitignored and must never be committed. An earlier `git add .` swept 83 scratch files into the baseline commit, and because pytest deletes and recreates them mid-run, every later `git add` aborted until they were untracked.

The repository lives on a Google Drive synced path. Bulk file walks are slow; prune `.venv` and `node_modules` explicitly rather than filtering after traversal.

---

## Current state at the start of integration

- All of P0 through P7 delivered.
- Test suite green at 729 passed, 2 skipped.
- Baseline tag `pre-integration-baseline` marks the pre-fix state.
- Still to build during integration: WP10 AI gateway, WP16 daily close routine, WP15 packaging.
