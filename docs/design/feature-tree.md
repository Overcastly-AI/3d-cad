# Feature-Tree Persistence — Design

Status: **proposed** (awaiting code-reviewer pass; kernel-architect concerns
pre-addressed in §8). Scope: **design only** — implementation is the
"Feature-tree persistence implementation" backlog item, which depends on this
doc and on parts CRUD.

This document specifies how parametric history (the ordered feature tree of a
part) is persisted in the **documents service**, validated via **py-kit**
pydantic models, and handed to the **geometry service** for evaluation —
without any kernel type ever leaving `services/geometry` (CLAUDE.md service
boundaries; RESEARCH §3).

Related: RESEARCH §3 (architecture / DRY), §4 (Postgres: "JSONB feature
params + relational tree structure" — this doc is the concrete design behind
that line), §9 (geometry QA gates that the evaluation contract must feed).

---

## 1. Document model

### 1.1 Storage shape: separate `features` table (decision)

Two candidate shapes for the ordered tree:

| | `parts.feature_tree` JSONB array | separate `features` table (chosen) |
|---|---|---|
| Ordering | free (array order) | needs an explicit order key |
| Load whole tree | 1 row | 1 indexed range scan (`part_id, order_index`) |
| Per-feature identity | app-managed ids inside JSON | real PK (uuid) |
| Inter-feature references | unverifiable strings | FK-enforceable via a side table (§2.3) |
| Edit one feature | rewrite whole array (TOAST churn, row-level write conflicts) | targeted `UPDATE` of one row |
| Per-feature timestamps / audit / error attachment | ad-hoc JSON | ordinary columns |
| Schema evolution of one feature type | migrate blobs inside arrays | `WHERE type = …` data migrations |
| Future collaborative editing | whole-tree conflicts | per-row granularity |

**Decision: separate `features` table.** Feature *identity* is load-bearing in
this design: extrude references sketch **by feature id** (§2), the rollback
bar points at a feature id (§3), evaluation errors are attached per feature id
(§4), and Phase 2 topological naming will hang per-feature data off the same
ids. A JSONB array would force us to reinvent identity, referential integrity,
and targeted updates inside a blob — the classic inner-platform failure. JSONB
is still used where it is strong: the **params of a single feature** are one
JSONB document (§1.3), because their shape varies per feature type and they
are always read/written as a unit.

### 1.2 Postgres schema

The `parts` table is created by the parts-CRUD item; this design **extends**
it and adds two tables. All DDL lands via alembic (§5).

```sql
-- Extension of the existing parts table
ALTER TABLE parts
  ADD COLUMN tree_version        bigint NOT NULL DEFAULT 0,   -- bumped on every tree mutation
  ADD COLUMN rollback_feature_id uuid   NULL;                 -- FK added after features exists (§3)

CREATE TABLE features (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  part_id        uuid        NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
  order_index    integer     NOT NULL,
  name           text        NOT NULL,            -- user-facing ("Sketch1", "Extrude1")
  type           text        NOT NULL,            -- feature-type discriminator ("sketch", "extrude")
  param_version  integer     NOT NULL,            -- version of the params schema for this type
  params         jsonb       NOT NULL,            -- validated pydantic dump (§1.3–1.4)
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_features_part_order UNIQUE (part_id, order_index)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ix_features_part_order ON features (part_id, order_index);

-- Materialized inter-feature references, derived from params on every write (§2.3)
CREATE TABLE feature_dependencies (
  feature_id            uuid NOT NULL REFERENCES features(id) ON DELETE CASCADE,
  references_feature_id uuid NOT NULL REFERENCES features(id) ON DELETE RESTRICT,
  PRIMARY KEY (feature_id, references_feature_id)
);

ALTER TABLE parts
  ADD CONSTRAINT fk_parts_rollback_feature
  FOREIGN KEY (rollback_feature_id) REFERENCES features(id) ON DELETE SET NULL;
```

**Ordering: dense integers, renumber on reorder.** `order_index` is
`0..n-1` with no gaps. Insert-in-middle / reorder renumbers the suffix inside
one transaction; the deferrable unique constraint makes the shuffle legal.
Rationale: feature trees are small (tens, rarely hundreds, of rows) and
reorders are rare, so renumbering costs nothing measurable, while dense
integers make the evaluation order trivially total and human-debuggable
(`ORDER BY order_index` — no ties possible, no fractional-key pathologies).
If real-time collaboration later makes renumbering a conflict hotspot, we can
migrate to fractional indexing behind the same API — the order key is never
exposed as meaningful to clients beyond relative position.

**`tree_version`** is a monotonic counter bumped in the same transaction as
*any* tree mutation (feature insert/update/delete/reorder, rollback move). It
serves optimistic concurrency (clients send the expected version, 409 via the
py-kit error envelope on mismatch) and keys evaluation-result caching (§4.4).

### 1.3 Per-feature params: versioned JSONB envelope

Each feature's parameters travel (API) and persist (DB) as the logical
envelope

```json
{ "type": "extrude", "version": 1, "params": { …type-specific… } }
```

In the database, `type` and `version` are **promoted to real columns**
(`type`, `param_version`) so they are indexable and constrainable, and
`params` holds only the type-specific payload. On the wire the envelope is
reassembled by the DTO — clients never see the split. Envelope rules:

- `version` is **per feature type** (sketch v1 and extrude v1 are unrelated
  counters) and is bumped only on a **breaking** shape change of that type's
  params. Additive optional fields do not bump it.
- The stored `params` is always the output of a successful pydantic
  validation (§1.4) — the DB never holds a params blob that no registered
  model accepts. A JSONB `CHECK` is deliberately not attempted; pydantic in
  the write path is the gate (single source of truth, not duplicated in SQL).

### 1.4 Validation: pydantic in py-kit as the single source

A new module `py_kit.schemas.features` (sibling of the existing
`py_kit.schemas.geometry`) defines, per feature type and version, one pydantic
model — used identically by documents (write-path validation, API DTOs) and
geometry (evaluation-request parsing). This is the CLAUDE.md DRY rule applied:
no hand-duplicated feature-param shapes on either side of the boundary, and
the OpenAPI contract (`just gen`) — hence the TS client — is generated from
these same models.

```python
class SketchParamsV1(BaseModel):
    plane: GeomRef                     # datum_plane only in v1 (§2.1)
    entities: list[SketchEntity]       # final shape owned by the sketch-model item
    constraints: list[SketchConstraint]

class ExtrudeParamsV1(BaseModel):
    profile: FeatureRef                # must resolve to an earlier sketch feature (§2.2)
    distance_mm: float = Field(gt=0, description="Extrusion depth (mm)")
    operation: Literal["add", "cut"]
    direction: Literal["normal", "reverse"] = "normal"

class SketchFeature(BaseModel):
    type: Literal["sketch"]
    version: Literal[1]
    params: SketchParamsV1

class ExtrudeFeature(BaseModel):
    type: Literal["extrude"]
    version: Literal[1]
    params: ExtrudeParamsV1

Feature = Annotated[SketchFeature | ExtrudeFeature, Field(discriminator="type")]
```

(`SketchEntity`/`SketchConstraint` shapes above are illustrative; they are
finalized by the "Sketch model + solver integration" backlog item. Everything
else in this doc is independent of their exact shape.)

**Registry + upcasts.** A module-level registry maps
`(type, version) → model class`. The discriminated `Feature` union always
describes the *current* version of each type (that is what OpenAPI exports);
older stored versions are handled by pure-Python **upcast functions**
(`upcast_extrude_v1_to_v2(params: dict) -> dict`) registered alongside.
Documents upcasts on read before anything leaves the repository layer, so the
rest of the system — including the evaluation request (§4) — only ever sees
current-version params. Bulk data migrations (rewriting old rows) are optional
housekeeping, not correctness-required, because upcasts are applied lazily.

**Mapping to JSONB:** write path is
`Feature.model_validate(envelope)` → split into columns →
`params = model.params.model_dump(mode="json")`. Read path is columns →
envelope dict → upcast if needed → `Feature.model_validate(...)`. `params`
JSONB is therefore always a faithful pydantic dump — canonical field names, no
nulls-as-absence ambiguity beyond what the model defines.

**Units are fixed per field, never tagged per value** (see §8): lengths are
millimetres, angles are degrees, encoded in field names/descriptions
(`distance_mm`) exactly as `py_kit.schemas.geometry` already does. No
`{"value": 10, "unit": "mm"}` wrappers.

---

## 2. References between features

### 2.1 `GeomRef` — the reference vocabulary

References inside `params` use a small discriminated union defined once in
`py_kit.schemas.features`:

```python
class DatumPlaneRef(BaseModel):
    kind: Literal["datum_plane"]
    plane: Literal["XY", "XZ", "YZ"]        # the three origin datum planes

class FeatureRef(BaseModel):
    kind: Literal["feature"]
    feature_id: UUID                         # a whole earlier feature (e.g. a sketch)

GeomRef = Annotated[DatumPlaneRef | FeatureRef, Field(discriminator="kind")]
```

v1 usage: *sketch-on-plane* is `SketchParamsV1.plane: GeomRef` (datum planes
only for now); *extrude-of-sketch* is `ExtrudeParamsV1.profile: FeatureRef`
pointing at a sketch feature.

### 2.2 Reference validity rules (write-time, documents service)

1. `feature_id` must exist and belong to the **same part**.
2. The referenced feature must be **strictly earlier in the tree**
   (`order_index` of target < `order_index` of referrer), checked on every
   feature write *and* every reorder. This keeps evaluation a single forward
   pass with no cycle detection needed (§8.1).
3. The referenced feature must have an acceptable **type** for the slot
   (extrude's `profile` must reference a `sketch`). Type checks live next to
   the param models in py-kit as validator helpers so documents and any future
   caller enforce identical rules.

### 2.3 `feature_dependencies` — materialized edges

On every feature write, documents extracts all `FeatureRef`s from the
validated params (a py-kit helper walks the model, so extraction can't drift
from the schema) and rewrites that feature's rows in `feature_dependencies`
in the same transaction. This buys:

- **DB-level integrity:** `ON DELETE RESTRICT` on the target side means you
  cannot delete a sketch that an extrude still consumes — the API surfaces a
  409 (py-kit envelope) listing the dependents instead of silently corrupting
  the tree.
- **Cheap dependency queries:** "what must be re-evaluated / what breaks if I
  edit or delete feature X" is one indexed query, needed by rollback UX and
  by future selective re-evaluation.

The JSONB stays the source of truth for *what* is referenced;
`feature_dependencies` is a derived index, rebuilt from params on write
(and rebuildable offline if ever suspected stale).

### 2.4 Forward-compatibility: the Phase 2 topological-naming extension point

Phase 2 features (fillet on *that edge*, sketch on *that face*) need
references to **subshapes of a feature's result**, stable across rebuilds.
This design reserves the slot without designing the mechanism:

- A third `GeomRef` variant is **reserved, not implemented**:

  ```python
  class SubshapeRef(BaseModel):          # Phase 2 — do not implement yet
      kind: Literal["subshape"]
      feature_id: UUID                   # whose result the subshape belongs to
      selector: dict[str, Any]           # opaque, versioned selector payload
      selector_version: int
  ```

  Because `GeomRef` is a discriminated union on `kind`, adding the variant
  later is additive: no persisted v1 ref changes shape, no param_version bump
  is forced on existing feature types.
- Sketch **entities carry sketch-local string ids** (`"e1"`, `"e2"`, … — see
  the worked example, §6). Topological-naming selectors will address sketch
  geometry through those ids, so v1 sketches are already name-addressable.
- The evaluation contract (§4) already returns per-feature results keyed by
  feature id, which is where Phase 2 will attach produced-subshape name maps.

What is explicitly **out of scope here:** selector semantics, persistence of
generated-name maps, and rebuild-time name resolution. That is the Phase 2
design doc.

---

## 3. Rollback semantics

Rollback ("roll the bar up the tree") = **evaluate a prefix** of the ordered
feature list. Nothing is deleted or mutated below the bar.

- **Where the state lives:** `parts.rollback_feature_id uuid NULL` — the id of
  the **last included** feature. `NULL` means the bar is at the tip (full
  tree). A feature id, not an order index, so the bar survives renumbering.
- **Semantics:** documents sends geometry only the prefix up to and including
  the bar (§4.2). Features after the bar are still returned by the tree API,
  marked `"rolled_back": true` in the response DTO so the UI can grey them
  out. Editing a rolled-back feature is allowed (that is the point of rolling
  back: insert/edit mid-history); inserting a feature while rolled back
  inserts immediately after the bar and moves the bar to the new feature.
- **Deletion of the bar feature:** `ON DELETE SET NULL` resets the bar to the
  tip. Simple and safe (never dangles); if UX later prefers "bar moves to the
  previous feature", documents can implement that in the delete path without
  a schema change.
- Moving the bar bumps `tree_version` (it changes what an evaluation of this
  part means, so caches must key on it).
- v1 rollback is **per part, not per user** — it is document state. Per-user
  bars (Onshape-style) would move to a user-prefs/session store later and are
  listed as an open question (§7).

---

## 4. Evaluation contract with the geometry service

### 4.1 Shape of the interaction

Geometry is stateless and never touches Postgres (RESEARCH §3); documents
never imports the kernel. Therefore **documents sends the full ordered,
validated, current-version feature list in the request**, and geometry
returns statuses plus **object-storage references** — never kernel types,
never inline meshes in JSON. Transport today is the same sync-HTTP path the
tessellate proxy uses; when the arq queue item lands, the identical
request/response DTOs become the job payload/result (the contract is
transport-agnostic on purpose).

DTOs live in `py_kit.schemas.features` / `py_kit.schemas.geometry` (single
source; both services import them; `just gen` exports them to contracts +
ts-client).

### 4.2 Request

```python
class EvaluateTreeRequest(BaseModel):
    part_id: UUID
    tree_version: int                      # echoed back; cache/correlation key
    features: list[EvaluatedFeatureInput]  # ordered prefix (rollback already applied)
    linear_deflection: float = DEFAULT_LINEAR_DEFLECTION  # presentation param, NOT persisted per feature

class EvaluatedFeatureInput(BaseModel):
    id: UUID                               # feature identity for refs + result keying
    feature: Feature                       # the discriminated envelope from §1.4
```

Notes:

- Documents applies the rollback bar **before** sending: geometry receives
  exactly the list to evaluate, in evaluation order, and never needs to know
  rollback exists.
- All params arrive already upcast to current versions and re-validated by
  FastAPI on the geometry side (same pydantic models — validation is DRY, not
  duplicated).
- Tessellation quality (`linear_deflection`) is a **request-level
  presentation parameter**, consistent with the existing `TessellateRequest`;
  it is never stored inside feature params (§8.3).

### 4.3 Response, partial results, and error surfacing

```python
class FeatureError(BaseModel):
    code: str                    # machine-readable: "profile_not_closed",
                                 # "boolean_failed", "reference_unresolved", …
    message: str                 # human-readable, kernel detail sanitized
    upstream_feature_id: UUID | None  # set when the root cause is an earlier feature's output

class FeatureResult(BaseModel):
    feature_id: UUID
    status: Literal["ok", "error", "skipped"]
    error: FeatureError | None = None

class EvaluateTreeResult(BaseModel):
    part_id: UUID
    tree_version: int
    features: list[FeatureResult]          # same order as the request
    mesh_glb_id: str | None                # object-storage key of the LAST-GOOD body mesh
    properties: ShapeProperties | None     # mass props of the last-good body (existing DTO)
    last_good_feature_id: UUID | None      # which feature the artifact reflects
```

**Partial-result rule (v1, strict prefix):** geometry evaluates features in
order; on the **first** failure it marks that feature `error` and every
subsequent feature `skipped`, then tessellates and uploads the **last-good
body** (the state after the last `ok` body-affecting feature) so the viewport
always has something honest to show. The rule is deliberately blunt:
deterministic, trivially explainable in the UI ("everything after the red
feature didn't run"), and it never presents a body that silently omits a
mid-history feature. Finer-grained skipping (only the failed feature's
dependency closure) is an open question (§7) — it requires deciding what a
body with a hole in its history *means*, which is a product question, not a
transport one.

**Error attachment:** the error rides on the failing feature's
`FeatureResult`, keyed by feature id — documents relays the result to the
client (and later over the gateway WebSocket), and the feature-tree UI pins
the message to the failing row. A feature failure is a **200 response with
per-feature errors** — the py-kit error envelope (4xx/5xx) is reserved for
transport/validation failures of the evaluation call itself, not for
geometry outcomes.

### 4.4 Persistence of evaluation state

Evaluation results are **not** stored in Postgres. They are a pure function
of `(features prefix, linear_deflection)`; documents caches the latest
`EvaluateTreeResult` keyed by `(part_id, tree_version, linear_deflection)`
(Redis, once the queue item lands; in-process until then) and the GLB lives
in object storage under a content-addressed key. Rows in the DB describe only
*intent* (the tree); geometry outcomes stay derivable and disposable. If
product later wants persisted rebuild-status ("part is broken" badges in a
part list), that is an additive cached column, listed in §7.

---

## 5. Alembic migration plan

Alembic is introduced in `services/documents` (env wired to the existing
`POSTGRES_URL` setting from py-kit config; migrations run via a
`just`-invocable target and on service start in dev). Sequencing:

- **`0001_parts`** — owned by the parts-CRUD Ready item (`parts` table:
  id/name/owner/timestamps). This design **depends on it** and does not
  define it.
- **`0002_feature_tree`** — this design. One revision, four operations, in
  order:
  1. `CREATE TABLE features` (§1.2) + `ix_features_part_order`.
  2. `CREATE TABLE feature_dependencies`.
  3. `ALTER TABLE parts ADD COLUMN tree_version bigint NOT NULL DEFAULT 0`.
  4. `ALTER TABLE parts ADD COLUMN rollback_feature_id uuid NULL` +
     `fk_parts_rollback_feature` (added after `features` exists — the
     parts↔features FK pair is circular, so the constraint must be a
     separate op, which alembic handles naturally).

  Downgrade drops in reverse order. No data migration: the tables are new and
  the `parts` additions have defaults, so `0002` is safe on any `0001`
  database, empty or not.
- **Later revisions:** param-shape changes prefer **upcast-on-read** (§1.4);
  a data migration rewriting `params` rows is only written when we want to
  retire an upcast. Such migrations filter `WHERE type = :t AND
  param_version = :v` — one more reason type/version are columns, not JSON
  keys.

Rules of the road (CLAUDE.md): all schema changes via alembic revisions in
`services/documents`, never ad-hoc SQL; geometry remains DB-less so there is
never an alembic tree anywhere else.

## 6. Worked example — one sketch + one extrude

A 40 × 25 mm rectangle on the XY datum plane, extruded 10 mm. Actual rows
(uuids abbreviated for legibility).

**`parts`** (columns from `0001` elided):

```json
{
  "id": "p-7f3a",
  "name": "demo-block",
  "tree_version": 4,
  "rollback_feature_id": null
}
```

**`features` row 1 — the sketch** (`params` is the JSONB column; entity and
constraint shapes are illustrative pending the sketch-model item, §1.4):

```json
{
  "id": "f-aaaa",
  "part_id": "p-7f3a",
  "order_index": 0,
  "name": "Sketch1",
  "type": "sketch",
  "param_version": 1,
  "params": {
    "plane": { "kind": "datum_plane", "plane": "XY" },
    "entities": [
      { "id": "e1", "kind": "line", "start": { "x": 0.0,  "y": 0.0  }, "end": { "x": 40.0, "y": 0.0  } },
      { "id": "e2", "kind": "line", "start": { "x": 40.0, "y": 0.0  }, "end": { "x": 40.0, "y": 25.0 } },
      { "id": "e3", "kind": "line", "start": { "x": 40.0, "y": 25.0 }, "end": { "x": 0.0,  "y": 25.0 } },
      { "id": "e4", "kind": "line", "start": { "x": 0.0,  "y": 25.0 }, "end": { "x": 0.0,  "y": 0.0  } }
    ],
    "constraints": [
      { "kind": "coincident", "a": { "entity": "e1", "point": "end" }, "b": { "entity": "e2", "point": "start" } },
      { "kind": "horizontal", "entity": "e1" },
      { "kind": "vertical",   "entity": "e2" },
      { "kind": "distance",   "entity": "e1", "value_mm": 40.0 },
      { "kind": "distance",   "entity": "e2", "value_mm": 25.0 }
    ]
  }
}
```

**`features` row 2 — the extrude**, referencing the sketch **by feature id**:

```json
{
  "id": "f-bbbb",
  "part_id": "p-7f3a",
  "order_index": 1,
  "name": "Extrude1",
  "type": "extrude",
  "param_version": 1,
  "params": {
    "profile": { "kind": "feature", "feature_id": "f-aaaa" },
    "distance_mm": 10.0,
    "operation": "add",
    "direction": "normal"
  }
}
```

**`feature_dependencies`** (derived on write, §2.3):

```json
{ "feature_id": "f-bbbb", "references_feature_id": "f-aaaa" }
```

Evaluation: documents loads the two rows ordered by `order_index`, validates
into `Feature` envelopes, sends `EvaluateTreeRequest` with the two-element
list; geometry solves the sketch, extrudes 10 mm, uploads the GLB, and returns
both features `ok` with `properties.volume == 10000.0` (mm³) — which is
exactly the shape of assertion the golden-model suite (RESEARCH §9) will make
against this part once the implementation item lands.

Failure flavour of the same example: delete constraint rows until the profile
is open → geometry returns `f-aaaa: ok`,
`f-bbbb: {status: "error", error: {code: "profile_not_closed", …}}`,
`last_good_feature_id: "f-aaaa"`, `mesh_glb_id: null` (no body exists yet),
and the UI pins the error to Extrude1.

## 7. Open questions

Genuinely undecided — none block the implementation item, each gets decided
by its owning item or a groom pass:

1. **Per-user rollback bars.** v1 stores the bar on the part (§3). Multi-user
   editing wants per-user bars in session/user-prefs storage. Decide with the
   collaboration phase.
2. **Feature suppression** (persistent per-feature on/off, distinct from
   rollback). Cheap to add (`suppressed boolean` + skip-with-dependents in
   the prefix builder) but has real dependency-semantics questions; deferred
   until a feature exists that users want to suppress.
3. **Finer-grained partial evaluation** — skip only the failed feature's
   dependency closure instead of the strict-prefix rule (§4.3). Product
   question about what a gap-history body means; revisit when multi-body or
   independent-branch trees exist.
4. **Persisted rebuild status** ("broken" badge on part lists without
   re-evaluating). Additive cached column if wanted; not correctness-bearing.
5. **Expressions/variables in params** (`distance = width/2`). Big,
   deliberately out of v1; would live inside `params` values as a tagged
   union, so the envelope already leaves room.
6. **Multi-body parts.** v1 assumes one body chain per part
   (`mesh_glb_id` singular). Revisit at booleans-between-bodies.
7. **Tree branching/versioned history** (named versions, undo beyond
   rollback). `tree_version` is a fencing counter, not a history mechanism;
   real versioning is a later-phase design.

## 8. Review — anticipated kernel-architect concerns

For the code-reviewer pass (routed by the orchestrator). Each concern with
where the design answers it:

### 8.1 Determinism of evaluation order

- Order is a **total, explicit, persisted** key: dense `order_index` with a
  uniqueness constraint — `ORDER BY order_index` admits no ties, and no
  dict/map iteration order participates anywhere in tree assembly.
- References must point **strictly backward** (§2.2), enforced at write time,
  so evaluation is a single forward pass — no topo-sort whose tie-breaking
  could vary, no cycles possible by construction.
- The failure rule is strict-prefix (§4.3): identical inputs produce identical
  statuses, never "whichever independent features happened to succeed".
- `EvaluateTreeRequest.features` is an ordered list built from that single
  `ORDER BY`; geometry evaluates it as given. Same request bytes → same
  evaluation sequence, which is what the golden suite's byte-level
  determinism gates already assert for tessellation and will assert for tree
  evaluation.

### 8.2 Parameter units

- Persisted params use **fixed canonical units per field**: millimetres for
  lengths, degrees for angles, encoded in the pydantic field name/description
  (`distance_mm`, `value_mm`) — the same convention
  `py_kit.schemas.geometry` already establishes (mm / mm² / mm³; GLB in
  metres per glTF). No per-value unit tags, no unit conversion in documents;
  the geometry service owns the single mm→kernel conversion at the boundary,
  as it does today for the box.
- Because units live in the schema (not the data), a future display-units
  preference is purely presentational and cannot corrupt stored params.

### 8.3 Tolerance handling

- **Feature params never carry tolerances.** Kernel tolerance policy (linear
  1e-7 m, CLAUDE.md) is owned by `services/geometry` and applied uniformly;
  letting documents persist per-feature tolerances would fork that policy
  across a service boundary.
- Tessellation `linear_deflection` is a **request-level presentation
  parameter** (§4.2), mirroring `TessellateRequest` — it affects the mesh
  artifact, never the B-rep evaluation, and is excluded from feature params
  so a quality slider can never dirty a document.
- Golden-suite assertions on tree-evaluated parts use documented per-model
  tolerances (RESEARCH §9 / GEOMETRY-QA), not ad-hoc epsilons — the worked
  example (§6) is written to become such a golden.

### 8.4 Boundary hygiene (standing check)

- No kernel types in any DTO here; geometry artifacts cross the boundary as
  object-storage ids (`mesh_glb_id`) plus the existing pydantic
  `ShapeProperties`. Documents' only new dependency is on
  `py_kit.schemas.features` — kernel-free by construction, same as
  `py_kit.schemas.geometry` today.
- Sketch **solve** determinism (same sketch + constraints → identical
  solution) is the SketchSolver spike's acceptance gate, not re-designed
  here; this contract only guarantees the solver is *invoked* with
  deterministic inputs in a deterministic order.
