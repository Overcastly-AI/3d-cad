# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`,
and the roadmap. The autonomous build loop pulls from **Ready (top of
queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication:

- **Sketching row — ➖.** Residual gaps: (1) over-constraint diagnosis is
  index-only; (2) no dimension expressions/driving-vs-driven; (3) splines are
  v1 non-constrained. All three in Ready below.
- **Part modeling row — flipped ➖→✅ this pass (`3c23c73`).** Sketch-on-face,
  click-specific edge selection, shell, and draft all landed backend+UI,
  closing the last named blockers; multi-body boolean (independently-built
  solids) is the one honest remaining scope boundary, not a daily-driver
  blocker. **Showcase stress test held the flip** (`d8d3b87`, qa-tester: four
  real 6–16-feature parts — bracket/enclosure/duct/pulley — built clean, mass
  properties matched hand-derivation to 0.01%, zero topological-naming
  failures). It also surfaced three real feature-coverage gaps (not engine
  defects), filed below: **F1** pattern is union-only (can't array a cut —
  bolt/lightening-hole rings unusable); **F2** a ring of disjoint circles
  isn't one sketch profile (compounds with F1); **F3** no UI warning before a
  thin-shell rim fillet hits the (correct) OCCT collision failure.
- **Interop row — ➖ (STEP import shipped end-to-end 2026-07-13).** `4964fab`
  (kernel) → gateway upload endpoint → UI file-picker: the full path — pick a
  local STEP file → upload → `import` feature → imported body in the tree +
  viewport → model on it (fillet/shell/sketch-on-face all work via the existing
  topological-naming machinery) — now works in the browser, proven by
  `import-step.spec.ts` on the real stack. IGES/multi-solid/blob-storage are
  deferred (Later); one P1 security fast-follow (bound the untrusted-STEP OCCT
  parse's wall-clock time) is still open. Note for the **vision-steward** to
  weigh the ➖→ scorecard update (VISION.md is vision-steward-owned, not touched
  here).
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; untouched this pass.

## Ready (top of queue)

Restocked 2026-07-13 (HEAD `d8d3b87`). Sketch-on-face, click-specific edge
selection, shell, and draft all shipped end-to-end and are archived below —
**Part modeling flipped ➖→✅** (`3c23c73`) and the showcase stress test
(`d8d3b87`) held it on real complex parts. **#0 leads on a code-review
security finding, ahead of everything else per standing policy** (wrong
geometry/security are always P0-adjacent). **The Interop UI leg is now
complete** (gateway upload endpoint + UI file-picker both shipped 2026-07-13;
Interop scorecard row flipped ❌→➖) — the one remaining STEP item is the P1
security fast-follow below (bound the untrusted-STEP OCCT parse time).
**#3–#4** are the
showcase's F1/F2 findings, which compound (pattern-a-cut + multi-hole-in-
one-sketch both attack the same bolt-circle/lightening-hole daily-driver
gap). #5 carries forward the engineering audit's mesh-store correctness
cliff (F1). #6–#8 are the sketch-session polish from the last re-score,
unchanged in substance.

- [ ] (P1, S) STEP import: hard wall-clock bound on the OCCT parse of
      untrusted files (code-review finding, `4964fab`) — `STEPControl_Reader.
      ReadFile`/`TransferRoots` runs in FastAPI's bounded threadpool with no
      time bound; the 16 MiB cap bounds memory, not parse *time* —
      adversarial/degenerate part-21 can be super-linear and pin a worker,
      and enough concurrent uploads soft-DoS the geometry service. First
      untrusted-external-file surface, about to get a friendly upload UI
      (#1–#2 below) that raises exposure — fix before or alongside those.
      Route import evaluation through the arq worker with a job timeout, or
      subprocess-bound the OCCT parse; also hardens the general REST eval
      path (pre-existing, sharpened here). Acceptance: a pathological/slow
      STEP file cannot pin a worker indefinitely — returns a clean per-feature
      timeout error, not a hang. [src: code-reviewer, 4964fab]
- [x] (P2, M) STEP import — gateway upload endpoint (Interop UI leg, part
      1 of 2) — `POST /api/v1/parts/{id}/features/import`: the STEP file is
      the RAW request body, streamed and size-capped chunk-by-chunk (oversize
      → 422 `import_too_large` BEFORE the body is fully read, the earliest DoS
      guard — a buffered multipart part would read the whole body first),
      decoded and mapped to an `import` feature via the existing documents
      feature-append path. Empty/non-STEP → clean 422; auth-gated; an import
      onto a part that already has a body is documents' new write-time 422
      `import_with_prior_body`. UI file-picker (part 2 of 2, below) is what
      flips the Interop row. [src: roadmap, engineering-auditor, step-import.md]
- [x] (P2, M) STEP import — UI file-picker (Interop UI leg, part 2 of 2;
      **flips the Interop scorecard row ❌→➖**) — landed 2026-07-13. An "Import
      STEP" affordance leads the in-workspace Create toolbar (new scribed
      import-cube glyph in `@loft/design`), enabled only as the first body and
      disabled with a legible reason once one exists. It opens the native
      picker (`.step,.stp`), reads the bytes, POSTs the raw octet-stream body
      via the generated `@loft/ts-client`, then refetches tree + evaluate +
      mesh so the imported body appears in the feature tree AND the r3f
      viewport. All `import_*` envelopes surface legibly in a HUD alert; size/
      extension pre-checked client-side for instant feedback. Playwright
      (`import-step.spec.ts`) drives pick→body→disabled + error paths on the
      real stack; desktop+laptop founder screenshots captured. `frontend-design`
      skill invoked. [src: roadmap, product-auditor, step-import.md]
- [ ] (P2, M) Pattern: array a cut, not just union (showcase **F1**) —
      `PatternFeature`'s `operation` is add-only (unions copies of the whole
      body); the two most natural pattern uses — bolt-circle mounting holes,
      lightening-hole rings — are cuts, so neither can use `pattern` today (the
      showcase pulley needed 6 hand-authored cut features instead of one
      pattern, `docs/showcase-parts.md` F1). Likely needs pattern to replicate
      the *source feature's operation* (cut vs. add) against its dependency
      rather than always unioning copies of the current body. Acceptance: a
      single circular-hole cut feature + `pattern` (count 6, 360°) produces 6
      holes removed, not 6 bodies added; existing add-pattern behavior
      unaffected (regression golden); worked e2e on a lightening-hole ring;
      new golden. Compounds with the next item. [src: product-auditor
      showcase-QA F1, competitive]
- [ ] (P2, M) Sketch: multi-disjoint-loop profile support for cut (showcase
      **F2**) — a sketch of N disjoint circles with no enclosing outer
      boundary is rejected `profile_unsupported` ("N closed loops not all
      enclosed by a single outer boundary"); combined with F1 this forces one
      sketch+cut pair per hole (the showcase pulley needed 16 features for a
      6-hole ring, `docs/showcase-parts.md` F2). Extend profile resolution to
      accept N disjoint closed loops as N independent removal regions on cut
      (no shared outer boundary required) — either this or the item above
      alone covers the common case; both together is best. Acceptance: a
      sketch of 6 disjoint circles + extrude(cut) removes 6 separate holes in
      one feature; existing single-outer-boundary multi-loop behavior
      (holes-in-a-plate) unaffected; worked e2e; new golden. [src:
      product-auditor showcase-QA F2, competitive]
- [ ] (P2, M) Mesh store: object-storage swap or explicit single-worker
      guard (engineering audit **F1**) — the in-process mesh LRU
      (`geometry/mesh_store.py`) is a process-global; evaluate and fetch
      landing on different workers/replicas 404s the mesh ~(N−1)/N of the
      time. Masked today (compose runs 1 geometry container, uvicorn
      defaults to 1 worker) but compose already provisions `S3_URL`/
      `S3_BUCKET` implying multi-replica readiness that isn't real yet — a
      correctness cliff on the "cloud-native/self-hostable" claim. v1
      acceptable scope: EITHER land the MinIO-backed mesh store (feature-tree
      design doc §7.8, preferred) OR add an enforced single-worker guard +
      readiness note gating any `--workers>1`/replica>1 deploy until the
      swap lands. Acceptance: a 2-worker smoke test round-trips
      evaluate→fetch without 404 (swap path) OR startup fails loud on
      `--workers>1` with a clear message pointing at §7.8 (guard path);
      GEOMETRY-QA/ROADMAP §7.8 updated to say which. [src: engineering-auditor F1]
- [ ] (P2, S) Sketch: over-constraint classification — upgrade
      `sketch_conflicting` from raw constraint indices to a classified
      redundant-vs-conflicting diagnosis with a suggested fix, surfaced in
      the typed `FeatureError` (not string-parsed). `planegcs_solver.py`
      already computes `redundant` internally per VISION.md's 2026-07-12
      re-score — this item is exposing it, not deriving it fresh. Depends
      on: nothing new. Acceptance: a deliberately over-constrained sketch
      (e.g. two conflicting distance dims) returns distinct redundant vs.
      conflicting classifications with the offending constraint ids named
      in the message; frontend reads the typed field instead of parsing
      text; worked e2e; supersedes the older "Structured conflict indices"
      Later item. [src: product-auditor, competitive]
- [ ] (P2, M) Sketch dimension expressions / driving vs. driven — a
      dimension value field accepts a literal, a reference to another
      dimension, or a math expression; each dimension gets a `driving: bool`
      flag (driving = feeds the solver, driven = read-only/informational).
      Confirmed absent by grep of `apps/web/src`. Depends on: nothing new.
      Acceptance: expression parser (+,-,*,/, parens, dimension-name refs);
      `driving` flag on the typed dimension-constraint schema; worked e2e —
      set width=20, height="width/2", confirm height solves to 10; toggle a
      dimension to driven, edit geometry directly, confirm the readout
      updates without feeding the solver; screenshots; `frontend-design`
      skill invoked for the expression-entry field. [src: competitive]
- [ ] (P2, M) Sketch: constrainable splines (v1.1) — splines shipped
      non-constrained (fixed geometry, zero DOF; `planegcs` has no native
      spline primitive per the #6 commit message). Design a fit-point
      constraint mapping (each fit point becomes a solver point subject to
      coincident/distance/etc like any other point) rather than a native
      spline primitive — smallest increment that makes a spline
      participate in a sketch's DOF instead of sitting outside it.
      Acceptance: a spline's fit points accept the existing point-level
      constraints (coincident, distance, horizontal/vertical) and the DOF
      readout reflects them; worked e2e — constrain a fit point to a line,
      confirm the spline reshapes on solve; spline tangency stays explicitly
      deferred (documented). [src: product-auditor, competitive]

## Next (P2)

- [ ] (P2, S) Revolve: construction-centerline axis opens the profile (UX
      trap, product audit #4) — marking the on-axis edge `construction: true`
      (the natural SolidWorks/Fusion idiom) excludes it from the profile wire
      → `422 profile_not_closed`; today only a real profile-boundary edge
      used *as* the axis works. Fix: accept a construction-flagged edge as
      the revolve axis without requiring it in the profile wire, or surface
      a clear hint distinguishing the two idioms. Acceptance: sketch a
      half-profile + a construction centerline on the axis → revolve
      succeeds using the centerline; existing real-edge-as-axis path
      unaffected; worked e2e. [src: product-auditor]
- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2**) — thread a bool through
      `evaluate_tree` so `export_tree`/measure (which never fetch the GLB)
      don't churn the 64-slot mesh LRU with never-fetched entries, evicting
      live interactive-session meshes. Acceptance: export/measure requests
      no longer call `store_mesh_glb` (test asserts cache occupancy
      unchanged after N exports); evaluate-for-viewport path unaffected.
      [src: engineering-auditor F2]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slices — the
      circular-pattern slice shipped, archived below) — all remaining
      goldens are additive-only and no offset-plane golden exercises
      revolve/sweep (code-noted "same path, untested"). Acceptance: one
      `*-cut-*` golden and one revolve-or-sweep-on-offset golden, same
      determinism gate as existing goldens. [src: engineering-auditor F4,
      geometry-qa]
- [ ] (P2, S) Units system — mm-only today; a per-part or per-workspace unit
      preference (in/mm) with display-layer conversion (kernel stays mm
      internally per CLAUDE.md tolerances). Independent. [src: roadmap]
- [ ] (P2, M) Undo/redo across feature operations — UI-level action history,
      distinct from the rollback bar (which moves the build point, not an
      action stack). Independent. [src: roadmap, competitive]
- [ ] (P2, M) Performance benchmark suite with CI budgets — formalize the
      ad-hoc per-golden warm-rebuild numbers already in GEOMETRY-QA.md
      (3.8 ms–33 ms today) into a tracked suite with committed budgets and a
      CI regression gate (GEOMETRY-QA gap #7). [src: geometry-qa]
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, M) Rate limiting + request-size caps on unauthenticated auth
      endpoints (py-kit middleware — DRY home) — pre-deploy hardening.
      [src: code-reviewer]

## Later (P3)

- [ ] (P3, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. **Downgraded P2→P3 this pass:** multi-loop closed-profile
      cuts now cover the common bolt-circle/mounting-hole case the product
      audit was pushing this for; a dedicated Hole feature is a nicety
      (counterbore/countersink, no sketch needed) once face picking lands,
      not the unblocker it was before multi-loop shipped. Depends on
      face/edge picking (Ready, above) landing — needs a stable face
      reference. [src: roadmap, product-auditor, competitive]
- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5**) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs so a non-consecutive coincidence falls into a
      legible `profile_*` error instead of the generic `evaluation_failed`
      catch-all. [src: engineering-auditor F5]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. Pairs with the hole feature
      above. [src: competitive]
- [ ] (P3, M) Multi-body boolean — join/cut/intersect between solid bodies.
      VISION.md names this the one remaining Part-modeling scope boundary
      post-✅-flip (uncommon workflow, not a daily-driver blocker). [src:
      competitive, roadmap]
- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim
      collision (showcase **F3**) — filleting all rim edges of a thin shell
      at r ≥ half the wall thickness correctly fails `fillet_failed` (OCCT
      refuses the colliding round-overs, `docs/showcase-parts.md` F3);
      backend behavior is correct, this is discoverability only. Acceptance:
      when the active body's history includes a shell feature, the fillet
      editor surfaces a soft warning (not a hard block — OCCT stays the
      authority) if the entered radius exceeds half the nearest known shell
      thickness; `frontend-design` skill invoked; worked e2e triggering +
      dismissing the warning; existing `fillet_failed` path unchanged. [src:
      product-auditor showcase-QA F3]
- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow
      (showcase forward note, qa-tester) — shell hollows the WHOLE current
      body; there's no way to shell only a selected region, so a flange
      added before shelling becomes a thin tray and one added after needs
      sketch-on-a-thin-rim — both awkward (`docs/showcase-parts.md`, "Not
      attempted"). Needs a design note first (what "a selected region" means
      for `MakeThickSolid` — sub-body face grouping vs. split-shell-rejoin).
      Not urgent: the showcase routed around it by placing flanges pre-shell/
      pre-loft, where it's natural. [src: qa-tester showcase-QA]
- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded
      (`docs/design/step-import.md` §2a); removes the inline
      `MAX_INLINE_STEP_CHARS` (16 MiB) cap for real-world assemblies-worth-
      of-geometry files. [src: roadmap, step-import.md]
- [ ] (P3, L) STEP import v2: IGES, multi-solid/assembly, sew/repair healing
      — the three deferred scope items from `4964fab`'s v1: (1) IGES as a
      second import format alongside STEP; (2) multi-solid source files
      (today: single-solid or a legible `import_not_single_solid` error) —
      likely couples to Phase 3 assemblies rather than shipping standalone;
      (3) a real sew/repair healing report beyond raw shape stats. Split into
      independent slices when picked up. [src: roadmap, geometry-qa,
      step-import.md]
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents HTTPValidationError)
      [src: kernel-architect]
- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening; deferred 🟢 from the Phase 0 review-fix batch.
      [src: code-reviewer]
- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic; deferred 🟢 from the Phase 0 review-fix batch.
      [src: code-reviewer]
- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's
      core wedge, but explicitly not urgent: doesn't flip a current ❌ row
      since Loft's parametric core isn't finished yet. Revisit once Part
      modeling is closer to parity. [src: competitive]

## Blocked (environment/timing — not build-blocked)

- [ ] (P2, S) Verify full `docker compose up` runtime on a Docker-capable
      host — this sandbox has no docker daemon; images and stack runtime are
      unproven. First Docker-capable session picks it up. [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended.
      [src: retro]

## Done — archive

Full evidence for every line below lives in `CHANGELOG.md`.

### Phase 0 (through commit 322a988)

- [x] (P1, M) Monorepo scaffold — uv + pnpm workspaces, justfile, lint/test
      gates green. [src: roadmap]
- [x] (P1, M) `packages/py-kit` service bootstrap — config, JSON logging,
      app factory, error envelope, queue client; unit tested. [src: roadmap]
- [x] (P1, L) Service skeletons + compose — gateway/geometry/documents on
      py-kit; parameterized Dockerfile + compose stack config-validated;
      smoke + dev-instance scripts (runtime `up` = blocked item above).
      [src: roadmap]
- [x] (P1, M) Contract pipeline — `just gen` + `just gen-check` drift gate;
      OpenAPI → `packages/contracts` → `packages/ts-client`. [src: roadmap]
- [x] (P1, L) Web shell + first light — design tokens (`packages/design`),
      r3f viewport rendering OCCT-tessellated GLB via the gateway, live
      parametric editing, Playwright e2e, founder screenshots.
      [src: roadmap, founder]
- [x] (P1, M) CI pipeline — lint/typecheck/unit, contract drift, compose
      validation as four parallel GitHub Actions jobs. [src: roadmap]
- [x] (P2, M) Geometry golden harness — data-driven golden runner + STEP
      round-trip gate; cube golden at 0.0 measured deviation; evidence in
      docs/GEOMETRY-QA.md. [src: roadmap]
- [x] (P2, S) Community surface — truth-only README, CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, issue/PR templates. [src: roadmap]
- [x] (P0, batch) Phase 0 review-fix batch — geometry image runtime libs,
      pytest exit-5 gate, OpenAPI dedupe helper, readyz detail hygiene,
      corrupt-GLB surfacing. [src: code-reviewer]

### Phase 1 — Ready batch 1 (through commit 565e337)

- [x] (P1, M) STEP/STL export endpoints + UI download — geometry endpoint,
      gateway proxy, title-block download UI; endpoint-level STEP round-trip
      at 0.0 deviation; Interop's first shipped half. [src: roadmap, geometry-qa]
- [x] (P1, S) First curved golden: `cylinder-r10-h25` — closes GEOMETRY-QA
      gap #1 (curved GProp, seam-edge topology, curved STEP round-trip).
      [src: geometry-qa]
- [x] (P1, M) Feature-tree persistence design doc — `docs/design/
      feature-tree.md`, code-reviewer-endorsed after one revision round.
      [src: roadmap]
- [x] (P1, M) SketchSolver interface + planegcs spike — verdict: planegcs
      adopted (LGPL-2.1 verified), benchmark rectangle at 0.0 deviation.
      [src: research]
- [x] (P1, M) Auth v1 backend — argon2id + HS256 JWT register/login/me,
      fail-fast `JWT_SECRET` posture. [src: roadmap]
- [x] (P1, M) Documents service: parts CRUD — owner-scoped CRUD, alembic
      `0001_parts`, gateway aggregation. [src: roadmap]
- [x] (P1, S) Auth v1 web sign-in — login/register + session persistence,
      15/15 Playwright green. [src: roadmap]
- [x] (P1, S) `just e2e` wiring — `scripts/e2e.sh` runs geometry gates +
      Playwright (GEOMETRY-QA gap #6). [src: geometry-qa]

### Phase 1 — Ready batch 2 (through commit 11eaa65)

- [x] (P1, M) Feature-tree persistence — documents schema + API slice —
      alembic `0002_feature_tree`, feature CRUD/reorder/rollback, reference
      rules, 409/422 conflict handling. [src: roadmap]
- [x] (P1, M) Feature-tree persistence — geometry evaluate slice — stateless
      `POST /api/v1/evaluate`, ordered dispatch, strict-prefix partial
      results. [src: roadmap]
- [x] (P1, M) Sketch model + solver API — typed sketch entity/constraint
      schemas, §6 worked example solved end-to-end at 0.0 deviation.
      [src: roadmap]
- [x] (P1, S) Sketcher UI — plane + entity authoring — `/parts/{id}`
      workspace, datum-plane pick, L/R/C/A tools, persistence e2e 19/19.
      [src: roadmap]
- [x] (P1, M) Sketcher UI — constraints + solve feedback — H/V/D/R/X/C
      verbs, in-viewport glyphs, DRO DOF cell, conflict diagnostics; e2e
      25/25. [src: roadmap]
- [x] (P1, M) Extrude (add/cut) end-to-end — first body-affecting feature +
      golden `sketch-extrude-40x25x10`, strict-prefix error rule, §7.8
      interim mesh endpoint. [src: roadmap]

### Phase 1 — Ready batch 3 / exit gate (through commit ff6b226)

- [x] (P1, S) Gateway mesh-fetch proxy — content-addressed GLB proxy,
      auth-protected, byte-identical to geometry's endpoint. [src: geometry-qa,
      product-auditor]
- [x] (P1, M) Viewport renders evaluated-tree bodies — extruded bodies
      visible for the first time (aluminium + B-rep edges, title-block
      inspector). [src: product-auditor, engineering-auditor]
- [x] (P1, M) Extrude feature UI + feature-tree edit/rollback — title-block
      authoring editor, selectable tree rows, brass rollback bar.
      [src: frontend-builder]
- [x] (P1, S) Parts home UI — drawing-register create/list/open/delete,
      closes the last navigation gap before the exit gate. [src: frontend-builder]
- [x] (P1, M) Fillet feature — geometric edge selection, golden
      `fillet-plate-r5` (first curved-topology-class fillet) at 1e-9.
      [src: roadmap, product-auditor]
- [x] (P1, M) Chamfer feature — reuses fillet's shared `select_edges`, golden
      `chamfer-plate-d5` (all-planar, exact 0.0 STEP round-trip).
      [src: roadmap, product-auditor]
- [x] (P1, M) Export-from-tree — `POST /api/v1/export/tree` +
      `POST /api/v1/parts/{id}/export`, closes GEOMETRY-QA gap #8.
      [src: geometry-qa, roadmap]
- [x] (P1, M) Full-flow Playwright e2e — the Phase 1 exit gate: login →
      sketch → extrude → edit param → export, desktop + 1280×800 + touch
      smoke. [src: frontend-builder]

### Phase 2 — Ready batch 1 (through commit 5777656)

- [x] (P1, M) Topological naming strategy — design doc —
      `docs/design/topological-naming.md`, staged hybrid signature+
      provenance, additive `SubshapeRef`; code-reviewer-endorsed. [src:
      roadmap, engineering-auditor]
- [x] (P1, S) Sketch: construction geometry — `construction: bool` field +
      `N` keyboard toggle, dashed/muted render, excluded from the extrude
      profile check. [src: product-auditor, roadmap]
- [x] (P1, M) Sketch constraints — tangent/perpendicular/parallel — 3
      planegcs `ConstraintKind`s + P/L/T verbs + ∥/⊥/T glyphs, worked e2e.
      [src: product-auditor, roadmap]
- [x] (P1, M) Sketch constraints — equal/symmetric/concentric — the
      remaining 3 kinds + E/S/O verbs + =/⟷/◎ glyphs; all 12 constraint
      kinds shipped. [src: product-auditor, roadmap]
- [x] (P1, M) Revolve feature — second body-affecting feature, golden
      `revolve-annulus-r10-20-h15`, title-block axis-pick + angle editor.
      [src: roadmap, product-auditor]
- [x] (P2, S) Measurement tool — point/edge distance — `/measure` +
      `/overlay` endpoints, viewport pick-and-read UI, brass dimension line
      + title-block readout; e2e reads the box golden √1400 ≈ 37.42 mm.
      [src: product-auditor]
- [x] (P2, M) Linear/circular pattern — `PatternFeature` v1 (world-space
      direction/axis, boolean-union into the body chain) + `PatternEditor`
      authoring UI; 5th body-affecting feature. [src: roadmap,
      product-auditor]

### Phase 2 — Ready batch 2: sketch session-tool cluster + sweep/loft backend (through commit 1e3d422)

- [x] (P1, M) Fillet/Chamfer authoring UI — predicate edge selector (all /
      axis-parallel), title-block radius/distance handle. [src: roadmap]
- [x] (P1, M) Sketch trim/extend — backend + UI (#2/#2b) — exact analytic
      line/arc/circle trim/extend, constraint reconciliation on split/delete.
      [src: product-auditor, competitive]
- [x] (P1, S) Sketch offset — backend + UI (#3/#3b) — signed-distance
      parallel copy, single-entity v1. [src: product-auditor, competitive,
      roadmap]
- [x] (P1, M) Sketch mirror — backend + UI (#4/#4b) — reflection about a
      line-entity or two-point axis, live reflection ghost. [src:
      product-auditor, competitive, roadmap]
- [x] (P1, S) Sketch fillet/chamfer (corner round) — backend + UI (#5/#5b) —
      line-line corners only v1. [src: product-auditor, competitive, roadmap]
- [x] (P1, M) Sketch splines (Fit-Point v1) — backend + draw-tool UI (#6/#6b)
      — non-constrained v1, Catmull-Rom viewport preview of the server B-spline.
      [src: product-auditor, competitive, roadmap]
- [x] (P1, M) Sweep feature — backend + UI (#7/#7b) — profile along a second
      sketch's open path wire, golden `sweep-circle-r8-h30`. [src: roadmap,
      product-auditor, competitive]
- [x] (P1, M) Loft feature (#8) — backend (ruled loft, ≥2 sections incl.
      loft-to-apex) + UI (#8b, ordered section-stack picker); e2e proves a
      real frustum via two offset-plane circles. [src: roadmap, product-auditor,
      competitive]

### Phase 2 — Ready batch 3: offset/datum planes + multi-loop holes (through commit a36e436)

- [x] (P1, S) Design note: offset/datum plane representation —
      `docs/design/datum-planes.md`, code-reviewer-endorsed. [src: product-auditor,
      engineering-auditor, roadmap]
- [x] (P1, M) Offset/datum planes — backend (`DatumFeature`, `resolve_sketch_plane`
      funnel) + picker UI (#2b, inline "+ Offset plane" + standalone Datum tool);
      unblocked #8b loft UI and sketch-on-a-height. [src: product-auditor,
      engineering-auditor, roadmap, frontend-builder]
- [x] (P1, M) Multi-loop closed profiles → holes — the product audit's #1
      daily-driver gap; one sketch (outer boundary + N inner loops) now
      extrudes/cuts a plate with N through-holes, shared across
      extrude/revolve/sweep/loft, no topological naming needed. [src:
      product-auditor #1]

### Phase 2 — Ready batch 4: sketch-on-face + edge-pick + shell + draft; Part modeling flips ✅ (through commit d8d3b87)

- [x] (P1, S) Sketch-on-a-model-face — backend + UI end-to-end; topological-
      naming consumer #1, "Pick a face" seats a sketch on a picked planar
      face; e2e boss-on-face. [src: product-auditor #2]
- [x] (P1, M) Click-specific edge selection for fillet/chamfer — backend +
      UI end-to-end; consumer #2, one-edge-rounds-not-its-neighbours; e2e
      `fillet-edge-pick`. [src: roadmap, product-auditor #3, engineering-auditor]
- [x] (P2, S) Shell feature — backend + UI end-to-end; hollows a body,
      picked faces stay open; e2e `shell.spec`. [src: roadmap, competitive]
- [x] (P2, M) Draft feature — backend + UI end-to-end; tapers picked faces
      about a neutral plane; e2e `draft.spec`. [src: roadmap, competitive]
- [x] (P2, S) Geometry QA: circular-pattern determinism golden (engineering
      audit F4, first slice) — `pattern-circular-4x-quadrant-box`. [src:
      engineering-auditor F4, geometry-qa]
- [x] (P1, M) Web e2e: multi-loop profile holes through the real browser —
      proves the audit's #1 gap end-to-end (topology 6→8 faces, volume
      strictly under bbox). [src: product-auditor #1]
- [x] (P1, M) STEP import v1 (geometry-kernel side) — `ImportFeature` reads
      inline STEP text and sets the body; modeled on by every later feature.
      Gateway upload + UI still open (BACKLOG Ready). [src: roadmap,
      engineering-auditor, step-import.md]
- Docs: `docs/showcase-parts.md` — four real 6–16-feature parts stress-test
  Part modeling ✅; held, no P0; surfaced F1–F3 (filed above). [src: qa-tester]

## Changelog

Older entries (incl. 2026-07-12/13 sketch-on-face/edge-pick/shell/draft/
STEP-import-v1 ship notes) live in `CHANGELOG.md`.

- 2026-07-13 — Groomed after STEP import v1 (`4964fab`, geometry-side only)
  + showcase stress test (`d8d3b87`, held, no P0). Filed the Interop UI-leg
  items (gateway upload + import UI — the actual flip path), showcase F1–F3
  + a partial-shell forward note, and a P1 security fast-follow (untrusted-
  STEP parse timeout). Archived 7 shipped items to Done batch 4.
  [backlog-groomer]
