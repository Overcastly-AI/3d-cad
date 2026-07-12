# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 2 — Parametric core.** The sketch session-tool cluster
shipped in full through commit 1e3d422 (2026-07-12): trim/extend, offset,
mirror, sketch fillet/chamfer, and splines (Fit-Point v1, non-constrained),
each backend + UI end-to-end. Sweep shipped full-stack (profile along a
second sketch's open path). Loft's backend shipped (ruled loft through ≥2
ordered sections incl. loft-to-apex). **Offset/datum planes — BACKEND shipped**
(2026-07-12): sketches can now sit on offset/parallel planes (a `datum` feature
offset a signed distance from an origin datum, + optional normal flip), lifting
the "3 origin datum planes only" limitation that had forced loft's golden to
fall back to loft-to-apex. Proven by two goldens — an analytic-exact offset
extrude and **the two-parallel-circles → cylinder loft the loft note deferred**.
The paired **plane-picker UI (#2b) shipped 2026-07-12**: the one-click origin
planes are preserved, offset planes are an additive inline "+ Offset plane"
affordance (plus a standalone Datum tool), and the viewport draws the sketch at
the offset — proven end-to-end by `datum-plane.spec.ts` (an XY+30 sketch
extrudes to a body sitting at z≈30..40). This **fully unblocks loft UI (#8b)**
and delivers sketch-on-a-height. Next foundational unlock is face/edge
picking (the other big Part-modeling parity gap). VISION.md's 2026-07-12
re-score flipped the Sketching scorecard row ❌→➖; Part modeling stays ❌ with
face/edge picking now its sharpest gap. See `docs/BACKLOG.md` Ready queue.

Source of truth for "what phase are we in." Every commit that ships an item
ticks it here (and on `docs/BACKLOG.md`) in the same commit — see CLAUDE.md.

## Phase 0 — Foundation ✅

All buildable items shipped through commit 322a988 (including the full
code-review fix batch). Two items below stay ⬜ because they are
**environment-blocked, not build-blocked** — neither can be attempted in this
sandbox regardless of code state, so they do not gate the phase advance; they
carry forward as blocked board items.

- ✅ Loop blueprint from Next-Lane review (`docs/AUTONOMOUS-LOOP.md`)
- ✅ Direction docs: VISION, RESEARCH, ROADMAP, BACKLOG
- ✅ `CLAUDE.md` constitution + `.claude/` agent org (agents, skills, workflows)
- ✅ Design mandate: `frontend-design` skill vendored (Apache-2.0) + standing
      UI/UX directive in CLAUDE.md/VISION.md, wired into frontend agents
- ✅ Monorepo scaffold: uv + pnpm workspaces (incl. `@loft/design`
      placeholder), `justfile`, ruff/pyright/eslint/prettier configs —
      `just lint` + `just test` green
- ✅ `packages/py-kit` service bootstrap (config, JSON logs, health/readiness,
      error envelope, arq queue client), unit tested
- ✅ Service skeletons + compose: `gateway`, `geometry`, `documents` boot on
      py-kit, serve `/healthz` + `/readyz`; one parameterized service
      Dockerfile + compose stack (db/redis/minio + services, healthy-gated)
      authored and config-validated; smoke + per-instance dev scripts;
      probes verified against bare-uvicorn boots (web joins compose with the
      web-shell item)
- ⬜ Verify full `docker compose up` on a Docker-capable host (this sandbox
      has no docker daemon — images and stack runtime are unproven).
      **Environment-blocked**, does not gate phase advances; first
      Docker-capable session picks it up
- ✅ Contract pipeline: OpenAPI generated from pydantic → committed to
      `packages/contracts` → `packages/ts-client` generated (`just gen`);
      drift check ready as `just gen-check` (CI wiring lands with the CI
      bullet below)
- ✅ Web shell: Vite + React + TS app with router, layout, and an r3f viewport
      rendering a server-tessellated cube from the geometry service via the
      gateway, with the `packages/design` token system (design-mandate debut:
      title-block inspector, one palette across DOM + WebGL) and live
      parametric dimension editing; proven end-to-end in Chromium with
      screenshots (`docs/screenshots/`). Honest note: the queue leg is still
      sync-inline — the pipe today is HTTP → gateway → OCCT → GLB → viewport;
      arq/redis queue runtime lands with the queue/storage items
- ✅ CI: lint + typecheck + unit tests + contract drift check + compose
      config validation as GitHub Actions (`.github/workflows/ci.yml`, four
      parallel jobs, uv cache keyed on uv.lock); workflow authored + every
      job's commands verified passing locally — first hosted run occurs on
      push (per-package path filtering deferred until job times warrant)
- ✅ Geometry golden-suite harness (first golden model: the cube) + STEP
      round-trip test — data-driven runner over `services/geometry/goldens/`
      (documented per-model tolerances, exact topology/mesh counts,
      byte-level determinism incl. interpreter-restart), STEP round-trip at
      0.0 measured deviation; evidence + gap list in `docs/GEOMETRY-QA.md`
      (`just e2e` wired 2026-07-10: `scripts/e2e.sh` runs geometry gates +
      Playwright, booting/reusing services itself; CI e2e job deferred)
- ✅ Community surface: README (truth-only — hero screenshot, honest status,
      verified quickstart, CI badge), CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, bug/feature issue templates + PR template
- ⬜ Watchdog: stall-recovery routine armed per `docs/AUTONOMOUS-LOOP.md` §1.4
      (blocked on the loop actually running unattended — armed when batch
      chaining starts; does not gate phase advances)

## Phase 1 — MVP: sketch → extrude → export ✅

Complete 2026-07-11 — the `full-flow` Playwright e2e (commit ff6b226) proves
the whole vertical slice end-to-end in a real browser against the real stack:
register → create part → sketch → extrude → edit param → export STEP/STL.
Full evidence lives in `CHANGELOG.md` and `docs/GEOMETRY-QA.md`; one line per
item below.

- ✅ Auth — email/password JWT via gateway, single-workspace
- ✅ Documents — parts CRUD + feature-tree persistence (create/list/get/
      delete, reorder, rollback-bar, versioned param envelopes)
- ✅ Sketcher v1 — plane pick, line/rect/circle/arc, 6 constraint kinds
      (coincident/horizontal/vertical/distance/radius/fixed) with
      keyboard-first verbs, DOF readout, conflict diagnostics
- ✅ Features v1 — extrude (add/cut), fillet, chamfer; per-feature rebuild
      errors surfaced legibly in the tree panel under the strict-prefix rule
- ✅ Viewport v1 — orbit/pan/zoom, evaluated-body render, feature-tree panel
      with select/edit/rollback (face/edge picking deferred — see Phase 2,
      gated on the topological-naming design doc)
- ✅ Export — STEP + STL, from bare shapes and from evaluated feature trees
- ✅ Golden models — 5 reference parts (`box-10x20x30`, `cylinder-r10-h25`,
      `sketch-extrude-40x25x10`, `fillet-plate-r5`, `chamfer-plate-d5`);
      every shipped feature is golden-covered at 1e-9, STEP round-trips
      0.0–1.26e-10
- ✅ E2E — `full-flow.spec.ts`: desktop + 1280×800 + a touch-viewport smoke

## Phase 2 — Parametric core 🚧

Ready batches 1–2 shipped in full (commits 2531850…1e3d422, 2026-07-11–12);
full evidence in `CHANGELOG.md` + `BACKLOG.md`'s Done archive. One line per
item:

- ✅ Topological naming strategy — design doc, code-reviewer-endorsed;
      unblocked face/edge picking (BACKLOG Ready).
- ✅ Full sketch constraint vocabulary — all 12 kinds + construction geometry.
- ✅ Sketch trim/extend, offset, mirror, sketch fillet/chamfer, splines
      (Fit-Point v1) — the full session-tool cluster, each backend + UI
      end-to-end, exact analytic geometry, legible 422s, real-stack e2e.
      **Sketching scorecard row flipped ❌→➖** (VISION.md, 2026-07-12):
      residual gaps are session polish, not missing capability — see
      BACKLOG Ready (over-constraint classification, dimension expressions,
      constrainable splines).
- ✅ Revolve + linear/circular pattern + sweep (backend+UI) + loft BACKEND —
      8 body-affecting features now.
- ✅ Offset/datum planes — BACKEND (2026-07-12): a `datum` feature (offset
      from an origin datum by a signed distance + optional normal flip) joins
      the Feature union additively; a sketch sits on it via the existing
      `FeatureRef` plane slot (widened to accept `datum`), and one
      `resolve_sketch_plane` funnel threads a resolved `build123d.Plane`
      through profile/path/loft/revolve. Goldens: analytic-exact offset extrude
      + the two-parallel-circles→cylinder loft (π·r²·h) the loft note deferred.
      Removes limitation (b) below; **unblocks loft UI (#8b)** + sketch-on-a-
      height. **#2b plane-picker UI shipped (2026-07-12):** origin planes stay
      one-click, offset planes are an inline "+ Offset plane" affordance + a
      standalone Datum tool; `plane.ts` generalized to a placed `PlaneBasis`
      (one plane-math source for DOM+WebGL); e2e proves an XY+30 sketch extrudes
      to a body at z≈30..40. Part-modeling row **stays
      ❌** on (a) edge selection still predicate-only — face/edge picking is now
      the top Part-modeling parity gap (startable, its design-doc blocker
      shipped).
- ✅ Fillet/Chamfer authoring UI — predicate edge selector, first
      body-affecting authoring UI beyond extrude/revolve.
- ✅ Design system: grouped-icon toolbar + flyouts, Create▸Modify split.
      Remaining follow-up: sketch-tool overflow flyout (slot/polygon).
- 🚧 Measurement — distance/angle tool shipped. Pending: mass-properties
      panel, units system (BACKLOG Next).
- 🚧 Competitive feature-discovery — `docs/COMPETITIVE.md` first pass landed
      2026-07-12; feeds Ready restocks as the queue runs thin.
- 🚧 Part-modeling breadth — shell, draft, dedicated hole, multi-body
      boolean still unbuilt, several gated on face/edge picking (BACKLOG
      Ready + Next).
- ⬜ Performance benchmark suite with budgets in CI
- ⬜ Undo/redo across feature operations

## Phase 3 — Assemblies, versioning, collaboration ⬜

- ⬜ Assemblies: instances, mates/joints, BOM
- ⬜ Document versioning: history, branch, merge-view (design doc first)
- ⬜ Realtime presence + multi-user editing via gateway WebSocket
- ⬜ Helm chart + Kustomize; HA topology guide

## Phase 4 — Interop & drawings ⬜

- ⬜ STEP/IGES import with healing report
- ⬜ 2D drawings: views from model, dimensions, PDF/DXF export
- ⬜ 3MF/OBJ export; mesh quality controls

## Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams
