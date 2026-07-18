<!--
Conventional-commit title please: feat(geometry): …, fix(web): …, docs: …
One logical change per PR. CONTRIBUTING.md has the full expectations;
CLAUDE.md is the project constitution.
-->

## What & why

<!-- What changes, and which ROADMAP/BACKLOG item or issue it serves. -->

## Definition of done (check what applies — truthfully)

- [ ] `just lint` green (ruff + pyright strict + eslint + prettier)
- [ ] `just test` green (pytest + vitest)
- [ ] API surface changed → `just gen` run and regenerated
      `packages/contracts` + `packages/ts-client` committed
      (`just gen-check` clean)
- [ ] Kernel-adjacent → geometry correctness covered (analytic/golden
      assertions with documented tolerances, not ad-hoc epsilons)
- [ ] User-facing → exercised against the real running stack (not just unit
      tests); e2e updated where it exists
- [ ] UI change → composes `packages/design` primitives (no raw hex/styles),
      preserves test hooks, before/after screenshots attached
      (desktop + 1280×800)
- [ ] `docs/ROADMAP.md` + `docs/BACKLOG.md` updated in this change if it
      ships a feature/fix (stale docs are a defect — CLAUDE.md)
- [ ] No new GPL/AGPL dependencies; service boundaries respected (kernel
      imports only in `services/geometry`, web talks only to the gateway)

## Evidence

<!-- Test output, screenshots, curl transcripts — show, don't tell. -->
