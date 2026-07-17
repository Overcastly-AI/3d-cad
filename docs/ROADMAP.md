# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 3 — Assemblies.** Phase 2 (parametric core)
**converged 2026-07-15**: Sketching and Part modeling both flipped their
last gaps to ✅ (sketch dimension expressions + driving/driven,
constrainable spline fit points, and typed over-constraint diagnosis closed
Sketching; multi-loop-cut + pattern-a-cut closed Part modeling, held under
the showcase stress test). Interop stands at ➖ (STEP import shipped
end-to-end; IGES/multi-solid deferred). The F7 gateway-auth security gap
closed the same day (`36dc3d9`). Full evidence: `CHANGELOG.md`.

Both independent audits re-baselined 2026-07-15 and converge on the same
next step — **Assemblies** (product audit: "the missing project container…
every other gap is inside a single part; assemblies is the majority of real
mechanical work"). The architecture decision landed the same day
(`docs/design/assemblies.md`, `b378633`): a new `assembly` document type
(instances + mates, not a feature-tree extension), a deterministic in-house
`AssemblySolver` behind a protocol mirroring `SketchSolver` (no license-clean
3D constraint-solver library exists), and a phased v1 — instances +
placement + 3 mates (lock/coincident/concentric) + shared-mesh tessellation,
**"bolt two parts together and see it."** Sequenced into 6 Ready items
(`docs/BACKLOG.md`) plus interleaved audit-debt items (MinIO mesh-store swap
✅ done; gateway rate limiting ✅ done; STEP re-parse caching ✅ done — the
last infra-debt item, per-worker content-keyed parse cache).

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

## Phase 2 — Parametric core ✅ (converged 2026-07-15)

Ready batches 1–5 shipped in full (commits 2531850…36dc3d9, 2026-07-11–15);
full evidence in `CHANGELOG.md` + `BACKLOG.md`'s Done archive. One line per
item:

- ✅ Topological naming strategy (design doc) → sketch-on-a-model-face
      (consumer #1) → click-specific edge selection for fillet/chamfer
      (consumer #2), both backend + UI.
- ✅ Full sketch session toolkit — all 12 constraint kinds, construction
      geometry, trim/extend, offset, mirror, sketch fillet/chamfer, splines
      (fit-point v1, then constrainable v1.1), dimension expressions +
      driving/driven, typed over-constraint diagnosis.
      **Sketching row flips ❌→➖→✅** (2026-07-12 → `a1c42be` 2026-07-15).
- ✅ Feature breadth — revolve, sweep, loft, linear/circular pattern
      (incl. pattern-arrays-a-cut), offset/datum planes, multi-loop closed
      profiles → holes (incl. multi-disjoint-loop cut), shell, draft.
      **Part modeling row flips ❌→➖→✅** (`3c23c73`), held under a
      4-part showcase stress test (`d8d3b87`); multi-body boolean is the
      one remaining scope boundary (BACKLOG Later).
- ✅ STEP import v1 — kernel (`4964fab`) → gateway upload → UI file-picker,
      with a P1 security wall-clock bound on the untrusted parse.
      **Interop row flips ❌→➖.**
- ✅ Measurement (distance/angle), design system (grouped-icon toolbar +
      flyouts), fillet/chamfer authoring UI.
- ✅ Mesh-store single-worker guard (engineering audit F1) — fail-loud v1
      ahead of the MinIO swap (BACKLOG Ready).
- ✅ Mesh-store MinIO/S3 object-storage swap (engineering audit **F6/F1**,
      resolves the mesh-store cliff — not just guarded). `S3_URL` set →
      shared content-addressed `S3MeshStore` (boto3, key stays `sha256:<hex>`,
      no tenant scope) with the single-worker guard **lifted**;
      `S3_URL` unset → in-process LRU + guard. moto (`ThreadedMotoServer`,
      real S3 HTTP) exercises the put/get + content-address round-trip; the
      real-MinIO 2-worker cross-process smoke is CI-gated (docs/GEOMETRY-QA.md).
- ✅ Gateway auth-gate on geometry-compute routes (`36dc3d9`, audit F7 P1
      security). F7's other half — **Redis-backed per-user rate limiting** —
      now shipped: a shared `py_kit.ratelimit.RateLimiter` (sliding-window
      log over a sorted set, fail-open on Redis outage) enforced at the
      gateway on the OCCT-CPU routes (tessellate/meta, export, evaluate,
      assembly + measure/overlay/sketch), 429 + `Retry-After`, 120 req/60 s
      per authenticated user (env-tunable). Audit F7 fully closed.
- ✅ Product + engineering audits, Pass 1 (2026-07-12) + Pass 2 (2026-07-15):
      no P0s either pass; Pass 2 verdict **"yes for a part, no for a
      project"** — names **Assemblies as #1**, the pivot to Phase 3.
- Not carried forward as Phase-2 debt (independent, stay BACKLOG Next P2):
  performance-benchmark CI budgets, undo/redo across feature operations.
  `docs/COMPETITIVE.md` (first pass 2026-07-12) is now stale — flagged for
  the vision-steward to refresh against Phase 3.

## Phase 3 — Assemblies, versioning, collaboration 🚧

**Current focus.** Architecture decision endorsed 2026-07-15
(`docs/design/assemblies.md`, `b378633`): a new `assembly` document type
(instances + mates), an in-house deterministic `AssemblySolver` (protocol
mirrors `SketchSolver`; no license-clean 3D constraint-solver library
exists), and a phased v1 — instances + placement + 3 mates (lock/
coincident/concentric) + shared-mesh tessellation. Sequenced into 6 Ready
items on `docs/BACKLOG.md` (document model → solver core → mate-geometry
resolution → gateway endpoints → evaluation/tessellation DoD golden →
frontend). Deferred past v1 (design doc §5): distance/angle mates,
interference detection, exploded views, BOM formatting, STEP-assembly
export, flexible sub-assemblies, part-version pinning-as-default.

- 🚧 Assemblies: instances, mates/joints — **v1 MVP complete 2026-07-15 (all 6
      items, backend→gateway→frontend); "bolt two parts together and see it" is
      real end-to-end.** BOM deferred to a trivial documents-side read model
      once instances exist. **v1 #1 landed**:
      the documents foundation — `py_kit.schemas.assemblies` (Placement/Quat,
      the discriminated 5-mate union, MateFace/AxisRef reusing the feature
      signatures), `assemblies`/`instances`/`mates` tables (migration `0003`),
      and the owner-scoped CRUD API with OCC (`doc_version`), write-time
      acyclicity, and cross-document 409-with-dependents. **v1 #2 landed**:
      the `AssemblySolver` core (the flagged §2.4 risk) in
      `services/geometry/src/geometry/assembly` — protocol mirroring
      `SketchSolver`, quaternion 6-DOF free instances, a closed-form tree
      fast path (bolt-two-parts, no iteration) + a deterministic
      numpy-only LM fallback (no GPL), the full under/over/conflicting/
      not-converged diagnosis (remaining-DOF via Jacobian rank), proven
      against synthetic residuals (bitwise-determinism + fresh-interpreter
      restart probe). **v1 #3 landed**: mate-geometry-ref resolution
      (`geometry.assembly.resolve`) — `MateFaceRef` → `ResolvedFace` via the
      `on_face` `resolve_face_plane`, `MateAxisRef` → `ResolvedAxis` (circle
      centre + axis from `BRepAdaptor_Curve`/`gp_Circ`) via the `resolve_edge`
      picked-edge resolver, plus `build_assembly_solve_input` assembling the
      full `AssemblySolveInput`; the first REAL bolted solve (two plates, two
      holes each) lands the free plate at the analytic pose (`well_constrained`,
      ~1e-8), with stale/ambiguous/wrong-instance/non-circular refs raising a
      clean `AssemblyDefinitionError`. **v1 #5 landed** (the v1 DoD, "bolt two
      parts together and see it"): `geometry.assembly.evaluate_assembly` +
      `POST /api/v1/assembly/evaluate` — evaluate each UNIQUE part once (dedup
      by `part_key` → one content-addressed mesh shared across instances),
      resolve + solve to a solved world `Placement` per instance, analytic
      combined mass-property roll-up (Σ volumes, mass-weighted centroid,
      transformed-bbox union — no re-meshing/boolean); the solved transform is
      applied at RENDER time over the shared mesh. First assembly golden
      `assembly-two-plates-bolted` (solved transforms == analytic within 1e-6,
      combined props == roll-up, byte-deterministic across interpreter restart,
      shared-mesh dedup) + per-instance/per-mate error + diagnosis tests.
      **v1 #4 landed**: gateway assembly endpoints — `gateway.assemblies`
      proxies the documents CRUD (assembly/instance/mate create/get/list/
      update/delete/reorder) and `gateway.geometry` adds the
      `POST /api/v1/geometry/assembly/evaluate` proxy, EVERY route auth-gated
      with `CurrentUser` from day one (heeding audit F7). The principal reaches
      documents (`X-Loft-User`), never geometry (identity-free hop); upstream
      422/409/404 envelopes re-surfaced verbatim. Contracts regenerated
      (7 new gateway paths). **v1 #6 landed — Assemblies v1 MVP COMPLETE
      (all 6 items):** the apps/web assembly workspace (`/assemblies` register +
      `/assemblies/{id}`, sibling of the part editor) — a Components/Mates
      title-block tree with drafting **balloon** item numbers (the signature
      device shared by tree + viewport; grounded ⏚ anchor), the multi-instance
      viewport (each unique `part_mesh_glb_id` fetched + parsed ONCE, drawn per
      instance at its solved `Placement` via a scene-frame transform — dedup +
      render-time transform, never a baked combined GLB), mate authoring reusing
      the face/edge pick overlays (planar face on each of two instances →
      Coincident, circular hole edge on each → Concentric, two instances → Lock)
      → POST → re-evaluate → the free part **snaps** seed-apart → bolted
      (reduced-motion-aware), and the solve title block (status + typed DOF
      diagnosis + combined roll-up). e2e `assembly.spec.ts` (desktop + 1280×800)
      proves it live; `frontend-design` skill run; founder before/after shots.
      **"Bolt two parts together and see it" is real in the browser.**
- 🚧 **Viewport makeover (founder recalibration 2026-07-16, design mandate
      3a; spec = `docs/UI-REVIEW.md` full audit).** **Batch 1 "the scene is a
      place" ✅ 2026-07-16:** full-bleed canvas + floating collapsible
      tree/inspector panels (P0-4); horizon-persistent camera-scaled grid,
      brighter grid tokens, atmosphere + baked ground contact pool (P0-1);
      procedural token-matcap studio shading, no scene lights (P0-3);
      reference-cube + view rail + numeric view snaps + fit + zoom-to-cursor
      (P0-2); assembly fit keyed on LOADED geometry (P1 race). Full
      `just e2e` green incl. new `viewport-makeover.spec.ts`; before/afters
      `docs/screenshots/viewport-makeover-*`; side-by-side vs
      Fusion/Plasticity recorded in UI-REVIEW. **Batch 2 "every element earns
      its place" ✅ 2026-07-16:** decorative chrome deleted (KERNEL/UNITS/TREE/
      SOLVER/tagline/First-light chip), counts folded into eyebrows; ToolButton
      aria-disabled so gated tools show their reason to mouse + keyboard;
      Create/Modify/Inspect + sketch-band group eyebrows; wordmark→home +
      register › document › mode breadcrumb; open-editor band lock (no silent
      pick loss); idempotent sketch exit + fresh naming. Gates green incl. new
      `nav-chrome.spec.ts`; evidence `docs/screenshots/makeover-batch2-*`.
      **Batch 3 "in-command depth" ✅ 2026-07-16:** in-command band state (an
      open editor recedes the band to the active command + wired OK/Cancel via a
      command-action bus + per-editor bridge; item 10); body selection/hover
      feedback — hovering the body glows its edges, selecting its feature warms
      it (brass edges + matcap tint), the tree→geometry link (item 11); empty-
      part first-run call to action (item 13). Gates green incl. new
      `makeover-batch3.spec.ts`; evidence `docs/screenshots/makeover-batch3-*`.
      **Deferred to BACKLOG:** per-face pick highlight + tree↔face linking (needs
      geometry-service face→feature attribution — OverlayResult carries none
      today), live ghost previews (item 12), resting datum sheets / origin triad
      + parts-home thumbnails (item 13 remainder — snapshot pipeline).
- 🚧 **Datum-plane completeness (founder ask 2026-07-16).** **Backend slice ✅
      2026-07-16:** **midplane** (between two planes / picked faces / datums)
      + **offset CHAINING** (offset from another datum) as two additive
      `DatumParams` kinds (`midplane`, `offset_from` — no `param_version`
      bump; existing offset payloads wire- AND generated-type-identical),
      resolved through the shared datum funnels with documented
      bisector/normal-sign conventions (`docs/design/datum-planes.md` §7a);
      golden `midplane-chained-offset-40x25x10` + kernel/evaluator/schema
      suites; self/forward-ref safety proven. **Authoring UI ✅ 2026-07-16:**
      the `DatumEditor` gained a Type selector and authors `offset_from` +
      `midplane` (origin-datum + earlier-datum sides) with a flip; the client
      resolves any datum kind to its sketch basis by the same math the kernel
      evaluates (`resolveDatumBasis`), so these datums are sketchable + preview
      in the plane picker; e2e authors a midplane + an offset_from through the
      real stack and extrudes bodies at the resolved heights. Remaining:
      midplane FACE-sides + `on_face` authoring in the editor (filed — needs
      the FacePickOverlay wired into the standalone editor), and the angled /
      3-point / tangent / normal-to-curve kinds.
- ⬜ Document versioning: history, branch, merge-view (design doc first) —
      the assemblies design doc's `ref_pinned_version` field is schema-ready
      for this; v1 assemblies track tip (design doc §1.3).
- ⬜ Realtime presence + multi-user editing via gateway WebSocket
- ⬜ Helm chart + Kustomize; HA topology guide

## Phase 4 — Interop & drawings ⬜

- 🚧 STEP/IGES import with healing report — **STEP import v1 shipped
      end-to-end** (kernel `4964fab` → gateway upload → UI file-picker,
      P1 security parse-timeout; **Interop row flips ❌→➖**), evidence
      summarized under Phase 2 above and in full in `CHANGELOG.md` /
      `docs/design/step-import.md`. Remaining: IGES, multi-solid/assembly
      (likely couples to Phase 3), sew/heal, blob-ref storage — BACKLOG
      Later.
- 🚧 2D drawings: views from model, dimensions, PDF/DXF export — the
      product audit's honest #2/near-#1 counter-argument to Assemblies
      (smaller build, completes the make-loop for the single-part case).
      **Drawings v1 #1 — document model + CRUD (documents) SHIPPED**:
      `py_kit.schemas.drawings` (sheets/views/dimensions/annotations,
      dimensions naming model geometry by the reused `EdgeSignature`),
      `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables
      (migration `0004`), owner-scoped CRUD with OCC (`doc_version`), and the
      cross-document 409-with-dependents extended so deleting a part a drawing
      VIEW references is blocked. **Drawings v1 #2 — HLR 2D-projection module
      (geometry) SHIPPED**: `geometry.drawings.project_view` runs exact HLR
      (`HLRBRep_Algo`, no new dep) → canonically-ordered visible (solid) +
      hidden (dashed) 2D edges as neutral primitives (line/circle/arc/polyline),
      the load-bearing determinism constraint (§1.4) met by a canonical total
      order + fixed decimal formatter — byte-identical across an interpreter
      restart; 4 analytic goldens (box rectangle, through-hole→true-Ø10-circle,
      back-pocket hidden set, cylinder rectangle) + 12-param restart probe
      (`test_drawings_project.py`, 20 passed), honest typed `ViewProjectionError`
      on HLR failure (§1.5). **Drawings v1 #3 — drawing-view evaluate endpoint
      (py_kit + geometry) SHIPPED**: `geometry.drawings.evaluate_drawing_views` +
      `POST /api/v1/drawing/evaluate` (stateless, identity-free) evaluate the part
      body ONCE (reusing `evaluate_tree`) then `project_view` per requested view,
      returning per-view canonically-ordered neutral 2D edges through new pure-
      pydantic crossing DTOs (no OCCT type crosses); a body-less part → whole-
      request `part_error`, a per-view HLR throw → that view's typed
      `view_projection_failed` (the rest still project) — never a 500; plate golden
      front=40x10 rect, top=2×Ø10 circles r5.000 (`test_drawings_evaluate.py`, 9
      passed). **Drawings v1 #4 — gateway proxy (gateway) SHIPPED**:
      `gateway.drawings` proxies the documents drawing CRUD (drawing + sheet +
      view + dimension + annotation create/get/list/update/delete) — every route
      auth-gated (`CurrentUser`, audit F7) with the principal reaching documents
      via `X-Loft-User`, upstream 422/409/404 envelopes re-surfaced verbatim —
      plus `POST /api/v1/geometry/drawing/evaluate` mirroring the assembly-evaluate
      proxy (auth-gated, identity-free geometry hop); contracts + ts-client
      regenerated, `test_drawings_proxy.py` + `test_drawing_evaluate_proxy.py`
      (34 passed). **Drawings v1 #7 — frontend drawing canvas (apps/web)
      SHIPPED**: a `/drawings` register + `/drawings/{id}` sheet editor (third
      sibling of parts/assemblies, built on the makeover command band +
      breadcrumb), the signature "paper on the bench" sheet surface (new
      `drawing` design tokens: cool vellum, graphite ink, mm-denominated
      visible/hidden stroke weights). One action auto-lays-out the standard four
      (front/top/right third-angle + iso): it creates the sheet + views (CRUD),
      projects the part via `POST /geometry/drawing/evaluate`, and renders each
      view as scale-correct SVG — visible solid, hidden dashed, a real circle for
      a hole — with an honest per-view "view failed" placeholder. e2e
      `drawings.spec.ts` (real stack) lays out the 4 and asserts edges + the
      top-view circle; `layout.test.ts` (8) covers the pure geometry; full
      `just lint` green. **Drawings v1 #6 — dimension measurement +
      projected-edge→model-edge provenance (geometry) SHIPPED**:
      `project_view` tags each sharp projected edge with its originating model
      `EdgeSignature` (`ProjectedViewEdge.source_edge`/`dimensionable`) by geometric
      re-matching in the projection plane (reusing the shipped `enumerate_edges`
      signatures + a depth tie-break for coincident faces); silhouette/free-form/
      ambiguous edges carry none (honest un-dimensionability, §1.5). HLR-provenance
      finding: OCP gives the 1:1 model↔`EdgeMap` correspondence but no per-output-
      edge tag through `HLRToShape`, so re-matching (deterministic, exact convention)
      is the mechanism. `measure_dimension` reads the 4 dimension types' model-true
      values off the exact 3D B-rep with the `foreshortened` flag (§3.2) and typed
      `subshape_unresolved`/`subshape_ambiguous`/`dimension_wrong_type` errors (never
      a 500). Analytic goldens Ø10→10.000, r5→5.000, 40 mm→40.000, 45° vee, +
      model-true-when-foreshortened (`test_drawings_measure.py`, 18 passed);
      determinism probes unaffected; `just lint`/`gen`/`gen-check` clean.
      **Drawings v1 #6a — measurement wired into the API (geometry) SHIPPED**:
      `POST /api/v1/drawing/evaluate` now carries the drawing's `dimensions`
      (each tagged with its `view`, optional echoed `id`) IN the request and
      returns each dimension's model-true `MeasuredDimensionResult` (value + unit
      + `foreshortened`, or a typed `subshape_unresolved`/`subshape_ambiguous`/
      `dimension_wrong_type` error) ALONGSIDE the projected edges — the body is
      evaluated once and every dimension measured off it (§3.1). Additive +
      backward-compatible (no dimensions → empty `dimensions`, edges unchanged);
      a per-dimension failure is that dimension's typed error, never a 500, never
      failing the request. Gateway proxy carries the new shape as a typed
      passthrough (no logic change). `just lint`/`gen`/`gen-check` clean;
      `test_drawings_evaluate.py` 4 new specs (measured 10.000/40.000 beside
      edges, bad-signature typed error + survivors, no-dimensions regression,
      endpoint JSON). **Drawings v1 #6b — dimension-authoring UI (apps/web)
      SHIPPED**: the sheet is now a dimensioning surface — a `dimensionable`
      projected edge is interactive (hover/focus/select in a blueprint-blue pick
      ink, keyboard-reachable), picking one opens a type menu gated to the valid
      types (circle → diameter/radius, straight edge → linear; invalid combos
      never offered), and the authored dimension persists via the CRUD then re-
      evaluates so each renders as a proper drafting annotation — extension lines
      + dimension line + filled arrowheads + the MODEL-true value with its prefix
      (Ø / R / bare), a `~` marker when `foreshortened`, an honest marker on a
      per-dimension measure error. A Dimensions panel lists + deletes them. New
      `drawing` tokens (dimension/extension ink + weights, arrow size, pick ink)
      — no raw hex, primitives not instances. `drawing/dimensions.ts` pure
      geometry + 14 unit tests; e2e authors Ø10.000 on the hole + 40.000 on the
      40 mm edge and deletes one, against the real stack; `just lint` green.
      Deferred to BACKLOG: angular + point-to-point linear authoring, manual
      drag-to-place. **Drawings v1 #5 — SVG export (apps/web) SHIPPED**: an
      **Export SVG** action in the drawing command band (near Re-project, shortcut
      **E**, enabled only once `hasLayout`, honest disabled reason before) and a
      keyboard path serialize the already-rendered `DrawingSheet` `<svg>` to a
      **standalone, self-contained** `.svg` download — `XMLSerializer` on a clone,
      XML prolog + `xmlns`, screen-only chrome (Tailwind sizing + bench shadow)
      stripped, concrete mm `width`/`height` from the `viewBox` (scale-correct),
      Blob + object-URL + synthetic `<a download>` (reuses the shared
      `downloadBlob`; DRY). Colours are already inline `drawing`-token attributes,
      so the file opens in a browser/Inkscape unchanged. ARCH DECISION (drawings.md
      §4.1a): v1 SVG ships **client-side** (reuse the shipped renderer, not a second
      Python drafting composer); server-composed PDF/DXF + content-addressed
      deterministic stored artifacts deferred to BACKLOG. New `SheetExportIcon`
      primitive; `drawing/exportSvg.ts` + 3 unit tests; e2e downloads the `.svg`
      and asserts the sheet root, the hole `<circle>`, and the `10.000` value;
      `just lint` green. **Drawings v1 export loop closed.** Remaining in the
      pillar: section/detail/assembly views + server-composed PDF/DXF.
- ⬜ 3MF/OBJ export; mesh quality controls

## Phase 4b — Sheet metal ⬜ (scoped, not yet endorsed/sequenced)

**Not started, not yet green-lit** — a candidate pillar the vision-steward
scoped 2026-07-17 in response to a founder ask ("anything for sheet metal?").
Architecture decision: `docs/design/sheet-metal.md`. Named after Drawings
(not before Phase 5) because it composes directly with the shipped
Drawings pipeline — the flat pattern rides the same `ViewGeometry`/HLR-view
machinery as a part drawing (design doc §7) — and because Drawings landing
first is what makes a flat-pattern-as-a-drawing-view cheap. **The genuine
kernel risk, named plainly (design doc §2): OCCT ships no turnkey
flat-pattern unfold** (verified — no `Unfold`/`Sheet`/`Develop`/`Flatten`
module in OCP); v1 scopes to a single provenance-tracked bend to avoid the
harder general bend-graph relaxation problem. No new document type needed
(unlike Assemblies/Drawings) — sheet-metal features extend the existing part
feature-tree model.

Sequenced slice titles (BACKLOG "Next" for full text; dependency-ordered,
kernel risk moved EARLY — mirrors how Assemblies proved its solver on
synthetic residuals before real mate-geometry resolution existed, `docs/
design/assemblies.md` v1 #2):

1. Base flange feature (`SheetMetalBaseFlangeParamsV1` — gauge thickness +
   default K-factor/bend radius, reuses `extrude.py`) — the minimal
   foundation the risk item needs a real (if trivial) sheet body to act on.
2. **The flat-pattern unfold algorithm — THE flagged risk, proven early**
   (`geometry.sheet_metal.unfold`: face classification + rigid-transform +
   bend-allowance reconstruction, single-bend v1 scope), proven against a
   directly hand-built OCCT test body (a known cylindrical bend face
   constructed without going through a real edge-flange feature yet) — the
   same "prove the hard algorithm in isolation before wiring real authored
   geometry to it" posture the mate solver took. Ships with the analytic
   unfolded-length + area-conservation goldens in the same commit.
3. Edge-flange (bend) feature (`SheetMetalEdgeFlangeParamsV1` — parameter-
   driven arc+line path, reuses `sweep.py`'s profile-along-path primitives;
   bend-region provenance tagged via the shipped `SubshapeRef`/
   `EdgeSignature` machinery) — wires #2's proven algorithm to real,
   user-authored bend geometry.
4. Flat pattern as a drawing view (`views.projection = "flat_pattern"`,
   reuses the shipped `ViewGeometry` DTO + sheet editor + SVG export with no
   new frontend renderer) + bend-table annotation (`annotations.type =
   "table"`) — the v1 DoD, "one bracket → a flat blank a shop can cut."

Explicitly deferred past v1 (design doc §10): multi-bend/bend-graph
flattening (boxes, hat channels), miter flanges/hems/jogs/tabs/corner
reliefs, gauge/material bend-allowance tables, lofted bends, cosmetic bend
reliefs, import-as-sheet-metal recognition, server-composed flat-pattern
export (rides the same deferred item as Drawings' PDF/DXF).

## Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams
