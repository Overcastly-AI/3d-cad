# Design — Multi-body modeling + booleans between independently-built bodies

Status: **accepted** (2026-07-18). Closes the one named Part-modeling gap
(VISION scorecard: "no booleans between independently-built bodies — a part
that is genuinely multiple lumps combined can't be built"). Grounded in the
current single-connected-solid pipeline (`services/geometry/.../features/
evaluate.py` `EvaluationState.body`, `kernel/extrude.py` `combine_body`).

## What exists today (grounded)

- **One running solid.** `EvaluationState.body: Solid | None` — a single slot;
  every body-affecting handler reads/writes it. The tree is *implicitly one body*.
- **Booleans already ship + are license-clean.** `combine_body` uses `body.fuse`/
  `body.cut` (build123d → OCCT `BRepAlgoAPI_Fuse`/`Cut`; OCCT is LGPL, already
  the kernel) and **raises `BooleanError` on a ≠1-solid result** — the exact guard
  multi-body relaxes *per body*.
- **Tessellation/stats/roll-up already multi-mesh.** `glb_stats` sums over meshes;
  the assembly path has an analytic `_combine_properties` roll-up to reuse.
- **Stage-1 topo-naming is geometry-only, best-effort.** `PlanarFaceSignature`/
  `EdgeSignature` from whatever body exists; stage-2 provenance (`Modified/
  Generated/IsDeleted`) is designed but unbuilt. A boolean seam/merge is the
  documented `subshape_ambiguous` source (`topological-naming.md` §2c).

## Decisions

**1. Body model — Option A: an eval-time partition keyed by the base feature's id.**
No Body table, no per-feature `body_id` column (reject Option B's migration + CRUD +
snapshot/undo blast radius). No pure connectivity partition (reject Option C —
non-deterministic "which body does fillet target", no stable naming anchor). A
body's identity *is* its base-feature id — the concept `SubshapeRef` already uses.
Internal eval-state change only:
```
bodies: dict[uuid.UUID, Solid]   # base-feature-id -> current solid, tree-ordered
active_body_id: uuid.UUID | None
```
Body-creating features (base extrude/revolve/sweep/loft/import) insert + activate;
modifying features (fillet/chamfer/shell/draft/pattern, add/cut) act on the ACTIVE
body. **Load-bearing correctness rule:** a modifying feature's topo-naming resolves
against `state.bodies[active_body_id]`, NEVER a union of all bodies — else a
congruent face on two bodies falsely ties `subshape_ambiguous`. Assert in a test.

**2. Starting a second body — an additive `merge: bool = True` flag** on add
extrude/revolve/sweep/loft (SolidWorks/Fusion "Merge result"). `True` = fuse into
active (today's behavior); `False` = start a new active body. Reads `True` for legacy
rows → **no `param_version` bump** (same idiom as `flip`/`direction`). `import` starts
a new body instead of erroring `import_with_prior_body`.

**3. The `boolean` feature.**
```python
class BooleanParamsV1(BaseModel):
    operation: Literal["union", "subtract", "intersect"]
    target: FeatureRef   # base feature of the SURVIVING body (subtract: minuend)
    tool:   FeatureRef   # base feature of the CONSUMED body   (subtract: subtrahend)
```
Operands are `FeatureRef`s to each body's base feature (→ `feature_dependencies`
edges → delete/reorder safety, generic documents validation, no documents code
change). OCCT `fuse`/`cut`/`intersect` (add `.intersect()` = `BRepAlgoAPI_Common`).
The result **replaces both operands, taking over the target's identity slot** (keeps
target's base-feature id so downstream refs resolve) and removes the tool body; the
boolean becomes active. v1 keeps the single-connected-solid-per-body invariant:
disjoint union / severing subtract → `boolean_disjoint`; empty intersect →
`boolean_empty` (multi-lump compound bodies deferred).

**4. Topo-naming across a boolean — ships stage-1, honest limit.** Boolean-result
faces/edges get signatures like any primitive; a downstream fillet on a boolean edge
resolves to one edge on a **clean rebuild**. Under a topology-changing upstream edit
it degrades to `subshape_unresolved`/`subshape_ambiguous` — the SAME documented
best-effort posture as every feature, booleans being its weakest case. Do NOT block
booleans on stage-2; document the degrade-under-edit limit; that's why
downstream-feature-on-a-boolean-face is the LAST slice.

## Blast radius (real touch-points)

`evaluate.py` state + every handler (mechanical swap to active body); new kernel
`boolean_bodies(target, tool, op)` + `boolean_disjoint/empty` taxonomy; part
mass-props = analytic combine over the body set (reuse assembly `_combine_properties`,
no re-mesh); tessellation/export widen `Solid → Shape/Compound` (deterministic
base-`order_index` order; STEP multi-solid is valid AP214); **the assembly evaluator's
mate resolvers must accept a Compound** (the sneaky ripple — miss it and mate
resolution breaks silently); frontend adds a Bodies panel + boolean authoring UI +
the `merge` checkbox (basic multi-body render is nearly free through the existing
combined-GLB path).

## Golden gate + determinism

Same-commit goldens (geometry-gates rule): **union two 20mm cubes overlapping 10mm =
12000 mm³** (8000+8000−4000), `shells=1`; subtract analytic; **intersect = 4000 mm³**;
Slice-0 **two disjoint boxes = 16000 mm³, shells=2** (de-risks roll-up/tess/export
before any boolean). Bodies tree-ordered; compound assembled in fixed order; boolean
is a pure OCCT function; byte-identical GLB+STEP across interpreter restarts;
`subshape_ambiguous` deterministic (not a coin flip) on a seam.

## Slice sequence

- **MB-0 — SHIPPED 2026-07-18.** Multi-body plumbing, no user-visible boolean:
  `EvaluationState.bodies` (base-feature-keyed, tree-ordered) + `active_body_id`;
  the additive `merge: bool = True` flag on extrude/revolve/sweep/loft ADD
  (`merge=False` starts a new active body; `import` starts a second body,
  retiring `import_with_prior_body`); analytic compound roll-up
  (`geometry.kernel.properties.combine_properties`) + `Compound` tessellation/
  export (STEP multi-solid); the face/edge/tessellate/export AND assembly-mate
  resolvers widened `Solid`→`BodyShape` (`geometry.kernel.types.BodyShape =
  Solid | Compound`, incl. the assembly mate path — the flagged sneaky ripple);
  body-scoped resolution (a modifying feature resolves against `bodies[
  active_body_id]` only). Golden `multibody-two-disjoint-boxes` (16000 mm³,
  shells=2, byte-identical GLB+STEP across restart). Single-body goldens stay
  byte-identical (one-entry `bodies` measured/tessellated as the bare solid).
- **MB-1** — the headline `union` feature + overlapping-cubes golden + `boolean_disjoint`;
  frontend boolean authoring UI + Bodies panel + `merge` checkbox.
- **MB-2** — `subtract` + `intersect` + analytic goldens + the error taxonomy.
- **MB-3 — SHIPPED 2026-07-18 (backend).** Downstream fillet/chamfer on a
  boolean-CREATED edge. **The claim, proven:** the fused body's edges get stage-1
  `EdgeSignature`s exactly like a primitive's, so a fillet naming a boolean-result
  edge (a picked-edge `SubshapeRef`) resolves to EXACTLY ONE edge on a clean
  rebuild — golden `boolean-union-then-fillet` (union two 20mm cubes → the fused
  30×20×20 box → fillet r=2 a picked vertical corner edge = 11920 + 20π mm³,
  7 faces / 15 edges / 1 shell, byte-identical GLB+STEP across an interpreter
  restart). **The honest degrade-under-edit limit (observed 2026-07-18):** a
  topology-CHANGING upstream edit that moves/removes the referenced edge degrades
  to a CLEAN typed `subshape_unresolved` (verified: moving cube B to x[-5,15] so
  it swallows the picked x=0,y=0 corner → the corner becomes interior → the
  picked outer edge no longer exists → `subshape_unresolved`), never a wrong-edge
  fillet or a crash. An edit that does NOT touch the picked edge (e.g. moving B to
  x[5,25]) still resolves `ok` — the signature is not brittle to every change,
  only to ones that move/remove the edge. This is the SAME best-effort stage-1
  posture as every feature (topological-naming.md §7.3), booleans being its
  weakest case (a boolean seam is the documented `subshape_ambiguous` source); the
  structural fix is stage-2 provenance naming (§10 there), NOT this slice.
  **Body-scoped (§MB-0 Decision 1):** the fillet resolves against the SINGLE
  post-boolean active body — the consumed tool body is gone from `bodies`, so no
  ghost of it can tie a false `subshape_ambiguous`. Documented in the
  `BooleanParamsV1` v1-limits docstring. **This closes the multi-body pillar v1
  through MB-3.**
- **MB-4 — ACCEPTED 2026-07-18 (design).** Multi-lump bodies + multi-solid STEP
  import. **Headline: the READ side already works** — MB-0 widened every resolver/
  measurer/exporter/mate path to `BodyShape`, and `faces()`/`edges()` traverse all
  lumps of a Compound; signatures are absolute-world-coordinate so lump 2's edge has
  a distinct signature and resolves to exactly one edge. The genuine work is the
  WRITE side + relaxing two guards.
  - **Body model:** a multi-lump body is ONE `bodies` entry whose value is a
    `Compound` of disjoint solids — widen `EvaluationState.bodies: dict[UUID,
    BodyShape]` (the MB-1a code-review 🟢). NOT N entries (identity = base-feature
    id; a disjoint union / a multi-solid import each have ONE surviving id, and must
    read as ONE Bodies-panel row).
  - **Modifying kernel ops** (fillet/chamfer/shell/draft/pattern, `combine_body`'s
    active side): relax the `.solids() == 1` assertion to **lump-count-preserving
    `== k`** (`k = len(input.solids())`) — a fillet on one lump of a k-lump body
    keeps k lumps; a merge/sever is still a typed failure. **k=1 is byte-identical
    to today** (every single-body golden unchanged). Widen their `Solid` params to
    `BodyShape`. `combine_body`'s in-chain merge stays one-lump (the `merge=False`
    seam is how you start a second body).
  - **Disjoint union is OPT-IN:** `allow_disjoint: bool = False` on `BooleanParamsV1`
    (reads `False` for legacy → NO `param_version` bump). Default keeps
    `boolean_disjoint` as an error (a disjoint union is usually a positioning bug —
    safety). When set, `boolean_bodies` returns a lump-sorted `Compound` on `>1`
    solids instead of raising. Empty results stay `boolean_empty`/`BooleanError`.
    **All existing boolean goldens stay byte-identical** — they union/subtract
    TOUCHING bodies (→ 1 solid), never reaching the relaxed branch, and none sets
    the flag (assert in the slice).
  - **Multi-solid STEP import → ONE multi-lump body** (a `Compound`), not N bodies
    (one import-feature id). `import_step_solid` returns `BodyShape`: a bare `Solid`
    when `solids == 1` (existing `import-step-box-10x20x30` golden byte-identical —
    do NOT wrap a lone solid), else a lump-sorted `Compound`. Retire
    `ImportNotSingleSolidError`'s "not single" meaning → reject only 0 solids (rename
    → `import_no_solid`; ripples py-kit → ts-client → `featureErrors.ts`). Widen
    `step_cache` (`solid_to/from_brep_bytes`). Splitting a multi-lump body into
    independent bodies is a later "split bodies" feature.
  - **Determinism — the one new knob:** an EXPLICIT lump sort (centroid x,y,z then
    volume) when assembling ANY multi-lump `Compound` (boolean result + import) —
    don't trust OCCT traversal order. Flatten the part roll-up
    (`Compound([s for b in bodies for s in b.solids()])`) to avoid nested Compounds.
  - **Goldens (same commit):** `boolean-union-two-disjoint-cubes` (two non-touching
    20mm cubes, `allow_disjoint` → ONE multi-lump body, 16000 mm³, shells=2 — same
    analytic numbers as the MB-0 `multibody-two-disjoint-boxes`, but ONE body via a
    boolean); a fillet-on-lump-2 golden (cross-lump naming proof); a 2-solid STEP
    import round-trip (`test_step_roundtrip` already handles multi-solid re-import).
  - **Sequence:** MB-4a (multi-lump body support + relaxed guards + disjoint-union
    golden, backend) → MB-4b (multi-solid STEP import) → MB-4c (frontend
    `allow_disjoint` checkbox + error-code map). Per-lump pick/highlight is the
    deferred tail.
  - **Risks:** the lump-count guard (capture `k` from the INPUT body — a wrong guard
    crashes legit ops or silently accepts a merge; shell especially); nested
    Compounds if the roll-up isn't flattened; lump-order determinism (the explicit
    sort); the import error-code rename ripple; a mate-against-a-multi-lump-face
    regression check (the historically silent path); coincident-lump
    `subshape_ambiguous` (honest — document in the v1-limits docstring).

## Risks (flagged)

`TreeEvaluation.body` type change rippling to the assembly mate resolvers (silent break
if missed); cross-body ambiguity if any resolver runs against a merged all-bodies shape
(must assert body-scoped); stage-1 naming degradation on boolean seams (honest,
stage-2 territory); disjoint-union deferral is a real authoring limit (name it in the
feature's v1-limits docstring).
