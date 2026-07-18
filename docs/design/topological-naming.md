# Topological Naming — Design

Status: **stage-1 PLANAR-FACE signature IMPLEMENTED for datum-from-face**
(2026-07-12; §9) **+ stage-1 EDGE signature IMPLEMENTED for click-specific
fillet/chamfer** (2026-07-13, backend + schema; see §10 scoping delta and
`docs/GEOMETRY-QA.md`). The rest — vertex signatures, the stage-2 provenance
half, and the in-viewport picker (the edge-pick UI slice) — remains design-only.
Originally: **revised after
code-reviewer request-changes** (2026-07-11; see §8 review log). This doc
specifies how a
`SubshapeRef` (the variant reserved by
[`docs/design/feature-tree.md`](./feature-tree.md) §2.4) identifies a specific
**face / edge / vertex of a feature's result, stably across feature-tree
re-evaluation**, and how that reference degrades honestly when a rebuild
invalidates it.

This is the problem that sinks parametric CAD projects. FreeCAD shipped for a
decade with "the topological naming problem" as its most-reported class of
bug; Onshape's founders cite solving it (Parasolid + a naming layer) as a core
reason the company exists. We do **not** improvise it — hence a design doc
reviewed before a line of kernel code (CLAUDE.md: hard problems get a design
doc first).

Related: RESEARCH §1 (OCCT via OCP, build123d), §9 (determinism + golden
gates); feature-tree §2.4 (the reserved `SubshapeRef` / `EdgeSelector` slot and
the additive-union rule), §4.3 (strict-prefix failure), §2.3 (materialized
`feature_dependencies`). Unblocks the Next-queue "face/edge picking" item and
every feature that persists a picked reference (hole-on-face, shell, draft,
pattern-by-edge, click-specific fillet/chamfer).

---

## 1. The problem, concretely

### 1.1 OCCT subshape ordering is a function of construction history, not geometry

A `TopoDS_Shape` is a tree of `TShape` nodes; subshapes are enumerated
(`TopExp_Explorer`, `TopExp::MapShapes`) in the order those nodes appear in
their parents' child lists. **That order is an artifact of the sequence of
kernel operations that built the shape, not a stable property of the geometry.**
Two consequences:

- **`HashCode` is session-local.** `TopoDS_Shape`'s hash derives from the
  underlying `TShape` pointer plus the location/orientation. A fresh rebuild
  allocates new `TShape`s, so the same geometric edge hashes differently across
  two evaluations. It is an in-memory identity, useless for persistence.
- **Booleans and re-runs renumber.** `BRepAlgoAPI_*` (cut/fuse/common) mint
  brand-new faces and edges along intersection curves; a fillet
  (`BRepFilletAPI_MakeFillet`) deletes the rounded edge and generates a new
  cylindrical face plus new boundary edges. The enumeration index of "the edge
  I care about" is not preserved when anything upstream changes the operation
  sequence — and OCCT makes **no cross-version guarantee** that even an
  identical build enumerates identically.

So an index into `TopExp_Explorer(shape, TopAbs_EDGE)` is **not a name**. It is
a position in a list whose order the kernel is free to change.

### 1.2 Geometric predicates cannot isolate one member of a symmetric set

Today's shipped `EdgeSelector` (`py_kit.schemas.features`) is honest and
deliberately limited (feature-tree §2.4):

- `all_edges` — every edge of the current body;
- `axis_parallel(axis)` — every straight edge parallel to a world axis.

These are **re-selection by geometry each rebuild**, which is why they survive
rebuilds without a name map at all — a real strength. But they select *sets*.
On an upright 40×25×10 plate, the four vertical edges **all** satisfy
`axis_parallel: "Z"`. There is no predicate in this vocabulary — and no obvious
one we could add — that means *"the front-left vertical edge, and not the other
three."* Enriching the vocabulary with positional predicates ("the Z-edge
nearest point P") is not a different category of solution: it **is** the
geometric-signature approach (§2b) wearing a predicate's clothes, and it still
cannot discriminate two truly congruent members of a symmetric part without a
tie-breaker. Predicates answer *"which edges match this rule";* naming must
answer *"which specific edge is this one,"* and those are different questions.

### 1.3 Worked failure — the silent retarget (why index-based is dangerous)

Take the `fillet-plate-r5` golden: a 40×25×10 plate, fillet radius 5 on the
front-top edge (the edge shared by the `+Z` top face and the `−Y` front face).
Suppose the fillet stored its target as **edge index 6** from
`TopExp_Explorer(EDGE)`.

Now the user inserts an **upstream** feature — say a small chamfer on a bottom
edge, or edits the sketch to add a corner notch — *before* the fillet in the
tree. On rebuild:

- The solid is reconstructed by a different operation sequence. The notch adds
  edges; the boolean renumbers. `TopExp_Explorer(EDGE)` now yields a different
  order.
- **Edge index 6 now refers to a different physical edge** — say the back-top
  edge. `MakeFillet.Add(edge_6)` succeeds. The rebuild produces a *valid,
  closed, plausible-looking body with the fillet on the wrong edge.* The
  closed-body check passes. Nothing errors.

This is the **silent retarget** — the single worst failure mode in parametric
CAD. Our golden suite would catch it (the `fillet-plate-r5` mass properties
would drift), but **a user's own part has no golden.** They edit history,
glance at the viewport, see a fillet, and ship a wrong part. Trust is gone.

The only "better" index outcome is the *loud* one: if the upstream edit removed
enough edges that index 6 is now out of range, `Add` throws and the feature
hard-errors. Loud-and-wrong beats silent-and-wrong, but a naming scheme whose
best case is "crashes instead of corrupting" is not a naming scheme.

The design goal, stated as a rule: **a reference must resolve to the same
geometric entity across rebuilds, or fail honestly (§5). It must never silently
retarget.** Be precise about what "never" costs, because the two stages earn it
differently:

- **Index-based retarget is _structural_** — an index is a position in a list
  the kernel reorders freely, so a wrong-but-valid target is the *expected*
  outcome of any upstream perturbation. That is what §1.3 rejects outright.
- **Signature-based retarget (stage 1) is _residual_, not structural.** A
  geometric fingerprint is not a stable list position, so the failure mode is
  usually *honest*: the intended subshape moves out of tolerance → zero match →
  `subshape_unresolved`, or a symmetric twin matches too → `subshape_ambiguous`.
  But there is one residual silent hole (§2b, §5): the intended subshape moves
  **out** of tolerance while a *different* subshape coincidentally lands
  **within** tolerance of the stored signature. That is a **unique** match, so
  the exactly-one-or-error rule (§7.2) sees no ambiguity and returns the wrong
  entity silently. Stage 1 makes this **unlikely and mostly honest-failing**;
  it does **not** make it structurally impossible.
- **Provenance-based non-retarget (stage 2) _is_ structural.** Provenance
  replay never inspects coordinates — it follows the operation's own
  `Modified`/`Generated` maps from stable anchors (§2c) — so a geometry move
  *cannot* make it latch onto a coincidentally-nearby entity, and the §2d
  step-4 signature cross-check catches the degenerate remainder. The structural
  "never silently retargets" guarantee therefore belongs to **stage 2**; stage
  1 approximates it.

---

## 2. Approaches considered

Each approach is scored on the same worked cases — the `fillet-plate-r5` edge
above, and a **hole-on-face** case (a hole placed on the `+Z` top face of the
40×25×10 plate, the archetype for the Next-queue hole feature) — for
**survival** under an upstream edit, **storage shape**, and **cost**.

### 2a. Index-based (OCCT enumeration order)

Store the integer index from `TopExp_Explorer`.

- **Fillet-plate:** `{ "edge_index": 6 }`. Survives *nothing* — §1.3 is the
  worked failure. An upstream insert, a reorder, or a parametric change that
  perturbs the operation sequence retargets or breaks it.
- **Hole-on-face:** `{ "face_index": 4 }` for the top face. Same fate: any
  upstream topology change re-orders faces and the hole migrates to a side
  face, silently.
- **Storage:** one integer. Cheapest possible.
- **Cost:** O(1) resolve. But it **violates the cardinal rule** (silent
  retarget). Rejected as a persisted identity; used by no serious parametric
  kernel for this purpose.

### 2b. Geometric signature (position + type + adjacency fingerprint)

Fingerprint the subshape by tolerance-robust geometric invariants and re-match
against all candidates on rebuild. A signature for an edge:

```
{ "type": "edge",
  "curve": "line",                 # line | circle | ellipse | bspline | ...
  "point": [20.0, 0.0, 10.0],      # canonical sample: edge midpoint (full precision)
  "length": 40.0,
  "adjacent_faces": [              # sorted, each a mini face-signature
    { "surface": "plane", "normal": [0,0,1] },     # the +Z top face
    { "surface": "plane", "normal": [0,-1,0] } ] }  # the −Y front face
```

Resolution: recompute the signature of every edge of the rebuilt body, keep
those within tolerance on every field, and require **exactly one** match
(§7.2 — refuse to guess between ties; that is the determinism contract).

- **Fillet-plate:** the front-top edge keeps `curve=line`, `length=40`, its
  adjacency (top plane + front plane). Survives an upstream edit that does not
  touch this edge's neighborhood (adding the bottom chamfer leaves the top-front
  edge's midpoint, length, and two neighbor faces unchanged) → unique match,
  resolves. **Fails** when the edit *moves* the edge: change the plate width
  40→60 and the midpoint moves to `[30,0,10]`, length→60; a naive
  exact-point/length match misses. Adjacency-only matching helps but a
  symmetric part yields **two** edges with an identical signature → ambiguous
  → honest error (the usual, redeeming outcome). **The residual silent hole
  (§1.3):** if the width edit pushes the target *out* of tolerance while some
  *other* edge happens to fall *within* tolerance of the stored signature, that
  is a lone match — the exactly-one rule (§7.2) fires no ambiguity and returns
  the wrong edge silently. Signature matching makes this rare and mostly
  honest-failing, not impossible; only provenance (2c) forecloses it
  structurally.
- **Hole-on-face:** signature of the `+Z` top face = `{surface: plane, normal:
  [0,0,1], area, centroid}`. Survives upstream edits that keep a single planar
  top face; fails / goes ambiguous if the upstream feature splits the top face
  into two coplanar faces (both share the normal).
- **Storage:** a structured blob (type + curve/surface kind + canonical point +
  metric + sorted neighbor descriptors), or a hash of its canonical form.
  Moderate.
- **Cost:** O(n) recompute + match per rebuild; **determinism risk lives here**
  and is the reviewer's sharpest concern (§7.2). Its honest virtue: matching is
  *by geometry*, so it needs **no captured history** — it works even for
  operations we have not instrumented, which makes it the ideal **fallback**.

### 2c. OCCT history API (`Modified` / `Generated` / `Deleted`, `BRepTools_History`, `TNaming`)

Name a subshape by its **generative provenance** — *what operation made it, out
of what inputs* — and follow OCCT's own evolution maps across a rebuild instead
of re-recognizing geometry. Every OCCT maker exposes `Modified(s)`,
`Generated(s)`, `IsDeleted(s)`; `BRepTools_History` accumulates these across an
operation chain; `TNaming` (OCAF) is the full framework that stores named
shapes and replays the naming after regeneration.

The key move: **anchor the name to entities that are already stable across
rebuilds** — the sketch-local entity ids (`e1`, `e2`, … — feature-tree §2.4,
already persisted and name-addressable) and the *roles* an operation assigns
its outputs (extrude's "start cap" / "end cap" / "side wall from profile
segment X").

- **Fillet-plate:** the front-top target edge is named *"the edge shared by the
  face generated from sketch-segment `e1` and the top cap face of Extrude1."*
  Both anchors are stable: `e1` is a persisted sketch id; "top cap of Extrude1"
  is a semantic role, not an enumeration index. On an upstream edit (insert the
  bottom chamfer, or change the extrude distance), the side wall is still
  `Generated` from `e1` and the top cap is still the extrude's end cap — the
  provenance is unchanged, so we follow `Generated`/`Modified` to the current
  edge regardless of how enumeration reshuffled. Survives parametric moves that
  defeat 2b, because it never looked at coordinates.
- **Hole-on-face:** the placement face is *"the top cap face of Extrude1"* —
  survives distance changes, upstream inserts, even width changes, because the
  cap-of-Extrude1 role is invariant.
- **Where it's hard (honest):** *topology-changing* upstream edits. If an
  upstream feature **splits** the face our edge borders, `Modified` maps
  one→many and provenance alone can't say which fragment; if a boolean
  **merges** two faces, many→one. These one↔many junctions are exactly where
  real CAD toponaming still has bugs, and where a disambiguator (2b as a
  tiebreak) earns its place.
- **Storage:** a structured provenance name — originating `feature_id` +
  subshape type + a role/anchor descriptor keyed on stable sketch-entity ids
  and operation roles + `selector_version`. Larger, structured, kernel-free
  (all strings/ids/enums — no `TopoDS` anything crosses the boundary).
- **Cost:** the real engineering cost. We must **capture** `Modified`/
  `Generated` maps at every body-affecting operation during evaluation and
  **replay** them on rebuild. Reachability nuance (verified, §7.1):
  build123d hands back finished `Solid`s and **discards the underlying maker**,
  so we capture history at our own OCP maker boundary inside `services/geometry`
  (we own the kernel layer — allowed). Whether the full `TNaming`/OCAF machinery
  or a hand-rolled `BRepTools_History` chain is the right weight is a **spike**
  (§6.2). This is the only approach that yields **true stable identity** rather
  than best-effort re-recognition.

### 2d. Hybrid — provenance-anchored name, geometric signature as fallback/validator

Store **both**: a provenance name (2c) as the primary identity, and a geometric
signature (2b) alongside. Resolution order:

1. Replay history from the originating feature; if provenance resolves to a
   **unique** subshape, done.
2. If provenance is **ambiguous** (a one→many split junction), use the stored
   signature to pick the fragment whose geometry matches — deterministic
   tie-break, or honest error if the signature *also* ties. **This tie-break is
   stage-2-only:** it disambiguates a provenance one→many where the candidate
   set is already pinned to genuine fragments of the named entity. It is **not**
   a licence for pure signature matching to guess — see the determinism note
   below.
3. If history is **unavailable** (an operation not yet instrumented, or a
   legacy stage-1 / `selector_version: 1` ref written before capture existed),
   fall back to pure signature matching (2b). Pure signature matching (this
   step, and all of stage 1) **never tie-breaks** — ≥2 in-tolerance candidates
   is always `subshape_ambiguous` (§7.2), because signature-only has no
   provenance-pinned candidate set to break the tie *within*.
4. **Cross-check:** if provenance resolves to a subshape whose signature
   diverges wildly from the stored one, flag low-confidence rather than trust
   blindly — this is the step that recovers the structural non-retarget
   guarantee against a degenerate provenance replay.
5. If nothing resolves uniquely → §5 honest failure.

**Determinism distinction (crisp):** signature is used **two different ways**.
As stage 1's *sole* identity it is a strict exactly-one filter that errors on a
tie (never guesses). As stage 2's *disambiguator* it breaks a provenance
one→many by choosing the geometrically-matching fragment — a deterministic
tie-break over an already-provenance-restricted set — and errors only when the
signature ties too. Same function, two roles: stage 1 refuses to guess; stage 2
may pick, but only among fragments provenance has already vouched for.

- **Fillet-plate / hole-on-face:** best of both — provenance survives the
  parametric moves that defeat 2b, and the signature disambiguates the
  symmetric/split cases that defeat 2c.
- **Storage:** provenance name + signature + `selector_version`. Largest.
- **Cost:** highest (both must be produced and, on resolve, both consulted) —
  but the signature half ships **first** and cheaply (2b needs no history
  capture), and the provenance half is added as a new member of the same
  versioned `Selector` union without a schema break (§4). This is the staged
  path §3 adopts.

---

## 3. Decision + rejected alternatives

**Decision: adopt the hybrid (2d) as the target architecture — a
provenance-anchored name with a geometric signature as disambiguator and
fallback — and deliver it in two stages under a single typed, version-
discriminated `SubshapeRef.selector` union (§4) so the stage boundary is an
additive union member, invisible to storage and callers.**

- **Stage 1 (ships with "face/edge picking"): geometric signature only (2b).**
  It unblocks the product goal *now* — a working engineer clicks a face or
  edge, we persist its signature, and it survives the common edits (upstream
  inserts, parametric changes that don't move the target). It is honest about
  its limits (symmetric ambiguity and moved geometry usually surface as an
  honest §5 error — `subshape_ambiguous` / `subshape_unresolved`), and —
  critically — it needs **no** kernel-history instrumentation, so it is
  buildable against build123d results as they exist today. It is **best-effort,
  not structurally non-retargeting**: the §1.3 residual hole (target moves out
  of tolerance while a different subshape moves in → lone wrong match) remains
  possible until stage 2's provenance closes it; the picking item ships
  mis-resolve telemetry / a guard sized by the §6.3 spike. `SubshapeRef`'s
  `selector` carries the signature at `selector_version: 1`.
- **Stage 2 (after the history-capture spike, §6): promote to full hybrid
  (2c primary + 2b fallback).** Add `Modified`/`Generated` capture at the OCP
  maker boundary; extend the selector payload with the provenance name at
  `selector_version: 2`. Signatures written at v1 keep resolving via step 3 of
  the 2d resolution order, so **no data migration is forced** — v1 refs are
  a legal degenerate hybrid (fallback-only).

**Why this ordering, against the operating question** ("Would a working
engineer model a real part in this today?"):

- Signature-first gets *clickable, mostly-durable* references into users' hands
  in the next feature, instead of blocking picking on the multi-month history
  layer. That is the difference between "can I select an edge this quarter" and
  "not yet."
- Provenance-later earns the robustness that keeps references alive under
  aggressive history editing — the property that separates a toy from a daily
  driver — and *upgrades* stage 1's best-effort honesty into the **structural**
  non-retarget guarantee (§1.3). Stage 1 never ships an *index-based* scheme
  (the §1.3 structural corruption); its residual signature hole is rare,
  telemetry-guarded, and closed by stage 2 rather than left standing.
- Both stages honor **determinism is a feature** (RESEARCH §9): resolution is a
  pure, total-ordered function of the tree; ambiguity is an honest error, never
  a coin flip (§7.2).

**Rejected as the persisted identity:**

- **2a index-based — rejected outright.** Silent retarget (§1.3) violates the
  cardinal rule. No serious parametric kernel persists enumeration indices.
- **2b signature *as the permanent answer* — rejected as the endpoint, adopted
  as stage 1 + fallback.** Pure geometric matching is what CADQuery-style
  selectors do and is genuinely fragile under parametric change (moved geometry,
  symmetric ties). Good enough to ship first and to backstop history; not good
  enough to be the whole story for a daily driver.
- **2c history *alone* — rejected as insufficient.** True identity, but the
  one↔many split/merge junctions need a disambiguator, and an uninstrumented
  operation would leave a ref with no way to resolve. It needs 2b beside it,
  which is why the decision is 2d, not 2c.
- **Full `TNaming`/OCAF as the mandated mechanism — deferred to the spike.**
  `TNaming` is reachable (§7.1) but drags the OCAF document model (`TDocStd`)
  into an otherwise document-less, stateless geometry service. Whether we adopt
  OCAF or hand-roll `BRepTools_History` tracking is an implementation choice the
  §6.2 spike settles; this doc commits to the *provenance model*, not to OCAF.

---

## 4. Migration path from v1 `EdgeSelector`

The decision is **purely additive** — no persisted selector changes shape, no
`param_version` churn, exactly as feature-tree §2.4 promised.

- **`EdgeSelector` gains a `kind: "subshape"` member.** Today it is
  `Annotated[AllEdgesSelector | AxisParallelEdgesSelector,
  Field(discriminator="kind")]`. Stage 1 adds a third variant carrying a
  `SubshapeRef`. Because the union discriminates on `kind`, every persisted
  `all_edges` / `axis_parallel` row still validates unchanged — a new union
  member is **additive** under the feature-tree §1.4 rule ("additive changes do
  not bump version"), so **fillet/chamfer `param_version` stays 1.** No
  `0002`-style data migration, no rewrite of existing rows.
- **`GeomRef` gains its reserved `SubshapeRef` member** for
  subshape-of-a-feature references (sketch-on-face, hole-on-face). The stub
  reserved in feature-tree §2.4 becomes concrete; same additive-union
  reasoning; no sketch/extrude `param_version` bump.
- **The selector payload is versioned *independently* of `param_version`.**
  `selector_version` is the **discriminator of the typed `Selector` union**
  (below), not a loose sibling int over an opaque blob. Stage 1 → stage 2
  (signature-only → hybrid) adds a `SelectorV2` union member, decoupled from
  feature `param_version` entirely — the elegant part of the reservation. This
  is the one place `param_version`'s upcast machinery (feature-tree §1.4) does
  **not** apply; the selector carries its own version and resolves
  fallback-first for older (`selector_version: 1`) selectors (§3 stage 2).
- **`SubshapeRef.feature_id` joins the dependency graph — with a stage-shifting
  definition, stated precisely.** Unlike today's fillet/chamfer (which carry no
  `FeatureRef` and depend on the prior body only by tree order — feature-tree
  §2.4, `feature_references()` → empty set), a `SubshapeRef` names a subshape
  *of a specific feature's result*, so its `feature_id` **materializes into
  `feature_dependencies`** (feature-tree §2.3) like a `FeatureRef`: the
  write-time 409-with-dependents pre-check protects that feature from deletion,
  and reorder re-checks the strict-backward rule (§2.2 rule 2) for named refs
  too. **But which feature `feature_id` names differs by stage, and this must
  be said plainly:**
  - **Stage 1 (signature-only):** the signature is matched against the **whole
    current body** at the selecting feature's point in the tree. There is no
    provenance, so `feature_id` is **"the prior body-affecting feature whose
    body I signature-match against"** — the tip of the body chain the selector
    sees — *not necessarily the true originating feature* of the subshape (the
    edge may have been born several features earlier). It is the honest v1
    anchor: the feature whose result the match is performed on.
  - **Stage 2 (provenance):** `feature_id` shifts to the **true originating
    feature** — the operation that generated the subshape, possibly several
    features earlier than the stage-1 body-chain tip.
  - **Consequence for the graph (no data migration, but a real edge shift):**
    for the *same user pick*, the materialized `feature_dependencies` edge — and
    therefore *which* feature the 409 protects — **can differ between v1 and
    v2**. This does **not** force a data migration (v1 refs keep resolving,
    fallback-first — §3), but the dependency the graph records is
    stage-dependent, and a v1→v2 selector upgrade may re-point that edge. Flag,
    not defect: the protected feature only ever moves *earlier* in the chain
    (originating feature is an ancestor of the body-chain tip), so no dependent
    is ever left unprotected.
- **Wiring `feature_id` into `feature_dependencies` is NOT "purely additive like
  a `FeatureRef`" — it touches shipped self-checking helpers.** The reserved
  §2.4 stub reads as if a `SubshapeRef` slots in for free; it does not. Three
  shipped, self-consistency-asserting helpers in
  `py_kit/schemas/features.py` need **real** (still-additive-on-the-wire, but
  code-changing) edits:
  - `iter_feature_refs` yields **only** `FeatureRef` today (`isinstance(value,
    FeatureRef)`); it must widen to also yield a `SubshapeRef`'s `feature_id`
    (or the walk must surface both ref kinds) or the graph silently drops
    named-ref edges.
  - `FeatureReference.ref` is typed `FeatureRef`; it must widen to a
    `FeatureRef | SubshapeRef` union (or the slot-map must carry a bare
    `feature_id` + kind) so `feature_references()` can surface a `SubshapeRef`
    slot.
  - The `walked == mapped` self-consistency assert in `feature_references()`
    compares the generic walk against the hand-written slot map; **both sides
    must learn about `SubshapeRef` together**, or the assert fires. That assert
    is exactly the guard that makes this non-additive visible — it will reject a
    half-done wiring, which is the point.
  Net: on the *wire / persisted shape* the `kind: "subshape"` union member is
  additive (no `param_version` bump); in the *dependency-extraction code* it is
  a genuine widening of three typed helpers, and the doc says so.

Illustrative stage-1 shape (final field names owned by the implementation item).
The selector is **typed and versioned** — a `selector_version`-discriminated
union, *not* `dict[str, Any]` — so pydantic validates the payload at the service
boundary and the generated TS client is typed (CLAUDE.md strict typing; no
unjustified `Any`). The discriminator is decoupled from `param_version` and the
union stays additive: stage 2 adds a `SelectorV2` member without disturbing
persisted `SelectorV1` rows.

```python
class SubshapeSignature(BaseModel):
    """§2b fingerprint — typed, kernel-free (no TopoDS)."""
    subshape_type: Literal["face", "edge", "vertex"]
    # curve/surface kind, canonical sample point, metric, sorted neighbour
    # descriptors — full-precision (§7.2); exact fields owned by the impl item.

class SelectorV1(BaseModel):
    selector_version: Literal[1]
    signature: SubshapeSignature

class SelectorV2(BaseModel):
    selector_version: Literal[2]
    signature: SubshapeSignature          # retained as fallback + §2d validator
    provenance: ProvenanceName            # §2c: originating feature + role/anchor ids

Selector = Annotated[
    SelectorV1 | SelectorV2, Field(discriminator="selector_version")
]

class SubshapeRef(BaseModel):
    kind: Literal["subshape"]
    feature_id: UUID                      # → deps graph; see the stage-shift note above
    subshape_type: Literal["face", "edge", "vertex"]
    selector: Selector                    # typed, version-discriminated union
```

> **Fidelity delta flagged:** the feature-tree §2.4 reserved stub sketches a
> bare `SubshapeRef` without a `subshape_type` field; adding
> `subshape_type: Literal["face","edge","vertex"]` (mirrored on the signature)
> is a small, harmless **addition** to that stub. This doc otherwise claims
> strict fidelity to the reservation, so the delta is called out rather than
> smuggled in. Whether `subshape_type` lives on `SubshapeRef`, on the signature,
> or (redundantly) both is an impl-item choice.

If deferring any selector-payload validation to the resolver is later preferred
over the typed union, that is a deliberate trade requiring its own
justification (it re-introduces an `Any` boundary and a TS-client hole); the
resolver would then need to distinguish a **malformed** selector
(`subshape_reference_invalid`, a data/authoring bug) from an **honest
unresolved** one (`subshape_unresolved`, §5). The typed union is preferred
precisely because it makes that distinction a boundary-validation error, not a
resolver heuristic.

---

## 5. Failure semantics — mirror the §4.3 strict-prefix rule

A named ref fails to resolve when, on a rebuild, the resolver finds **zero**
matching subshapes, **more than one** within tolerance (refuse to guess —
§7.2), or the **originating feature is gone or changed type** so provenance
replay dead-ends. This is not new machinery: it reuses feature-tree §4.3
verbatim.

- The **selecting feature** (the fillet/hole/shell that owns the ref) evaluates
  to `status: "error"` with a `FeatureError`. Distinct machine codes so the UI
  and tests can tell the modes apart:
  - `subshape_unresolved` — zero candidates match (the named entity no longer
    exists);
  - `subshape_ambiguous` — two or more candidates within tolerance and no
    deterministic tie-break resolves them (determinism mandate: never pick one
    at random);
  - `subshape_reference_invalid` — the originating `feature_id` was deleted or
    re-typed (should be caught earlier by the §2.3 409 pre-check; this is the
    evaluation-time backstop).
  `upstream_feature_id` is set to the originating feature so the message can
  name the true cause.
- **Strict prefix (§4.3):** the failing feature is `error`; **every subsequent
  feature is `skipped`**; geometry tessellates and uploads the **last-good
  body** (the state *before* the failing feature) so the viewport always shows
  something honest. Identical inputs → identical statuses (determinism), never
  "whichever features happened to still resolve."
- **UI (mirrors the extrude/fillet error path already shipped):** the
  feature-tree row pins the message — *"Fillet1: the referenced edge no longer
  exists after editing Extrude1"* — downstream rows grey out (`rolled_back`-style
  muted token), and the viewport shows the last-good body with a non-blocking
  banner. The user rolls the bar to the failing feature and re-picks the edge,
  or edits the upstream feature back to a state where the ref resolves. **No
  _index-based_ silent retarget** — the §1.3 *structural* failure is excluded at
  both stages because we never persist an enumeration index, and ambiguity is an
  error, not a guess. The **residual signature retarget** (target moves out of
  tolerance while a different subshape moves in → lone wrong match, §1.3/§2b) is
  the one silent hole stage 1 does not fully close: it is rare and mostly
  surfaces as `subshape_unresolved`/`subshape_ambiguous` where detectable, but a
  unique wrong match is *not* detectable from geometry alone. Stage 2's
  coordinate-blind provenance replay (plus the §2d cross-check) closes it
  structurally. Stage 1 therefore ships the §6.3-sized mis-resolve telemetry so
  the residual is *observed*, not merely asserted away.
- **Consistency with `FeatureRef` deletion:** because `SubshapeRef.feature_id`
  materializes into `feature_dependencies` (§4), deleting the originating
  feature is *already* a write-time 409-with-dependents (feature-tree §2.3) —
  the user is stopped before evaluation, and `subshape_reference_invalid` only
  fires on a path that slips the pre-check (a corruption backstop, like the
  §2.3 FK).

---

## 6. Open questions / follow-up spikes

Each is genuinely undecided and owned by the implementation item it names; none
blocks *this* design's endorsement.

1. **History-capture reachability across a build123d-built tree (blocking for
   stage 2).** The OCP surface is present (§7.1), but build123d discards the
   maker after each operation, so we must capture `Modified`/`Generated` at our
   own OCP maker boundary. Spike: confirm we can wrap build123d's body-affecting
   operations (extrude, fillet, chamfer, boolean) to retain the maker and
   accumulate a coherent `BRepTools_History` across the whole feature chain —
   or that we drop to OCP makers in our kernel wrappers where build123d won't
   expose it. **Verdict gates stage 2.**
2. **`TNaming`/OCAF vs. hand-rolled `BRepTools_History`.** OCAF is the
   "official" naming framework but pulls a document model (`TDocStd`) into a
   stateless, document-less service. Spike both weights; default lean is
   hand-rolled `BRepTools_History` tracking (no OCAF document), promoted only if
   OCAF's replay demonstrably beats it on the split/merge junctions.
3. **Signature determinism *and mis-resolve rate* under tolerance, measured on
   goldens.** Confirm the `fillet-plate-r5` / `chamfer-plate-d5` bodies produce
   **stable, unique** edge/face signatures across rebuilds at the documented
   per-model tolerance (RESEARCH §9), and quantify **two** separations, not one:
   (a) how close two *distinct* edges get before the ambiguity rule fires (the
   §7.2 tolerance policy); and (b) — the residual silent hole (§1.3/§2b) — under
   a *parametric move* of the target, **how often a moved target yields a unique
   but WRONG match** (target out of tolerance, a different subshape in). (b)
   sizes the mis-resolve telemetry/guard the picking item must ship, since a
   lone wrong match is invisible to the ambiguity rule. Produces a new
   `subshape-ref-<name>` golden (new capability ⇒ new golden, per the DoD),
   asserting *both* that intended targets resolve and that the mis-resolve rate
   stays within the measured, documented bound.
4. **Truly symmetric selections.** Four congruent edges with identical
   signatures *and* identical provenance roles (a 4-fold-symmetric part) cannot
   be told apart by either half of the hybrid. The pick UI must then store an
   explicit discriminator (e.g. a canonical index into the deterministically
   ordered congruence class) — decide the discriminator shape with the picking
   item; it lives inside the typed `selector` union.
5. **The cross-rebuild stability *guarantee* we publish.** Define a tiered
   contract users can rely on, stated honestly per stage:
   - **(T0)** parametric-value edits that don't move the target — **guaranteed**
     to resolve, both stages.
   - **(T1)** upstream inserts that don't touch the target's neighborhood —
     **guaranteed at stage 2**; **best-effort at stage 1** (a lone wrong match
     is possible — §1.3 — surfaced as `subshape_unresolved`/`subshape_ambiguous`
     only *where detectable*, not always).
   - **(T2)** topology-changing edits in the neighborhood (split/merge) —
     **best-effort at both stages**, with an honest §5 error on failure.
   The load-bearing honesty: at **stage 2** T1/T2 carry the *structural*
   non-retarget guarantee (coordinate-blind provenance + §2d cross-check); at
   **stage 1** T1/T2 are best-effort with a **residual mis-resolve possible** —
   NOT "never silent." Publishing that distinction, rather than overselling
   stage 1, is the daily-driver promise.
6. **Sketch-entity id stability under sketch edits.** Stage-2 provenance anchors
   on sketch-local ids (`e1`…). If the user deletes and redraws an entity, its
   id may change and every downstream provenance name breaks. How stable are
   sketch entity ids across sketch edits? Ties to the sketch-model item; may
   need id-preserving sketch edits.
7. **Persistence of produced-subshape name maps.** feature-tree §2.4 says
   evaluation results (keyed by feature id) are "where Phase 2 will attach
   produced-subshape name maps." Do we **persist** those maps or **recompute**
   them every evaluation? Lean: **recompute** — geometry stays stateless
   (RESEARCH §3) and names are a pure function of the tree, so a map is
   derivable, never stored. Confirm the recompute cost fits the performance
   budget (RESEARCH §9) on a deep tree.
8. **Stage-1 `feature_id` definition + the v1→v2 dependency-edge shift.** Stage
   1 anchors `SubshapeRef.feature_id` on the **body-chain tip the signature is
   matched against**, not the true originating feature (§4). Confirm this is the
   right v1 anchor for the `feature_dependencies` edge (and thus the 409 target),
   and specify the v1→v2 migration behaviour when the edge re-points to the
   originating (earlier) feature: does an in-place selector upgrade rewrite the
   materialized edge, or is it recomputed on next evaluation? Owned by the
   picking item + the stage-2 provenance item jointly.
9. **Residual false-unique-match risk (the stage-1 silent hole).** Tracked as a
   first-class risk, measured by the §6.3 spike (b): a moved target yielding a
   *unique but wrong* signature match is the one silent retarget stage 1 does
   not close. The open decision is the **guard**: mis-resolve telemetry only, a
   confidence threshold that downgrades a lone low-similarity match to
   `subshape_unresolved`, or gating the riskiest edits until stage 2. Decide
   with the picking item, sized by §6.3.
10. **Vertex signatures.** `subshape_type` admits `"vertex"`, but no vertex
    signature or worked case is specified — an edge fingerprints on curve kind +
    length + adjacency, a face on surface kind + area + centroid, but a vertex
    is a degenerate point (zero length, zero area). A vertex signature must lean
    on **point coordinates + adjacency** (the sorted set of incident edges/faces
    and their signatures), and even then congruent corners of a symmetric part
    tie exactly. Specify the vertex signature and its worked failure case with
    the picking item; until then `"vertex"` is reserved-but-unspecified, not
    shippable.

---

## 7. Review — anticipated code-reviewer concerns

Written ahead of the code-reviewer pass; the three sharpest concerns first.

### 7.1 Is the OCCT history API actually reachable through OCP?

**Verified by import probe in this repo's geometry env (OCP + build123d 0.11.1):**

- `OCP.BRepTools.BRepTools_History` imports and exposes
  `Generated`, `Modified`, `IsRemoved`, `HasGenerated`, `HasModified`,
  `AddGenerated`, `AddModified`, `Merge`, `Remove` — the full accumulate-and-
  query surface a hand-rolled tracker (§6.2) needs.
- `OCP.BRepFilletAPI.BRepFilletAPI_MakeFillet` exposes instance
  `Generated`, `Modified`, `IsDeleted`; `OCP.BRepAlgoAPI.BRepAlgoAPI_Cut`
  (and fuse/common siblings) exposes `Generated`, `Modified`, `IsDeleted`,
  **`History`** (returns a `BRepTools_History`), and `SectionEdges`. These are
  the makers behind fillet/chamfer/boolean — the operations whose history
  stage 2 must capture.
- `OCP.TNaming` imports (the full OCAF naming framework is reachable if the
  §6.2 spike chooses it); `OCP.GProp` / `OCP.BRepGProp` / `OCP.TopExp` are
  reachable for computing the §2b signatures (centroid, area, length).

**The honest reachability nuance, flagged as the stage-2 spike (§6.1):**
build123d returns finished `Solid`s and **discards the underlying maker**, so
the history is *not* readable off a build123d result after the fact — it must be
captured at our own OCP maker boundary during evaluation. That is *inside*
`services/geometry` (we own the kernel layer — CLAUDE.md), so it is architecturally
allowed; what remains unverified without the spike is that we can retain the
maker and accumulate a coherent chain across the whole build123d-mediated tree.
**Stage 1 (signature) depends on none of this** and is buildable today, which is
exactly why it ships first.

### 7.2 Are geometric signatures deterministic under tolerance?

The determinism mandate (RESEARCH §9) is non-negotiable, and floating-point
matching is where it's easiest to violate. Rules:

- **Store full-precision signature fields; do not quantize the stored
  identity.** Quantizing to a grid invites the boundary-jitter bug (a value
  that rounds up on one rebuild and down on the next). Matching is instead
  **nearest-within-tolerance**, using the **documented per-model tolerance**
  (RESEARCH §9 / GEOMETRY-QA), never an ad-hoc epsilon (CLAUDE.md).
- **Exactly-one-or-error.** If two candidates fall within tolerance, the
  resolver does **not** pick — it returns `subshape_ambiguous` (§5). Same
  request bytes → same match or the same honest error, every time. No dict/set
  iteration order participates: candidates are compared in a **total,
  deterministic order** (lexicographic on the canonical signature tuple) so even
  the tie-break, where one exists, is reproducible.
- The §6.3 spike measures actual signature separation on the goldens and pins
  the tolerance, so the "within tolerance" threshold is evidence-based, not
  guessed — and becomes a golden assertion.

### 7.3 What cross-rebuild stability do we actually guarantee?

The tiered contract (§6.5), stated per stage: T0 parametric edits resolve at
both stages; T1 non-neighborhood inserts resolve (guaranteed at stage 2,
best-effort at stage 1); T2 topology-changing neighborhood edits are best-effort
at both and, on failure, produce the §5 honest error. What is guaranteed across
**all** tiers and both stages is the narrow, structural claim: **the resolver
never persists or follows an enumeration index, so the §1.3 _index-based_ silent
retarget is excluded** — ambiguity is an error, not a guess.

What is **not** guaranteed at stage 1 is the *full* non-retarget property. The
§1.3/§2b residual holds: a signature-only match can return a lone WRONG subshape
when the intended one moved out of tolerance and a different one moved in — a
real silent retarget, geometric rather than index-based, invisible to the
ambiguity rule. Stage 1 makes it **unlikely and mostly honest-failing**, and
ships §6.3 mis-resolve telemetry so it is observed; only **stage 2** makes
non-retargeting *structural*, because provenance replay never inspects
coordinates and the §2d step-4 cross-check catches the degenerate remainder. The
doc states this rather than claiming stage 1 "never silently retargets."

### 7.4 Boundary hygiene (standing check)

- `SubshapeRef` is **pure pydantic**: `feature_id` (UUID), `subshape_type`
  (enum), and a **typed, `selector_version`-discriminated `Selector` union**
  (§4) of strings/ids/numbers — *not* a `dict[str, Any]`, so pydantic validates
  it at the boundary and the TS client is typed (CLAUDE.md strict typing). **No
  `TopoDS`, no OCP type, nothing kernel** crosses the service boundary —
  resolution happens entirely inside `services/geometry`, and the persisted name
  is kernel-free by construction, same posture as `EdgeSelector` today.
- The provenance name (stage 2) anchors on **already-crossing, kernel-free
  identifiers** — sketch-local entity ids (`e1`…, already in the schema) and
  operation-role enum strings — so adding it introduces no new boundary
  crossing.
- Documents never resolves names; it only stores/relays the typed selector and
  materializes `feature_id` into `feature_dependencies` (via the widened
  `iter_feature_refs`/`feature_references` helpers — §4). The kernel stays behind
  the boundary; documents stays kernel-free (feature-tree §8.4).

### 7.5 Determinism of resolution order (standing check)

Resolution is a pure, total function of `(rebuilt body, stored selector)`.
Candidate enumeration is sorted into a deterministic total order before any
match; provenance replay follows captured maps (no map iteration order leaks
into the result); ambiguity errors rather than guesses. This is the same
determinism posture feature-tree §8.1 establishes for evaluation order, applied
to name resolution — and it is asserted by a golden (§6.3), not merely claimed.

### 7.6 Why not simply extend the geometric-predicate vocabulary?

Because predicates answer *"which edges match a rule"* and naming answers
*"which specific edge is this one"* (§1.2). A positional predicate ("the Z-edge
nearest P") is not a third category — it **is** the §2b signature approach,
which we adopt as stage 1 and as the hybrid's fallback, not reinvented under the
predicate union. `all_edges` / `axis_parallel` remain the right tool for
*set* selections (round every vertical edge) and are **not** deprecated; the
`subshape` variant is added **beside** them for *singular* selections.

---

## 8. Review / decision log

- **2026-07-11 — request-changes → revised.** `code-reviewer` endorsed the
  design and the staged plan and requested correctness-of-claims fixes (the
  approach was not changed). Per-finding resolution:
  - 🔴 **"Never silently retargets" overstated for stage 1.** Fixed throughout.
    The guarantee is now split: index-based silent retarget is *structurally*
    excluded at both stages (we never persist an index); the **residual
    signature retarget** (intended subshape moves out of tolerance while a
    different one moves in → lone WRONG match, invisible to the ambiguity rule)
    is acknowledged as a real, geometric, non-index silent retarget that stage 1
    makes *unlikely and mostly honest-failing*, **not impossible**. The
    *structural* non-retarget guarantee is attributed to stage 2 (coordinate-
    blind provenance + §2d step-4 cross-check). Reworked: §1.3 framing (new
    stage-by-stage rule), §2b (residual hole), §3 (stage-1 limits + ordering
    rationale), §5 (UI bullet), §6.5 tier contract (per-stage T1/T2 honesty),
    §7.3. Folded the residual "false unique match after a move" into the §6.3
    spike as a *second* measured separation (mis-resolve rate), sizing the
    picking item's telemetry/guard.
  - 🟡 **1 — typed selector union.** `selector: dict[str, Any]` replaced with a
    typed `selector_version`-discriminated `Selector = SelectorV1 | SelectorV2`
    union (§4 code block, §7.4). Kills the unjustified `Any`, gives pydantic
    boundary validation + a typed TS client, stays additive and decoupled from
    `param_version`. Deferring validation to the resolver is noted as the
    rejected alternative with its malformed-vs-unresolved cost.
  - 🟡 **2 — `feature_id` defined precisely.** §4 now states stage 1's
    `feature_id` = the prior body-affecting feature whose body the signature is
    matched against (not necessarily the originating feature); stage 2 shifts to
    the true originating feature (possibly several earlier). The v1→v2
    dependency-edge/409-target shift is called out (no data migration; protected
    feature only moves earlier). New Open Question 8 tracks the migration
    behaviour.
  - 🟡 **3 — not "purely additive."** §4 now states plainly that wiring
    `feature_id` into `feature_dependencies` requires **real** edits to three
    shipped self-checking helpers in `py_kit/schemas/features.py`
    (`iter_feature_refs`, `FeatureReference.ref`, the `walked == mapped`
    assert) — additive on the wire, a genuine typed-helper widening in code.
  - 🟡 **4 — tie-break vs refuse-to-guess.** §2d step 2/3 + a new determinism
    note: stage 1 (pure signature) **never** tie-breaks and errors on ≥2
    matches; stage 2 (provenance) **may** use the signature to disambiguate a
    provenance one→many, erroring only if the signature also ties.
  - 🟡 **5 — `subshape_type` fidelity delta.** §4 flags that adding
    `subshape_type: Literal["face","edge","vertex"]` is an addition to the
    feature-tree §2.4 reserved stub (harmless, now explicit).
  - 🟢 **Open Questions added:** 8 (stage-1 `feature_id` definition + edge
    shift), 9 (residual false-unique-match risk, tied to §6.3), 10 (vertex
    signatures — degenerate length, point + adjacency, `"vertex"` reserved-but-
    unspecified).

---

## 9. Scoping delta — stage-1 PLANAR-FACE signature, implemented (2026-07-12)

Backend + schema for the FIRST consumer, **datum-from-face** (the
sketch-on-a-model-face foundation, BACKLOG #1). This pins exactly what v1
implements against the design above, and — per the §8 review lesson (do not
overstate stage-1 stability) — states plainly what it does and does **not**
guarantee. Owner: kernel-architect. Evidence: `docs/GEOMETRY-QA.md`
(2026-07-12), golden `boss-on-face-40x40x10-20x20x10`, `test_faces.py`.

**Mechanism (which of §2–§4 landed):**

- **§2b geometric signature only, PLANAR FACES only.** `PlanarFaceSignature`
  (`py_kit.schemas.features`) = `subshape_type:"face"` + `surface:"plane"` +
  outward unit `normal` (Vec3) + area `centroid` (Vec3, world mm) + `area_mm2`
  — full precision (§7.2, no quantizing). Edge/vertex signatures and any
  curved-surface signature are **not** implemented (Open Questions 10; edge
  selection is BACKLOG #2).
- **§4 typed selector union, degenerate to one member.** `SelectorV1`
  (`selector_version:1` + `signature`); `Selector` is a plain alias until
  stage 2 adds `SelectorV2` (pydantic forbids a single-member discriminated
  union — same idiom as `FeatureData`). `SubshapeRef` = `kind:"subshape"` +
  `feature_id` + `subshape_type:"face"` + `selector`.
- **§4 dependency-graph wiring landed as described (the "not purely additive"
  part).** `iter_feature_refs` now yields `FeatureRef | SubshapeRef`;
  `FeatureReference.ref` widened to that union; the `walked == mapped`
  self-check balances with both kinds. A datum-on-face's `feature_id`
  materializes into `feature_dependencies` (allowed targets = the
  body-affecting feature types), so deleting the named body feature is a
  write-time 409 and reorder re-checks strict-backward. `feature_id` is the
  **stage-1 anchor** (the body-chain tip the signature matches against), per §4.
- **Datum-node path, NOT a direct sketch-plane `SubshapeRef`.** Per
  `datum-planes.md` §7, on-face is a `kind:"on_face"` variant of the `datum`
  feature (carrying the face `SubshapeRef` + optional offset along the normal);
  the sketch references it by the existing `FeatureRef` plane slot. So `GeomRef`
  did **not** gain a `subshape` member in this slice (it stays reserved for a
  possible future direct reference). No `param_version` bump — the datum union
  reads legacy kind-less params as `offset` via a before-validator.
- **Resolution (`geometry.kernel.faces`).** Enumerate the rebuilt body's planar
  faces in `body.faces()` order → match the stored signature
  nearest-within-tolerance → **exactly one or error**. Derived plane: origin =
  face centroid (+ offset·normal), `z_dir` = outward normal, `x_dir` **pinned
  from the normal** (world axis least aligned with it, ties X<Y<Z, projected
  into the plane) so the 2D→3D basis is deterministic and OCCT-parametrisation-
  independent. Match tolerances (documented, not ad-hoc): normal 1−cos ≤ 1e-9,
  centroid ≤ 1e-6 mm, area rel ≤ 1e-6.
- **Pick↔resolve same enumeration.** `/overlay` enumerates faces
  (`OverlayResult.faces`), each planar face carrying the SAME
  `PlanarFaceSignature` the resolver matches, built by the SAME
  `geometry.kernel.faces` helper — asserted by an order-equality gate
  (`test_faces.py`), the measurement §6b lesson applied to faces.

**Honest guarantee (per-stage tiers, §6.5/§7.3):** T0 parametric edits that
don't move the face **resolve**; T1/T2 are **best-effort at stage 1** — an
edit that removes/moves the face is an honest `subshape_unresolved` /
`subshape_ambiguous` on the datum, but a drastic change **can** retarget to a
coincidentally-congruent face **without erroring** (the residual signature hole,
§1.3/§2b). Stage 1 does **not** ship the §6.3 mis-resolve telemetry yet — it is
"unlikely and mostly honest-failing", not measured; that (and the structural
non-retarget guarantee) waits on stage-2 provenance. **For FACES specifically,**
`subshape_ambiguous` is effectively unreachable today: two distinct planar faces
of a manifold solid cannot share a centroid, so the exactly-one rule always
finds one (the ambiguity branch is guarded-but-defensive, becoming load-bearing
for edge/vertex signatures). This is stated so no reader mistakes "faces don't
tie in practice" for "signatures never retarget."

---

## 10. Scoping delta — stage-1 EDGE signature, implemented (2026-07-13)

Backend + schema for the SECOND consumer, **click-specific fillet/chamfer**
(the §3 "edge selection is BACKLOG #2" item; the first non-face `SubshapeRef`).
Owner: kernel-architect. Evidence: `docs/GEOMETRY-QA.md` (2026-07-13), golden
`fillet-top-edge-40x25x10-r5`, `test_edges.py`. This is the "second consumer"
the topo-naming design anticipated, built by mirroring the §9 face machinery for
edges — same stage-1 posture, same honesty.

**Mechanism (which of §2–§4 landed):**

- **§2b geometric signature only, EDGES.** `EdgeSignature`
  (`py_kit.schemas.features`) = `subshape_type:"edge"` + `curve`
  (line/circle/other) + two canonically-ordered endpoints `end_a`/`end_b` +
  `midpoint` (curve param 0.5) + `length_mm` — full precision (§7.2, no
  quantizing). **Fidelity delta from the §2b sketch, flagged honestly:** the §2b
  illustrative edge signature carried an `adjacent_faces` list (a sorted
  mini-face-signature per neighbour). The **shipped** stage-1 edge signature does
  **NOT** include adjacency — endpoints + midpoint + length + curve kind already
  distinguish the distinct edges of a manifold solid (two distinct edges differ
  in at least one, by whole mm), so adjacency was dropped as not-yet-needed
  complexity (extract on real need, not the first imagined one). Adjacency
  remains available as an additive signature field if a future case needs finer
  discrimination; its absence does not weaken the honest-failure posture (a moved
  edge still surfaces as `subshape_unresolved`/`subshape_ambiguous` where
  detectable). Vertex signatures remain unspecified/unshipped (Open Question 10).
- **§4 typed selector union, degenerate to one member.** `EdgeSelectorV1`
  (`selector_version:1` + `signature`); the edge selector alias is a plain
  member until stage 2, same idiom as the face `Selector`. `EdgeSubshapeRef` =
  `kind:"subshape"` + `feature_id` + `subshape_type:"edge"` + `selector`.
- **`EdgeSelector` predicate union gains a `kind:"edges"` picked member.** The
  fillet/chamfer `EdgeSelector` — previously `all_edges | axis_parallel` — gains
  a `PickedEdgesSelector` (`kind:"edges"`, `refs: EdgeSubshapeRef[]`, min 1),
  discriminated on `kind`. **Purely additive** (design §4/§2.4): every persisted
  `all_edges`/`axis_parallel` selector validates and evaluates BYTE-IDENTICALLY,
  so fillet/chamfer `param_version` stays 1 and the existing fillet/chamfer
  goldens are unchanged. The predicates are NOT deprecated (§7.6) — they remain
  the right tool for SET selections; `edges` is added beside them for the
  singular "the edge I clicked" selection the predicates structurally cannot
  express (§1.2).
- **§4 dependency-graph wiring landed as described (the "not purely additive"
  part), extended to fillet/chamfer.** `iter_feature_refs` now yields
  `FeatureRef | SubshapeRef | EdgeSubshapeRef`; `FeatureReference.ref` widened to
  that; the `walked == mapped` self-check balances with all three kinds. A
  fillet/chamfer with a PICKED selector surfaces each `EdgeSubshapeRef.feature_id`
  as a dependency (allowed targets = `BODY_AFFECTING_FEATURE_TYPES`), so deleting
  the named body feature is a write-time 409-with-dependents and reorder
  re-checks strict-backward — **new for fillet/chamfer**, which carried no
  reference under a predicate selector (and still carry none there). `feature_id`
  is the **stage-1 anchor** (the body-chain tip the signature matches against),
  per §4.
- **Resolution (`geometry.kernel.edges`).** Enumerate the rebuilt body's edges in
  `body.edges()` order → match the stored signature nearest-within-tolerance →
  **exactly one or error**. `select_edges` gained the `PickedEdgesSelector` case
  (each ref → exactly one edge; deduped; returned in `body.edges()` order for
  determinism). Match tolerances (documented, not ad-hoc — the face tolerances'
  twins): endpoints + midpoint ≤ 1e-6 mm, length rel ≤ 1e-6, curve family exact.
- **Error codes (per-feature, strict-prefix, never 500):** the fillet/chamfer
  handlers map `SubshapeUnresolvedError` → `subshape_unresolved` and
  `SubshapeAmbiguousError` → `subshape_ambiguous` (the SAME codes the datum-on-
  face path uses), beside the existing `no_fillet_edges`/`no_chamfer_edges`
  (predicate matched nothing) and `fillet_failed`/`chamfer_failed` (kernel).
- **Pick↔resolve same enumeration.** `/overlay` edges (`OverlayEdge`) now each
  carry the SAME `EdgeSignature` the resolver matches, built by the SAME
  `geometry.kernel.edges` helper over the SAME `body.edges()` enumeration —
  asserted by an order-equality gate (`test_edges.py`), the measurement/faces
  lesson applied to edges. A pick UI echoes an overlay edge's `signature`
  straight into an `EdgeSubshapeRef`.

**Honest guarantee (per-stage tiers, §6.5/§7.3):** T0 parametric edits that
don't move the edge **resolve**; T1/T2 are **best-effort at stage 1** — an edit
that removes/moves the edge is an honest `subshape_unresolved` /
`subshape_ambiguous`, but a drastic change **can** retarget to a
coincidentally-congruent edge **without erroring** (the residual signature hole,
§1.3/§2b). Stage 1 does **not** ship the §6.3 mis-resolve telemetry yet; that
(and the structural non-retarget guarantee) waits on stage-2 provenance.
**Unlike faces,** edge `subshape_ambiguous` is genuinely REACHABLE — a symmetric
part has congruent edges (the §1.2 four vertical edges) — so the exactly-one rule
is load-bearing here, not merely defensive.
