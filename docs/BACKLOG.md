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

- **Sketching, Part modeling — both ✅ (2026-07-15).** Sketching's last three
  gaps (over-constraint diagnosis, dimension expressions/driving-driven,
  constrainable splines) closed this batch (`a1c42be`); Part modeling held
  under the showcase stress test the pass before. Residual, non-gating scope
  boundaries: multi-body boolean, spline tangency, expression functions/units.
- **Interop — ➖.** STEP import shipped end-to-end (upload → sketch-on-it →
  re-export), verified live by the product-auditor. IGES, multi-solid,
  healing report deferred (Later).
- **Assemblies, Drawings — ❌, now the headline gaps.** Both auditors and the
  founder converge on **Assemblies as #1** (product audit 2026-07-15: "the
  missing project container" — most real mechanical work is two-or-more
  parts, not one lonely bracket). Drawings is the audit's honest #2/near-#1
  counter-argument (smaller build, completes the make-loop for the
  already-solid single-part case via STEP-to-shop) — not sequenced this
  pass; pick up once assemblies v1 has landing room or if Ready runs dry.
- **Unfiled-but-named product-audit follow-ups** (history-tree drag-reorder/
  suppress, feature-mirror + 2-direction pattern, a friendlier
  `boolean_failed` message) — next groom pass, once assemblies v1 has room.
- **`docs/COMPETITIVE.md` is stale** (dated 2026-07-12 — pre-dates Phase 2's
  close and the assemblies design doc); flagged for the vision-steward to
  refresh against the Phase 3 focus.
- Performance, Collaboration, Extensibility, Agent access — untouched, later
  phases.

## Ready (top of queue)

Restocked 2026-07-15 (HEAD `36dc3d9`) — major reconcile at the Phase 2→3
boundary. **Phase 2 (parametric core) converged this batch**: Sketching and
Part modeling both closed to ✅; every item that carried that work is
archived below (Done, Phase 2 batch 5). **Assemblies is now the queue's
spine** — the founder-chosen #1 (`docs/design/assemblies.md`, endorsed
architecture decision), sequenced into 6 dependency-ordered slices: **#1**
the documents foundation → **#2/#3** the flagged-risk solver + mate-geometry
resolution → **#4** gateway → **#5** the v1 DoD golden (evaluation +
shared-mesh tessellation) → **#6** frontend. **#7–#8 interleave real,
independent audit debt** (MinIO mesh-store swap F1/F6; STEP re-parse caching
F8) — pick up whenever a builder frees up, not gated on the assemblies
dependency chain. **#9 (rate limiting)** is F7's unbuilt second half,
promoted from Next — security-adjacent debt outranks polish even mid-pillar.
**Judged OUT of Ready this pass:** F2 (evaluate_tree tessellation churn —
real but low severity/likelihood, stays Next) and F5 (spline epsilon — P3
nit, no user impact, stays Later).

- [x] (P1, M) Assemblies v1 #1 — document model + CRUD API (documents) — **DONE
      2026-07-15.** `py_kit.schemas.assemblies` (Placement/Quat, MateFace/AxisRef
      reusing PlanarFaceSignature/EdgeSignature verbatim, the discriminated
      5-mate union lock/coincident/concentric/distance/angle), `assemblies`/
      `instances`/`mates` tables (migration `0003`, deferrable instance order
      unique, ref_document_id app-enforced not FK), owner-scoped CRUD with OCC
      (`doc_version` 422-on-stale), write-time acyclicity (`assembly_cycle`
      422, DFS over sub-assembly edges), cross-document 409-with-dependents on
      deleting an instanced part/sub-assembly. Full lint/pyright + 1044 py
      tests (SQLite + real PG) + gen-check green. [src: design/assemblies.md,
      product-auditor #1]
- [ ] (P1, M) **← NEXT** Assemblies v1 #2 — `AssemblySolver` core (geometry, numeric)
      — **THE FLAGGED RISK** (design doc §2.4). New `AssemblySolver` protocol
      mirroring `SketchSolver` (RESEARCH §2): quaternion 6-DOF free
      instances, deterministic damped Gauss-Newton/LM seeded from authored
      placement (grounded instances fixed, no random restarts), the §2.2
      closed-form fast path for a mate-tree rooted at a grounded instance,
      full diagnosis vocabulary (`well_constrained`/`under_constrained`/
      `over_constrained`-redundant/`conflicting`/`not_converged`,
      remaining-DOF via Jacobian rank, offending mate ids named,
      `removable` flag) mirroring `SketchConstraintDiagnosis`. Tested
      standalone against **synthetic** residuals (no OCCT, no mate-geometry
      resolution yet — that's #3) so the numeric core is provable in
      isolation. Acceptance: unit tests — two-instance `lock` solve;
      `coincident`+`concentric` solve matches a hand-derived analytic
      transform; an under-constrained case reports the correct
      `remaining_dof`; a conflicting pair reports `conflicting` + the right
      mate ids; a determinism test (bitwise-identical transforms across
      repeated runs AND a fresh interpreter, mirroring `test_goldens.py`'s
      restart-probe). No GPL/AGPL dependency (RESEARCH §8 — numpy/scipy
      only, license-checked in the same commit). Depends on: nothing new
      (numeric-only, parallel to #1). [src: design/assemblies.md §2,
      engineering risk]
- [ ] (P1, M) Assemblies v1 #3 — mate-geometry-ref resolution (geometry) —
      resolves a `MateFaceRef` against the `PlanarFaceSignature` resolver an
      `on_face` datum already uses, and a `MateAxisRef` against the
      `EdgeSignature` resolver (`curve == "circle"`, axis = normal through
      the seam-point centre) — **reusing the exact stage-1 signature
      machinery** (`topological-naming.md` §9), exactly-one-or-honest-error
      (`subshape_unresolved`/`subshape_ambiguous`, never a silent skip).
      Wires the resolved (point, normal)/(point, direction) pairs into #2's
      `AssemblySolver` residuals, replacing synthetic test fixtures with
      real OCCT-derived geometry. Acceptance: unit tests — a resolved
      coincident+concentric pair reproduces #2's analytic-transform test
      against a REAL evaluated part body (not synthetic); an ambiguous/
      missing signature returns the typed error, never a 500. Depends on:
      #2 (solver protocol), the existing `geometry.kernel.faces`/`.edges`
      resolvers. [src: design/assemblies.md §2.1, §4]
- [ ] (P1, M) Assemblies v1 #4 — gateway assembly endpoints — proxy the
      documents CRUD (assembly/instance/mate create/get/list/delete) with
      `CurrentUser` auth on every route from day one (closing the F7-class
      gap proactively instead of retrofitting later). Acceptance: a
      401-without-token test per route; an integration test drives
      create-assembly → add-two-instances → add-a-lock-mate → get through
      the gateway against isolated documents+gateway ports (CLAUDE.md
      recipe); contracts regenerated. Depends on: #1 (documents API to
      proxy). [src: design/assemblies.md §3]
- [ ] (P1, M) Assemblies v1 #5 — assembly evaluation + shared-mesh
      tessellation — **"bolt two parts together and see it," the v1 DoD.**
      The full `EvaluateAssemblyRequest`/`Result` pipeline (design doc §4):
      evaluate each UNIQUE part once (dedup by `part_key`), call #2+#3's
      resolver/solver for the solved world `Placement` per instance,
      tessellate + `store_mesh_glb` each unique part ONCE (content-
      addressed, reused across instances of the same part), compose
      analytic combined properties (Σ volumes, mass-weighted centroid, bbox
      union — no re-meshing, no boolean). New golden
      `assembly-two-plates-bolted` (design doc §6.1): plate A grounded,
      plate B mated coincident+concentric — assert each solved `Placement`
      equals the hand-derived analytic transform within a documented
      tolerance, and combined mass properties equal the analytic roll-up.
      Solve-determinism gate (§6.2, bitwise-identical across runs/fresh
      interpreter). Shared-mesh-dedup test (§6.4): the same part instanced
      twice yields ONE `part_mesh_glb_id` referenced by two placements.
      Per-mate/per-instance errors surface as a typed `FeatureError` inside
      a 200, never a transport 4xx. Depends on: #2, #3. [src: design/
      assemblies.md §4, §6]
- [ ] (P1, M) Assemblies v1 #6 — frontend assembly tree + instance
      placement + mate authoring — apps/web: an assembly workspace (sibling
      of `/parts/{id}`), an instance list (add-instance-from-a-part picker,
      grounded toggle, placement gizmo), and mate authoring (pick a face on
      each of two instances → Coincident; pick a circular edge on each →
      Concentric; Lock two instances) driving #4's gateway endpoints and
      rendering #5's per-instance shared meshes + solved transforms via r3f
      instancing (one part mesh drawn N times). `frontend-design` skill
      invoked (new surface). Acceptance: worked e2e — create an assembly,
      instance two parts, mate them coincident+concentric, see both solved
      in the viewport (screenshot evidence, desktop + 1280×800); a
      conflicting-mate case surfaces the typed diagnosis legibly. Depends
      on: #4, #5. [src: design/assemblies.md §4, product-auditor #1]
- [ ] (P2, M) Mesh store: MinIO-backed object-storage swap (engineering audit
      **F1/F6**, forward goal) — the single-worker guard (shipped
      2026-07-13) only covers in-process workers; replica fan-out
      (`docker compose --scale`, k8s `replicas>1`) still reproduces the
      intermittent-404 cliff since `_STORE` is process-global (F6, Pass 2).
      **Remaining scope:** swap the in-process LRU for content-addressed
      MinIO writes (key stays `sha256:<hex>`, byte-for-byte the current DTO
      contract) plus the gateway mesh-streaming path (§7.8 default posture),
      then lift the guard. Worth interleaving with assemblies (not
      blocking): more instances per assembly means more meshes competing
      for the 64-slot LRU, so this swap's payoff grows with #5 above.
      Acceptance: a **real-MinIO** 2-worker/2-replica smoke round-trips
      evaluate→fetch without 404 **in CI** (this sandbox can't prove it — no
      docker daemon, no `moto` cross-process fidelity) — the swap MUST NOT
      land without that CI gate. [src: engineering-auditor F1/F6]
- [ ] (P2, M) STEP import: cache the transferred body across evaluations
      (engineering audit **F8**) — `_evaluate_import` re-spawns the parse
      subprocess (~0.9 s cold start) and re-parses up to 16 MiB of part-21
      on EVERY feature-tree evaluation, because the imported STEP is stored
      inline and `evaluate_tree` re-runs the whole prefix on every edit — a
      per-edit latency floor on the interop workflow that never improves
      regardless of tree depth. Fix: cache the transferred body keyed on
      the import params' content hash (the STEP text is immutable once
      stored) — either at the evaluation-state level or a small
      process-level LRU keyed on the hash. Acceptance: a test asserts the
      parse subprocess is invoked ONCE per distinct upload across N
      sequential feature-tree evaluations sharing that import, not N times;
      existing import goldens/tests unaffected; the killable-subprocess
      timeout bound (P1 security, shipped) is preserved for the one real
      parse. Depends on: nothing new. [src: engineering-auditor F8]
- [ ] (P2, M) Rate limiting + request-size caps (py-kit middleware — DRY
      home) — pre-deploy hardening, the unbuilt half of audit F7 (whose
      auth gap shipped 2026-07-15, `36dc3d9`). Covers the unauthenticated
      auth endpoints AND the per-principal geometry-compute surface
      (tessellate/export/measure/overlay — now all auth-gated but still
      unbounded per-caller). Promoted to Ready this pass: security-adjacent
      cross-cutting debt outranks new-pillar polish even while assemblies is
      the headline priority. Acceptance: a per-principal request-rate cap
      (429 beyond the limit) on the geometry-compute routes + auth
      endpoints, unit-tested; documented default limits. [src: code-reviewer,
      eng-audit F7]

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
      callers (engineering audit **F2**, now also `/overlay` — 3 non-fetching
      callers) — thread a bool through `evaluate_tree` so `export_tree`/
      measure/overlay (which never fetch the GLB) don't churn the 64-slot
      mesh LRU with never-fetched entries, evicting live interactive-session
      meshes. Acceptance: export/measure/overlay requests no longer call
      `store_mesh_glb` (test asserts cache occupancy unchanged after N
      calls); evaluate-for-viewport path unaffected. [src: engineering-
      auditor F2]
- [ ] (P2, M) Multi-body + boolean intersect (product audit Pass 2 — "a
      cheaper adjacent win than assemblies") — allow a disjoint additive
      solid in one part (today: `boolean_failed`) and add
      `operation:"intersect"` alongside add/cut. **Tension note:** VISION.md
      frames this as a non-blocking scope boundary now that Part modeling is
      ✅; the fresh product audit rates it P1 ("unlocks tooling/mold/split
      workflows"). Bumped P3→P2 this pass to reflect that reweighing, but
      kept behind assemblies (the founder's explicit #1) rather than in
      Ready. [src: product-auditor Pass 2, competitive, roadmap]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism
      gate as existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Units system — mm-only today; a per-part or per-workspace unit
      preference (in/mm) with display-layer conversion (kernel stays mm
      internally per CLAUDE.md tolerances). Independent. [src: roadmap]
- [ ] (P2, M) Undo/redo across feature operations — UI-level action history,
      distinct from the rollback bar (which moves the build point, not an
      action stack). Independent. [src: roadmap, competitive, product-auditor
      Pass 2 history-tree ergonomics]
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

## Later (P3)

- [ ] (P3, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. Multi-loop closed-profile cuts cover the common
      bolt-circle/mounting-hole case; a dedicated Hole feature is a nicety
      (counterbore/countersink, no sketch needed) once face picking lands,
      not the unblocker it was before multi-loop shipped. Depends on
      face/edge picking (shipped) — needs a stable face reference. [src:
      roadmap, product-auditor, competitive]
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
      likely couples to the assemblies pillar rather than shipping
      standalone; (3) a real sew/repair healing report beyond raw shape
      stats. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]
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

### Phase 1 (through commit ff6b226)

- [x] (P1, M) STEP/STL export endpoints + UI download, first curved golden,
      feature-tree persistence design doc, `SketchSolver`+planegcs adoption,
      auth v1 (backend+web), documents parts CRUD, `just e2e` wiring.
      [src: roadmap, geometry-qa]
- [x] (P1, M) Feature-tree persistence (documents API + geometry evaluate
      slice), sketch model + solver API, sketcher UI (plane/entity authoring
      + constraints/solve feedback), extrude (add/cut) end-to-end.
      [src: roadmap]
- [x] (P1, M) Gateway mesh-fetch proxy, viewport renders evaluated bodies,
      extrude UI + feature-tree edit/rollback, parts home UI, fillet,
      chamfer, export-from-tree, full-flow Playwright exit gate.
      [src: roadmap, product-auditor, engineering-auditor]

### Phase 2 (through commit a1c42be) — parametric core converges

**Batch 1** (topological-naming design doc, construction geometry,
tangent/perpendicular/parallel + equal/symmetric/concentric constraints,
revolve, measurement tool, linear/circular pattern) through commit `5777656`.
**Batch 2** (fillet/chamfer authoring UI, sketch trim/extend/offset/mirror/
fillet-chamfer, splines v1, sweep, loft) through commit `1e3d422`. **Batch 3**
(offset/datum planes, multi-loop closed profiles → holes) through commit
`a36e436`. **Batch 4** (sketch-on-a-model-face, click-specific edge selection,
shell, draft — **Part modeling flips ➖→✅**; circular-pattern determinism
golden; STEP import v1 kernel-side; showcase stress test surfaces F1–F3;
pattern-a-cut + multi-disjoint-loop cut close F1/F2) through commit `d8d3b87`.
**Batch 5 — Phase 2 converges** (through `36dc3d9`): STEP import P1 security
+ gateway upload + UI file-picker (**Interop flips ❌→➖**); typed
over-constraint diagnosis (#6); sketch dimension expressions + driving/driven;
constrainable spline fit points v1.1 (backend+frontend) — **Sketching flips
➖→✅** (`a1c42be`); gateway auth-gate on geometry-compute routes (audit F7 P1
security, `36dc3d9`); assemblies architecture decision endorsed (`b378633`);
both audits re-baselined 2026-07-15. Full per-item evidence: `CHANGELOG.md`.

## Changelog

Older entries live in `CHANGELOG.md`.

- 2026-07-15 — Phase 2→3 reconcile: Phase 2 converged (Sketching + Part
  modeling ✅), 9 shipped items archived. **Assemblies sequenced into 6
  Ready items** (`docs/design/assemblies.md`); interleaved F1/F6/F8/F7-rate-
  limit debt as #7–#9; bumped multi-body boolean P3→P2. [backlog-groomer]
