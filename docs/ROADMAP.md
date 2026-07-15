# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 2 — Parametric core, converging; Phase 4 interop
pulled forward.** Sketch-on-a-model-face and click-specific edge selection
(both `SubshapeRef`-based, topological-naming consumers #1–#2), shell, and
draft all shipped backend+UI through 2026-07-13 (`a663db7`) — full evidence
in `CHANGELOG.md`. **Part modeling flipped ➖→✅** (`3c23c73`): sketch →
extrude/revolve/sweep/loft → fillet/chamfer(pick-or-predicate) → pattern →
shell → draft → holes now covers a single connected solid comprehensively;
multi-body boolean (independently-built solids) is the one honest remaining
scope boundary. **The flip held under a real stress test** (`d8d3b87`,
qa-tester: four 6–16-feature parts — bracket/enclosure/duct/pulley — built
clean, zero topological-naming failures) and surfaced three feature-coverage
gaps — of which **pattern-a-cut (F1) and multi-disjoint-loop cut (F2) are now
CLOSED** (bolt-circle / lightening-hole rings drill via one hole-cut + a
pattern, or one multi-circle cut sketch); the thin-shell rim fillet UI warning
(F3) remains filed to `docs/BACKLOG.md` Ready. **STEP import shipped end-to-end** (`4964fab`
kernel → gateway upload endpoint → UI file-picker, 2026-07-13): an `import`
base feature reads STEP text and sets the body; the "Import STEP" toolbar
affordance picks a local `.step`/`.stp`, uploads it via the generated client,
and lands the imported body in the tree + viewport, modeled on via the
existing topo-naming machinery. **The Interop scorecard row flips ❌→➖**
(both UI-leg items done). The P1 security fast-follow — a hard wall-clock bound
on the untrusted-STEP OCCT parse — **shipped 2026-07-13**: the parse runs in a
killable subprocess (default 5 s, `import_parse_timeout`), so a degenerate
part-21 can no longer pin a worker. **Sketch dimension expressions +
driving/driven: COMPLETE 2026-07-15 (backend + frontend).** Backend: additive
`name`/`expression`/`driving` on the dimension-constraint schema, a safe
recursive-descent expression evaluator (`geometry.sketch.expression`, cycle /
unknown-ref / div-zero → clean `sketch_invalid`), driving dims feeding the
solver their evaluated value and driven dims read back onto
`SolvedSketch.dimensions[]`. Frontend: the inline dimension editor now takes an
expression (a bare number → `value_mm`, `width/2` → `expression`, with a brass
"= 10 mm" resolved echo) + an optional reference name + a DRIVING/DRIVEN toggle;
driven dims render in reference parentheses `(20)` in quiet ink, the `10`
readout comes from `SolvedSketch.dimensions[]`, and a bad expression surfaces
the `sketch_invalid` message in the solve-diagnostic stamp. Worked e2e green
(width=20, height=`width/2`→10; driven readout tracks edited geometry without
over-constraining) + founder screenshots. **P1 security fast-follow (audit F7)
shipped 2026-07-15:** the three gateway geometry-compute routes
(`/geometry/tessellate`, `/tessellate/meta`, `/export`) now require
`CurrentUser` like every sibling stateless proxy — closing an anonymous
OCCT-CPU DoS vector (401 without a token, unchanged for the signed-in web
client); contract regenerated with the `HTTPBearer` block, 401 test per route.
Rate limiting (the finding's other half) stays filed for its own py-kit item.

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

Ready batches 1–3 shipped in full (commits 2531850…a36e436, 2026-07-11–12);
full evidence in `CHANGELOG.md` + `BACKLOG.md`'s Done archive. One line per
item:

- ✅ Topological naming strategy — design doc, code-reviewer-endorsed;
      unblocks sketch-on-face + edge selection (BACKLOG Ready, re-sequenced
      2026-07-12 per the product audit — sketch-on-face first).
- ✅ Full sketch constraint vocabulary — all 12 kinds + construction geometry.
- ✅ Sketch trim/extend, offset, mirror, sketch fillet/chamfer, splines — the
      full session-tool cluster, backend + UI end-to-end. **Sketching
      scorecard row flipped ❌→➖** (VISION.md, 2026-07-12); residual gaps are
      session polish (BACKLOG Ready).
- ✅ Revolve + linear/circular pattern + sweep + loft (backend + UI, #8) —
      8 body-affecting features.
- ✅ Offset/datum planes — backend + picker UI (#2b): a `datum` feature
      (signed offset from an origin datum) joins the sketch-plane `FeatureRef`
      slot via one `resolve_sketch_plane` funnel; unblocked loft UI (#8b) and
      sketch-on-a-height.
- ✅ Multi-loop closed profiles → holes (2026-07-12, `a36e436`) — the
      product audit's #1 daily-driver gap: one sketch (outer boundary + N
      inner loops) extrudes/cuts a plate with N through-holes, shared across
      extrude/revolve/sweep/loft, no topological naming needed.
- ✅ Fillet/Chamfer authoring UI — predicate edge selector, first
      body-affecting authoring UI beyond extrude/revolve.
- ✅ Design system: grouped-icon toolbar + flyouts, Create▸Modify split.
      Remaining follow-up: sketch-tool overflow flyout (slot/polygon).
- 🚧 Measurement — distance/angle tool shipped. Pending: mass-properties
      panel, units system (BACKLOG Next).
- 🚧 Competitive feature-discovery — `docs/COMPETITIVE.md` first pass landed
      2026-07-12; feeds Ready restocks as the queue runs thin.
- ✅ Sketch-on-a-model-face — backend + UI, 2026-07-12; topological-naming
      consumer #1 (`SubshapeRef`-based `on_face` datum); e2e proves a boss
      extrudes on a picked planar face. Full evidence: `CHANGELOG.md`.
- ✅ Click-specific edge selection for fillet/chamfer — backend + UI,
      2026-07-13; consumer #2 (`EdgeSignature`); e2e `fillet-edge-pick`
      rounds one edge, neighbours stay sharp. Full evidence: `CHANGELOG.md`.
- ✅ Shell feature — backend + UI, 2026-07-13; hollows a body, picked faces
      stay open (reuses the sketch-on-face `SubshapeRef`). Full evidence:
      `CHANGELOG.md`.
- ✅ Draft feature — backend + UI, 2026-07-13; tapers picked faces about a
      neutral plane. Full evidence: `CHANGELOG.md`.
- ✅ Part-modeling breadth — **Part modeling row flipped ➖→✅**
      (`3c23c73`): sketch → extrude/revolve/sweep/loft →
      fillet/chamfer(pick-or-predicate) → pattern → shell → draft → holes now
      covers a single connected solid comprehensively. Multi-body boolean
      (independently-built solids) is the one remaining scope boundary
      (BACKLOG Later). Dedicated hole feature also deferred (P3) — multi-loop
      cut covers the common bolt-circle case.
- ✅ Showcase stress test (`d8d3b87`, qa-tester) — four real 6–16-feature
      parts held the Part-modeling ✅ flip on complex geometry (no P0, zero
      topological-naming failures) and surfaced three feature-coverage gaps
      (pattern union-only, disjoint-circle-ring profile, thin-shell fillet
      UI warning) — filed to BACKLOG Ready/Later.
- ✅ Multi-disjoint-loop CUT (2026-07-13, showcase **F2**/BACKLOG #4) — a
      sketch of N disjoint circles (no enclosing outer boundary) now cuts N
      independent holes in ONE feature (`build_profile_faces`/`_group_regions`);
      add-vs-cut guard preserved (ADD of disjoint loops stays a multi-body
      error); new 6-hole-ring-cut golden. Kills the pulley's 16-feature ring.
- ✅ Pattern arrays a CUT (2026-07-13, showcase **F1**/BACKLOG #3) — a
      circular/linear `pattern` after a hole-cut REMOVES a hole at each
      placement (bolt circles, lightening rings) instead of unioning whole-body
      copies. Option (a): the mode is inferred from the immediately-preceding
      body-affecting feature (no schema change, no `param_version` bump, no
      frontend toggle); add-pattern path byte-identical (regression-guarded);
      new `pattern-cut-6hole-boltcircle` golden.
- 🚧 Product + engineering audits (2026-07-12, `docs/AUDIT-PRODUCT.md`
      6c1e600, `docs/AUDIT-ENGINEERING.md` 9ecec33): no P0s found; findings
      filed to BACKLOG (mesh-store scale cliff, remaining determinism-golden
      slices, revolve construction-axis trap, evaluate_tree tessellation churn).
- ✅ Mesh-store single-worker guard (2026-07-13, engineering audit **F1**/
      BACKLOG #5) — the in-process mesh LRU 404s across workers/replicas, so
      geometry now REFUSES to start on `WEB_CONCURRENCY > 1`
      (`assert_single_worker_mesh_store`, fires at the `geometry.main:app`
      import) instead of silently 404-ing ~(N-1)/N of evaluated-mesh fetches.
      Fail-loud v1 chosen over a blind MinIO swap the sandbox can't exercise
      (no docker daemon / no `moto`). The MinIO-backed content-addressed swap
      stays the forward Ready item, gated on a real-MinIO 2-worker CI smoke.
- ✅ Constrainable splines (v1.1) — **backend + frontend landed 2026-07-15**: a
      spline's fit points are addressable as solver points
      (`EntityPointRef.point:"fitN"`), take the point-level constraints (only
      *referenced* fit points enter the solver, so an unconstrained spline keeps
      zero added DOF and the spline golden stays byte-identical), and the spline
      is rebuilt through the solved fit positions. Frontend: fit points pick /
      hover / select through the existing point-pick path (the `namedPoints`
      seam), take coincident / fixed / symmetric, and wake diamond fit-point
      handles when the spline is engaged; the DOF readout reflects the
      constrained fit points and the spline reshapes on solve (e2e proven).
      Spline tangency deferred (needs a native primitive).
- ⬜ Performance benchmark suite with budgets in CI
- ⬜ Undo/redo across feature operations

## Phase 3 — Assemblies, versioning, collaboration ⬜

- ⬜ Assemblies: instances, mates/joints, BOM
- ⬜ Document versioning: history, branch, merge-view (design doc first)
- ⬜ Realtime presence + multi-user editing via gateway WebSocket
- ⬜ Helm chart + Kustomize; HA topology guide

## Phase 4 — Interop & drawings ⬜

- 🚧 STEP/IGES import with healing report — **STEP import v1 landed
      2026-07-13, geometry-kernel side only** (`4964fab`): an `import` base
      feature reads inline STEP text through a pinned single-solid
      `STEPControl_Reader`, sets the part's body, and every later feature
      works on it via the existing topological-naming machinery. Golden
      `import-step-box-10x20x30` proves import ≡ inverse-of-export (0.0
      deviation). Docs: `docs/design/step-import.md`. **Gateway upload
      endpoint landed** (`POST /api/v1/parts/{id}/features/import`,
      streamed+size-capped raw STEP body → `import` feature via the existing
      feature-append path). **UI file-picker leg landed 2026-07-13** — an
      "Import STEP" affordance leads the Create toolbar (enabled only as the
      first body, disabled once a body exists), reads the chosen `.step`/`.stp`
      bytes and POSTs them via the generated client, refetches the tree +
      evaluate + mesh so the imported body appears in the tree AND viewport, and
      surfaces the server's `import_*` envelope legibly; Playwright drives the
      pick→body→model-on-it flow on the real stack. **Interop scorecard row
      flips ❌→➖.** **P1 security fast-follow shipped 2026-07-13:** the
      untrusted OCCT parse runs in a killable subprocess bounded by
      `step_import_timeout_seconds` (default 5 s) → per-feature
      `import_parse_timeout`, so a degenerate part-21 can't pin a worker
      (docs/design/step-import.md §6). Remaining: IGES, multi-solid/assembly,
      sew/heal, blob-ref storage — all BACKLOG Later.
- ⬜ 2D drawings: views from model, dimensions, PDF/DXF export
- ⬜ 3MF/OBJ export; mesh quality controls

## Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams
