# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 2 — Parametric core.** Ready batch 1 (topological
naming design doc, all 12 sketch constraint kinds, revolve, measurement,
linear/circular pattern) shipped in full through commit 5777656 (2026-07-12).
The solid Fillet/Chamfer authoring UI (Ready #1) shipped 2026-07-12, so a
user can now round/bevel a body through the product (predicate edge
selector). The session-tool cluster is closing: trim/extend, offset, mirror,
and sketch fillet/chamfer shipped end-to-end, and the **splines backend**
shipped 2026-07-12 (fit-point `SketchSpline`; interactive draw tool #6b
pending). Current target: the Sketching row's remaining named gap —
splines draw-tool UI (#6b) — corroborated by `docs/COMPETITIVE.md`'s first
Fusion 360/Plasticity
discovery pass; plus sweep/loft (Part-modeling breadth) and face/edge
picking (now unblocked). See `docs/BACKLOG.md` Ready queue.

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

Ready batch 1 shipped in full (commits 2531850…5777656, 2026-07-11–12); full
evidence in `CHANGELOG.md`. One line per item:

- ✅ Topological naming strategy — design doc (`docs/design/
      topological-naming.md`), code-reviewer-endorsed; unblocks face/edge
      picking (BACKLOG Ready).
- ✅ Full sketch constraint vocabulary — all 12 kinds (base 6 + tangent/
      perpendicular/parallel/equal/symmetric/concentric) + construction
      geometry. Sketching row re-scored, held ❌ — the remaining named gap is
      the session-tool cluster (trim/extend, offset, mirror, splines, sketch
      fillet/chamfer) — see BACKLOG Ready.
- ✅ Sketch trim/extend — BACKEND + UI (2026-07-12): stateless server-side
      geometry ops `POST /api/v1/sketch/{trim,extend}` (gateway-proxied),
      exact analytic line/arc/circle trim (Onshape "cut at intersection") +
      extend-to-neighbor, deterministic, legible 422 error codes. UI (#2b,
      closes #2): Trim/Extend on the sketch strip as a MODIFY group (J/K),
      click-a-curve to edit through the proxy, buffer swap + re-solve, and
      constraint reconciliation (dangling refs on a deleted/split id dropped,
      surfaced as an "N removed" note). 3 e2e green on the real stack.
- ✅ Sketch offset — BACKEND + UI (2026-07-12, closes #3): stateless
      server-side geometry op `POST /api/v1/sketch/offset` (gateway-proxied),
      exact closed-form line/arc/circle offset (parallel copy at a signed
      distance; +distance = left of the directed curve, so a CCW arc/circle's
      +distance shrinks its radius). ADDS a fresh entity, deterministic,
      legible 422 error codes. UI (#3b): Offset joins Trim/Extend in the sketch
      strip MODIFY group (accelerator F), armed like the modify tools — hover
      highlights the target, a click opens an in-canvas signed-distance editor
      (default 2 mm, documented sign convention + Flip-side), and the returned
      NEW entity is APPENDED (source unchanged, no reconciliation) then
      re-solved; degenerate/zero/unsupported 422s read as clean hints. 3 e2e
      green on the real stack. Single-entity v1; chain offset deferred.
- ✅ Sketch mirror — BACKEND + UI (2026-07-12, closes #4): stateless
      server-side geometry op `POST /api/v1/sketch/mirror` (gateway-proxied),
      exact analytic reflection (rational foot-of-perpendicular; no sqrt/trig)
      of point/line/circle/arc about an axis line — axis given as a line-entity
      id OR two points (discriminated union). ADDS fresh copies (construction
      inherited), deterministic, legible 422s. Arc CCW-from-start invariant
      preserved by swapping reflected start/end. Distinct from the `symmetric`
      CONSTRAINT (creates geometry, doesn't enforce symmetry); v1 does not
      auto-pair source↔copy. UI (#4b): Mirror joins Trim/Extend/Offset in the
      sketch strip's MODIFY group (accelerator **I**); two-phase pick (build the
      target set → click a line/construction centerline as the axis), with a
      live client-side reflection ghost as the signature affordance, APPENDS the
      returned copies + re-solves. 315 vitest + 3 mirror e2e green on the real
      stack; before/after/ghost screenshots. Line-entity axis is the shipped
      path; two-point axis deferred.
- ✅ Sketch fillet/chamfer — BACKEND + UI (2026-07-12, closes #5): stateless
      server-side geometry ops `POST /api/v1/sketch/{fillet,chamfer}` (gateway-
      proxied), exact closed-form corner round (tangent arc) / bevel (straight
      line): both corner lines trimmed in place to their tangent/setback points
      (ids preserved) and the arc/line bridge appended with a fresh `f"{a}.{n}"`
      id (seeded from the whole entity set). UI (#5b): Fillet (U) / Chamfer (B)
      on the sketch strip's MODIFY group — pick two lines, an in-canvas value
      editor collects the radius/distance, the whole rewritten set is SWAPPED in
      (`applyCornerResult`, `reconcileConstraints` like trim/extend) and re-
      solved; legible 422s surface as hints, Esc cascades. **v1 line-line
      corners only** (line-arc/arc-arc deferred → `sketch_unsupported_entity`).
      Deterministic, legible 422s (`sketch_corner_not_found`,
      `sketch_corner_too_large`, `sketch_degenerate_result`). Distinct from the
      SOLID fillet/chamfer. 324 vitest + 4 fillet/chamfer e2e green on the real
      stack; before/after screenshots under docs/screenshots/.
- ✅ Sketch splines (Fit-Point) — BACKEND (2026-07-12, #6; draw-tool UI #6b
      pending): the last hard Sketching capability gap (no free-form profiles
      at all). New `SketchSpline` entity (`kind:"spline"`, ordered `points`,
      min 2) in the discriminated `SketchEntity` union — a NEW entity KIND, so
      persisted sketches are unaffected (`param_version` unchanged). **Solver
      spike verdict: NON-CONSTRAINED v1** — planegcs has no spline primitive, so
      a spline is FIXED geometry: skipped when building the constraint system,
      preserved bitwise in the solve, contributing zero DOF (constraining
      splines / fit points + spline tangency deferred). Kernel emits an
      interpolating C2 B-spline edge (`Edge.make_spline`), so a closed profile
      containing a spline edge extrudes/revolves and tessellates. Golden
      `sketch-spline-extrude` (3 lines + 1 spline) uses the honest
      measured-then-set strategy (no closed-form area/volume) with a documented
      1e-6 mm tolerance; OCCT interpolation verified DETERMINISTIC across three
      fresh interpreter processes (byte-identical GLB + STEP round-trip).
      `apps/web` carries minimal forward-compat stubs (marked `STUB (#6b
      upgrades)`) for #6b to replace with real curve sampling + the draw tool.
- ✅ Revolve + linear/circular pattern — 5 body-affecting features now
      (extrude/revolve/fillet/chamfer/pattern). Part-modeling row re-scored,
      held ❌: edge selection is still predicate-only, and sweep/loft/shell/
      draft/hole are unbuilt — see BACKLOG Ready + Next.
- ✅ Sweep (Ready #7 + #7b) — first NON-PRISMATIC feature, now end-to-end:
      `SweepFeature` sweeps a closed profile along a SECOND sketch's open path
      wire (add/cut), reusing the FeatureRef-to-sketch mechanism (path = whole
      feature, not a sub-edge → independent of topological naming). Golden
      `sweep-circle-r8-h30` (analytic cylinder π·r²·h) through every gate; 6
      body-affecting features now. **UI (#7b):** `SweepEditor` with a double
      feature-reference picker (Profile + Path selects over the tree's
      sketches), Sweep tool + `S` accel gated on ≥2 solved sketches, rebuild
      errors surfaced in the tree; `sweep.spec.ts` real-stack green. v1: no
      twist/scale/guide-rails; anchored at the profile.
- ✅ Fillet/Chamfer authoring UI (Ready #1) — FilletEditor + ChamferEditor
      wired into PartPage (create/edit/submit), CreateStrip buttons live on a
      body; predicate edge selector + brass radius/distance handle. A user can
      finally round/bevel through the product. Also: reopened #6 P1 — measure
      pick-marks now hit-test by real click/tap (true-midpoint edge marks,
      vertex z-priority, visible reticle nodes).
- ✅ Design system: grouped-icon toolbar + flyouts, full text-idiom
      conversion, Create▸Modify split. Doc: `docs/design/toolbar-system.md`.
      Remaining follow-up: sketch-tool overflow flyout (slot/polygon/spline),
      once splines ship.
- 🚧 Measurement — distance/angle tool shipped (BACKLOG archive). Pending:
      mass-properties panel, units system (BACKLOG Next).
- 🚧 Competitive feature-discovery — `docs/COMPETITIVE.md` first pass landed
      2026-07-12 (commit e022114); feeds this groom's Ready restock.
- 🚧 Part-modeling breadth — sweep shipped end-to-end (#7 + #7b); loft
      BACKEND shipped (#8 — ruled loft through ≥2 ordered sections incl.
      loft-to-apex; UI #8b pending); shell, draft, dedicated hole,
      feature-scoped patterns, multi-body boolean, offset datum planes/axes
      still unbuilt (see BACKLOG Ready + Next).
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
