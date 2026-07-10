# Feature-Tree Persistence — Design

Status: **revised** (code-reviewer verdict 2026-07-10: request-changes —
design endorsed, schema-integrity findings; all findings addressed in this
revision, resolution log in §8.5). Scope: **design only** — implementation is the
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
    DEFERRABLE INITIALLY DEFERRED,
  -- Composite-FK target: lets every reference TO a feature also pin its part,
  -- making the same-part invariant (§2.2 rule 1) DB-enforced, not app-only.
  CONSTRAINT uq_features_part_id UNIQUE (part_id, id)
);
-- No separate (part_id, order_index) index: the unique index backing
-- uq_features_part_order already serves the ordered range scan.

-- Materialized inter-feature references, derived from params on every write (§2.3)
CREATE TABLE feature_dependencies (
  part_id               uuid NOT NULL,
  feature_id            uuid NOT NULL,
  references_feature_id uuid NOT NULL,
  PRIMARY KEY (feature_id, references_feature_id),
  -- Both endpoints are pinned to the same part via composite FKs (§2.2 rule 1).
  FOREIGN KEY (part_id, feature_id)
    REFERENCES features (part_id, id) ON DELETE CASCADE,
  -- Backstop only (friendly 409 comes from documents' pre-check, §2.3).
  -- Deferred so whole-part CASCADE deletes pass; NOT RESTRICT — see §2.3.
  FOREIGN KEY (part_id, references_feature_id)
    REFERENCES features (part_id, id)
    ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
);

-- Postgres does not auto-index the referencing side of an FK; without this,
-- reverse lookups ("who references X", §2.3) and the RI check fired by a
-- feature delete are sequential scans over feature_dependencies.
CREATE INDEX ix_feature_deps_target
  ON feature_dependencies (references_feature_id);

ALTER TABLE parts
  ADD CONSTRAINT fk_parts_rollback_feature
  FOREIGN KEY (id, rollback_feature_id) REFERENCES features (part_id, id)
  ON DELETE SET NULL (rollback_feature_id);
  -- Composite: the bar can only point at a feature of the SAME part. The
  -- referencing-column list on SET NULL is Postgres 15+; the stack pins
  -- Postgres 16 (CLAUDE.md). MATCH SIMPLE (default) means a NULL bar is
  -- exempt from the check, as intended.
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
*any* tree mutation (feature insert/update/delete/reorder, rename, rollback
move). It serves optimistic concurrency — clients send the expected version
with every write; a stale version is rejected **422** via the py-kit error
envelope (409 stays reserved for the delete-with-dependents conflict, §2.3,
so the two failure modes are distinguishable by status alone) — and keys
evaluation-result caching (§4.4). Renames bump it too: a name-only change
invalidates one cached evaluation for no geometric reason, and that waste is
**accepted for v1** — one uniform "any mutation bumps" rule is worth more
than the cache hit, and carving out exceptions invites drift.

**Authorization:** all feature routes authorize against the **owning part** —
the caller must have access to `part_id`; features carry no ACLs of their own.

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
Upcast rules: every upcast is **total** — it must succeed on any params blob
that validated under the old version (no partial upcasts, no "unmigratable"
rows); the registry enforces **complete chains** at import time (v1→v2→…→
current with no gaps, so lazily-read old rows can always reach the current
shape); and a version bump may introduce a new **required** field only when
its value derives from the old version's implicit behavior (e.g. if extrude
v2 had introduced `direction` as required, the upcast fills the `"normal"`
that v1 semantics implied).

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

1. `feature_id` must exist and belong to the **same part**. This invariant is
   also **DB-enforced**, not app-only: `features` carries `UNIQUE (part_id,
   id)` so composite FKs pin both `feature_dependencies` endpoints and
   `parts.rollback_feature_id` to the owning part (§1.2) — a cross-part
   reference cannot be persisted even by a buggy code path.
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

- **Friendly conflict surfacing — documents' job, not the FK's:** before
  deleting a feature, documents runs a pre-check query (`SELECT feature_id
  FROM feature_dependencies WHERE references_feature_id = :id`, served by
  `ix_feature_deps_target`) and, if rows exist, returns a **409** (py-kit
  envelope) listing the dependents. See §7.11 for the v1-vs-later UX shape.
- **DB-level integrity as backstop only:** the target-side FK is
  `ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED` — checked at **commit**,
  not per row. A lone delete of a still-referenced feature that somehow slips
  past the pre-check still fails at commit, so a code-path bug can never
  silently corrupt the tree; a whole-part delete passes, because by commit
  time the parts→features CASCADE has removed the dependent features and
  (via the `feature_id`-side CASCADE) every edge. Plain `ON DELETE RESTRICT`
  would be wrong here: RESTRICT checks immediately per row and cannot be
  deferred, and the parts→features CASCADE fires RI triggers row by row in
  insertion order — deleting the sketch row trips its trigger while the
  extrude's dependency edge still exists, making **part deletion impossible**
  for any part whose tree contains a reference.
- **Cheap dependency queries:** "what must be re-evaluated / what breaks if I
  edit or delete feature X" is one indexed query
  (`ix_feature_deps_target`, §1.2 — Postgres does not create it for us),
  needed by rollback UX and by future selective re-evaluation.

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
- **Deletion of the bar feature:** `ON DELETE SET NULL (rollback_feature_id)`
  on the composite FK (§1.2) resets the bar to the
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
always has something honest to show. A **body-affecting feature** is one whose
evaluation mutates the part's solid body (extrude add/cut today; fillet,
chamfer, etc. later) as opposed to one that only produces input geometry for
later features (a sketch). The rule is deliberately blunt:
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
  1. `CREATE TABLE features` (§1.2), with both unique constraints —
     `uq_features_part_order` (deferrable; its backing unique index also
     serves the ordered tree load, so no separate index is created) and
     `uq_features_part_id` (the composite-FK target for same-part
     enforcement).
  2. `CREATE TABLE feature_dependencies` (`part_id` column + the two
     composite FKs, the target side `NO ACTION DEFERRABLE INITIALLY
     DEFERRED`) + `CREATE INDEX ix_feature_deps_target` (§1.2 — Postgres
     does not auto-index the FK's referencing side).
  3. `ALTER TABLE parts ADD COLUMN tree_version bigint NOT NULL DEFAULT 0`.
  4. `ALTER TABLE parts ADD COLUMN rollback_feature_id uuid NULL` +
     composite `fk_parts_rollback_feature` with
     `ON DELETE SET NULL (rollback_feature_id)` (added after `features`
     exists — the parts↔features FK pair is circular, so the constraint must
     be a separate op, which alembic handles naturally; the SET NULL column
     list needs Postgres ≥ 15, satisfied by the pinned Postgres 16).

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
{ "part_id": "p-7f3a", "feature_id": "f-bbbb", "references_feature_id": "f-aaaa" }
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
8. **Client mesh-delivery path.** `EvaluateTreeResult` carries `mesh_glb_id`,
   an object-storage key — but today's only GLB path is the tessellate proxy,
   which returns the bytes **inline** through the gateway. Getting an
   evaluated tree's mesh to the browser is a **new** path and it shapes the
   gateway surface (CLAUDE.md: the web app talks only to the gateway):
   gateway streams from object storage vs. presigned URL handed to the client
   vs. documents relaying bytes. Decide in the implementation item, with the
   gateway route as the default posture.
9. **GLB lifecycle / GC.** Content-addressed artifacts (§4.4) are never
   overwritten, so every tree mutation can strand an orphan in object
   storage. v1 accepts unbounded growth in dev; a retention/GC policy
   (refcount vs. age-based sweep keyed on cache keys) is needed before
   self-host guidance calls storage bounded.
10. **Per-feature solved-sketch payload.** The sketcher needs the **solved**
    sketch geometry back (post-constraint positions), not just ok/error.
    That is an **additive `FeatureResult` extension** — e.g. an optional
    per-feature `data` payload populated for sketch features — owned by the
    "Sketch model + solver integration" item; nothing in this contract blocks
    it.
11. **Delete-with-dependents UX.** v1 is the 409-with-dependents-list
    (§2.3): the client must delete or re-point dependents first.
    Cascade-with-confirmation ("delete Sketch1 and 2 dependent features?")
    is a later UX decision implemented in documents' delete path — the
    dependency edges to walk already exist, so **no schema change** is
    needed.

## 8. Review — anticipated kernel-architect concerns

§8.1–8.4 were written ahead of the code-reviewer pass; §8.5 records the pass
itself and how each finding was resolved. Each concern with
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

### 8.5 Review log

**2026-07-10 — code-reviewer: request-changes → revised same day.** The
fundamental design (separate `features` table, versioned envelope, strict
backward references, strict-prefix evaluation) was endorsed ("strong design";
determinism and service boundaries airtight); all findings were
schema-integrity and doc-completeness items, resolved as follows:

- 🔴 **`ON DELETE RESTRICT` on `feature_dependencies.references_feature_id`
  broke part deletion** — the parts→features CASCADE fires RI triggers per
  row in insertion order, so the sketch's trigger sees the not-yet-deleted
  extrude edge and errors. **Resolved:** target-side FK is now `ON DELETE NO
  ACTION DEFERRABLE INITIALLY DEFERRED` (commit-time check — whole-part
  deletes pass, lone deletes of referenced features still fail as a
  corruption backstop), and §2.3 now states the friendly 409-with-dependents
  comes from documents' pre-check query, with the FK as backstop only.
- 🟡 **Reverse-lookup index missing** — Postgres does not auto-index the
  referencing side of an FK, so the "one indexed query" claim was false.
  **Resolved:** `ix_feature_deps_target` added to §1.2 and the migration
  plan (§5).
- 🟡 **Same-part invariants were app-level only.** **Resolved with the
  DB-enforced option:** `UNIQUE (part_id, id)` on `features`; composite FK
  `(id, rollback_feature_id) → features (part_id, id)` for the rollback bar;
  `part_id` column on `feature_dependencies` with composite FKs on both
  endpoints (§1.2, §2.2 rule 1). No blocker found; the doc's stated reason
  for the side table is DB-enforceable integrity, so it is DB-enforced.
- 🟡 **Missing open questions.** **Resolved:** §7.8–7.11 added — client
  mesh-delivery path (new gateway-shaping path vs. today's inline-GLB flow),
  GLB lifecycle/GC, per-feature solved-sketch payload (additive
  `FeatureResult` extension), delete-with-dependents UX (409-with-list v1,
  cascade-with-confirmation later without schema change).
- 🟢 (all taken): redundant `ix_features_part_order` dropped (the unique
  constraint's backing index serves the scan); rename-bumps-`tree_version`
  waste explicitly accepted for v1 (§1.2); upcast-totality rule added
  (§1.4); "body-affecting feature" defined (§4.3); stale-version writes →
  **422** envelope, keeping 409 for dependents conflicts (§1.2); feature
  routes authorize against the owning part (§1.2).
