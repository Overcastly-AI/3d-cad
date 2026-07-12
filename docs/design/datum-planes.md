# Offset / Datum-Plane Representation — Design

Status: **BACKEND IMPLEMENTED** 2026-07-12 (offset slice: DTOs, kernel,
documents, goldens — see GEOMETRY-QA; plane-picker UI #2b is the follow-up).
The **v2 on-a-face variant (§7) is ALSO backend-implemented** 2026-07-12 (the
`on_face` datum params variant carrying a face `SubshapeRef`, resolved to the
face's plane — stage-1 topological naming; see `docs/design/topological-naming.md`
§9 and GEOMETRY-QA; the in-viewport face picker is its follow-up UI). Purely
additive — no `param_version` change, no migration (the datum params union
reads legacy kind-less rows as `offset` via a before-validator).
Scope: how an **offset (parallel) datum plane** enters the architecture so a
sketch can sit somewhere other than the three origin datum planes, and so the
follow-up implementation item ("Offset/datum planes — implementation",
BACKLOG Ready #2) is unambiguous.

Related: [`docs/design/feature-tree.md`](./feature-tree.md) §1.3–1.4 (versioned
param envelopes + upcast registry), §2.1–2.3 (the `GeomRef` vocabulary,
reference-validity rules, materialized `feature_dependencies`), §3 (rollback),
§4.3 (strict-prefix failure); [`docs/design/topological-naming.md`](./topological-naming.md)
(the `SubshapeRef` the v2 on-a-face plane will consume); RESEARCH §9
(determinism + golden gates). This is deliberately a *smaller* design than
topological naming — offset-from-a-stable-origin-datum needs **no** naming
layer — but it is the single highest-leverage foundational unlock, so it gets
a note first per the CLAUDE.md "hard problems get a design doc" discipline
applied to the document/kernel contract.

**What this unblocks (the dependency chain the implementer + groomer should
see):**

- **#8b loft UI** — a real loft needs two or more **parallel** sections at
  different heights; today the only planes are the three mutually-perpendicular
  origin datums, so loft shipped backend-only and its golden had to fall back
  to loft-to-apex (a cone) for lack of a second parallel plane
  (`LoftParamsV1` docstring, GEOMETRY-QA 2026-07-12). Offset planes make the
  two-parallel-circles → frustum golden authorable.
- **sketch-at-a-height** — the everyday "sketch on a face 10 mm above the
  base" gesture, in its face-free form (offset from an origin datum).
- **prerequisite for sketch-on-a-face** (v2) — that feature is *the same datum
  node* carrying a face reference instead of an offset (§7); designing the
  datum node now is what makes the on-face increment additive later.

---

## 1. The gap, concretely

Two hard-coded assumptions, one on each side of the boundary, restrict every
sketch to the three origin datum planes:

- **Frontend** — `apps/web/src/sketch/plane.ts` defines
  `DATUM_PLANES = ["XY","XZ","YZ"]` and `PLANE_BASES` with each plane's origin
  implicitly at the world origin (`planeToWorld` is `u*x + v*y`, no origin
  term). The pointer raycast, entity renderers, and camera rig all read that
  origin-anchored basis, so there is no way to draw or pick on a plane that
  is not through `[0,0,0]`.
- **Geometry** — `services/geometry/src/geometry/features/evaluate.py`
  `_evaluate_sketch` (lines ~171–184) resolves `SketchParamsV1.plane` and, if
  it is a `FeatureRef` rather than a `DatumPlaneRef`, returns
  `reference_unresolved` outright ("Sketch planes must be datum planes
  (XY/XZ/YZ) in v1"). The kernel plane mapping
  (`geometry.kernel.extrude`: `DATUM_PLANES`, `plane_point_to_world`,
  `build_profile_face`, `entity_edges`) is keyed by the plane-*name* literal
  `"XY"|"XZ"|"YZ"` and only ever uses `Plane.XY/.XZ/.YZ` — all with origin at
  `[0,0,0]`.

The `GeomRef` union (`py_kit.schemas.features`) already anticipates more than
origin datums — it is `Annotated[DatumPlaneRef | FeatureRef, …]`, and the
`FeatureRef` variant is *present but rejected* in the plane slot
(`feature_references()` maps a sketch-plane `FeatureRef` to `frozenset()` = no
acceptable target type). The schema left the door open; this design walks
through it.

---

## 2. Decision 1 — datum plane is a first-class FEATURE, not an inline spec

Two ways to represent an offset plane:

### 2a. Inline plane-spec on the sketch (rejected)

Add an `OffsetPlaneRef` variant to `GeomRef` (or fields to `DatumPlaneRef`)
carrying `{base, offset_mm, flip}` **inline on the sketch's `plane` field**. No
new feature, no new tree node.

- **For:** simplest possible change for a single sketch — one union member,
  one resolver branch, no CRUD surface, no dependency edge.
- **Against — it does not compose, and composition is the whole point:**
  - Two sketches that should share a plane must **duplicate** the spec; edit
    the height once and you edit it in N places (a WET defect by the CLAUDE.md
    DRY rule, applied to the document model).
  - The plane is not an addressable *thing*: nothing else in the tree can
    reference it (a future section plane, a mirror-about-a-plane 3D feature, a
    second sketch), because it has no id.
  - **The v2 on-a-face plane would need a *second*, parallel mechanism** — an
    inline face `SubshapeRef` on the sketch — rather than reusing one node.
    That is exactly the kind of divergence that sinks a schema.

### 2b. Datum plane as a feature (chosen)

A datum plane is a **feature** with its own type (`"datum"`), id, `order_index`,
name ("Plane1"), and versioned params. It is evaluated in tree order like any
feature, produces a **plane** (not a solid — it is not body-affecting, exactly
like a sketch), and a sketch references it through the **existing `FeatureRef`
variant of `GeomRef`** — the identical mechanism extrude/revolve/sweep/loft
already use to point `profile`/`path`/`profiles` at an earlier sketch.

- **Reuses what exists.** `FeatureRef` is already a `GeomRef` member and
  already in the sketch `plane` slot; the strict-backward reference rule
  (feature-tree §2.2), the materialized `feature_dependencies` edge (§2.3), the
  409-with-dependents delete guard, reorder re-checks, and rollback all apply
  **for free** — a datum plane is just another node in the graph they already
  police.
- **Everything is a tree node.** The plane is inspectable, renameable,
  reorderable (subject to strict-backward), deletable (protected by dependents),
  and roll-back-past — the behaviour a working engineer expects from every
  production CAD's datum/construction/reference plane (Onshape, Fusion,
  SolidWorks all model user planes as history features; the three origin planes
  are implicit, §4).
- **DRY at the model level.** N sketches share one datum feature by id; move the
  plane once, every sketch on it moves. No duplication.
- **The v2 on-a-face plane is the same node.** On-a-face is a *different params
  variant of the same `datum` feature* (an `on_face` variant carrying a face
  `SubshapeRef`), and the sketch still references it by the same `FeatureRef`.
  v1 and v2 share the datum node; only the datum's own params differ (§7). This
  is the decisive argument — it makes the hard v2 feature an additive params
  variant instead of a new mechanism.

**Tradeoff, stated honestly:** 2b adds a feature type and a small
CRUD/UX surface (author-or-select a plane, then sketch — §8), where 2a would let
a sketch carry its plane inline in one step. We pay that one-time cost to buy
composition, DRY, and an additive v2 path. **Recommend 2b.** The cost is a UX
step, not a modeling limitation; the benefit is structural.

---

## 3. Decision 2 — v1 plane representation: offset-from-origin-datum

The `datum` feature's v1 params are a **signed offset of an origin datum along
its own normal**, plus an optional normal flip:

```python
class DatumParamsV1(BaseModel):
    """A datum plane parallel to an origin datum, offset along its normal.

    v1 is the face-free slice (docs/design/datum-planes.md §3): `base` is one of
    the three stable origin datums, `offset_mm` slides the plane along that
    datum's normal, and `flip` optionally reverses the normal. No picked
    geometry, no reference to another feature's output — so this is independent
    of topological naming (#1), exactly like revolve's world-axis or a pattern's
    world-vector.
    """

    base: Literal["XY", "XZ", "YZ"] = Field(
        description="Origin datum this plane is parallel to (its orientation)."
    )
    offset_mm: float = Field(
        allow_inf_nan=False,
        description="Signed distance along `base`'s normal (mm). 0 coincides "
        "with the origin datum; +/- selects side. Any finite value is valid.",
    )
    flip: bool = Field(
        default=False,
        description="Reverse the plane normal (negate z_dir, keeping x_dir so "
        "sketch +u is unchanged and +v flips). Additive-optional; absent reads "
        "as False. Position is fully covered by signed `offset_mm`; `flip` only "
        "chooses which way 'normal' points for authoring/extrude-side.",
    )


class DatumFeature(BaseModel):
    """`{"type": "datum", "version": 1, "params": {...}}` envelope."""

    type: Literal["datum"]
    version: Literal[1]
    params: DatumParamsV1
```

`DatumFeature` joins the `Feature` discriminated union and registers in
`FEATURE_REGISTRY` at v1 — additive, exactly as `sweep`/`loft`/`pattern` did
(feature-tree §1.4). Final field/type names are the #2 implementer's to fix;
the shape above is what they implement against.

### 3a. Kernel mapping — one resolved `Plane`, one shared helper

build123d's `Plane` is offset along its own normal by `Plane.offset(amount)`
(shifts `origin` by `z_dir * amount`, preserving `x_dir`/`z_dir`). The v1 datum
resolves to:

```
plane = DATUM_PLANES[base].offset(offset_mm)          # origin datum, slid along normal
if flip:  plane = Plane(origin=plane.origin, x_dir=plane.x_dir, z_dir=-plane.z_dir)
```

The load-bearing kernel change: **the plane threaded to the profile/path
builders becomes a resolved `build123d.Plane`, not a `Literal["XY","XZ","YZ"]`
name.** Today `state.sketch_planes` holds a `DatumPlaneRef` and callers pass
`plane.plane` (the name) into `build_profile_face(plane_name, …)`,
`plane_point_to_world(plane_name, …)`, revolve's axis mapping, and loft's
section builder. Going forward:

- A single `resolve_sketch_plane(ref, state) -> Plane` helper maps **either**
  an origin `DatumPlaneRef` (name → `DATUM_PLANES[name]`) **or** a `FeatureRef`
  to a datum feature (look up its resolved `Plane` in evaluation state) to one
  concrete `Plane`. This is the DRY funnel: the name→Plane lookup moves *up*
  into the resolver, and every downstream builder takes a `Plane`.
- `build_profile_face`, `entity_edges`, `plane_point_to_world`, the revolve
  axis mapping, and the loft section builder switch their public signature from
  the name literal to a `Plane`. Their *internals* barely change —
  `entity_edges`/`_to_world` already operate on a `Plane` object; only the
  public entry points that currently accept the name are generalized. No
  behavioural change for origin datums: `DATUM_PLANES["XY"]` is `Plane.XY` with
  origin `[0,0,0]`, so an existing sketch resolves to the identical `Plane` and
  extrudes to the byte-identical body (§4, §11.2).

**No topological naming, confirmed.** `base` is a constant origin frame and
`offset_mm`/`flip` are scalars — nothing is picked off a rebuilt body, so there
is no subshape to name and no `SubshapeRef`. An offset datum survives rebuilds
because it is a pure function of `(base, offset_mm, flip)`, the same way
`axis_parallel` edge selection survives without a name map (feature-tree §2.4).

### 3b. v1 has no degenerate/rebuild-error mode of its own

A plane offset any **finite** distance along its normal is still a valid plane;
`offset_mm = 0` is just the origin datum; `flip` cannot degenerate it. So —
unlike revolve (axis-intersects-profile), loft (incompatible sections), or a
boolean (disjoint result) — **the v1 datum feature is total: given valid params
it always evaluates `ok`.** Its only invalid input is a non-finite `offset_mm`,
rejected at parse time by `allow_inf_nan=False` as a clean 422 (never a rebuild
error, never a 500). Every *other* failure around a datum plane is a
*downstream* reference-resolution error owned by the sketch, not the datum
(§6). This is a v1 robustness win worth stating plainly.

---

## 4. Decision 3 — how a sketch names its plane, and the backward-compat upcast

`SketchParamsV1.plane` stays `GeomRef` — the union is **unchanged on the wire**.
The two variants split cleanly by role:

- **`DatumPlaneRef` (`kind: "datum_plane"`, `plane: XY|XZ|YZ`) — the three
  origin datums, unchanged.** These are the implicit world frame, always
  present, not user-created (mirroring how Onshape's Top/Front/Right are
  implicit, not tree features). Every existing sketch — every persisted
  `{"kind":"datum_plane","plane":"XY"}` — parses and evaluates **byte-identically**
  after this change. That is the backward-compatibility guarantee, and §3a's
  identical-`Plane` resolution is what makes it hold at the geometry level too.
- **`FeatureRef` (`kind: "feature"`, `feature_id`) — now accepted when it
  resolves to a `datum` feature.** Today this variant is rejected in the plane
  slot; going forward it is the way a sketch sits on a user-authored plane.

**The change is purely additive — no `param_version` bump for sketch.** The
`GeomRef` union already contains `FeatureRef`; we are **widening the set of
accepted `FeatureRef` targets** (from none to `{datum}`), not changing the
stored shape. Concretely, the *reference-graph* delta is three edits, none of
which touches the wire format (NB — these three are only the reference-graph
change; the FULL implementation also includes the `DatumParamsV1`/`DatumFeature`
DTOs (§3), the `_evaluate_datum` handler + `assert_never` `case DatumFeature()`
arm, the `resolve_sketch_plane` kernel refactor to a resolved `Plane` (§3a/§11.3),
and the two goldens + determinism gates (§5/§9/§11.2) — implemented 2026-07-12,
see GEOMETRY-QA):

1. **`feature_references()` SketchFeature case:** the sketch-plane `FeatureRef`
   slot rule changes `frozenset()` → `frozenset({"datum"})`. That is the entire
   write-time acceptance change — documents' §2.2 rule-3 check then permits a
   plane `FeatureRef` iff it points at a `datum` feature.
2. **`_evaluate_sketch` (geometry):** replace the blanket
   `isinstance(plane, FeatureRef) → reference_unresolved` rejection with
   resolution against the datum planes evaluated earlier in the prefix
   (§6 spells the error paths).
3. **New `datum` feature type** registered in `FEATURE_REGISTRY` at v1
   (additive `Feature` union member).

**Notably cleaner than the topological-naming migration.** That design had to
*widen* `iter_feature_refs` and the `FeatureReference.ref` type and keep the
`walked == mapped` self-check in sync (topo-naming §4). Here, `iter_feature_refs`
**already** yields the sketch-plane `FeatureRef` (the generic pydantic walk has
always reached it), and `feature_references()` **already** emits it as a slot —
only the slot's `allowed_types` changes. So `walked == mapped` still balances
with no code change; we are toggling an acceptance set, not teaching the walker
a new ref kind.

**No sketch upcast function is needed:** the stored sketch params do not change
shape, so there is nothing to upcast (the identity holds trivially, totality is
preserved — feature-tree §1.4). The `datum` feature is new, so it has no prior
version and no upcast either. Bulk data migration: none.

---

## 5. Feature-tree integration

The datum node slots into the existing graph machinery:

- **Dependency edges.** `DatumParamsV1` (offset-from-origin) carries **no
  `FeatureRef`** — `base` is an origin-datum enum, `offset_mm`/`flip` are
  scalars — so a datum feature materializes **no** `feature_dependencies` row
  and depends only on the implicit origin frame (like a fillet depends on the
  prior body only by tree order). The **sketch→datum** edge *is* materialized,
  because the sketch's plane is now an accepted `FeatureRef`: deleting a datum
  with sketches on it is a write-time **409-with-dependents** (feature-tree
  §2.3), and a reorder re-checks strict-backward for that edge.
- **Strict-backward / evaluation order.** A datum must be **strictly earlier**
  than any sketch that uses it (feature-tree §2.2 rule 2), enforced at write
  and reorder. Evaluation stays a single forward pass: the datum handler runs
  before the sketch handler and records the resolved `Plane`, so the sketch
  always finds it. No cycles possible by construction.
- **Rollback.** Rolling the bar before a datum simply omits it from the prefix
  documents sends (feature-tree §3/§4.2); a sketch that referenced it then
  fails to resolve exactly like any dropped upstream reference (§6) — the
  strict-prefix rule already handles this.
- **Determinism.** Resolution is a pure function of `(base, offset_mm, flip)`;
  no dict/set iteration order participates (the datum registry entry is
  consulted by key, like every other handler). Same tree → identical resolved
  planes → identical bodies and mass properties (RESEARCH §9).

---

## 6. Error paths + evaluation semantics

All paths are per-feature rebuild errors or write-time 4xx envelopes — **never
a 500** (feature-tree §4.3). The pattern mirrors `_resolve_profile_face`:

- **Datum referenced before it is defined.** Forbidden at write time by the
  strict-backward rule (422 on the sketch write / reorder). Eval-time backstop:
  the sketch's plane lookup misses → **`reference_unresolved`** `FeatureError`
  on the *sketch* feature, `upstream_feature_id` = the datum's id. Strict-prefix
  then skips everything after the sketch and tessellates the last-good body.
- **Sketch on a deleted plane.** Deleting a referenced datum is a write-time
  **409-with-dependents** (feature-tree §2.3) — the user is stopped before
  evaluation and told which sketches depend on it. If a code path ever slips
  the pre-check, the eval-time backstop is the same `reference_unresolved` on
  the sketch (the datum id no longer resolves).
- **Sketch on a rolled-back plane.** The datum is simply absent from the sent
  prefix; the sketch's plane `FeatureRef` resolves to nothing →
  `reference_unresolved` on the sketch, `upstream_feature_id` = datum id. Same
  code path as the previous two — one honest error, deterministic.
- **`FeatureRef` that resolves to a non-datum feature** (e.g. a sketch pointed
  at an extrude). Rejected at write time by the widened §2.2 rule-3 check
  (`allowed_types={"datum"}`); eval-time backstop is `reference_unresolved`.
- **Zero/degenerate plane.** Cannot occur in v1 (§3b): a finite offset of an
  origin datum is always a valid plane. A non-finite `offset_mm` is a parse-time
  422 (`allow_inf_nan=False`), not a rebuild error. The datum feature itself
  therefore never carries an `error` status in v1.

New machine codes are unnecessary — `reference_unresolved` already covers every
sketch-side failure and is what `_evaluate_sketch`/`_resolve_profile_face`
emit today. (Consistency: the sketch is the feature that fails, because it is
the one that could not obtain a plane; the datum, being total, does not fail.)

---

## 7. The v1 / v2 line — deferred, named not designed

**v1 (this design + the #2 implementation):** offset-from-an-origin-datum by a
signed distance, plus optional normal flip. Nothing picked, no reference to
another feature's output. Total and naming-free.

**v2 (named here so the #2 implementer does not over-build; each is a future
additive params variant of the *same* `datum` feature type):**

- **On-a-face plane. — BACKEND IMPLEMENTED 2026-07-12.** A `datum` params
  variant (`kind: "on_face"`) carrying a face **`SubshapeRef`**
  (topological-naming design, stage-1 planar-face signature) + an optional
  offset along the face normal. The **backend/schema** landed ahead of the
  picker (the `SubshapeRef` signature is authorable directly / from the
  `/overlay` face list); the **in-viewport face picker** that produces the
  `SubshapeRef` from a click is the remaining UI slice (BACKLOG #1 UI leg). This
  variant materializes a `feature_dependencies` edge to the body feature whose
  face it names, as designed. It landed exactly as an **additive variant of this
  datum node**, not a new mechanism — the decisive §2b/§7 argument, now proven.
  See `docs/design/topological-naming.md` §9 + GEOMETRY-QA (golden
  `boss-on-face-40x40x10-20x20x10`).
- **Angled / 3-point plane.** A plane through three picked points/vertices, or
  at an angle to a base plane about a picked edge. Needs vertex/edge picking
  (topological naming) for its anchors. Deferred.
- **Plane offset from another datum (chaining).** `base` becomes a union of the
  origin-datum enum **or** a `FeatureRef` to another datum feature, so planes
  stack. A small additive increment (the resolver would look up the parent
  datum's resolved `Plane` instead of `DATUM_PLANES[name]`; strict-backward
  already guarantees the parent evaluates first), but **not needed for the
  loft/height unlock**, so held to v2 to keep the v1 line clean.

The line, stated as a rule: **anything that requires picking a face/edge/vertex,
or referencing another feature's output, is v2.** v1 is offset from a stable
origin frame by a scalar — and nothing more.

---

## 8. UI implication (brief — enough to scope #2 + the eventual UI)

`apps/web/src/sketch/plane.ts` and the plane-pick flow become:

- **`DATUM_PLANES = ["XY","XZ","YZ"]` stays** — but as the list of *origin*
  datums (the always-present base orientations), not the list of everything a
  sketch may sit on. The set of sketchable planes is now "the three origin
  datums **plus** any `datum` feature in the tree".
- **`PLANE_BASES` gains an origin term.** An offset datum has the *same*
  `u`/`v`/`normal` as its base but `origin = base_normal * offset_mm` (and
  `flip` negates `normal` and `v`). `planeToWorld` becomes `origin + u*x + v*y`;
  `worldToPlane`, `planeCameraPose`, and the raycast must use that origin too.
  The resolved basis is derivable **client-side** from `(base, offset_mm,
  flip)` — the design fixes the formula (§3a) so the TS viewport math and the
  kernel `Plane.offset` agree exactly (the CLAUDE.md "one source of plane math,
  two renderers" rule). No new server round-trip is needed to draw on the plane.
- **Authoring flow: author-or-select a plane, then sketch.** The sketch-create
  UX gains a plane step — pick an origin datum, *or* pick an existing datum
  feature, *or* author a new offset plane (base + signed offset + optional
  flip) which creates a `datum` feature and then starts the sketch on it via a
  `FeatureRef`. Whether that is a distinct two-step flow or a one-step create
  with an inline "new offset plane" affordance is the UI item's call (§10).
- **Datum planes appear as first-class, nameable feature-tree rows** ("Plane1"),
  like sketches — matching production CAD and making the plane inspectable and
  editable.

The #2 implementer owns the geometry/documents slice; the viewport
generalization (offset origin in the plane math, plane authoring UI) is either
folded into #2 or tracked as its paired UI item.

---

## 9. Worked example — a sketch on a plane 10 mm above XY

Three feature rows (uuids abbreviated), for a rectangle drawn on a datum plane
offset 10 mm above the XY origin datum:

**`features` row 0 — the datum plane** (not body-affecting; produces a plane):

```json
{
  "id": "f-p001", "order_index": 0, "name": "Plane1",
  "type": "datum", "param_version": 1,
  "params": { "base": "XY", "offset_mm": 10.0, "flip": false }
}
```

**`features` row 1 — a sketch on it**, referencing the datum by feature id
through the existing `FeatureRef` variant:

```json
{
  "id": "f-s002", "order_index": 1, "name": "Sketch1",
  "type": "sketch", "param_version": 1,
  "params": {
    "plane": { "kind": "feature", "feature_id": "f-p001" },
    "entities": [ … ], "constraints": [ … ]
  }
}
```

**`feature_dependencies`** (derived on write, §5):

```json
{ "part_id": "p-…", "feature_id": "f-s002", "references_feature_id": "f-p001" }
```

Evaluation: the datum handler resolves `Plane.XY.offset(10)` and records it
under `f-p001` (`ok`, no body); the sketch handler resolves its plane
`FeatureRef` → that `Plane`, solves, and its entities map to world space at
z = 10 mm; a following extrude builds a body 10 mm above the base exactly as it
would on XY. A backward-compatible sketch on the origin XY datum
(`{"kind":"datum_plane","plane":"XY"}`) is unchanged and resolves to
`Plane.XY` (origin `[0,0,0]`) — byte-identical to today.

**The loft unlock, concretely:** two `datum` features (`offset_mm: 0` and
`offset_mm: 30`), a circle sketch on each, and a `loft` through both →
the two-parallel-circles frustum golden the loft note deferred for lack of a
second parallel plane.

---

## 10. Open questions (none block this design's endorsement)

1. **Plane-authoring UX shape** — distinct "create plane" step vs. inline
   "new offset plane" affordance in sketch-create. UI item's call; may warrant
   a founder look (§8, and the flag below).
2. **`flip` in v1 at all?** Position is fully covered by signed `offset_mm` and
   extrude side by `direction: normal|reverse`, so `flip` only sets the
   authoring/normal sense. Kept as additive-optional (default False) so it can
   be dropped from the first cut without a schema change if the UI doesn't need
   it yet.
3. **Datum-plane visual in the viewport** — extent, grid, hover/selection
   affordance for an infinite plane rendered as a bounded quad. Design-system
   token work for the UI item (the frontend-design skill governs it).
4. **Chaining resolution cost** (v2) — datum-from-datum adds one indirection to
   plane resolution; trivial at v1's tree sizes, confirm when v2 lands.

---

## 11. Review — anticipated code-reviewer concerns

### 11.1 Boundary hygiene (standing check)

`DatumParamsV1` is pure pydantic — a string enum, a float, a bool. No kernel
type crosses the boundary: the resolved `build123d.Plane` lives **only** inside
`services/geometry` evaluation state (a kernel type held service-internal,
exactly like `state.body`), never serialized. Documents stores/relays the datum
params and materializes the sketch→datum `feature_dependencies` edge; it never
imports the kernel (feature-tree §8.4). The sketch references the plane through
the already-crossing, kernel-free `FeatureRef` (a UUID) — no new boundary
crossing is introduced.

### 11.2 Determinism + golden gate

Plane resolution is a pure function of `(base, offset_mm, flip)`; `Plane.offset`
is deterministic; no iteration order participates. An existing origin-datum
sketch resolves to the identical `Plane` (§3a/§4), so **every current golden's
mass properties and topology are unchanged** — this is a strict superset, not a
behavioural change to the origin-datum path. New capability ⇒ new golden (DoD):
the #2 item ships the two-parallel-offset-circles → **frustum** golden
(analytic volume/centroid within the documented per-model tolerance, topology
counts exact) plus a sketch-on-an-offset-plane extrude whose body is the
XY-extrude translated by `offset_mm` — asserting the offset lands where the
math says. STEP round-trip on the offset-plane body confirms the plane origin
survives export.

### 11.3 DRY — one plane-math source, two renderers

The plane-resolution formula (§3a: `DATUM_PLANES[base].offset(offset_mm)`, plus
flip) is the single source; the TS viewport mirrors it as the same
`origin + u*x + v*y` mapping (§8). No hex-value-style duplication of plane math
between kernel and DOM — the same discipline the design system applies to the
palette. The kernel refactor (name literal → resolved `Plane` on the shared
`build_profile_face`/`plane_point_to_world`/revolve/loft entry points) *removes*
a duplication rather than adding one: the name→`Plane` lookup funnels into one
`resolve_sketch_plane` helper instead of being re-applied per caller.

### 11.4 Why not extend `DatumPlaneRef` with an offset instead of a new feature?

That is the §2a inline spec under a different name — it puts a shareable,
addressable plane inside a value with no id, forfeiting composition, DRY, and
the additive v2 on-face path (§2). `DatumPlaneRef` stays exactly what it is —
the three implicit origin datums — and user planes become features. Keeping the
two concepts distinct (implicit origin frame vs. authored feature) is what every
production CAD does and what makes the v2 increment clean.

---

## 12. Founder flags (surfaced before implementation)

- **The datum-as-feature decision changes the sketch-create feel** from
  one-step ("pick one of three planes, draw") to plane-then-sketch (author or
  select a plane, then draw). This is the right long-term model (it is how
  Onshape/Fusion/SolidWorks work and it is what makes offset/on-face/angled
  planes all one mechanism), but it is a real change to the most-used gesture in
  the app, so it is called out rather than smuggled in. The one-step feel can be
  preserved with an inline "new offset plane" affordance (§8/§10.1).
- **`flip` scope (§10.2)** is a small, reversible call the #2/UI items can make;
  no founder decision needed unless the UX wants it surfaced.
