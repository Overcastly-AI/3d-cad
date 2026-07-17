# Assemblies — Design

Status: **design only** (kernel-architect, 2026-07-15). Reviewed by
`code-reviewer` **before** implementation (CLAUDE.md: hard problems get a design
doc first — the 3D mate solver is exactly such a problem). Scope: the
architecture decision for the **Assemblies** pillar named #1 by the product
audit (`docs/AUDIT-PRODUCT.md`, pass 2026-07-15). Implementation is sequenced by
the groomer into the normal build loop **after** this doc is endorsed; nothing
below is code yet.

This document decides, with rationale and tradeoffs:

1. the assembly **document model** (documents service);
2. the v1 **mate set** and — the crux — the **3D constraint solver** (build vs.
   adopt);
3. the **service-boundary split** (who owns the document, who resolves mate
   geometry, where the solver lives);
4. **end-to-end evaluation & output** (per-instance meshes + transforms, BOM,
   STEP-assembly export);
5. a **phased plan** (smallest genuinely useful v1 + explicit deferrals);
6. the **golden / geometry-QA strategy**.

Related: RESEARCH §1 (OCCT via OCP, build123d — the only kernel), §2 (the
`SketchSolver` precedent — a solver behind a protocol, deterministic,
diagnostic-first, **no GPL**), §3 (service boundaries + DRY contract pipeline),
§8 (licensing — **no GPL/AGPL**), §9 (determinism + golden gates), and the new
RESEARCH §10 (the assemblies decision record this doc backs);
`feature-tree.md` (the part document model an assembly instances and reuses
the patterns of); `topological-naming.md` §2b/§9/§10 (the
`PlanarFaceSignature` / `EdgeSignature` machinery a mate reuses to name a
face/axis of a part body).

**The honest headline:** the document model, the boundary split, and the
evaluation pipeline are low-risk restatements of patterns the codebase already
runs. **The 3D mate solver is the genuine risk** and this doc says so plainly
(§2.4). The mitigation is to scope the mate set narrowly, own determinism
end-to-end, and ship a solver we control behind an `AssemblySolver` protocol —
not to inherit a library's nondeterminism or a GPL license.

---

## 1. Assembly document model (documents service)

### 1.1 Decision: a NEW document type, not an extension of the part feature tree

An assembly is **a set of instances + a set of mates** — a *graph*, not an
ordered single-body feature history. The part model's load-bearing invariants
(strict-backward references, a single body chain §7.6, strict-prefix evaluation,
dense `order_index` as a total evaluation order) **do not apply** to an
assembly: instances have no inherent order, mates form an undirected constraint
graph, and evaluation is a constraint solve, not a forward replay. Forcing
assemblies into the `features` table would be the inner-platform mistake
`feature-tree.md` §1.1 warned against, wearing the opposite hat.

**Decision: `assembly` is a first-class document type in `services/documents`,
in its own tables, reusing the part model's *patterns* (owner-scoped auth,
uniform-404 visibility, optimistic-concurrency `version` counter, alembic-only
DDL, the pydantic→OpenAPI→ts-client contract flow) but not its *tables*.** Parts
and assemblies are siblings under a document umbrella, not parent/child.

Rejected: (a) *assembly-as-a-feature-type inside a part* — collapses the graph
into a linear history, breaks the single-body-chain contract, and can't express
inter-part mates; (b) *one polymorphic `documents` table* — parts and
assemblies share almost no columns; a shared table is a nullable-column swamp.

### 1.2 The instance tree — instances reference documents by id (+ version)

An assembly is a flat (v1) set of **instances**, each referencing another
document — a **part** or a **sub-assembly** — by id, with a **placement
transform** and a **grounded** flag. Sub-assemblies nest by an instance whose
referenced document is itself an `assembly` (§1.4).

```
assemblies                          instances
----------                          ---------
id            uuid pk               id                    uuid pk
owner_id      uuid                  assembly_id           uuid fk→assemblies(id) ON DELETE CASCADE
name          text                  ref_document_id       uuid   -- the part/sub-assembly instanced
doc_version   bigint  -- OCC ctr    ref_document_kind     text   -- 'part' | 'assembly'
created_at    timestamptz           ref_pinned_version    bigint NULL  -- §1.3 (NULL = track tip)
updated_at    timestamptz           name                  text   -- "Bracket <1>", "Bracket <2>"
                                    grounded              bool   -- fixed (0-DOF root); at least one per assy
                                    placement             jsonb  -- Placement DTO (§1.5): position + quaternion
                                    order_index           integer -- stable display/BOM order (not eval order)
UNIQUE (owner_id, name)             UNIQUE (assembly_id, order_index) DEFERRABLE INITIALLY DEFERRED
```

```
mates
-----
id            uuid pk
assembly_id   uuid fk→assemblies(id) ON DELETE CASCADE
order_index   integer                       -- stable order (determinism); UNIQUE(assembly_id, order_index)
type          text                          -- 'lock' | 'coincident' | 'concentric' | 'distance' | 'angle'
params        jsonb                         -- the MateParams DTO (§2.2): the two MateGeometryRefs + value
```

- **`ref_document_id` is a cross-document reference, not an FK.** Like
  `Part.owner_id` (db.py: "cross-service referential integrity is not a thing we
  pretend to have"), and because a referenced document may live behind the same
  service but the reference must survive the referenced doc's independent
  lifecycle, integrity is **app-enforced in documents at write time**, not a DB
  FK. Deleting a part that assemblies instance is surfaced by a documents
  pre-check (mirroring `feature_dependencies`' friendly 409, `feature-tree.md`
  §2.3): a `DELETE part` that instances reference returns **409-with-dependents**
  listing the assemblies, or (later UX) cascades with confirmation. A dangling
  `ref_document_id` that slips the pre-check resolves to an honest per-instance
  `instance_document_missing` error at evaluation (§4), never a silent empty
  instance.
- **Acyclicity is enforced at write time.** An assembly may not instance itself
  directly or transitively (A→B→A is infinite geometry). documents walks the
  instance graph on every instance insert/update and rejects a cycle
  (`assembly_cycle`, 422) — the cross-document analogue of the part tree's
  strict-backward acyclicity (`feature-tree.md` §2.2 rule 2, §8.1). The walk is
  bounded (documents-side, no kernel), deterministic, and cached-invalidated on
  mate/instance mutation.
- **`grounded`** fixes an instance at its placement (0 DOF) — the solver's
  anchor. **v1 requires at least one grounded instance** per assembly (the
  "fix the first component" convention every incumbent uses); an assembly with
  none is a solvable-but-floating diagnosis (`assembly_ungrounded`, surfaced,
  not fatal — the whole rigid body is free, which is honest, not an error).

### 1.3 Version pinning — DECISION: pin-ready schema, v1 tracks tip (honestly)

**The correct long-term default is to pin an immutable part version.**
Determinism-is-a-feature (RESEARCH §9) and the no-spooky-action-at-a-distance
principle both demand it: editing a part should not silently mutate every
assembly that uses it. Incumbents agree (Onshape versioned references,
SolidWorks configurations).

**But immutable part versioning does not exist yet.** `Part.tree_version`
(db.py) is a *mutable optimistic-concurrency counter*: editing a part bumps it
and **discards the prior state** — there is no snapshot to pin to. `tree_version`
is explicitly "a fencing counter, not a history mechanism"
(`feature-tree.md` §7.7), and real versioning is a separate, unbuilt **Phase 3**
item (ROADMAP: "Document versioning: history, branch, merge-view (design doc
first)").

**Decision: carry `ref_pinned_version` in the schema now (pin-ready), but v1
resolves every instance to the referenced document's TIP** (`ref_pinned_version
= NULL`). Rationale and honesty:

- Within a single evaluation the result is fully deterministic (same inputs in →
  same geometry out — the §4 pipeline is a pure function). What v1 does **not**
  yet get is determinism *across time*: editing a part re-resolves its
  assemblies on their next evaluation. That is an accepted, documented v1
  limitation forced by the missing snapshot mechanism, **not** a design
  preference.
- The field is present so that the moment the versioning item lands (same
  Phase 3), pinning becomes an **additive** upgrade: `ref_pinned_version` goes
  from always-NULL to a real snapshot id, resolution switches tip→pinned, and
  an "update instance to latest" documents action re-pins + re-resolves. No
  schema churn, no DTO break — the additive-union discipline (`feature-tree.md`
  §1.4) applied to a column default.
- **Sequencing note for the groomer:** assemblies-v1 and part-versioning are
  coupled at the *default*, not the *mechanism*. v1 ships useful on tip; the
  versioning item flips the default. The two are independently shippable in
  either order; this doc does not block on versioning.

### 1.4 Sub-assembly nesting — rigid in v1

An instance whose `ref_document_kind = 'assembly'` nests a sub-assembly.
Resolution recurses (§4): the sub-assembly is evaluated in **its own** mate
context to solved relative instance transforms, then inserted into the parent as
a **rigid group** — its internal solved transforms are frozen and the whole
group is placed/mated as one rigid body (one 6-DOF placement the parent's mates
drive). This is SolidWorks' default (rigid sub-assemblies) and the right v1 call:
it makes nesting a clean compositional recursion with no cross-level coupling.

**Flexible sub-assemblies** (a parent mate driving a sub-assembly's *internal*
DOF) are explicitly **deferred** (§5): they couple the constraint systems across
document boundaries and multiply solver difficulty — the wrong place to spend v1
risk.

### 1.5 Persisted shapes — `py_kit.schemas.assemblies` (the DRY contract flow)

New module `py_kit.schemas.assemblies`, sibling of `py_kit.schemas.features`,
is the **single source of truth** (RESEARCH §3 DRY rule): documents validates
writes and serves its assembly CRUD API with these models, geometry parses the
evaluation request with the SAME models, and `just gen` exports them to
`packages/contracts` → `packages/ts-client`. Pure pydantic — **no kernel type
appears** (CLAUDE.md boundaries). Reuses `Vec3`, `ShapeProperties`
(`py_kit.schemas.geometry`) and `SubshapeRef` / `EdgeSubshapeRef` /
`PlanarFaceSignature` / `EdgeSignature` (`py_kit.schemas.features`) — mates name
part geometry with the *exact* signature machinery topological naming already
ships (reuse, not a parallel taxonomy).

```python
# --- placement + orientation -------------------------------------------------
class Quat(BaseModel):                 # unit quaternion — no gimbal, matches the
    x: float; y: float; z: float; w: float   # solver's internal representation (§2.3)

class Placement(BaseModel):
    position: Vec3                     # translation, world mm
    orientation: Quat = Quat(x=0, y=0, z=0, w=1)   # identity default

# --- how a mate names part geometry (§2.1) -----------------------------------
class MateFaceRef(BaseModel):          # a planar face of an instance's part body
    kind: Literal["face"]
    instance_id: UUID
    signature: PlanarFaceSignature     # reused verbatim (topo-naming §9)

class MateAxisRef(BaseModel):          # an axis, from a circular EDGE of a part body
    kind: Literal["axis"]
    instance_id: UUID
    signature: EdgeSignature           # curve == "circle"; axis = normal through centre (§2.1)

MateGeometryRef = Annotated[MateFaceRef | MateAxisRef, Field(discriminator="kind")]

# --- the v1 mate set (§2.1) --------------------------------------------------
class CoincidentMate(BaseModel):
    type: Literal["coincident"]
    a: MateFaceRef; b: MateFaceRef     # two planar faces made coplanar+flush
    flush: bool = True                 # True = normals anti-parallel (mating faces touch)

class ConcentricMate(BaseModel):
    type: Literal["concentric"]
    a: MateAxisRef; b: MateAxisRef     # two axes made collinear

class DistanceMate(BaseModel):         # fast-follow (§5): coincident + offset
    type: Literal["distance"]
    a: MateFaceRef; b: MateFaceRef
    distance_mm: float

class AngleMate(BaseModel):            # fast-follow (§5)
    type: Literal["angle"]
    a: MateFaceRef; b: MateFaceRef
    angle_deg: float

class LockMate(BaseModel):             # 0-DOF: rigidly fixes two instances' relative pose
    type: Literal["lock"]
    a_instance_id: UUID; b_instance_id: UUID

Mate = Annotated[
    CoincidentMate | ConcentricMate | DistanceMate | AngleMate | LockMate,
    Field(discriminator="type"),
]
```

CRUD/response DTOs (`AssemblyCreate`, `InstanceCreate`, `MateCreate`,
`AssemblyResponse`, …) mirror the feature-CRUD DTOs (`FeatureCreate`,
`FeatureResponse`, …) including the `expected_version` optimistic-concurrency
guard (422 on stale — the `feature-tree.md` §1.2 pattern). The evaluation
contract DTOs are §4.

---

## 2. Mates and the 3D constraint solver — THE CRUX

### 2.1 v1 mate set: `lock`, `coincident` (planar face-face), `concentric` (axis-axis)

**Decision: v1 ships three mates — `lock`, `coincident`, `concentric` — with
`distance` and `angle` as the immediate fast-follow (§5).** Rationale: these
three *fully locate the single most common assembly joint in mechanical CAD* — a
bolted/pinned connection is a face mate (parts sit flush) plus a concentric mate
(holes/shafts align). That pair alone lets an engineer bolt two brackets
together, which is exactly the "two parts that bolt together" wall the audit
names. `lock` is trivial (it fixes a relative pose, 0 solver work) and covers
weldments/press-fits.

- **`coincident`** references two **planar faces** (`MateFaceRef`), resolved
  against each instance's part body by the **`PlanarFaceSignature`** the
  `on_face` datum already resolves (`topological-naming.md` §9). `flush` chooses
  the normal sense.
- **`concentric`** references two **axes** (`MateAxisRef`). **v1 derives an axis
  from a circular EDGE** — reusing `EdgeSignature` with `curve == "circle"`,
  whose centre (the signature's `midpoint`, a closed-edge seam point) and plane
  give the axis. This deliberately **avoids needing a cylindrical-face
  signature** (`PlanarFaceSignature` is planar-only; a `CylindricalFaceSignature`
  is a clean *additive* future member, not v1). A hole rim and a shaft rim are
  both circular edges — enough for the canonical bolt joint.
- **`distance` / `angle`** are `coincident` with a non-zero offset in the
  residual (§2.3) — the same solver, one extra scalar — hence fast-follow, not
  v1-blocking.

`distance`/`angle`/richer axis sources join the discriminated `Mate` union
additively (the `feature-tree.md` §1.4 rule) with no version churn.

### 2.2 The 3D constraint solver — DECISION: build our own, behind `AssemblySolver`

**Decision: build a minimal, deterministic rigid-body mate solver in
`services/geometry`, behind an `AssemblySolver` protocol that mirrors
`SketchSolver` (RESEARCH §2).** Do **not** adopt a third-party 3D constraint
solver for v1.

**Why not a library — the license + maturity survey (RESEARCH §8: no
GPL/AGPL):**

| Candidate | License | Verdict |
|---|---|---|
| SolveSpace `libslvs`, `py-slvs`, `python-solvespace` | **GPLv3** | **Forbidden** (§8). Already rejected once for the sketch solver (§2). The obvious 3D GCS — and unusable here. |
| FreeCAD **OndselSolver** (the new Assembly WB solver) | **LGPL-2.1** | *License-compatible* (LGPL-dynamic, §8), but C++ with **no maintained PyPI wheel**, and a full multibody-dynamics engine — heavier than a mate solver needs, an unproven packaging + boundary-crossing risk. The one candidate worth a **future spike** if we outgrow our own; not a v1 dependency. |
| planegcs (our sketch solver) | LGPL-2.1 | **2D only** — PlaneGCS has no 3D primitives. Not applicable. |
| FreeCAD Assembly4 (LCS/skeleton) | LGPL | Not a solver — a manual local-coordinate-system placement scheme. Different (weaker) UX model. |

There is **no mature, license-clean, Python-packaged 3D geometric constraint
solver** to adopt. So the choice is really "roll our own" vs. "vendor + wrap a
C++ LGPL MBD engine," and for a *small* v1 mate set the former is lower-risk and
keeps us on the RESEARCH §2 posture (solver behind a protocol, **we own
determinism**, no GPL).

**Why building it is tractable (the DOF argument):**

- Each **free** instance is a rigid transform with **6 DOF** — translation
  `t ∈ ℝ³` + orientation as a **unit quaternion** `q ∈ S³` (§2.3). Grounded
  instances contribute 0 DOF (fixed). A sub-assembly contributes one rigid 6-DOF
  group (§1.4).
- Each mate contributes a small residual vector that vanishes when satisfied
  (§2.3): `coincident` = coplanar + flush (distance-along-normal = 0, normals
  (anti)parallel); `concentric` = axes collinear (direction parallel + line
  coincident); `lock` = relative pose fixed; `distance`/`angle` = the same with a
  target offset.
- The assembled system is `F(x) = 0` for `x ∈ (ℝ³ × S³)^{n_free}` — a modest
  nonlinear least-squares. Solve with a **deterministic damped Gauss-Newton /
  Levenberg-Marquardt**, seeded from the instances' current placements (the
  authored positions — the same "entities are the starting guess" posture
  planegcs uses, §2), grounded instances held fixed. Quaternions re-normalised
  each step; the unit constraint handled by the seed + renormalisation (or a
  soft `|q|=1` residual).
- **Determinism (RESEARCH §9, non-negotiable):** fixed iteration order (mates
  and instances in persisted `order_index` order — no dict/set iteration leaks),
  a fixed seed (authored placement), a fixed algorithm with **no random
  restarts** (planegcs posture), and full-precision arithmetic → same assembly
  bytes in ⇒ **bitwise-identical solved transforms** out. This is asserted by a
  golden (§6).
- **Numerics dependency:** the least-squares core is small linear algebra
  (numpy, already transitively present via OCP/tessellation) or scipy
  `least_squares` (the RESEARCH §2 *named* SketchSolver fallback — its presence
  is already sanctioned). The choice is an implementation detail **behind the
  protocol**; if scipy is undesirable, a hand-rolled LM over numpy is ~150 lines
  and keeps determinism fully in our hands. Either way, no GPL, no kernel type
  in the solver's numeric core.

**Closed-form fast path (a real simplification, not gold-plating):** when the
mate graph is a **tree rooted at a grounded instance** where each instance is
*fully* located by its mate chain (the common bolt-two-parts case), transforms
propagate **directly** from ground with no iteration — a rigid-transform compose
per edge. The numerical LM is only entered for **coupled / loop / partially
constrained** graphs. This keeps the common case exact and instantaneous and
confines the solver's genuine difficulty to the cases that need it.

### 2.3 Transform + residual representation (concrete, for review)

- **Instance pose:** `Placement { position: Vec3, orientation: Quat }` on the
  wire (§1.5); internally `x_i = (t_i ∈ ℝ³, q_i ∈ S³)`. Quaternion (not Euler,
  not a 3×3 matrix on the wire) because it is gimbal-free, minimal, and
  renormalises cleanly under iteration — and it is what the solver manipulates,
  so no lossy conversion at the boundary.
- **Resolved mate geometry** (produced *inside* geometry — never crosses the
  boundary): a face → `(point p, unit normal n)` in the instance's *local* part
  frame; an axis → `(point p, unit direction d)`. Transformed by the current
  instance pose to world for residual evaluation.
- **Residuals (world frame):**
  - `coincident(A,B, flush)`: `[ n_A · (p_B − p_A),  n_A + n_B (flush) / n_A − n_B
    (non-flush) ]` — signed gap along the normal = 0, normals anti-parallel
    (flush, the mating faces touch) or parallel (non-flush). The alignment block
    uses the vector **difference/sum** `n_A ∓ n_B`, not the cross product `n_A ×
    n_B`: the difference is the stronger constraint (it pins the sign, forcing the
    two normals (anti)parallel *and* co-directed), whereas the cross product
    leaves a 180° flip free. The implementation
    (`services/geometry/.../residuals.py`) uses `n_A ∓ n_B`; this line is the
    spec of record.
  - `distance(A,B)`: the coincident residual with the gap target = `distance_mm`
    and the flush (anti-parallel) alignment. **PINNED sign convention (shipped
    2026-07-17):** `distance_mm` is the signed gap measured along face A's
    **outward** normal `n_A` — at the solution `n_A·(p_B − p_A) = distance_mm`, so
    `p_B` sits `distance_mm` along `+n_A` from `p_A` (positive = a gap on the
    `+n_A` side, the two outward normals facing each other across it; negative = B
    on the `−n_A` side; **zero = a plain flush coincident**). Proved by the
    `assembly-two-plates-gap` golden (two real plates landing exactly 5 mm apart)
    + `test_assembly_distance_angle` (both signs + the zero degenerate).
  - `angle(A,B)`: the angle `φ` between the two **outward** normals driven to
    `angle_deg`, i.e. `acos(n_A·n_B) = angle_deg` (no `flush` sense — an angle mate
    constrains only the scalar angle). **PINNED (shipped 2026-07-17):** the
    residual is `sin(φ − θ) = sinφ·cosθ − cosφ·sinθ` (with `cosφ = n_A·n_B`,
    `sinφ = ‖n_A×n_B‖`), **not** the scalar `n_A·n_B − cosθ`: both vanish at
    `φ = θ`, but `sin(φ − θ)` has unit gradient at the target whereas the scalar
    form is flat near alignment and stalls the LM seed-dependently just short of
    tolerance. The parallel/anti-parallel **degenerate** target (`θ ≈ 0°/180°`)
    falls back to `cosφ − cosθ` (whose sign distinguishes the two ends) and is
    reported honestly (`under_constrained`/`not_converged`), never NaN, never a
    wrong pose. Proved by `test_assembly_distance_angle` (30°, 90°, 120° land
    exactly; 0°/180° handled cleanly).
  - `concentric(A,B)`: `[ d_A × d_B (parallel),  (p_B − p_A) − ((p_B − p_A)·d_A)
    d_A (line-coincident) ]`.
  - `lock(A,B)`: relative pose residual (6) driving `x_B` to a fixed transform of
    `x_A`.

### 2.4 Diagnosis — mirror the SketchSolver status vocabulary; and THE RISK

**The 3D mate solver is the risk in this whole pillar. Stated plainly:** a
general N-body simultaneous mate solve can be ill-conditioned, admit multiple
solutions (a mate chain often has a "flip"), or fail to converge. This is the
part that sinks naïve assembly features. Mitigations, all deliberate:

- **Scope caps the difficulty.** Three mates, a grounded root, rigid
  sub-assemblies, and the §2.2 closed-form tree fast path mean the *common* case
  never enters the general solver at all. The numerical solver is the fallback,
  not the hot path.
- **Under-constrained is a first-class, non-fatal status — not a failure**
  (exactly the SketchSolver posture, §2: "underconstrained sketches still
  solve"). The solver reports **remaining DOF** (from the numerical Jacobian's
  rank at the solution: `remaining_dof = 6·n_free − rank(J)`) and leaves the free
  DOF at the seed. The assembly still renders — positioned at best-fit.
- **Over-constrained / conflicting mirror `SketchConstraintDiagnosis`** exactly
  (`py_kit.schemas.sketch`, reused/mirrored): a typed `AssemblySolveDiagnosis`
  carries a `classification` (`redundant` vs `conflicting`), the offending
  **mate ids**, `removable`, and a `suggested_fix` ("Remove mate N"). Redundant
  (consistent but linearly dependent) mates are **not** an error — they solve and
  are flagged. Conflicting (unsatisfiable) mates are the error case.

Status vocabulary (mirrors the sketch solver so the UI and tests share the
mental model):

| Status | Meaning | Fatal? |
|---|---|---|
| `well_constrained` | 0 remaining DOF, unique solve | no |
| `under_constrained` | `remaining_dof > 0`; free DOF left at seed | no (rendered at best-fit) |
| `over_constrained` (redundant) | consistent but dependent mates; `removable` named | no |
| `conflicting` | unsatisfiable mates; offending ids named | **yes** — per-mate error (§4) |
| `not_converged` | LM failed to reach tolerance | **yes** — honest `mate_solve_failed`, never a bad pose |

Determinism guarantee (RESEARCH §9): identical assembly → identical status and
identical transforms, never "whichever solution the iteration happened to land
in." The "flip" multiplicity is resolved deterministically by the seed (authored
placement) — the solution *nearest the authored pose* — never a coin flip.

---

## 3. Service boundaries (enforced in review)

Explicit ownership, consistent with CLAUDE.md ("Only `services/geometry` imports
OCP; documents never imports the kernel; the web app talks only to the gateway";
"No kernel types cross a service boundary"):

| Concern | Owner | Why |
|---|---|---|
| Assembly **document** (instances, mates, placements, versions) | **documents** | It is persisted intent — Postgres, owner-scoped, alembic. Kernel-free (all DTOs pure pydantic). |
| Cross-doc integrity, acyclicity, 409-with-dependents, OCC `version` | **documents** | Graph bookkeeping over ids — no geometry. |
| Resolve a `MateGeometryRef` → a face/axis of a part body | **geometry** | Needs the *evaluated* part body (OCCT) + the signature resolver (`geometry.kernel.faces`/`.edges`). |
| Evaluate each unique part body (dedup by part+version) | **geometry** | The kernel lives here; reuses the existing `EvaluateTree` dispatch. |
| **The mate SOLVER** | **geometry** | Its residuals need resolved geometry (face/axis positions from OCCT bodies). documents is kernel-free and *cannot* resolve them. Solver + resolution belong together, behind `AssemblySolver` — the `SketchSolver` posture (§2 lives in geometry too). |
| Tessellate instances / combined properties | **geometry** | Meshing + GProp are kernel ops. |
| Interference / collision (deferred, §5) | **geometry** | OCCT boolean-common / BOP is a kernel op. |
| STEP-assembly export (deferred, §5) | **geometry** | OCCT XCAF writer. |
| Aggregation, auth, WebSocket fan-out | **gateway** | apps/web talks **only** to the gateway; it never calls geometry/documents directly. |

**Boundary hygiene (standing check):** the *only* things crossing
documents↔geometry are pure pydantic — the assembly DTOs in (instances + mates +
per-part feature lists), and per-instance `Placement` transforms + content
addresses + `ShapeProperties` out. **No `TopoDS`, no quaternion-of-a-kernel-type,
no build123d anything** crosses. The solver's numeric core (numpy/scipy) is
internal to geometry and consumes resolved primitives, not kernel handles —
identical to how `SketchSolver` consumes solved 2D points, not OCCT wires.

---

## 4. Assembly evaluation & output (end to end)

The evaluation contract mirrors `EvaluateTreeRequest`/`EvaluateTreeResult`
(`feature-tree.md` §4) — one more transport-agnostic request/response pair over
sync-HTTP today, the arq queue payload tomorrow (RESEARCH §4).

**Request (`EvaluateAssemblyRequest`, documents → geometry):**

```python
class EvaluatedInstance(BaseModel):
    instance_id: UUID
    part_key: str                    # dedup key: f"{ref_document_id}@{version-or-tip}"
    features: list[EvaluatedFeatureInput]   # the part's feature prefix (reuses §4 exactly)
    placement: Placement             # authored seed pose
    grounded: bool

class EvaluateAssemblyRequest(BaseModel):
    assembly_id: UUID
    version: int                     # echoed; cache/correlation key
    instances: list[EvaluatedInstance]
    mates: list[Mate]                # ordered (determinism)
    linear_deflection: float = DEFAULT_LINEAR_DEFLECTION
```

Documents flattens sub-assemblies into the recursive structure before sending
(or sends the nested form and geometry recurses — an impl choice; the rigid-group
result is identical). Documents sends **each part's feature list** so geometry is
the sole evaluator (documents stays kernel-free and sends *intent*, never bodies).

**Pipeline (geometry):**

1. **Evaluate each UNIQUE part once**, keyed by `part_key`, via the existing
   `EvaluateTree` dispatch → a body + a content-addressed **part mesh**
   (`mesh_store`, reused) + `ShapeProperties`. **Two instances of the same part
   share one evaluation and one cached mesh** — the central perf win.
2. **Resolve every `MateGeometryRef`** against its instance's part body (in the
   part's local frame) via `geometry.kernel.faces`/`.edges` — nearest-within-
   tolerance, **exactly-one-or-honest-error** (the stage-1 signature contract).
   An unresolved ref is a per-mate error (§ below), never a silent skip.
3. **Solve** (§2) → a world `Placement` per instance (grounded fixed).
4. **Compose properties analytically:** total volume = Σ part volumes; combined
   centroid = mass-weighted Σ of each part's transformed centroid; combined bbox
   = union of transformed part bboxes. **No re-meshing, no boolean** — assembly
   mass properties are a closed-form roll-up of per-part properties + transforms.

**Response (`EvaluateAssemblyResult`, geometry → documents → gateway → web):**

```python
class InstancePlacementResult(BaseModel):
    instance_id: UUID
    part_mesh_glb_id: str            # content address — SHARED across instances of a part
    placement: Placement             # SOLVED world pose
    properties: ShapeProperties      # the part's own props (for BOM/inspection)
    error: FeatureError | None       # e.g. instance_document_missing / subshape_unresolved

class EvaluateAssemblyResult(BaseModel):
    assembly_id: UUID
    version: int
    instances: list[InstancePlacementResult]
    status: Literal["well_constrained","under_constrained","over_constrained","conflicting","not_converged"]
    diagnosis: AssemblySolveDiagnosis | None      # remaining DOF + offending mate ids (§2.4)
    properties: ShapeProperties | None            # combined assembly mass props (roll-up)
    bounding_box: BoundingBox | None
```

**The output is per-instance {mesh content-address + solved transform}, NOT a
baked combined GLB.** The viewport instances the shared part meshes with the
solved transforms (r3f instancing) — one part mesh drawn N times. This is the
determinism + perf posture: unique-part meshes are cached/deduplicated, and the
assembly "geometry" is a tiny transform list. A *baked* combined GLB or STEP is
an **export** concern (deferred, §5), not the interactive path.

**Per-mate / per-instance error surfacing** mirrors `feature-tree.md` §4.3: a
failing mate/instance is a **200 with a typed error** on that entry (codes:
`instance_document_missing`, `subshape_unresolved`/`subshape_ambiguous` from the
reused resolver, `mate_conflicting`, `mate_solve_failed`), not a transport 4xx —
the envelope stays reserved for validation/transport failures. The assembly
still renders every instance it *could* place (unlike the part tree's
strict-prefix, an assembly has no linear prefix — a single bad mate degrades the
solve to under-constrained + flags the mate, rather than skipping "everything
after").

**BOM — v1 = a trivial documents-side read model.** The instance list already
*is* the BOM: rolling up `(ref_document_id, ref_document_kind, name)` by quantity
is a pure documents-side aggregation over rows — **no geometry**. A **flat,
quantity-rolled BOM** ships cheaply in v1 (or immediate fast-follow); **indented
/ hierarchical BOM** (sub-assembly rollup, item numbers) and **CSV/formatted
export** are deferred (§5). The point: the data is free; only the presentation is
staged.

**STEP-assembly export — DEFERRED (§5).** True structured STEP assembly (AP214
product structure / NAUO instances + placements) needs OCCT **XCAF**
(`STEPCAFControl_Writer` + a `TDocStd` document) — a heavier machinery that pulls
a document model into the stateless geometry service (the same weight concern
`topological-naming.md` §6.2 flags for OCAF). v1 interop for an assembly is: each
*part* still exports STEP individually (already works). Structured assembly STEP
(and an interim "combined compound" STEP) is a fast-follow with its own round-trip
golden.

---

## 5. Phased plan

**Smallest genuinely useful v1 — "bolt two parts together and see it":**

- `assembly` document type + `instances` + `mates` tables (documents), CRUD API,
  owner-scoped auth, OCC `version`, acyclicity + 409-with-dependents integrity.
- Instances referencing **parts** (tip-tracking, `ref_pinned_version` present but
  NULL), authored `Placement`, one `grounded` root.
- **Three mates: `lock`, `coincident` (planar face-face), `concentric`
  (axis-from-circular-edge)** — reusing `PlanarFaceSignature`/`EdgeSignature`.
- The **`AssemblySolver`** (own, deterministic LM + closed-form tree fast path)
  with the full under/over/conflict/DOF **diagnosis** vocabulary (§2.4).
- **Assembly evaluation → per-instance shared-mesh + solved transform + combined
  mass-property roll-up**, rendered instanced in the viewport (gateway-proxied;
  apps/web design work invokes the `frontend-design` skill).
- New **golden(s)** in the same commit (§6) — DoD.

**Explicitly deferred (each a later, independently shippable loop item):**

- `distance` + `angle` mates (immediate fast-follow — same solver, offset
  residual).
- **Interference / collision** detection (OCCT boolean-common; §6 golden ready).
- **Exploded views** (a per-instance display offset — pure presentation).
- **BOM export** formatting (data is free in v1; CSV/indented is staging).
- **STEP-assembly IO** (XCAF writer + round-trip golden).
- **Flexible sub-assemblies** (v1 sub-assemblies are rigid, §1.4).
- **Part version PINNING as default** (couples to the Phase 3 versioning item;
  schema is pin-ready, §1.3).
- **Mate-driven motion / drag-within-DOF**, instance patterns/mirror,
  cylindrical-face axis references, non-circular-edge axes.

---

## 6. Golden / geometry-QA strategy

Assembly correctness is **analytically checkable** — the reason this pillar is
gateable the same rigorous way parts are (RESEARCH §9; `geometry-qa` agent →
`docs/GEOMETRY-QA.md`). New capability ⇒ new golden **in the same commit** (DoD).

1. **Mate transforms are exact and checkable.** Golden `assembly-two-plates-
   bolted`: plate A grounded, plate B mated `coincident` (top-of-A ↔ bottom-of-B)
   + `concentric` (a hole in each). Assert **each instance's solved `Placement`
   equals the hand-derived analytic transform** within a documented per-model
   tolerance (RESEARCH §9 — never an ad-hoc epsilon), and that combined mass
   properties equal the analytic roll-up (Σ volumes; mass-weighted centroid).
2. **Solve determinism** (the RESEARCH §9 solver-determinism gate, restated for
   3D): the same assembly → **bitwise-identical** solved transforms across runs
   and fresh solver instances, and insensitive to a displaced authored seed for a
   *fully*-constrained assembly (the planegcs §2 acceptance posture, in 3D).
3. **Diagnosis goldens:** an under-constrained assembly reports the correct
   **remaining DOF**; a redundant mate is flagged `over_constrained` + `removable`
   (not an error); a conflicting mate set surfaces `conflicting` with the right
   offending **mate ids** — mirroring the sketch over-constraint goldens.
4. **Shared-mesh dedup** is asserted: the same part instanced twice yields **one**
   `part_mesh_glb_id` (content address) referenced by two placements — the perf
   contract, testable without pixels.
5. **Interference (when it lands):** a golden with **known overlap volume** (two
   boxes overlapping by a known amount → exact boolean-common volume); a
   correctly-mated (face-touching) assembly → **zero** interference within
   tolerance. Interference is a boolean — an ideal golden target.
6. **STEP-assembly round-trip (when it lands):** assembly → STEP-assembly →
   re-import → **instance count + per-instance mass properties preserved**, the
   assembly analogue of the existing part STEP round-trip gate (§9).
7. **Performance budgets** (RESEARCH §9): assembly evaluate + solve + tessellate
   wall-clock ceilings; the shared-mesh dedup and analytic property roll-up keep
   an N-instance assembly near the cost of its *unique* parts, not N× — a
   regression tripwire.

---

## 7. Open questions (owned by the implementing items; none block endorsement)

1. **scipy vs. hand-rolled LM** for the solver core — decide in the solver item;
   determinism + no-GPL are the only hard constraints (§2.2).
2. **Multiple-solution ("flip") policy** beyond "nearest the seed" — do we expose
   an explicit flip toggle per mate? (SolidWorks does.) Defer to a UX pass.
3. **Mate-reference stability under part edits** — a `MateGeometryRef` inherits
   the stage-1 signature's best-effort honesty (`topological-naming.md` §7.3): a
   part edit that moves the mated face/edge is an honest `subshape_unresolved`,
   but a drastic edit can rarely retarget. Stage-2 provenance closes this for
   parts and assemblies together — no separate mechanism.
4. **Where sub-assembly flattening happens** (documents pre-flatten vs. geometry
   recursion) — §4 notes both give identical rigid-group results; pick in the
   eval item.
5. **Realtime co-editing of an assembly** (Phase 3 collaboration) — the OCC
   `version` counter is a fencing token, not a merge mechanism, exactly as
   `tree_version` is for parts (`feature-tree.md` §7.7).
</content>
</invoke>
