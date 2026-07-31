# Decision log

**Status:** populated at WP0 with the decisions already made in
`vn_terminal_multi_ai_development_plan.md` v1.1, Section 29. Reproduced here,
unmodified, so the repository carries its own decision record. New decisions
made during later work packages should be appended below the reproduced
table, each with the same three columns and a date.

**Owner:** Lead integrator (contracts/OWNERSHIP.md, Section 24.1).

## Decisions from the development plan (Section 29)

| Decision | Alternatives considered | Reason |
|---|---|---|
| Build a modular local web application | One HTML file; immediate desktop wrapper | Best balance of maintainability, security, and parallel development |
| Use FData EOD first | Realtime first; Vnstock only | Matches medium-term horizon and existing local data |
| Treat FData as read-only | Modify or normalize source files in place | Protects vendor-managed data and recovery |
| Use DuckDB/Parquet | Browser-only arrays; large CSV files; server database | Appropriate for local analytical workloads |
| Use FastAPI | Browser direct file access; Node-only backend | Reuses Python quantitative ecosystem and typed contracts |
| Use Lightweight Charts | Custom canvas; proprietary advanced chart library | Open-source financial charting with manageable integration; the presenter's own tool is built on the same TradingView base [1:01:42] |
| Keep calculations deterministic | Let AI calculate indicators | Reproducibility and auditability |
| Use AI provider adapters | Depend on one AI model | Models and costs can change |
| Build 3, then 10-15, then approximately 52 strategies | Build all strategies simultaneously | Reduces systemic design errors |
| Lead AI owns contracts | Every specialist changes schemas | Prevents integration drift |
| Defer broker execution | Include orders in v1.0 | Reduces financial and security risk |
| Exclude intraday as a standing non-goal | Enable all FData intervals immediately | Post-session analysis is the stated use, and the current FData feed delivers EOD only (intraday directories verified empty) |
| Rescope v1.0 to 10-15 strategies | Ship approximately 52 in v1.0 | Only eight AFL specifications exist; user specification writing is the bottleneck |
| Add AmiBroker reconciliation loop | Trust the binary parser alone | AmiBroker is the format's intended consumer, so mismatches surface loudly instead of silently |
| Add daily close routine (WP16) | Compute on demand at first use | Matches the post-session use pattern, removes waiting, and caps daily AI cost |
| Treat `Aux1` as candidate unadjusted VWAP pending verification | Ignore Aux fields entirely | Inspection evidence indicates unadjusted average price, which would solve adjusted-versus-quoted price reconciliation |

## Decisions made during WP0 (contract freeze), 2026-07-30

| Decision | Alternatives considered | Reason |
|---|---|---|
| Freeze OpenAPI contract version at `0.1.0` | Starting at `1.0.0`; using an unversioned draft | Section 31 Step 4 names the first freeze "OpenAPI v0.1"; `1.0.0` should be reserved for the accepted v1.0 release per Definition of Done |
| Wrap every endpoint response in a shared `provenance` object (`as_of_date`, `data_version`, `source`, `freshness_status`, `warnings`) instead of repeating four flat fields on every schema | Repeating `as_of_date`/`data_version`/`source` as flat fields on each of the 18 response schemas | Section 11 requires these fields on every endpoint; a single reusable component avoids 18 independent copies drifting apart, which is the exact failure mode Section 28 calls "contract drift" |
| Set `additionalProperties: false` on all canonical contract schemas | Leaving schemas open (`additionalProperties: true`) | Section 21.1 and Section 28 identify contract drift between independently built modules as a named risk; a strict schema fails loudly instead of silently accepting an unexpected field |
| Leave categorical-looking fields without a plan-given closed vocabulary (for example `security_type`, `trading_status`, `signal`, `adjustment_status`, `quality_status`, `statement_type`) typed as open strings rather than invented enums | Guessing a closed enum for each field | The instruction for this session is explicit: where the plan is ambiguous, log the ambiguity in `contracts/OPEN_ITEMS.md` rather than guessing. See that file for the full list |
| Do not populate `docs/strategy_catalogue.md` with concrete strategy rules | Drafting sample entry/exit rules to demonstrate the format | Section 13.2 and the P7 prompt in the execution playbook state strategy specification is the user's analytical work (Stream F), not an agent's; inventing rules here would violate that boundary even as an example |
