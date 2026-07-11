# Topological Naming — Design

Status: **draft for code-reviewer** (2026-07-11). Scope: **design only** — no
code, no contracts, no `param_version` change. This doc specifies how a
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
retarget.**

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
  → honest error (never a silent retarget — the redeeming property).
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
   tie-break, or honest error if still ambiguous.
3. If history is **unavailable** (an operation not yet instrumented, or a
   legacy ref written before capture existed), fall back to pure signature
   matching (2b).
4. **Cross-check:** if provenance resolves to a subshape whose signature
   diverges wildly from the stored one, flag low-confidence rather than trust
   blindly.
5. If nothing resolves uniquely → §5 honest failure.

- **Fillet-plate / hole-on-face:** best of both — provenance survives the
  parametric moves that defeat 2b, and the signature disambiguates the
  symmetric/split cases that defeat 2c.
- **Storage:** provenance name + signature + `selector_version`. Largest.
- **Cost:** highest (both must be produced and, on resolve, both consulted) —
  but the signature half ships **first** and cheaply (2b needs no history
  capture), and the provenance half is added under the same opaque
  `selector_version` without a schema break (§4). This is the staged path §3
  adopts.

---

## 3. Decision + rejected alternatives

**Decision: adopt the hybrid (2d) as the target architecture — a
provenance-anchored name with a geometric signature as disambiguator and
fallback — and deliver it in two stages under a single opaque, versioned
`SubshapeRef.selector` payload so the stage boundary is invisible to storage
and callers.**

- **Stage 1 (ships with "face/edge picking"): geometric signature only (2b).**
  It unblocks the product goal *now* — a working engineer clicks a face or
  edge, we persist its signature, and it survives the common edits (upstream
  inserts, parametric changes that don't move the target). It is honest about
  its limits (symmetric ambiguity, moved geometry → honest §5 error, never a
  silent retarget), and — critically — it needs **no** kernel-history
  instrumentation, so it is buildable against build123d results as they exist
  today. `SubshapeRef.selector` carries `{ signature, feature_id }` at
  `selector_version: 1`.
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
  driver — without ever having shipped a scheme that silently corrupts.
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
  `SubshapeRef.selector_version` (already in the reserved shape) versions the
  opaque `selector` blob. Stage 1 → stage 2 (signature-only → hybrid) is an
  increment of `selector_version` *inside* the opaque payload, decoupled from
  feature `param_version` entirely — the elegant part of the reservation. This
  is the one place `param_version`'s upcast machinery (feature-tree §1.4) does
  **not** apply; the selector carries its own version and resolves
  fallback-first for older selectors (§3 stage 2).
- **`SubshapeRef.feature_id` joins the dependency graph.** Unlike today's
  fillet/chamfer (which carry no `FeatureRef` and depend on the prior body only
  by tree order — feature-tree §2.4, `feature_references()` → empty set), a
  `SubshapeRef` names *the result of a specific originating feature*, so its
  `feature_id` **materializes into `feature_dependencies`** (feature-tree §2.3)
  exactly like a `FeatureRef`. This is a strict improvement: the write-time
  409-with-dependents pre-check now protects the originating feature from
  deletion, and reorder re-checks the strict-backward rule (§2.2 rule 2) for
  named refs too. `feature_references()`' slot map extends to surface the
  `SubshapeRef.feature_id` per selecting feature.

Illustrative stage-1 shape (final field names owned by the implementation item;
`selector` stays **opaque and versioned** so the resolver, not the schema, owns
its meaning):

```python
class SubshapeRef(BaseModel):
    kind: Literal["subshape"]
    feature_id: UUID          # whose result the subshape belongs to (→ deps graph)
    subshape_type: Literal["face", "edge", "vertex"]
    selector: dict[str, Any]  # opaque, versioned payload (signature @ v1; + provenance @ v2)
    selector_version: int
```

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
  or edits the upstream feature back to a state where the ref resolves. **Never
  a silent retarget** — the §1.3 failure mode is structurally impossible because
  ambiguity is an error, not a guess.
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
3. **Signature determinism under tolerance, measured on goldens.** Confirm the
   `fillet-plate-r5` / `chamfer-plate-d5` bodies produce **stable, unique**
   edge/face signatures across rebuilds at the documented per-model tolerance
   (RESEARCH §9), and quantify how close two edges get before the ambiguity
   rule fires. Sets the tolerance policy for §7.2. Produces a new
   `subshape-ref-<name>` golden (new capability ⇒ new golden, per the DoD).
4. **Truly symmetric selections.** Four congruent edges with identical
   signatures *and* identical provenance roles (a 4-fold-symmetric part) cannot
   be told apart by either half of the hybrid. The pick UI must then store an
   explicit discriminator (e.g. a canonical index into the deterministically
   ordered congruence class) — decide the discriminator shape with the picking
   item; it lives inside the opaque `selector`.
5. **The cross-rebuild stability *guarantee* we publish.** Define a tiered
   contract users can rely on: (T0) parametric-value edits that don't move the
   target — **guaranteed** to resolve; (T1) upstream inserts that don't touch
   the target's neighborhood — **guaranteed** (stage 2) / best-effort (stage 1);
   (T2) topology-changing edits in the neighborhood (split/merge) —
   **best-effort with an honest §5 error, never silent**. Publishing this
   honestly is part of the daily-driver promise.
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

The tiered contract (§6.5): T0 parametric edits and T1 non-neighborhood
inserts resolve (guaranteed at stage 2, best-effort at stage 1); T2
topology-changing neighborhood edits are best-effort and, on failure, produce
the §5 honest error. The load-bearing guarantee across **all** tiers and both
stages: **the resolver never silently retargets.** It resolves to the same
entity or it errors — the §1.3 catastrophe is structurally excluded because
ambiguity is an error, not a guess.

### 7.4 Boundary hygiene (standing check)

- `SubshapeRef` is **pure pydantic**: `feature_id` (UUID), `subshape_type`
  (enum), an opaque `selector` dict of strings/ids/numbers, and
  `selector_version` (int). **No `TopoDS`, no OCP type, nothing kernel** crosses
  the service boundary — resolution happens entirely inside `services/geometry`,
  and the persisted name is kernel-free by construction, same posture as
  `EdgeSelector` today.
- The provenance name (stage 2) anchors on **already-crossing, kernel-free
  identifiers** — sketch-local entity ids (`e1`…, already in the schema) and
  operation-role enum strings — so adding it introduces no new boundary
  crossing.
- Documents never resolves names; it only stores/relays the opaque selector and
  materializes `feature_id` into `feature_dependencies`. The kernel stays behind
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
