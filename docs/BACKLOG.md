# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Ready (top of queue)

- [x] (P1, M) Monorepo scaffold — uv + pnpm workspaces (incl. empty
      `packages/design` member), justfile, ruff/pyright/eslint/prettier
      configs, root README pointers. No app code yet; `just lint` and `just
      test` pass trivially. [src: roadmap] (README pointers deferred to the
      P2 community-surface item to avoid a territory clash)
- [x] (P1, M) `packages/py-kit` — service bootstrap: pydantic-settings config,
      structlog JSON logging, FastAPI app factory with `/healthz` + `/readyz`,
      standard error envelope, arq queue client. Unit tested. [src: roadmap]
- [ ] (P1, L) Service skeletons + compose — gateway/geometry/documents boot on
      py-kit, Dockerfiles, `docker compose up` brings up db/redis/minio/
      services; smoke script curls all healthz. [src: roadmap]
- [ ] (P1, M) Contract pipeline — `just gen` exports OpenAPI from services to
      `packages/contracts`, generates `packages/ts-client`; CI fails on drift.
      [src: roadmap]
- [ ] (P1, L) Web shell + first light — Vite React app, TanStack Router
      layout, r3f viewport; geometry service tessellates a parametric cube to
      GLB via the queue; viewport renders it. Proves HTTP → queue → OCCT →
      GLB → viewport. **Includes the initial design token system in
      `packages/design`** (palette / type / layout / signature element —
      Tailwind preset + TS constants + fonts) via the mandatory
      `frontend-design` skill; the r3f scene reads the same tokens. The
      shell must land distinctive, not templated (CLAUDE.md design mandate).
      [src: roadmap, founder]
- [ ] (P1, M) CI pipeline — lint/typecheck/unit per package (path-filtered),
      compose config validation, contract drift check. [src: roadmap]
- [ ] (P2, M) Geometry golden harness — golden-model runner (mass properties
      + topology counts vs. committed goldens), STEP round-trip test; cube as
      first golden. [src: roadmap]
- [ ] (P2, S) Community surface — README (truth-only: what runs today, no
      aspirational badges), CONTRIBUTING, SECURITY, issue templates.
      [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop starts running.
      [src: retro]

## Next (P2)

- [ ] (P2, M) Auth v1 — email/password + JWT in gateway; user table in
      documents service or dedicated store per RESEARCH §3. [src: roadmap]
- [ ] (P2, L) Feature-tree persistence design doc — document model for
      parametric history (JSONB params, ordered tree, references); reviewed
      before implementation. [src: roadmap]
- [ ] (P2, M) SketchSolver interface + planegcs spike — validate the LGPL
      planegcs packaging; fall back to scipy least-squares if unworkable
      (RESEARCH §2). [src: research]

## Later (P3)

- [ ] (P3, L) Sketcher v1 UI (after solver spike + feature-tree design)
- [ ] (P3, L) Extrude/fillet/chamfer features end-to-end
- [ ] (P3, M) STEP/STL export endpoints + UI

## Changelog

- 2026-07-09 — `packages/py-kit` service bootstrap shipped: env-driven
  `BaseServiceSettings` (pydantic-settings), structlog JSON logging (console
  renderer via `LOG_FORMAT=console`) with request-context binding, `ApiError`
  hierarchy + standard error envelope (404/409/422/500, opaque unhandled
  500s), `create_app` factory wiring request-id middleware + `/healthz` +
  `/readyz` (per-check detail, 503 on failure), thin arq `QueueClient`.
  21 unit tests; `just lint` + `just test` green; probes verified against a
  real uvicorn boot. [backend-builder]
- 2026-07-09 — Monorepo scaffold shipped: uv workspace (`services/*` +
  `packages/py-kit`, Python 3.12) + pnpm workspace (`apps/*` + `packages/*`,
  `@loft/design` placeholder), justfile with lint/test/dev/gen/e2e targets,
  ruff + pyright(strict) + eslint(flat) + prettier configs. `just lint` and
  `just test` green. [platform-builder]
- 2026-07-09 — Founder decision: design system lives in `packages/design`
  (source-only workspace pkg: tokens as Tailwind preset + TS constants,
  primitives, fonts; one palette for DOM and WebGL). RESEARCH §5, CLAUDE.md,
  frontend agents, and the scaffold/web-shell items updated. [orchestrator]
- 2026-07-09 — Design mandate recorded (founder): frontend-design skill
  vendored and made mandatory for all UI work; web-shell item below now
  includes establishing the initial design token system. [orchestrator]
- 2026-07-09 — Board created (Phase 0 sliced from ROADMAP). [orchestrator]
