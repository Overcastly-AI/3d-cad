# @loft/contracts

**GENERATED — do not edit; run `just gen`.**

OpenAPI 3.1 schemas exported from each service's `build_app()` factory
(pydantic models are the single source of truth — CLAUDE.md DRY rule):

- `gateway.openapi.json` ← `services/gateway` (`gateway.main.build_app`)
- `documents.openapi.json` ← `services/documents` (`documents.main.build_app`)
- `geometry.openapi.json` ← `services/geometry` (`geometry.main.build_app`)

Output is deterministic (sorted keys, 2-space indent, trailing newline) so
the drift check never flaps. `packages/ts-client` is generated from these
files. CI runs `just gen-check` and fails when committed output is stale.

Only this `README.md` and `package.json` are hand-written; everything else
here is produced by `scripts/gen-contracts.py`.
