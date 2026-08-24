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
  [0,0,1], area, centroid}`. Matching is **two-tier** (FINDINGS #3): tier 1 is the
  strict signature (normal + centroid + area, exact on a clean rebuild); tier 2,
  reached only when tier 1 finds nothing, re-matches on the **strongest planar
  invariant alone** — same-sense normal + the coincident supporting plane
  (`centroid · normal`, invariant under any *in-plane* boundary change). This is
  what makes the reference actually survive the most common parametric edit:
  resizing **one** hole on a shared face shifts that face's area **and**
  area-centroid, which under strict-only matching orphaned every *sibling*
  reference to the same face (`subshape_unresolved`). Still honest — two distinct
  coplanar faces both match tier 2 → `subshape_ambiguous`, never a guess; fails /
  goes ambiguous if the upstream feature splits the top face into two coplanar
  faces (both share the normal).
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

---

## 11. Scoping delta — durable EDGE anchors for drawing dimensions (2026-07-30)

**Problem (product audit 2026-07-30, N1 — P0).** A dimension on a bracket's 84 mm
overall-length edge composed `84.000`. Widening the plate 100 → 120 — one number in
the base sketch, the part rebuilt clean, all 8 features `ok` — turned that dimension
into `code:"subshape_unresolved"`, printed as a 2.6 mm dashed circle holding a `!`.
The Ø10 dimension survived *because its hole did not change*. So the rule was exactly
inverted from the promise of an associative drawing: **the dimensions destroyed were
precisely the ones that measured what you changed**, and a print revision became a
re-dimensioning job.

**Why faces already survived this and edges did not.** §9's planar-face matcher is
TWO-TIER since FINDINGS #3: the strict signature (normal + centroid + area), then —
only when that finds nothing — a resilient re-match on the strongest INVARIANT alone
(same-sense normal + coincident supporting plane), which no in-plane boundary change
can break, with the origin re-anchored at the stored centroid (`5e685ac`). §10's edge
matcher has only the strict tier: endpoints AND midpoint AND length, all within
tolerance. Every field of an edge signature is a function of the edge's own extent, so
ANY parametric change to the measured edge is fatal — and a dimension is by definition
attached to the geometry the designer is about to change.

**Decision: give edges the missing tier, in the drawings layer, with no new persisted
state.** `geometry.drawings.anchor.resolve_anchor_edge`:

1. **Tier 1 — exact.** `geometry.kernel.edges.resolve_edge`, unchanged and untouched.
   A clean rebuild, or any edit that does not touch the measured edge, resolves here —
   byte-identically to before (the compose goldens prove it: only the §N2 layout moved
   them, and the diameter dimension of an unchanged hole still reports `tier: exact`).
2. **Tier 2 — durable.** Only on a tier-1 *unresolved* (a tier-1 AMBIGUITY still
   propagates — the invariant tier cannot disambiguate congruent twins), re-match on
   the rebuild-invariant of the edge's curve kind, both derived from the stored
   `EdgeSignature` alone:
   - **line** — the same SUPPORTING LINE (parallel within the documented direction
     bound, the stored `end_a` on the candidate's line within the documented linear
     bound) whose span OVERLAPS the stored span. Invariant under the edge growing or
     shrinking along itself: the widened plate, the moved wall, a re-radiused corner
     round that shortens the edge between two fillets. Overlap (rather than a shared
     endpoint) makes it symmetric — a part that grows about its centre moves BOTH
     endpoints and keeps the midpoint.
   - **circle** — the same CENTRE and the same ANGULAR STATION: the unit directions
     from the centre to the stored `end_a`/`end_b`/`midpoint` are all preserved, and
     closedness matches (a full circle never re-anchors onto an arc). Invariant under
     a radius change: the resized hole, the boss turned down. The centre is derived
     from the signature — the seam/opposite-point midpoint for a full circle, the
     circumcentre of the three stored points for an arc — so nothing new is persisted,
     and the station directions also pin the circle's PLANE and an arc's sweep.
   - **other** (spline / ellipse) — no invariant we can state honestly, so it stays an
     honest `subshape_unresolved` whose message says exactly that.

**What is NOT claimed.** §7.3's residual is unchanged: an invariant-based match can
still land on a *different* edge that moved into the stored slot while the intended one
vanished. That is the same geometric (never index-based) retarget stage 1 already
carries. Three things keep it honest rather than silent: zero candidates errors, two or
more candidates is `subshape_ambiguous` (two collinear segments left by a slot cut
through the dimensioned edge — refuse to pick one), and the wire reports WHICH tier
fired (`MeasuredDimension.anchor.tier` = `exact` | `durable`) so a UI can badge a
re-anchored dimension. The value is always RE-MEASURED off the current B-rep — never
re-stamped from the authored number.

**Documented limit.** A corner ROUND's arc is not covered: changing R4 → R6 moves the
arc's centre (it sits R in from the corner), so a dimension on a fillet arc fails
honestly instead of re-measuring a differently-placed arc. Re-anchoring it needs
adjacency ("the arc tangent to these two faces") — i.e. stage-2 provenance, §2d. A
dimension that silently resolves to the wrong geometry is worse than one that errors,
so this stays an error until the provenance name exists. Gated by
`tests/test_drawings_anchor.py::test_a_re_radiused_FILLET_arc_is_an_honest_error_not_a_guess`.

**Placement must use the re-anchored name too.** Re-measuring alone was not enough: the
composer looks a dimension's projected edge up by signature key, so with the stale
authored signature the annotation was dropped even when the value was fine. The
measurement therefore returns the CURRENT signatures (`DimensionAnchor.primary` /
`.secondary`) and `compose.anchored_signature` prefers them, falling back to the
authored ones when a caller supplies no anchor (byte-identity for every existing
sheet). Where a reference genuinely cannot be re-anchored, the sheet now says so in
words beside the view (`ComposedDimensionError.message` — "LINEAR DIM: REFERENCE LOST -
RE-PICK THE EDGE" in SVG/PDF/DXF), the dimension-level twin of the typed per-view
reason FINDINGS #15 stamps.

**Where this should eventually live.** The tier belongs in `geometry.kernel.edges`
beside `resolve_edge`, so a picked-edge FILLET/CHAMFER survives the same edits a
dimension now does. It ships in `geometry.drawings` because the kernel module was held
by another agent in this batch; promoting it (and deleting the drawings-side wrapper)
is a follow-up on the backlog, not a second naming scheme — the predicate, tolerances
and error taxonomy are already the kernel's.

---

## 12. Scoping delta — a picked FACE survives the plane MOVING (2026-07-30)

**Problem (QA wave 2026-07-30, QA-2 — P1).** The commonest revision in CAD
destroys every feature on the face it moves. A bracket (sketch → extrude → Ø6
hole on the top face → linear pattern → mirror → R1 fillet) solving at
142,020.953 mm³ was revised the way every revision arrives — retype Extrude1's
distance, 10 → 16. `Hole1` came back `subshape_unresolved` ("No planar face of
the current body matches the stored face signature"), the three features after it
stranded, and the body collapsed to a featureless 38,400 mm³ brick with the export
blocked.

**Why the existing two tiers could not see it.** §9's face matcher is strict
(normal + centroid + area), and FINDINGS #3 added a resilient tier on the
strongest planar invariant ALONE — same-sense normal + coincident supporting plane
(`centroid · normal`). Both PIN THE PLANE. A depth edit does not change anything
*about* the face — same area 2400 mm², same +Z normal, same (x, y) outline — it
**translates the plane itself**, z 10 → 16, and that is precisely the one quantity
both tiers require to be unchanged. So the tier that was built to survive in-plane
boundary changes had exactly the blind spot §11 had just removed from edges: it
survives a change *within* the plane and not a move *of* the plane.

**Decision: a third tier, freeing the offset along the normal and nothing else.**
`geometry.kernel.faces.translated_signatures_match`, reached only when tiers 1 and
2 both find NOTHING:

| quantity | tier 1 (strict) | tier 2 (coplanar) | tier 3 (translated) |
|---|---|---|---|
| same-sense normal | required | required | **required** |
| supporting-plane offset `centroid · n` | required | required | **FREE** |
| area | required | free | **required** |
| centroid position IN the plane | required | free | **required** |

Read across: each tier frees exactly the quantities the edit it models actually
changes, and holds every other one. Tier 2 models "the boundary of this face
changed" (a sibling hole resized) — area and in-plane centroid move, the plane
does not. Tier 3 models "this face moved along its own normal" (a thickness,
depth, or offset edit) — the plane moves, the face's own shape and its in-plane
station do not. An edit that does BOTH matches neither tier and stays an honest
`subshape_unresolved`; that is the conservative choice on purpose, because
inventing a match across two simultaneous changes is where a matcher starts
guessing.

**What tier 3 must NOT match — the part that makes it safe.** A looser matcher
that re-anchors a hole onto the WRONG face is silent wrong geometry, strictly
worse than the visible failure it replaces. Three separate guards keep it tight,
and the *first* is the load-bearing one:

1. **The opposite face is excluded by the NORMAL SENSE.** A plate's bottom face
   has the identical area and the identical in-plane centroid as its top face —
   the two differ ONLY in the offset tier 3 just freed, and in the sense of the
   normal. `PlanarFaceSignature` stores an ORIENTED outward normal, so +Z never
   matches −Z (the `1 − cos θ ≤ 1e-9` bound is a full-flip apart from a match).
   Drill the top of a plate, thicken it, and the tool cannot land on the bottom.
2. **A parallel face of a different size, or at a different in-plane station, is
   excluded by area and by the in-plane centroid** — a step, a boss top, a pocket
   floor, the flange of an L-bracket.
3. **Two stacked faces that agree on all of the above are an honest
   `subshape_ambiguous`**, never a nearest-plane guess. "Prefer the closest one
   along the normal" was considered and rejected: it is right for a small edit and
   silently wrong for a large one (thicken 10 → 30 and the *original* offset is
   nearer the untouched far face), and a rule that depends on the size of the edit
   is not an invariant.

**The origin rule already existed and is reused verbatim.** A tier-3 match means
the face is somewhere else in space, so the stored centroid — the point the
reference was authored against — now sits at the plane's OLD offset, inside the
solid. `_anchored_plane`, written for tier 2, already does the right thing: keep the
matched face's orientation, and sit at the STORED centroid PROJECTED onto the
matched supporting plane. Under a translation that is the same in-plane station
(which tier 3 pinned) at the face's new place. Everything seated on the face then
follows the move for free, because each consumer projects its own point onto that
plane: a hole authored at (15, 20, 10) on a plate thickened to 16 drills at
(15, 20, 16) (`hole._drill_axis`), and a sketch on the face travels with it. That is
what a modeller expects from having picked a FACE rather than a datum at a fixed
offset — and it is asserted, not assumed: the golden's off-centre bore fixes the
part centroid at x = 30.178821275282164, which no other drill point reproduces.

**The offset is freed WITHOUT a bound, deliberately.** A 10 mm plate retyped to
160 mm re-anchors exactly as one retyped to 16 mm. Bounding the travel would need an
epsilon with no geometric meaning (CLAUDE.md forbids ad-hoc ones) and would make
resolution depend on the SIZE of the user's edit rather than on an invariant. The
consequence is stated where it bites: a stored signature whose area and in-plane
station match a face at a *wildly* different offset now resolves to it. That is the
same best-effort §7.3 posture stage 1 has always had, one degree of freedom wider.

**Blast radius.** The tier lives in the shared `_match_face_records`, so every
picked-face consumer inherits it at once: hole placement, `on_face` datums (and so
sketches), shell's removed faces, and the sheet-metal base-face split. That is
deliberate — they resolve one kind of reference and should not disagree about what
it means — and it is the same posture §11 took for edges.

**Measured (docs/GEOMETRY-QA.md 2026-07-30).** The QA-2 bracket rebuilds at 16 mm
instead of stranding; golden `revise-thickness-hole-on-moved-face-60x40x16` locks
the analytic volume of the revised plate against a hand-derived closed form, and
`test_faces.py` gates the three refusals above by name.

## 12a. The "conservative choice on purpose" was the P0 — tier 4 (2026-08-14)

**§12 named this defect and shipped without it.** Its own words: *"An edit that
does BOTH matches neither tier and stays an honest `subshape_unresolved`; that is
the conservative choice on purpose."* The 2026-08-14 product audit (M17) then hit
exactly that case on the most ordinary parametric edit there is, and rated it P0:
thickening a bracket's plate 10 → 14 mm left **4 of 11 features red** (`Hole3` →
`subshape_unresolved`, `Hole4`/`Hole5`/`Fillet1` stranded by the strict-prefix
rule). The conservative choice is only conservative when the "BOTH" case is rare.
It is not rare — it is the *default* state of any face that more than one feature
was picked on.

**Root cause, reproduced (`test_faces_m17_revision.py`).** A face's stored
signature is `{normal, centroid, area_mm2}`, and both `centroid` and `area_mm2`
are functions of **what has been cut into the face**, not of the face's identity.
So on a plate whose top face carries four mounting holes, hole *n*'s stored area
is one hole's worth smaller than hole *n−1*'s — measured 3293.1417, 3258.9297,
3224.7178, 3190.5058 mm² for Ø6.6 holes, each exactly π·3.3² = 34.2119 mm² apart,
reproducing the audit's table to 4 dp. Every one of those numbers goes STALE the
moment any earlier hole on that face is resized, moved, or inserted — and the
signature has no way to say so. Tier 2 hides this (it frees area and in-plane
centroid), which is why the part keeps working at constant thickness. Retype the
thickness and tier 2 stops applying; tier 3 takes over and pins both stale
quantities, so the reference dies. The audit's own reading — *"the failure is
caused by the thickness change alone, not by the earlier Ø6.6 → 7 hole edit"* —
is half right: reverting either edit fixes it, because it takes **both** to defeat
the tier stack. Measured control, same tree, three trees deep:

| tree | `Hole2` | `Hole3` | `Hole4` | `Hole5` |
|---|---|---|---|---|
| t = 10, Ø6.6 → 7 on `Hole2` (in-plane only) | ok | ok | ok | ok |
| t = 14, no diameter edit (plane move only) | ok | ok | ok | ok |
| t = 14 **and** Ø6.6 → 7 (both) | ok | **subshape_unresolved** | skipped | skipped |

`Hole2` survives in the failing tree for the reason the audit noticed and could
not explain: its stored signature predates every mounting hole, so nothing has
been cut into the face since — it is the one reference on that face whose area is
still true.

**Decision: a fourth tier, anchored on the face's OUTER BOUNDARY.** The property
the first three tiers lack is one that is invariant under *interior subtraction*.
The face's outer wire is exactly that: drilling, enlarging, moving or adding a hole
in the interior of a face cannot change the region its outer boundary encloses.
`geometry.kernel.faces.enclosing_face_match`, reached only when tiers 1, 2 and 3 all
find NOTHING:

| quantity | tier 1 strict | tier 2 coplanar | tier 3 translated | tier 4 enclosing |
|---|---|---|---|---|
| same-sense normal | required | required | required | **required** |
| plane offset `centroid · n` | required | required | FREE | **FREE** |
| area | required | free | required | **FREE** |
| centroid position in the plane | required | free | required | **FREE** |
| stored centroid inside the candidate's OUTER boundary | — | — | — | **required** |
| stored area in `[2·candidate area − outer area, outer area]` | — | — | — | **required** |

Tier 4 therefore models "this face moved AND its boundary changed", which is every
revision of a face that carries more than one feature.

**Why the anchor is the outer boundary and not the picked point on the face.** The
stored `centroid` is the face's AREA centroid, which for a plate with a central
bore is a point **inside the bore — not on the face at all** (re-measured by
review: the M17 plate's top-face area centroid is **(50.335933, 20.0, z)** and
the bore centre is (50, 20) — 0.336 mm off centre, inside the Ø30 bore. The
original text here said "(0, 0, z), dead centre of its own Ø30 hole", which was
wrong on both counts while being labelled "measured"; the substantive point —
that the anchor is not on the face — is unaffected and is gated by
`test_the_tier4_anchor_point_is_not_even_ON_the_face`). A
containment test against the face itself would reject the very case this tier
exists for. Against the outer boundary region it is inside, and stays inside under
any interior edit.

**What tier 4 must NOT match.** It frees three of the four stored quantities, so
the guards carry more weight than in §12:

1. **The opposite face is still excluded by the NORMAL SENSE** — §12's guard 1,
   unchanged and still the load-bearing one. A plate's bottom face is a full flip
   away, so a hole drilled in the top can never re-anchor to the bottom.
2. **A face that VANISHED does not re-anchor onto whatever larger face happens to
   contain the point — the AREA BAND is what stops it.** Its two ends do NOT have
   the same standing, and an earlier draft of this section called both of them
   "derived", which overstates the lower one. The UPPER end is derived: a face is
   a subset of the region its own outer wire encloses, so `stored ≤ outer`
   follows from the hypothesis alone. The LOWER end is an additional
   ATTRIBUTION ASSUMPTION — under "same face, different interior" the stored area
   could be anything in `(0, outer]`, because a DELETED hole shrinks
   `candidate − stored` by an amount unrelated to what the candidate currently
   subtracts. It is chosen because `outer − candidate` is the only quantity
   available, it is conservative in the right direction, and it is proven
   load-bearing below — but calling it derived made it look immune to "why this
   bound and not 1.5x?", which is a fair question the honest-limits paragraph
   then has to answer. This is the guard the first draft of tier 4 got wrong, and the cost
   was measured rather than argued: with only the obvious `stored ≤ outer` subset
   bound, three of `test_faces.py`'s honest-error gates went from red to
   silently-resolving, including the "the plane is gone" one. Delete the boss a
   sketch was placed on and the sketch would have re-anchored to the plate top
   underneath it — silent wrong geometry replacing a visible failure, which is the
   trade §12 refused and this section is not entitled to make either. The band is
   `2·candidate_area − outer_area ≤ stored_area ≤ outer_area`. The upper end is the
   subset argument: the stored face was a subset of the region its own outer wire
   enclosed. The lower end is the *attribution* argument: the difference between
   the stored area and the candidate's current area has to be explainable by the
   interior boundaries the candidate actually HAS, whose total area is
   `outer_area − candidate_area`. Consequences, all of them the safe direction:
   a face with nothing cut into it admits only `stored == outer` (so a plain
   plate top rescues nothing that is not itself); a hole that was widened, moved
   or added still matches; a face whose only hole was DELETED, or whose holes
   changed by more than the total currently subtracted, is refused.
3. **Two candidates that pass are an honest `subshape_ambiguous`**, never a
   nearest/smallest guess — §12's guard 3, unchanged.
4. **Tier 4 is strictly ADDITIVE and cannot change any resolution that works
   today.** It runs only when tiers 1–3 return an empty list, so the set of
   references that resolve can only grow; a reference that resolves now resolves
   to the same face, with the same tier flag, at the same anchored origin. That
   property is what makes a P0 fix safe to land in the shared
   `_match_face_records` that hole placement, `on_face` datums, shell and the
   sheet-metal base-face split all go through. Evidence rather than assertion: the
   22 pre-existing `test_faces.py` gates — every strict, coplanar, translated,
   ambiguity and honest-error case — pass unchanged, and the golden suite is
   byte-identical.

**Honest limits (§7.3 posture, one degree wider again).** A CONCAVE face whose
area centroid falls outside its own outer boundary (a deep U-shaped face) is not
rescued — tier 4 fails honestly, exactly as today. A face that grew in-plane in the
same revision that moved it (the base sketch was enlarged AND the thickness
retyped) is refused by the band's lower end, which is the price of guard 2. And the
general stage-1 caveat stands: a drastic model change can still land on a
coincidentally-plausible face.

**The band is only as strong as the face is SOLID, and that is worth saying out
loud.** Its width is `2·(outer_area − candidate_area)` — twice what is currently
cut out of the face — so on a heavily perforated face it opens up, and in the limit
of a face that is half holes it admits any stored area at all, leaving tier 4 with
only the normal sense and the containment test. That is inherent to inferring the
missing invariant from the three numbers the signature actually stores, and it is
the strongest argument for the `PlanarFaceSignature` change below rather than a
reason to prefer no fix: the alternative on offer is a P0 that strands features on
every multi-feature face.

**THREE existing negative controls moved, plus a rename — corrected by review.**
An earlier version of this paragraph said "one", which contradicted the same
commit's own `docs/GEOMETRY-QA.md` table and understated the riskiest part of the
change in the sentence a future reader would use to learn what coverage moved.
The three are `test_assembly_evaluate.py`, `test_assembly_resolve.py` and
`test_draft.py`; each stated "this face is gone" about a face still plainly
there with only its offset — or, in `test_draft`'s case, only its in-plane
station — wrong, which tier 4 now correctly resolves. Each was retuned to state
something no interior edit to that face could produce. In all three the ONLY
changed lines are the fixture's `centroid`/`area_mm2` and the docstring; every
assertion is byte-identical, so the subjects are unchanged. Separately,
`test_faces.py`'s `test_a_face_that_moved_AND_changed_shape_stays_an_honest_error`
was RENAMED to `…_moved_AND_GREW_…` with a new docstring and an unchanged body.

That the retuning is real rather than a loosening is not asserted, it is measured:
under the lower-bound mutation below, **all three retuned fixtures go red**. The
lower bound is precisely what makes them unmatchable, so they still bind.

Nothing else in the geometry suite moved. That suite collects **2485** tests —
the ~2 900 figure quoted here previously is the whole Python CI job (gateway +
documents + geometry), not this suite.

**Cost.** Tier 4 is the only tier that touches the B-rep beyond the signatures it
is handed — it builds one face per candidate from that candidate's outer wire. It
is on the RESCUE path only (tiers 1–3 all missed), and it skips any candidate that
fails the cheap normal test first, so a clean rebuild pays nothing. Measured on a
200 × 200 plate with 36 through-holes: a full four-tier MISS over its planar faces
costs **0.74 ms**, and only same-sense-normal candidates ever build a region — one,
on that part. Note a machined plate has few PLANAR faces however much is drilled
into it (holes contribute cylinders), so the candidate set stays small in practice.

**The stored signature is still wrong, and this does not fix that.** The real fix
for "a face's identity encodes what has been cut into it" is to stop storing area
and the area centroid as identity and store outer-boundary invariants instead —
which changes `PlanarFaceSignature`, a `packages/py-kit` contract shared with the
document service and every persisted part. Tier 4 buys the correctness now,
without a migration and without invalidating a single stored selector, and leaves
that contract change as a separate, sequenced piece of work (see
`docs/BACKLOG.md`). Note the contract change would ALSO need tier 4's containment
logic for every selector authored before it, so this is the prerequisite, not a
workaround.

**Measured (docs/GEOMETRY-QA.md 2026-08-14).** The M17 bracket rebuilds all-ok
after the combined edit; golden `revise-thickness-and-hole-dia-100x40x14` locks the
revised part's hand-derived closed form and is cross-checked byte-for-byte against
the same tree with signatures authored at the current state (a tier-1 match), so
the rescued body is provably the body an exact pick would have made.

## 12b. The inferred bound had a number, and it was too close — outer-boundary invariants (2026-08-16)

**§12a wrote its own successor's ticket and this section is it.** Its closing
paragraph: *"The stored signature is still wrong, and this does not fix that. The
real fix … is to stop storing area and the area centroid as identity and store
outer-boundary invariants instead."* The GEOM-2 code review then turned §12a's
qualitative caveat (*"the band is only as strong as the face is SOLID"*) into an
admission rule, and the rule is closer than the prose suggested: tier 4 accepts
any stored face whose relative area `f` satisfies **`f >= 1 - 2r`**, where `r` is
the candidate's open-area fraction. That is linear in `r`, so it is not a cliff at
some pathological perforation — it degrades from the first hole.

**Reproduced here, on this branch, before anything was changed**, on a 100x100
vented plate with an 8x8 grid of Ø9 through-holes (`r = 40.7 %` — an ordinary
grille or lightened web, not a contrived one):

```
outer=10000.0  current=5928.5  removed_frac=0.407  lower_bound=1857.0
  deleted 70x70 boss top (4900 mm2): tier4=True   -> RESOLVES onto the plate
  deleted 60x60 boss top (3600 mm2): tier4=True   -> RESOLVES
  deleted 50x50 boss top (2500 mm2): tier4=True   -> RESOLVES
  deleted 40x40 boss top (1600 mm2): tier4=False  -> honest unresolved
```

Delete the boss a sketch sits on and the sketch silently re-anchors to the plate
underneath. That is guard 2's own designed failure case — the case §12a says the
lower bound exists to keep an HONEST error — firing on a boss covering a quarter
of an ordinary perforated plate. It is strictly worse than the failure it
replaced: before tier 4 the user got a visible `subshape_unresolved`; now they get
a part that is quietly wrong. For scale the M17 bracket that motivated tier 4 is
`r = 17.7 %` and comfortably safe, so this is **not** an argument for reverting
tier 4 — the alternative on offer is still a P0 that strands features on every
multi-feature face.

**Root cause, stated precisely: the lower bound is an ATTRIBUTION ASSUMPTION, and
§12a says so.** Under the hypothesis "same face, different interior" the stored
area could be anything in `(0, outer]`; `2*candidate - outer` is chosen because
`outer - candidate` is the only quantity the three stored numbers make available.
No re-tuning of that expression fixes it, because the information it needs is not
in the signature. **The fix is to put it there.**

### Decision — store the OUTER WIRE's invariants, and make tier 4 exact when they are present

`PlanarFaceSignature` (`packages/py-kit`) gains three OPTIONAL fields, emitted by
the pick side from this commit forward:

| field | quantity |
|---|---|
| `outer_area_mm2` | area of the region the face's outer wire encloses (holes plugged) |
| `outer_centroid` | area centroid of that region, world mm |
| `outer_perimeter_mm` | length of the outer wire |

All three are pure functions of the outer wire alone, which is exactly the object
§12a identified as invariant under interior subtraction. Tier 4 therefore stops
INFERRING a bound on an unknown and starts COMPARING a stored invariant against a
recomputed one:

| quantity | tier 4a **outer** (new) | tier 4b **inferred** (legacy) |
|---|---|---|
| same-sense normal | required | required |
| plane offset `centroid . n` | FREE | FREE |
| area / area centroid | FREE | FREE |
| stored area within `[2*cand - outer, outer]` | — | required |
| stored centroid inside the outer region | — | required |
| stored centroid == outer centroid when `stored == outer` | — | **required (GEOM-4)** |
| `outer_area_mm2` equal | **required** | — |
| `outer_centroid` equal IN-PLANE | **required** | — |
| `outer_perimeter_mm` equal | **required** | — |

On the vented plate every row of the table above flips: the deleted boss top
stored `outer_area = side^2` while the plate top's outer region is 10000 mm^2, so
4900 / 3600 / 2500 / 1600 are all REFUSED — the honest error is restored, and it
is restored by an equality rather than by a bound that happens to be far enough
away.

**Why the offset stays free and the centroid comparison is IN-PLANE.** Tier 4
models "the face moved AND its boundary changed". A thickness retype translates
the outer wire along the normal, so its centroid's along-normal component is
exactly the quantity that must be free; its in-plane station is exactly the
quantity that must be pinned. This is §12's tier-3 reasoning applied to the outer
wire instead of to the face.

**Why three quantities and not one.** Area alone collides: an 80x50 boss top
(4000 mm^2, centred) sitting on a 100x40 plate top (4000 mm^2, centred) has the
same outer area AND the same outer centroid, so deleting that boss would
re-anchor its sketch onto the plate — the GEOM-3 defect one notch down. The
perimeter separates them (260 vs 280 mm) and costs one `GProp` call on a wire the
code has already fetched. The three together fingerprint the outer wire; none of
them is a tuned threshold.

**The anchor rule is deliberately UNCHANGED.** `_anchored_plane` still sits at the
stored AREA centroid projected onto the matched plane, not at the outer centroid,
even though the outer centroid is the more stable point. The plane origin is the
frame every seated sketch's 2D coordinates are expressed in, so changing it would
translate every sketch on every resiliently-matched face — audit regression A,
which §12 exists to prevent. The new fields are IDENTITY, not ORIGIN.

### Rejected

- **Re-tuning the lower bound** (`1.5x`, `3x`, a fraction of `outer`). The bound
  is not too loose by a constant; it is a function of `r` with no safe value, and
  any constant makes resolution depend on how perforated the part happens to be.
- **A hard version bump on `PlanarFaceSignature` with a migration.** A migration
  cannot invent an outer wire from three numbers; it would have to re-evaluate
  every persisted part in the document service, which is a cross-service change
  with a worse failure mode — a migration that mis-derives a signature is silent
  wrong geometry applied to the whole corpus at once, rather than to one edit.
- **Making the new fields REQUIRED.** Every persisted selector and every
  `apps/web` construction site would have to change in one commit, and old
  documents could not be read at all. Optional-with-dual-read keeps every stored
  selector resolving.
- **Adding the new fields to the STRICT tier's comparison.** Tier 1 stays on the
  three original quantities. It is an exact match on a clean rebuild either way,
  and widening it would make a new-style stored signature fail tier 1 against a
  hypothetical old-style record — a downgrade path for no gain.
- **Re-anchoring on the outer centroid** (see the anchor paragraph above).

### How selectors authored before this commit keep resolving

**Dual-read, with tier 4b as the compatibility path — which is why §12a is this
change's prerequisite and not its workaround.** A signature with no outer fields
takes the §12a inferred band, byte-for-byte the shipped behaviour plus GEOM-4's
extra refusal. A signature with all three takes the exact comparison. A signature
with SOME but not all of them is refused outright rather than silently downgraded
(a partial signature is a bug, and falling back would be a downgrade path an
error could walk into).

Two honest consequences, stated rather than buried:

1. **GEOM-3 is fixed for every selector authored from this commit forward, and
   NOT for one persisted before it.** A document saved yesterday still carries
   three-number signatures and still gets the inferred band with its `f >= 1 - 2r`
   admission rule. The population is closed and shrinks whenever a user re-picks a
   face, but it does not empty itself.
2. **Closing it fully needs a document-side re-emit**, not a kernel change: the
   geometry service is stateless and never owns the selector it is handed, so it
   has nowhere to write an upgraded signature back to. The natural shape is for
   the evaluate response to return upgraded selectors for references that resolved
   through a tier-1 STRICT match — an exact identification, so the upgrade is
   sound — and for the document service to persist them. That is a cross-service
   contract and belongs in its own ticket.

### GEOM-4 folded in — the derivable constraint tier 4b left unenforced

`outer*C_outer = stored*C_stored + removed*C_removed` implies that when the stored
area EQUALS the outer region's, the stored centroid must equal the outer region's
centroid; there is nothing left over to move it. Tier 4b tested only containment,
so a plain 100x40 face with `area_mm2 = 4000` and `centroid = (5, 3, 10)` — a
signature no real face could produce — matched. It now refuses. This does not
touch the vented-plate case (the boss and the plate share a centroid there), so it
is a strengthening, not the GEOM-3 fix; it is folded in here because it lives in
the same three lines of code. Tier 4a subsumes it: the outer centroid is compared
on every match, not only when the areas coincide.

### Honest limits (§7.3 posture)

The limits §12a lists are unchanged in KIND, but tier 4a states them against the
outer wire directly instead of against an inferred bound, so they are now exact:

- A face that **grew in-plane** in the same revision that moved it changes its
  outer wire, so it is refused. Same limit as §12a, now for a stated reason rather
  than as a side effect of the band's lower end.
- A **hole enlarged until it BREACHES the outer boundary** — a scallop, an edge
  slot, a lightening hole opened out to the rim — changes the outer wire itself,
  which is the one invariant tier 4 rests on (GEOM-5). It fails SAFE: the outer
  region shrinks, its perimeter changes, and the equality refuses. It is listed
  because it is the most likely real edit that defeats the claimed invariant, and a
  reader is entitled to know that "no interior edit can touch the outer wire" stops
  being true the moment the edit stops being interior. **The scope is narrower than
  that sounds, and measuring it is what established the boundary:** a breach ON ITS
  OWN never reaches tier 4 at all — the supporting plane has not moved, so tier 2
  resolves it, correctly, because tier 2 exists precisely for in-plane boundary
  changes. Tier 4 gets the question only when the plane moved as well, so the
  refusal costs a reference only in the "both at once" case §12a is about. Both
  halves are gated in
  `test_a_hole_that_BREACHES_the_outer_boundary_changes_it_and_fails_SAFE`.
- An **in-plane fillet or chamfer on the face's own boundary** is the same case:
  a boundary edit, not an interior one, and refused.
- A **CONCAVE face whose area centroid falls outside its own outer boundary** is
  no longer a tier-4a limit at all — 4a never classifies the stored point. It
  remains a tier-4b (legacy) limit.
- The general stage-1 caveat stands: a drastic model change can still land on a
  coincidentally-congruent face. Tier 4a narrows "congruent" from "an area inside
  a band, somewhere inside the region" to "the same outer AREA, PERIMETER and
  in-plane CENTROID, to tolerance".

  **That is NOT "the same outer wire", and an earlier draft of this line said it
  was — disproven by geometry QA (GQA-1).** All three quantities are invariant
  under any rigid motion of the wire about its own centroid, so a rotated
  congruent wire compares equal on every one of them. Measured on an ordinary
  transition bracket (100x40 bottom flange, 30x30 column, 40x100 rotated top
  flange): the picked top flange at z=50 and a survivor at z=10 both present
  `outer A=4000.000  P=280.000  C=(0,0)`, tiers 1-3 all miss, and **4a returns
  TRUE — 40.000 mm of silent error**. Note 4b admits it identically, so this is
  a pre-existing limit of the whole approach and NOT a regression introduced by
  4a; 4a is still strictly narrower than 4b on every case measured. It is P2
  rather than P0 because resolver-level reachability is definite while
  product-level is not: three attempts to build a feature-tree vehicle died on
  real kernel guards (`cut_removed_nothing`, `boolean_failed`) or on an honest
  `subshape_ambiguous`. Closing it properly needs an orientation-bearing
  invariant — the wire's principal axis, or a vertex-ordered hash — which the
  three scalars deliberately are not.

### Cost

The pick side now computes the outer invariants for every planar face, where
before nothing outside tier 4's rescue path built a region. Two things keep that
cheap, and the first does most of the work: **a face with no inner wires IS its
own outer region**, so the common face needs no region build at all — only
`face.inner_wires()`, plus an area and a centroid the enumeration already
computes. Only holed faces pay, and a machined part has few PLANAR faces however
much is drilled into it (holes contribute cylinders).

### Measured

**The invariant is bit-identical, not merely close.** The M17 top face's outer wire
across the combined revision (thickness 10 -> 14 AND Hole1 Ø6.6 -> 7):
`area 4000.0 / centroid (50.0, 20.0, z) / perimeter 280.0` before and after —
`d(area) = 0.0`, `d(perimeter) = 0.0`, `d(in-plane centroid) = 0.0`. Gated over five
further edits (drill, enlarge, move, add a second, delete one, add a bore) in
`test_the_outer_invariants_are_UNTOUCHED_by_any_interior_edit`, which asserts
equality of the triple rather than a tolerance, while the pair the old signature
stored as identity takes six distinct values across the same six edits.

**The vented-plate table flips, and the legacy one does not.** Same plate, same four
boss tops, before/after the contract change:

| stored boss top | outer area | tier 4a (new) | tier 4b (legacy) |
|---|---|---|---|
| 70x70 | 4900 | **refused** | resolves |
| 60x60 | 3600 | **refused** | resolves |
| 50x50 | 2500 | **refused** | resolves |
| 40x40 | 1600 | **refused** | refused |

Both columns are gated
(`test_a_deleted_boss_top_no_longer_swallows_a_reference_on_a_VENTED_plate` and
`test_the_LEGACY_band_still_swallows_it_which_is_why_the_contract_changed`), the
second deliberately: the residual exposure is a fact in the suite rather than a
caveat in this file, and it goes red the day a document-side re-emit closes it.

**At the tree level it is 8 mm of silent error.** `test_faces_geom3_vented_plate.py`
seats a datum + sketch + 5 mm pin on a boss top and then toggles the block extrude
add -> cut. New-style: the datum is `subshape_unresolved` and the two features on it
are stranded — visible. Legacy: an all-ok rebuild whose pin stands at **z = 15
instead of z = 23**. Two framing corrections came out of building it, both gated:
a literal DELETE never reaches the matcher (dangling `feature_id`) and neither does a
SUPPRESS (`references_suppressed`), so the product was already safe against those;
and any edit that leaves a face on the reference's own plane is absorbed by tier 2,
correctly. The hazard needs the plane to empty while the feature lives.

**The M17 rescue survives** (`test_tier4a_rescues_the_M17_revision_that_tier4b_was_introduced_for`),
and `test_faces_m17_revision.py` is UNCHANGED: it authors three-field signatures, so
it now doubles as the legacy-compatibility gate at the tree level. So does the golden
`revise-thickness-and-hole-dia-100x40x14`, whose committed `model.json` carries
three-field selectors written before this change — a selector authored before the
contract, still resolving, byte-for-byte.

**New golden `revise-lightened-plate-thickness-and-web-dia-100x100x14`.** A 100x100
plate lightened by four Ø40 holes, revised twice (Ø39 -> Ø40 and 10 -> 14 mm), with a
Ø6 hole seated on the top face through a tier-4a match. Chosen because on THIS shape
the legacy inference is worthless: the face is 50.3 % open, so `2*current - outer`
evaluates to **-53.096491487338426 mm^2** — negative, §12a's own limiting case.
Closed forms `14*(10000 - 1609*pi)` and `25600 - 894*pi`; measured deviations
**1.5e-11 mm^3 / 3.6e-12 mm^2 / 1.4e-14 mm** at the documented 1e-9. Cross-checked
byte-for-byte (GLB sha256 `86a503fdf3e03c7d...`) against the same tree authored at
the current state, which is a tier-1 strict match — so the rescued body is provably
the body an exact re-pick makes, not merely a body.

**Cost.** `planar_faces` medians over 30 runs, before -> after:

| body | planar faces (holed) | before | after |
|---|---|---|---|
| plain box 50x40x10 | 6 (0) | 1.974 ms | 2.458 ms |
| M17 plate, 3 bores | 6 (2) | 2.249 ms | 4.344 ms |
| vented plate, 64 vents | 6 (2) | 8.729 ms | 13.738 ms |

So a hole-free face costs ~0.08 ms (one `wires()` + one wire length; its area and
centroid are handed in by `planar_face_signature` rather than integrated twice) and a
holed one ~0.9-2.4 ms, dominated by `Face(wire)`. End to end on a COLD rebuild of the
M17 golden (rebuild cache cleared, three face resolutions): **103 ms -> 121 ms**,
which is ~6 % of a part-rebuild three orders of magnitude inside the 2 s tripwire, and
nothing at all on a warm cache hit. A cheaper route exists and was measured and NOT
taken: `BRepBuilderAPI_MakeFace(gp_Pln, wire)` with the face's known plane is 0.249 ms
against build123d's 0.686 ms on the 64-hole face, because `Face(wire)` runs
plane-finding and `BRepCheck_Analyzer`. It was rejected to keep ONE region
construction shared with the legacy path rather than two that could disagree
numerically; if the pick path ever becomes hot, that is the lever.

**Mutation evidence.** See `docs/GEOMETRY-QA.md` (2026-08-16, GEOM-3) — both
directions, because the arm that matters most here is the one proving an honest error
stays honest, which is exactly what tier 4's first draft got wrong.

---

## 13. Scoping delta — the durable EDGE tier is PROMOTED to the kernel (2026-08-24)

**This is §11's own follow-up, taken.** §11 ends: *"The tier belongs in
`geometry.kernel.edges` beside `resolve_edge`, so a picked-edge FILLET/CHAMFER
survives the same edits a dimension now does. It ships in `geometry.drawings` because
the kernel module was held by another agent in this batch."* It is now in
`geometry.kernel.edges` (`resolve_edge_durable`), and the drawings-side wrapper is
deleted — see the honest exception at the end.

**Problem (product audit 2026-08-21, S-24 / S-24b — P0, filed as NAME-2).** Sketch1's
`120` retyped to `150` on a sheet-metal bracket: `03 Edge flange1 ERR
SUBSHAPE_UNRESOLVED`, `04 Hem1 SKIP`, `05-08 Hole1..4 SKIP`, all four exports blocked.
The audit noted the edge that broke is *topologically identical* — "the same y = +30
boundary edge of the same face, just 30 mm longer" — and pointed straight at §11:
*"The drawings subsystem already re-anchors exactly this; the feature subsystem does
not."* A controlled ladder (S-24b) then read as **first edit OK, second edit BROKEN**,
which the audit reasonably inferred meant a matched reference goes stale because it is
never re-stamped, so edit N+1 compares against geometry from two edits ago.

**The kernel measurement is blunter than that, and it changes the fix.** Reproduced
against the `l-bracket-edge-flange` golden with the stored signature authored once and
NEVER re-stamped — i.e. exactly the "stale" condition the audit hypothesised — every
step of the ladder failed, including the first:

```
authored (50 x 20)                    OK
edit -> 21   subshape_unresolved      edit -> 22   subshape_unresolved
edit -> 23   subshape_unresolved      edit -> 24   subshape_unresolved
```

There was no tolerance to exhaust and nothing that could go stale-by-N: the feature
tree had **no tolerant edge tier at all**. `resolve_edge` pins both endpoints, the
midpoint AND the length, so the FIRST edit that moves a picked edge orphans it, and
the second one fails for the identical reason. A face has had four tiers since
§12a/§12b; an edge had one. That asymmetry is the whole defect. (The audit's ladder
was observed through the UI, where a rebuild that is served without re-resolving reads
as "OK"; the kernel-level ladder is the sharper instrument and disagrees with it in the
first row only.)

**Decision.** `geometry.kernel.edges.resolve_edge_durable(body, target) ->
ResolvedEdge{edge, signature, tier}` — tier 1 the strict `edge_signatures_match`,
tier 2 §11's two predicates promoted verbatim (`collinear_overlapping_match`,
`concentric_same_station_match`), reached ONLY on an empty tier-1 result. Every
feature-tree picked-edge consumer now goes through it: fillet and chamfer via
`select_edges` -> `_resolve_picked_edges`, the sheet-metal edge flange and hem via
`_fold_flange_off_edge` (both the live resolve and the clean-body re-fold).

`resolve_edge` itself is deliberately UNCHANGED and stays strict-only, which is a
contract split worth stating because the obvious refactor breaks a shipped feature:
`geometry.drawings.anchor.resolve_anchor_edge` runs it as its tier 1 and reports
`tier: exact` when it succeeds, so widening `resolve_edge` would make every
re-anchored dimension report itself as exact and silence the `RE-ANCHORED … CONFIRM`
chip §11 exists to raise. The assembly mate resolver wants the strict answer for the
same reason. Gated by
`test_edges.py::test_resolve_edge_stays_STRICT_for_drawings_and_mates`.

**Why an INVARIANT tier needs no re-stamping — the half of NAME-2 that dissolves.**
NAME-2's stated fix is "write the new signature back so the NEXT edit compares against
current geometry". That is the right fix for a DRIFT-budget matcher, whose tolerance
is spent against the authored state. These predicates do not measure drift: they
compare quantities the edit does not move at all — a supporting line, a centre and an
angular station — so the stored signature never goes stale, and the N-th consecutive
edit resolves for the same reason the first one does. Gated at 41, 42, 43, 80 and
400 mm from one signature authored at 40
(`test_consecutive_edits_do_not_accumulate_drift`). Re-stamping remains worth
REPORTING and the resolver returns what a client needs for it —
`ResolvedEdge.signature` is the CURRENT signature and `.tier` says whether it moved,
mirroring `DimensionAnchor` field for field — but it is no longer load-bearing for
correctness. The remaining work to make it REACH a client (a field on `FeatureResult`
and a web-side healer, the exact shape `DrawingPage.tsx` already implements for
dimensions) is a py-kit + web change, not a kernel one, and is not in this commit.

**What is NOT claimed, and what stays an honest error.** An edge that leaves its own
supporting line — a top-front edge carried up when the plate is thickened — is still
`subshape_unresolved`, and deliberately: freeing the perpendicular offset makes every
parallel edge of the same length an equally good candidate, so the tier could only
report an ambiguity or guess. That is the EDGE analogue of §12's tier 3 and it does
not have §12's escape, because a face's area and in-plane centroid carry an identity
that an edge's direction and length do not. Gated by
`test_an_edge_that_left_its_supporting_line_still_fails_honestly`. Likewise the §11
corner-round limit is unchanged (an R4 -> R6 arc moves its centre), and the overlap
clause still refuses a collinear edge lying END-TO-END with the stored one.

**Golden.** `revise-width-fillet-on-grown-edge-55x25x10` — the edge sibling of
`revise-thickness-hole-on-moved-face-60x40x16`. It is
`fillet-top-edge-40x25x10-r5` after the sketch's 40 is retyped to 55, with the fillet's
stored `EdgeSignature` still naming the 40 mm edge. Closed forms `12375 + 343.75*pi`
and `3750 + 150*pi`; measured deviations **1.8e-12 mm^3 / 9.1e-13 mm^2 / 1.8e-15 mm**
at the documented 1e-9. Two free cross-checks fell out and are recorded in its
`derivation`: the removed prism's cross-section does not depend on the edge's length,
so `centroid.y` / `.z` must equal the 40 mm golden's *exactly* (they do), and a
cylindrical face is ruled along its length, so the mesh closed form `26 + 4N` / `12 +
4N` carries no length term and must predict 154 / 140 again (it does). `max.x = 55`
and `centroid.x = 27.5` are the two witnesses that the fillet followed the edge to its
NEW extent rather than stopping at the stale 40.

**Mutation evidence.** Disabling tier 2 (`_match_edge_records` returning `[]` instead
of the durable candidates) reddens **exactly four tests, all four of them the new
golden's**, with `('...ee003', 'error', 'subshape_unresolved')` — the whole
`test_goldens.py` suite is otherwise unaffected, so no existing golden was silently
depending on the new tier, and the new one fails for the stated reason rather than on
a number.

**The one thing deliberately left undone.** `geometry.drawings.anchor` still carries
its own copy of the two predicates (`_collinear_overlapping`,
`_concentric_same_station`, `_circle_centre`) and should now delegate to the kernel's
— a mechanical delete-and-import in that package. It is not in this commit for the
same reason §11 shipped in drawings rather than the kernel: that package was held by
another agent in this batch. The duplication is behaviour-identical (the predicates
were promoted verbatim, and both read the same documented tolerances), and it is named
here and in the kernel module's block comment rather than left silent, so the collapse
is a known follow-up and not a second naming scheme.

