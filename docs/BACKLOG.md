# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Ready (top of queue)

- [ ] (P1, M) Monorepo scaffold — uv + pnpm workspaces, justfile, ruff/pyright/
      eslint/prettier configs, root README pointers. No app code yet; `just
      lint` and `just test` pass trivially. [src: roadmap]
- [ ] (P1, M) `packages/py-kit` — service bootstrap: pydantic-settings config,
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
      GLB → viewport. [src: roadmap]
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

- 2026-07-09 — Board created (Phase 0 sliced from ROADMAP). [orchestrator]
