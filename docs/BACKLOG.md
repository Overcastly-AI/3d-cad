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
- **Assemblies — ➖ (2026-07-15, flipped from ❌).** v1 MVP shipped
  end-to-end this batch (documents → solver → resolution → evaluation →
  gateway → viewport, all 6 Ready slices below), golden independently
  geometry-QA'd, e2e green live. Honest residuals, not gating the ➖: only
  lock/coincident/concentric wired (distance/angle schema'd, unimplemented),
  no collision detection, no exploded views, no BOM, no assembly-level STEP
  IO, instances track a part's live tip not a pinned version, sub-assemblies
  rigid-only. See VISION.md row for full evidence chain.
- **Drawings — ❌, now the headline gap** (product audit's honest #2 —
  smaller build than Assemblies, completes the make-loop for the
  already-solid single-part case via STEP-to-shop). Pick up now that
  Assemblies v1 has landed, or sooner if Ready runs dry.
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
dependency chain. **#9 (rate limiting) — F7's unbuilt second half — shipped
2026-07-15** (Redis-backed per-user limiter in py-kit, 429 + Retry-After on
the gateway's OCCT-CPU routes); audit F7 now fully closed.
**Judged OUT of Ready this pass:** F2 (evaluate_tree tessellation churn —
real but low severity/likelihood, stays Next) and F5 (spline epsilon — P3
nit, no user impact, stays Later).

- [x] (P0, L) Viewport makeover Batch 1 — "the scene is a place" (apps/web +
      packages/design) — **DONE 2026-07-16** (founder recalibration, mandate
      3a; spec = UI-REVIEW 2026-07-16 audit). Full-bleed canvas + floating
      collapsible panels; horizon-persistent adaptive grid + brighter grid
      tokens + atmosphere + ground contact pool; procedural token-matcap
      studio shading (no scene lights); reference cube + view rail + numeric
      snaps + fit + zoom-to-cursor; assembly fit keyed on loaded geometry.
      Evidence: `docs/screenshots/viewport-makeover-*`; e2e
      `viewport-makeover.spec.ts`; UI-REVIEW addendum w/ Fusion/Plasticity
      side-by-side. [src: UI-REVIEW full audit, Batch 1]
- [x] (P1, M) Viewport makeover Batch 2 — "every element earns its place" —
      **DONE 2026-07-16.** Deleted the decorative chrome (KERNEL ×2/UNITS ×3/
      TREE/SOLVER cells, header tagline, First-light default chip); folded
      FEATURES/INSTANCES/MATES counts into section eyebrows; ToolButton
      aria-disabled so gated tools show their reason to mouse + keyboard;
      Create/Modify/Inspect + sketch-band group eyebrows (band 32→46);
      wordmark→home + register › document › mode breadcrumb; open-editor band
      lock (no silent pick loss); idempotent sketch exit + fresh-tree naming.
      Evidence `docs/screenshots/makeover-batch2-*`; e2e `nav-chrome.spec.ts`;
      UI-REVIEW Batch-2 addendum. [src: UI-REVIEW 2026-07-16 items 6–9]
- [x] (P1, L) Viewport makeover Batch 3 — "in-command depth" — SHIPPED
      2026-07-16. Item 10: in-command band state (open editor recedes the band
      to the active command + wired OK/Cancel via a command-action bus + a
      per-editor bridge hook). Item 11: body selection/hover feedback + the
      tree→geometry link (hover glows body edges; selecting a feature warms the
      body — brass edges + matcap tint). Item 13 (partial): empty-part first-run
      call to action. Evidence `docs/screenshots/makeover-batch3-*`; e2e
      `makeover-batch3.spec.ts`; UI-REVIEW Batch 3 addendum. [src: UI-REVIEW
      full audit, Batch 3]
- [ ] (P1, M) Viewport makeover Batch 3 remainder / deferred slices —
      per-face pick highlight + tree↔FACE linking (blocked: OverlayResult has no
      face→feature attribution — needs a geometry-service slice attributing
      B-rep faces/edges to their source feature; frontend wires once it exists);
      live ghost previews (item 12 — datum plane cheapest, then extrude/pattern;
      deferred whole to avoid a half-built preview); empty-viewport origin triad
      + resting datum sheets, and parts-home thumbnails (item 13 remainder —
      needs a last-evaluated-mesh snapshot pipeline). [src: UI-REVIEW Batch 3]
      [src: UI-REVIEW 2026-07-16 remediation items 10–13]
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
- [x] (P1, M) Assemblies v1 #2 — `AssemblySolver` core (geometry) — **DONE
      2026-07-15.** The flagged §2.4 risk, landed numeric-only.
      `services/geometry/src/geometry/assembly`: `AssemblySolver` protocol
      mirroring `SketchSolver`; quaternion 6-DOF free instances; a closed-form
      tree fast path (`method="closed_form"`, no iteration for a
      single-parent mate-tree rooted at a grounded instance) + a deterministic
      **numpy-only** damped Levenberg-Marquardt fallback (no GPL, no scipy);
      full diagnosis vocabulary (`well_constrained`/`under_constrained`/
      `over_constrained`-redundant/`conflicting`/`not_converged`, remaining-DOF
      via Jacobian rank, offending/redundant mate ids, `removable`). The
      resolved-geometry seam (`SolverMate.geometry` → `ResolvedFace`/
      `ResolvedAxis` in an instance's local frame) is where #3 plugs in with no
      solver change. 15 synthetic-residual tests (no OCCT): closed-form bolt +
      lock; numeric coupled solve; under-constrained (`remaining_dof=3`, non-
      fatal, seed-consistent); redundant/over-constrained; conflicting + named
      ids; bitwise determinism across runs AND a fresh-interpreter restart
      probe. Full lint/pyright green. [src: design/assemblies.md §2]
- [x] (P1, M) Assemblies v1 #3 — mate-geometry-ref resolution (geometry) —
      **DONE 2026-07-15.** `geometry.assembly.resolve`: `resolve_mate_geometry`
      resolves a `MateFaceRef` via the `on_face` `resolve_face_plane` (centroid
      point + outward `z_dir` normal — the `flush` sign) and a `MateAxisRef`
      (circle) via `resolve_edge` + `BRepAdaptor_Curve`/`gp_Circ` (centre +
      axis), reusing the exact stage-1 signature machinery; every
      stale/ambiguous/wrong-instance/non-circular ref → a clean
      `AssemblyDefinitionError` (chaining the subshape error for #5).
      `build_assembly_solve_input(instances, mates)` assembles the full
      `AssemblySolveInput` (geometry per mate slot, `lock` → None, mates in
      `(order_index, mate_id)` order). Headline test: the first REAL bolted
      solve — two plates each with two holes, coincident + two concentric
      resolved from real OCCT bodies → free plate at the analytic pose
      (`well_constrained`, numeric, ~1e-8); + single-ref, determinism, and
      clean-error tests (11 new, `test_assembly_resolve.py`). Full lint/pyright
      + geometry suite green. [src: design/assemblies.md §2.1, §4]
- [x] (P1, M) Assemblies v1 #4 — gateway assembly endpoints — **DONE
      2026-07-15.** `gateway.assemblies` proxies the documents CRUD (assembly
      create/list/get/update/delete; instance add/update/delete; mate
      add/delete — reorder via instance `order_index`), `gateway.geometry`
      adds `POST /api/v1/geometry/assembly/evaluate` → geometry's
      `/api/v1/assembly/evaluate`. EVERY route `CurrentUser`-gated from day one
      (F7): principal `X-Loft-User` to documents, identity-free hop to geometry.
      Upstream 422 stale / 409 dependents / 404 non-owner envelopes re-surfaced
      verbatim under the gateway request id. Tests: CRUD round-trip
      (create → 2 instances → lock mate → read graph), evaluate proxy returns
      `EvaluateAssemblyResult`, a parametrized 401-per-route (nothing
      forwarded), error re-surfacing. Contracts regenerated (7 gateway paths);
      full lint/pyright + 1122 py + 494 ts tests + gen-check green.
      [src: design/assemblies.md §3]
- [x] (P1, M) Assemblies v1 #5 — assembly evaluation + shared-mesh
      tessellation — **DONE 2026-07-15. "bolt two parts together and see it,"
      the v1 DoD.** `geometry.assembly.evaluate_assembly` +
      `POST /api/v1/assembly/evaluate` (additive `EvaluateAssemblyRequest`/
      `Result`, `EvaluatedInstance`/`Mate`, `InstancePlacementResult`,
      `MateEvaluationError` in `py_kit.schemas.assemblies`;
      `AssemblySolveStatus`/`AssemblySolveDiagnosis` moved to the boundary,
      solver imports them back). Evaluate each UNIQUE part once (dedup by
      `part_key`, reusing `evaluate_tree` → one content-addressed mesh shared
      by all instances), resolve every mate against the real bodies (#3), solve
      (#2) to a solved world `Placement` per instance, analytic combined
      roll-up (Σ volumes, mass-weighted centroid, transformed-bbox union,
      summed topology — no re-meshing, no boolean); solved transform applied at
      RENDER time over the shared mesh. Golden `assembly-two-plates-bolted`
      (§6.1): A grounded, B mated coincident+2×concentric → each solved
      `Placement` == analytic transform within 1e-6 (worst dev 1.2e-8), combined
      props == analytic roll-up, `well_constrained`. Determinism gate byte-
      identical across in-process rebuild + fresh interpreter. Shared-mesh dedup
      + under/conflicting/ungrounded/bodyless-part/unresolvable-mate error tests
      (`test_assembly_evaluate.py`). Full lint/pyright + geometry suite +
      gen-check green. [src: design/assemblies.md §4, §6]
- [x] (P1, M) Assemblies v1 #6 — frontend assembly tree + instance placement
      + mate authoring — **DONE 2026-07-15. Assemblies v1 MVP COMPLETE (all 6).**
      apps/web assembly workspace (`/assemblies` register + `/assemblies/{id}`,
      sibling of the part editor): a Components/Mates title-block tree (drafting
      **balloon** item numbers — the signature device shared by tree + viewport;
      grounded ⏚ anchor), the multi-instance viewport (each unique
      `part_mesh_glb_id` fetched ONCE + parsed once, drawn per instance at its
      solved `Placement` via a scene-frame transform `S·q·S⁻¹`/`occtToScene(t)`),
      mate authoring reusing the face/edge pick overlays (a planar face on each
      of two instances → Coincident, a circular hole edge on each → Concentric,
      two instances → Lock) → POST → re-evaluate → the free part **snaps** from
      seed-apart to the bolted pose (reduced-motion-aware lerp), and the solve
      title block (status + typed DOF diagnosis + combined roll-up). `@loft/design`
      gained an `assembly` token group (references only). `frontend-design` skill
      run. e2e `assembly.spec.ts` (desktop + 1280×800): instance a plate-with-hole
      twice, author coincident+concentric, assert the free instance moved seed→
      solved (bolted) — green live. Full lint + 517 ts + 1122 py tests green;
      founder before/after screenshots under docs/screenshots/. [src:
      design/assemblies.md §4, product-auditor #1]
- [x] (P2, M) Mesh store: MinIO-backed object-storage swap (engineering audit
      **F1/F6**) — **DONE 2026-07-15.** `configure_mesh_store` (wired in
      `build_app`) selects a shared content-addressed `S3MeshStore`
      (`geometry.s3_store`, boto3) when `S3_URL` is set — key stays
      `sha256:<hex>`, object key `meshes/sha256/<hex>.glb`, no tenant scope
      (RESEARCH §5) — and **lifts the single-worker guard** (multi-worker/replica
      now correct); `S3_URL` unset → in-process LRU + guard kept. `EvaluateTreeResult`
      and every caller unchanged. moto `ThreadedMotoServer` (real S3 HTTP)
      proves put/get + content-address + miss→None + idempotent put + config
      selection in `test_s3_store.py`. **Residuals:** the real-MinIO
      cross-process evaluate→fetch smoke is **wired and CI-verified** — the
      `geometry-minio-smoke` job (`66c4011`) boots compose MinIO and runs the
      true second-OS-process round-trip (`LOFT_MINIO_SMOKE=1`); and
      the optional gateway presigned/streamed read (§7.8 default posture) stays
      a separate gateway concern (current geometry-served `/meshes/{id}` route
      is unchanged and correct). [src: engineering-auditor F1/F6]
- [x] (P2, M) STEP import: cache the transferred body across evaluations
      (engineering audit **F8**) — **DONE 2026-07-15.** New
      `geometry.step_cache`: a per-worker bounded LRU (cap 32) keyed on
      `sha256(step_text)` (tenant-free, like the mesh store) storing the
      parsed body as geometry-only BREP bytes; `_evaluate_import` calls
      `import_step_solid_cached` — a HIT re-reads a FRESH shape and SKIPS the
      subprocess, a MISS runs the UNCHANGED bounded/killable/subprocess parse
      and caches only a cleanly-parsed body (a raise is never cached, so the
      timeout re-enforces next attempt). Determinism preserved: BREP re-read is
      byte-identical downstream (`test_hit_is_byte_identical_to_miss`, same
      `mesh_glb_id`), the `import-step-box-10x20x30` golden stays byte-exact.
      One-parse-not-two proven by a counter on the cache module's
      `import_step_solid` (`test_second_evaluation_of_same_import_does_not_reparse`).
      Per-worker is fine post-F6 (each worker warms independently; a hit is
      never a correctness dependency). [src: engineering-auditor F8]
- [x] (P2, M) Rate limiting (py-kit — DRY home) — F7's unbuilt half — **DONE
      2026-07-15.** Shared `py_kit.ratelimit.RateLimiter`: Redis sorted-set
      sliding-window log, atomic per call (one `MULTI`/`EXEC`), **fails open**
      with a logged warning on any Redis error (a limiter must never take the
      API down). Config on the py-kit settings base (`RATE_LIMIT_ENABLED`,
      `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_S`; default **120 req / 60 s**
      per authenticated user — generous for the debounced viewport, low enough
      to stop a hammer loop). Enforced at the gateway on the OCCT-CPU surface
      (tessellate, tessellate/meta, export, evaluate, assembly/evaluate,
      measure, overlay, sketch/*) as a `dependencies=[…]` entry keyed on the
      `CurrentUser` id — no OpenAPI/contract move (gen-check clean). On exceed:
      429 `rate_limited` envelope + `Retry-After`, nothing forwarded upstream.
      New dep `redis>=5` (MIT), already transitive via arq. Tested (py-kit unit
      + gateway integration, hermetic in-memory fake Redis + injected clock):
      under/over limit, 429 + Retry-After, window reset, per-user + per-scope
      isolation, denied-request-frees-no-slot, fail-open on outage, anon 401
      before the limiter. Residual (Next): a generic request-**body-size** cap
      beyond the existing STEP-import + password caps. [src: code-reviewer,
      eng-audit F7]

## Next (P2)

- [ ] (P2, M) Datum-plane completeness (founder ask 2026-07-16: "do we have
      planes, offset planes, midpoint planes etc") — **backend slice ✅
      2026-07-16**: **midplane** (`kind: "midplane"` — each side an origin
      plane, an earlier datum, or a picked planar face; documented
      parallel/bisector/normal-sign conventions, datum-planes §7a) and
      **offset chaining** (`kind: "offset_from"` — base is a FeatureRef to an
      earlier datum; a SEPARATE additive kind rather than widening
      `DatumOffsetParams.base`, keeping the generated client type of existing
      offset datums untouched) shipped with golden
      `midplane-chained-offset-40x25x10`, kernel/evaluator/schema suites,
      self/forward-ref safety, contracts regenerated. **Remaining:** angled
      plane (about an edge/sketch line), three-point, tangent-to-cylinder,
      normal-to-curve — each a future additive kind — plus the
      midplane/chaining **authoring UI** (queued behind the viewport-makeover
      batches; the plane picker + DatumEditor gain the new kinds then).
      [src: founder]
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

- 2026-07-16 — **Datum-planes backend slice done:** midplane + offset-chaining
  as additive kinds (`midplane`, `offset_from`), documented conventions, golden
  `midplane-chained-offset-40x25x10`, contracts regen. [kernel-architect]

- 2026-07-15 — **Mesh-store MinIO/S3 swap done (F6/F1):** `S3_URL`-driven shared
  `S3MeshStore` (boto3, content-addressed, no tenant), single-worker guard
  lifted when S3 configured; moto HTTP round-trip verifies put/get, real-MinIO
  2-worker smoke CI-gated. [kernel-architect]
- 2026-07-15 — **Assemblies v1 #6 done → v1 MVP COMPLETE (all 6):** apps/web
  assembly workspace + multi-instance viewport (dedup shared mesh + solved
  transform) + mate authoring + snap-on-solve + solve readout; `assembly.spec.ts`
  green live, founder before/after shots. [frontend-builder]
- 2026-07-15 — Assemblies v1 #4 done: gateway assembly CRUD + evaluate
  proxies, every route `CurrentUser`-gated (F7); contracts regenerated.
  [backend-builder]
- 2026-07-15 — Phase 2→3 reconcile: Phase 2 converged (Sketching + Part
  modeling ✅), 9 shipped items archived. **Assemblies sequenced into 6
  Ready items** (`docs/design/assemblies.md`); interleaved F1/F6/F8/F7-rate-
  limit debt as #7–#9; bumped multi-body boolean P3→P2. [backlog-groomer]
