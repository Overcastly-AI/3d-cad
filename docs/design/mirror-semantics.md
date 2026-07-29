# Mirror Semantics — Design

Status: **design only** (kernel-architect, 2026-07-29, HEAD `edbcee6`). To be
reviewed by `code-reviewer` **before** implementation (CLAUDE.md: hard problems
get a design doc first). Scope: the **v2 mirror feature's input contract and
per-feature-kind semantics** — the decision that unblocks the single remaining
`xfail(strict)` in the geometry suite (`CM1_BOSS_UNMIRRORED`,
`services/geometry/tests/test_composition_matrix.py`) and retires the last
guess left in a body-affecting verb.

This is a **contract** problem wearing a geometry problem's clothes. The v1
mirror INFERS what the user meant from the shape of the body chain, and a prior
agent proved (§1, with three measured numbers) that no inference rule can be
right for every chain — three legitimate user intents map onto the same tree and
demand three different volumes. The fix is not a cleverer heuristic; it is to
stop guessing and let the tree state the intent, which is what SolidWorks
("Features to Mirror"), Fusion 360 (Mirror → Type: Features) and Onshape
(feature-scope mirror) all do.

Related: RESEARCH §1 (OCCT via OCP + build123d — the mirror is an exact OCCT
isometry, no new dependency), §2 (unaffected — the sketch solver is not
involved), §9 (determinism + golden gates — the load-bearing constraint on
selection ORDER, §8);
[`feature-tree.md`](./feature-tree.md) §1.4 (additive param changes do not bump
`param_version`), §2.3 (materialized `feature_dependencies` + the
409-with-dependents pre-check), §4.3 (strict-prefix failure);
[`multi-body.md`](./multi-body.md) §MB-0 (active body; a tool recorded against
body A never applies to body B);
[`topological-naming.md`](./topological-naming.md) §9/§10 (the shipped face/edge
signature machinery — §7 explains why v2 needs **nothing** from it, and exactly
what a v3 would);
`docs/GEOMETRY-QA.md` 2026-07-25 (CM-1 and its residual — the source evidence
for every number below).

**The honest headline:** the mechanism is low-risk (reflect recorded rigid tool
solids and re-apply each tool's own boolean — an exact isometry plus booleans we
already run), the **input contract is the whole design**, and the genuinely hard
case — a modifier (fillet / chamfer / shell / draft) whose face/edge references
have no counterpart on the reflected side — is **explicitly REFUSED in v2 with a
typed error** (§4.3). Pretending a fillet's removed slivers can be reflected and
re-cut is how we would ship the next silent-wrong-geometry bug, so this doc
refuses it in writing rather than discovering it in a golden.

---

## 1. The problem, precisely — three numbers, mutually exclusive under any one rule

v1's contract is one field: `MirrorParamsV1 { plane: GeomRef }`. The semantic
lives entirely in the kernel/feature layer and is a two-way guess
(`services/geometry/src/geometry/kernel/mirror.py`,
`geometry.features.evaluate._evaluate_mirror` / `_mirror_cut_tools`):

- if the active body has a **recorded cut** (the most recent one, however many
  non-cut features sit between — the CM-1 fix), reflect **that cut's tools** and
  subtract them (`mirror_cut`);
- otherwise, or when the reflected tools cannot reach the body
  (`removal_reaches_body`), reflect the **whole body** and fuse (`mirror_union`).

Three chains, each with a defensible expected volume, measured on HEAD:

| # | chain | wants | v1 gives | reachable by |
| --- | --- | --- | --- | --- |
| **A** | `plate 40x40x20 -> hole Ø8 @(10,20) -> boss 8x8x5 @x∈[30,38] -> datum YZ@20 -> mirror` | **30629.3807** (hole mirrored **and** boss duplicated) | 30309.3807 (hole mirrored, boss single) | `mirror_union` + re-subtract of **both** tool sets |
| **B** | `plate 40x40x20 -> pocket A x∈[4,8] -> pocket B x∈[14,18] -> datum YZ@20 -> mirror` | **29600.0** (B mirrored, A untouched) — **LOCKED** by `test_mirror_preserves_a_cut_that_precedes_the_mirrored_one` | 29600.0 ✓ | reflect the **last** cut, never union |
| **B'** | the same chain | **28800.0** (both pockets mirrored) | 29600.0 | reflect **all** tracked cuts |

The exclusion is structural, not a bug:

- The approach that reaches **A** (union the reflected body, then re-subtract
  every tool set) **welds pocket A shut in B — 30400.0 where 29600.0 is
  correct**, because the union step fills every void the reflection covers and
  only the tools we re-subtract are restored.
- The approach that reaches **B'** (reflect every tracked cut) **breaks B's lock
  — 28800.0 where 29600.0 is asserted.**
- The approach that reaches **B** (v1: reflect the last cut only) **cannot reach
  A**, because a mirror that never unions cannot duplicate material an
  intervening ADD contributed.

So three implicit rules, three chains, and every rule is wrong on a chain
another rule gets right. **No amount of cleverness inside the "mirror the body
so far" shape resolves this**, because A, B and B' are not three readings of one
request — they are three *different requests* that v1's DTO cannot tell apart.
`B` and `B'` are both **correct**: one user meant "put pocket B on the other
side," the other meant "make the plate symmetric." v1 answers both with 29600.0
and is silently wrong for one of them.

That reframing is the design: the ambiguity is in the **input**, and it is
removable there.

---

## 2. Approaches considered

Scored on the same three chains, plus the two shipped mirror workflows that must
not regress: the **midplane** mirror (`mirror-hole-feature-plate-40x40x20`) and
the **complete-the-half** mirror (`mirror-cut-clearing-plane-block-40x40x20`,
60000.0 from a 30000.0 pocketed block about its own `+X` face).

### 2a. A better implicit rule (rejected)

Keep the one-field DTO and refine the inference — "reflect every cut since the
last add," "reflect the maximal suffix of same-kind features," "reflect
everything since the previous mirror."

Rejected by §1 as a category: any implicit rule is a *function of the tree*, and
A, B and B' are **the same tree shape** (base → n body features → datum →
mirror) with three answers. A function cannot return three values for one
argument. Every candidate rule therefore picks one of the three numbers by fiat
and is silently wrong for the other two intents — the defect class we are
closing, restated. This is also the precise reason §3 ships **no** automatic
"mirror everything up to here" default (§3.3).

### 2b. Explicit feature selection + reflect the recorded TOOL solids (adopted)

Widen the DTO with an explicit list of feature ids. At evaluation, each selected
feature's **recorded tool solid(s) and its own operation** (`fuse` or `cut`) are
reflected about the plane and re-applied to the active body, in tree order.

The store already half-exists and was built for exactly this discipline:
`EvaluationState.record_cut_tools` captures a cut's removal solids **at cut-eval
time, from the pre-cut body** (the FINDINGS #1/#3 lesson — never re-derive a
tool later against a mutated body). v2 generalises it to
`record_feature_tools(feature_id, op, tools)` so additive verbs record their
prism/revolve/loft solid the same way.

- **A:** `features: [hole, boss]` → reflect the bore tool (−1005.3096) then fuse
  the reflected boss prism (+320) → 31314.6904 − 1005.3096 + 320 = **30629.3807** ✓
- **B:** `features: [pocket B]` → 30400.0 − 800 = **29600.0** ✓
- **B':** `features: [pocket A, pocket B]` → 30400.0 − 800 − 800 = **28800.0** ✓
- **complete-the-half:** `features: [base extrude, pocket]` → 30000.0 + 32000.0
  (reflected base prism at x∈[40,80]) − 2000.0 (reflected pocket tool) =
  **60000.0** — the same value the v1 union fallback produces, by a different
  boolean sequence (see §6 on why that is *not* claimed as byte equivalence).
- **Cost:** one exact reflection + one boolean per selected feature. No
  reference re-resolution, no per-handler transform plumbing, no new kernel
  algorithm.
- **Limit (the honest one):** a feature whose contribution is not a rigid tool —
  every modifier — has nothing to reflect. §4.3 refuses those with a typed
  error rather than approximating them.

### 2c. Re-evaluate the selected features under a reflected frame (rejected for v2, named as v3)

The "true" feature mirror: reflect each selected feature's *inputs* (sketch
plane, profile, hole placement, picked edges/faces) and re-run its handler, so
the reflected side is built by the same code path as the original side.

- Handles **A/B/B'** identically to 2b, and additionally handles **modifiers**:
  a fillet re-runs on the reflected side's edges.
- **Cost:** every feature handler must accept a transform; every stored
  reference must resolve on the reflected side, which needs a symbolic
  "reflection of face F" (§7) that does not exist; and it walks straight into
  the handedness trap of §7.3 (a right-handed frame rebuilt from a reflected
  normal is the *rotated*, not reflected, frame — an asymmetric sketch would come
  out un-mirrored). That is a multi-slice project resting on stage-2 provenance.
- Rejected **for v2** on cost and on sequencing (it needs 2b's store anyway to
  know which features are in scope), retained as the **only** path to mirrored
  modifiers (§10, §11.1).

### 2d. Hybrid — 2b now, 2c per-kind later (adopted as the staging)

2b ships the additive/subtractive verbs; 2c is added later **per feature kind**
behind the same DTO, so a kind graduating from "typed refusal" to "supported" is
a pure capability addition with no contract change. This is the same staging
shape topological-naming §3 used (signature now, provenance later, one versioned
union), and it is why §3's DTO carries a *scope* discriminator rather than a bare
list.

---

## 3. Decision — the v2 mirror's input

**Decision: `MirrorParamsV1` gains a `scope` field, a `kind`-discriminated union
with exactly TWO members in v2 — `body` (the v1 semantic, retained verbatim) and
`features` (an explicit, non-empty, tree-ordered list of `FeatureRef`). A
persisted mirror with no `scope` key normalises to `{"kind": "body"}` through a
before-validator, so every existing row and every shipped golden evaluates on the
unchanged v1 code path. There is NO automatic "mirror everything up to here"
default.**

### 3.1 Shape

Illustrative; final field names owned by the implementation item.

```python
class MirrorBodyScope(BaseModel):
    """v1, named: reflect the CURRENT BODY (cut-aware — mirror.py's two readings)."""
    kind: Literal["body"]


class MirrorFeaturesScope(BaseModel):
    """v2: reflect the RESULTS OF THESE FEATURES, in tree order (§8.1)."""
    kind: Literal["features"]
    features: list[FeatureRef] = Field(min_length=1)


MirrorScope = Annotated[
    MirrorBodyScope | MirrorFeaturesScope, Field(discriminator="kind")
]


class MirrorParamsV1(BaseModel):
    plane: GeomRef
    scope: MirrorScope = Field(default_factory=lambda: MirrorBodyScope(kind="body"))
    # + a `model_validator(mode="before")` supplying {"kind": "body"} when the
    # key is absent, so legacy rows validate — the SAME idiom the datum union
    # uses to read legacy kind-less params as `offset`
    # (topological-naming.md §9).
```

Three deliberate choices inside that shape:

1. **`FeatureRef`, not a bare `UUID`.** `FeatureRef` is already the `GeomRef`
   member that `iter_feature_refs` walks, so each selected feature
   **materialises into `feature_dependencies`** for free (feature-tree §2.3):
   deleting a mirrored feature is a write-time 409-with-dependents, a reorder
   re-checks the strict-backward rule, and a forward/self reference is a
   write-time 422. That is *correct* — a `features`-scope mirror genuinely
   depends on the features it reflects, unlike v1's mirror, which depends on the
   prior body only by tree order. It also means documents can enforce
   "body-affecting types only" at write time, the same allowed-target constraint
   the on-face datum and picked fillet already use
   (topological-naming §9/§10) — so §4.4's non-body-affecting refusal is a 422
   long before it is an evaluation error.
2. **A discriminated union, not `features: list[FeatureRef] | None`.** `None`
   and "mirror the body" would be two spellings of one meaning — the smell that
   made v1's semantic implicit in the first place. Naming the v1 reading
   `kind: "body"` makes it a *choice the user made*, gives the UI two radio
   buttons instead of a mystery absence, and keeps a future third reading
   (`kind: "bodies"`, for multi-body selection) additive.
3. **`min_length=1`.** An empty selection is authoring nonsense, not a no-op
   mirror; rejected at the boundary rather than degrading to "did nothing" —
   the no-silent-no-op rule the composition matrix enforces on every cell.

### 3.2 Why this is additive (and how the goldens stay byte-identical)

- On the wire, a new params field with a default is additive under feature-tree
  §1.4 → **`param_version` stays 1**, no `0012`-style data migration, every
  persisted mirror row validates unchanged.
- In the kernel, `scope.kind == "body"` dispatches to **today's
  `_evaluate_mirror` body unchanged** — the same `_mirror_cut_tools` read, the
  same `mirror_cut` / `mirror_union` pair, the same `removal_reaches_body`
  fallback. Byte identity for the shipped goldens is therefore **structural**
  (the code on that path does not change), not measured — the strongest form of
  the guarantee, and the reason §6 refuses the "elegant" unification.
- The one place the widening genuinely touches shipped behaviour is the **store**
  (§6.2), and that risk is called out with its own acceptance criterion.

### 3.3 Refused: an automatic "mirror everything up to here"

Tempting (it is what a novice expects from a bare mirror) and **refused**,
because §1 shows an implicit default must pick one of A / B / B' by fiat. Worse,
the natural spelling of "everything" — every body-affecting feature since the
last mirror — is exactly the rule that returns **28800.0** on chain B and breaks
the 29600.0 lock. An implicit default cannot be added later without changing
answers for models already authored under it; the `body` scope already serves
the workflow a novice reaches for (complete-the-half) and serves it correctly. A
third scope stays additively available **if** usage evidence demands it, and it
would arrive as a new union member, not as a change of default.

---

## 4. What "mirror a feature" means, per feature kind

The mechanism is uniform: reflect the feature's **recorded rigid tool solid(s)**
about the plane and re-apply **that feature's own operation** to the active body.
A kind is in v2 scope **iff** it has a rigid tool and a single boolean.

### 4.1 In scope — additive tool contributors → reflect + `fuse`

`extrude` (add), `revolve` (add), `sweep`, `loft`, `import`.

The recorded tool is the solid the feature fused (the prism, the revolved solid,
the swept/lofted solid, the imported body), captured pre-boolean. The reflected
tool is fused into the active body. A reflected additive tool that lands clear of
the body legitimately **increases the lump count** — the §MB-0 disjoint-copy case
the `2V` goldens already assert — so, unlike a cut, an add imposes no
lump-count invariant.

### 4.2 In scope — subtractive tool contributors → reflect + `cut`

`extrude` (cut, **per region**), `revolve` (cut), `sweep`/`loft` cut, `hole`
(simple / counterbore / countersink / tapped — bore + recess, as recorded today).

Reflect the recorded removal tools and subtract them in one variadic `cut`,
retaining `mirror_cut`'s two existing guards verbatim: the cut may not empty the
body, and it may not **change the lump count** (a reflected tool that slices a
lump apart is a typed error, never a silently severed body).

**The reachability fallback becomes an ERROR here, and that is the point.** v1
falls back to `mirror_union` when the reflected tools cannot reach the body,
because v1 had to guess which of two workflows the user meant. With an explicit
selection there is nothing to guess: a reflected cut that removes nothing means
the user selected the wrong feature or the wrong plane, so `removal_reaches_body`
returning false is **`mirror_feature_unreachable`** (§8.2), not a silent switch
to a different semantic. Explicit intent buys an honest error where implicit
intent could only buy a fallback.

### 4.3 REFUSED in v2 — modifiers (the genuinely hard case, stated plainly)

`fillet`, `chamfer`, `shell`, `draft`, and the sheet-metal fold/flange/relief
family → **`mirror_feature_unsupported`** (typed, per-feature, strict-prefix; the
last-good body is tessellated).

Why refuse rather than approximate. A modifier has no tool; it has a *result*.
The tempting approximation is a **delta solid** — `body_before.cut(body_after)`,
the slivers a fillet removed — reflected and re-cut. It is wrong in the way that
matters:

- The sliver is only the right removal where the reflected side's material is
  **congruent** to the original side's. Where it is not, the reflected sliver
  cuts a groove that is not a fillet of anything — a valid, closed,
  plausible-looking body with wrong geometry. That is the **silent retarget**
  failure class (topological-naming §1.3) reappearing in the boolean layer, and
  it is strictly worse than an error, because a user's own part has no golden.
- The correct construction re-runs `MakeFillet` on the reflected side's edges,
  which needs the reflected side to *carry* those edges (true only if the
  selection also reflects everything that created them) **and** a way to name
  "the mirror image of edge E" (§7.2 — does not exist). That is approach 2c.

So: refused, typed, loud, and documented as the v3 boundary (§11.1). One
consequence must be said out loud because a shipped doc currently overstates it:
**v2 does NOT retire the "a crossing mirror erases an asymmetric modifier"
limit.** The BACKLOG item for this work claims it does; that claim is wrong and
§12 corrects it. A midplane mirror still reflects only what the selection names,
and a modifier cannot be named.

### 4.4 REFUSED — non-body-affecting and cross-body selections

- `sketch`, `datum`, and any non-body-affecting kind: not selectable. Enforced
  at write time by the same body-affecting allowed-target constraint the on-face
  datum uses (§3.1), with `mirror_feature_unsupported` as the evaluation-time
  backstop.
- A feature whose tools were recorded against a **different body** than the
  active one: **`mirror_feature_other_body`**, generalising v1's
  `last_cut_body_id` guard (`test_mirror_does_not_reflect_a_cut_made_in_another_body`).
  §MB-0 stands: material from body A is never reflected into body B.
- A `boolean` feature between bodies: refused in v2 (its contribution is a
  two-body operation, not a tool).

### 4.5 `pattern` — in scope, and the chirality reason it works

A pattern's contribution is **N placed rigid instances**: N unioned body copies
(add) or N placed tool instances (cut), both already constructed inside
`geometry.kernel.pattern`. Recording and reflecting those *placements* is
mechanically identical to §4.1/§4.2.

Reflecting the placements — rather than reflecting the pattern's *parameters* and
re-deriving it — is what makes a reflected **circular** pattern correct. A
reflection reverses handedness: a reflected axis with the same positive
`angle_deg` winds the ring the wrong way, so a re-derived pattern would land its
instances at mirrored-but-wrongly-ordered angles (right on a symmetric ring,
visibly wrong on a partial one). Reflected placements cannot make that mistake,
because a reflection of a set of solids is the mirror image of that set, by
construction. This is a concrete instance of the general rule that keeps v2
sound: **reflect finished solids, never re-derive parameters.**

### 4.6 Nested `mirror` — in scope only when the inner mirror is itself `features`-scope

The 4-fold quadrant workflow (mirror about YZ, then mirror *that* about XZ) is a
daily action and composes exactly under v2:

- an inner `mirror` with `scope.kind == "features"` recorded the tool list it
  applied, so the outer mirror reflects **those** tools — and a composition of
  two reflections is an exact isometry (a rotation or translation), so
  `features: [base, hole, mirror1]` populates all four quadrants exactly;
- an inner `mirror` with `scope.kind == "body"` has **no** tool list — its
  contribution is a whole-body reflection whose delta is not a tool → typed
  **`mirror_feature_unsupported`**. Honest and narrow: the user converts the
  inner mirror to a `features` scope and the nesting works.

### 4.7 Summary table

| feature kind | v2 | reflected contribution | op |
| --- | --- | --- | --- |
| `extrude` add / `revolve` add / `sweep` / `loft` / `import` | ✅ | the fused tool solid | `fuse` |
| `extrude` cut (per region) / `revolve` cut / sweep-cut / loft-cut | ✅ | the recorded removal prisms | `cut` |
| `hole` (simple / cbore / csink / tapped) | ✅ | bore + recess solids (recorded today) | `cut` |
| `pattern` (add or cut) | ✅ | the N placed instances (§4.5) | `fuse` / `cut` |
| `mirror`, `scope: features` | ✅ | the tool list it applied (§4.6) | per tool |
| `mirror`, `scope: body` | 🛑 `mirror_feature_unsupported` | — (whole-body reflection) | — |
| `fillet` / `chamfer` / `shell` / `draft` | 🛑 `mirror_feature_unsupported` | — (no rigid tool; §4.3) | — |
| sheet-metal fold / flange / relief / unfold | 🛑 `mirror_feature_unsupported` | — (modifier family; own flat-pattern semantics) | — |
| `boolean` (body↔body) | 🛑 `mirror_feature_unsupported` | — | — |
| `sketch` / `datum` / non-body-affecting | 🛑 write-time 422 (§3.1); `mirror_feature_unsupported` backstop | — | — |

---

## 5. The three numbers — satisfied or refused, by value

Stated by value so a reviewer can check each one against §1's table.

- **30629.3807 (chain A) — SATISFIED, and only with an explicit selection.**
  `mirror { plane: datum YZ@20, scope: { kind: "features", features: [hole, boss] } }`
  reflects the bore tool (−1005.3096, tree order first) then fuses the reflected
  boss prism (+320): 31314.6904 → 30309.3807 → **30629.3807**. New golden
  (§6.3).
- **30629.3807 as an IMPLICIT mirror — REFUSED, deliberately.** The chain as
  `CM1_BOSS_UNMIRRORED` parametrises it today carries **no** selection, so under
  v2 it still normalises to `scope: body` and still returns **30309.3807**. That
  is not a shortfall to be fixed later: 30629.3807 from a bare
  `mirror { plane }` requires guessing that the user meant *hole and boss*
  rather than *hole* — precisely the guess §1 proves cannot be made correctly
  for all chains. **Consequence for the suite, stated up front: the `xfail` is
  cleared by giving the test an explicit selection, not by a silent green.** The
  case is rewritten into two locked tests — the selection variant asserting
  30629.3807 (marker removed) and an implicit variant asserting 30309.3807 as
  the locked `body`-scope semantic. A reviewer expecting the marker to vanish
  with the assertion untouched should read this bullet first.
- **29600.0 (chain B) — SATISFIED twice, and the lock stands untouched.** As an
  implicit / `body`-scope mirror it runs the unchanged v1 path and still returns
  29600.0 (`test_mirror_preserves_a_cut_that_precedes_the_mirrored_one` needs no
  edit — §3.2's structural byte-identity). As
  `scope: { features: [pocket B] }` it returns 30400.0 − 800 = **29600.0** by the
  v2 mechanism. Both spellings agree, which is the strongest evidence the two
  paths mean the same thing where they overlap.
- **28800.0 (chain B') — SATISFIED, and it stops being "the wrong answer."**
  `scope: { features: [pocket A, pocket B] }` → 30400.0 − 800 − 800 =
  **28800.0**. Under v1 this number was the *symptom* of a rejected rule; under
  v2 it is the correct answer to "make the plate symmetric," and B's 29600.0 is
  the correct answer to "put pocket B on the other side." The mutual exclusion
  dissolves because the two requests are now distinguishable. New golden (§6.3).
- **60000.0 (the shipped complete-the-half golden) — UNCHANGED, and reachable
  two ways.** `scope: body` runs the untouched union fallback (byte-identical
  golden). `scope: { features: [base extrude, pocket] }` reaches the same
  **value** by a different boolean sequence — equal volume/topology counts, but
  **not** asserted byte-identical (§6.1).

Net: all three of §1's numbers are reachable, none by a heuristic; the only
refusal is the *implicit* spelling of A, refused on the grounds that it is
unknowable.

---

## 6. Migration

### 6.1 The old whole-body behaviour is RETAINED, not re-expressed

**Decision: `scope: body` keeps the v1 code path verbatim. The v1 semantic does
NOT become a special case of the v2 mechanism.**

The elegant unification is available — "mirror the body" ≡ "mirror every
preceding body-affecting feature" — and it is **refused**, for a reason the
brief's own bar demands: equivalence would have to be *exact for the shipped
goldens*, and it is not provable. Equal volume and topology counts are plausible
(§2b/§5 show the 60000.0 case agrees numerically), but the goldens assert
**byte-identical GLB**, which is sensitive to B-rep face ORDER, and the two paths
hand OCCT different boolean sequences — one `fuse` of a reflected body versus k
booleans of reflected tools. The composition matrix already documents that
"a mirror-and-fuse rebuild legitimately hands OCCT the same solid with a
different internal face ORDER" (GEOMETRY-QA 2026-07-25, the identity-comparison
tolerance note). Unifying would therefore trade a **structural** byte-identity
guarantee for a hoped-for one. Keeping both branches costs one `if` and buys the
guarantee. Not clever; correct.

### 6.2 The real migration risk is the STORE, not the DTO

`record_cut_tools` currently has **one** meaning — "the most recent CUT of the
active body" — and **two** readers with two locked rules
(`_mirror_cut_tools`: most recent cut, however far back; `_pattern_cut_tools`:
immediate predecessor only). v2 widens the store to record **additive** tools
too. If an additive feature's tools land in the slot those readers use, the v1
rule silently changes meaning and every cut-aware mirror/pattern golden moves.

The widening must therefore keep the cut store's semantics exactly: tools are
recorded **with their operation**, and both v1 readers filter to `op == "cut"`
and to the most recent such record. This is the single highest-risk hunk in the
implementation and gets its own acceptance criterion (§12): the v1 readers must
return the *same tool list* before and after the widening, proven by the
unchanged goldens plus the existing `test_mirror.py` / `test_pattern.py` locks —
notably `test_pattern_after_an_intervening_fillet_unions_whole_body_not_recut`,
which exists specifically to pin the pattern's narrower rule.

Two coverage gaps to close in the same slice, because §4 claims kinds the store
does not yet cover: today only **extrude-cut** and **hole** call
`record_cut_tools`. `revolve`/`sweep`/`loft` cuts (the `_cut_active` funnel), all
additive verbs, and `pattern` record nothing. A kind claimed in §4.7 whose tools
are not recorded would surface as `mirror_feature_not_evaluated` — an error where
the user is entitled to geometry — so the recording must land with the claim.

### 6.3 Goldens (new capability ⇒ new goldens, same commit)

Three new goldens, each pinned to an existing documented tolerance tier — no new
epsilon (RESEARCH §9 / GEOMETRY-QA's two tiers):

| golden | chain | asserts | tier |
| --- | --- | --- | --- |
| `mirror-features-hole-boss-plate-40x40x20` | chain A + `features: [hole, boss]` | **30629.3807**, both bores present, both bosses present | `CURVED_TOL` 1e-8 (cylindrical faces) |
| `mirror-features-pocket-b-only-40x40x20` | chain B + `features: [pocket B]` | **29600.0**, 21 faces (a welded pocket A reads 16) | `PLANAR_TOL` 1e-9 |
| `mirror-features-both-pockets-40x40x20` | chain B + `features: [pocket A, pocket B]` | **28800.0**, 4 notches | `PLANAR_TOL` 1e-9 |

Plus, in the unit suites rather than the golden inventory: the nested-quadrant
case (§4.6), one typed refusal per refused kind (§4.7 — fillet, `body`-scope
mirror, cross-body, non-body-affecting), the `mirror_feature_unreachable` case
(§4.2), tree-order independence of the array order (§8.1), and the
composition-matrix `mir-mid`/`mir-clear` columns re-run to prove they did not
move.

---

## 7. Reference survival on the reflected side

### 7.1 v2 needs NOTHING from `faces.py` / `provenance.py`

This is the decisive property of approach 2b and the reason it is shippable now:
**no reference is resolved on the reflected side.** Every selected feature
resolved its own references once — at its own evaluation, on the original side —
and the mirror reflects the *finished solids* that resulted. A reflection is an
exact OCCT isometry of rigid solids; there is no signature to re-match, no
`resolve_face_plane` call, no `resolve_faces` call, no ambiguity rule to invoke.
Correspondingly there is no new `subshape_unresolved` / `subshape_ambiguous`
surface, and stage-1 signature matching's residual silent-retarget hole
(topological-naming §1.3) is **not** widened by this feature.

Two existing mechanisms are load-bearing-but-unchanged, and a reviewer will ask
about both:

- **`kernel/faces.py`** — downstream features *can* target the mirrored side
  today with no new machinery: the reflected face is a real face of the rebuilt
  body, `/overlay` enumerates it, and it carries a `PlanarFaceSignature` computed
  by the same helper (normal and centroid are the reflections of the original's;
  area is invariant under an isometry). A user clicks it and gets a signature
  that resolves by the ordinary exactly-one rule.
- **`kernel/provenance.py`** — the reflected material's faces first appear in
  final form in the snapshot *after the mirror*, so `attribute_faces` attributes
  them to the **mirror feature**. That is the correct and already-implemented
  behaviour (earliest snapshot containing a geometrically-equal face); selecting
  the mirror highlights the reflected material, selecting the source feature
  highlights the original. No change needed. Worth noting that a *midplane*
  mirror whose reflected material coincides with existing material will attribute
  those faces to the earlier feature, which is also right.

### 7.2 What does NOT exist: a symbolic "mirror image of face F"

There is no way to *name* the reflected counterpart of a subshape. Consequences,
stated so nobody assumes otherwise:

- a downstream feature can **pick** the mirrored side's face (fresh signature,
  §7.1) but the pick does not **track** the source face — edit the original and
  the picked reference resolves or fails on its own geometric merits, with no
  knowledge that it was "the mirror of" anything;
- symmetric authoring ("fillet this edge and its mirror image") is therefore not
  expressible in v2; and
- **approach 2c cannot be built until it is.** A reflected-frame re-run of a
  fillet must name the reflected edges, so a `MirroredSubshapeRef`
  (source ref + the mirror feature id, resolving by reflecting the source's
  resolved subshape) is the first thing v3 needs. It is an additive `GeomRef` /
  `EdgeSelector` union member under topological-naming §4's rules, and it belongs
  to the v3 item, not this one (§11.1).

### 7.3 The handedness trap (flagged for v3, harmless in v2)

`faces.py::deterministic_x_dir` pins a face's in-plane basis **from its normal**
(world axis least aligned, ties X<Y<Z, projected in). A reflection maps the
normal to the reflected normal, and the basis is then recomputed from *that* —
so the derived frame on a mirrored face is **not** the reflection of the
original's frame. Combined with the fact that a reflection reverses handedness
while the derived frame is always right-handed, re-running a sketch on a mirrored
face under approach 2c would produce a **rotated**, not mirrored, profile: an
asymmetric or lettered sketch would come out un-mirrored, in a body that looks
correct at a glance.

v2 is immune (it re-runs no sketches — it reflects solids), and that immunity is
another argument for 2b-first. Recorded here because it is exactly the trap a
future 2c slice would otherwise discover in a golden.

---

## 8. Determinism, errors, multi-body

### 8.1 Selected features apply in TREE order, not array order

The reflected tools are applied in the **evaluation order of the selected
features**, ignoring the order of the `features` array. Rationale, in the
RESEARCH §9 register:

- array order is UI-incidental (it depends on the order the user ctrl-clicked),
  so honouring it would make identical models tessellate to different bytes;
- tree order replays the selected sub-chain in the same relative order the
  original side was built in, which is what makes composition sound: chain A's
  hole-then-boss reflects as cut-then-fuse, matching the original;
- it is a total order derived from the tree, so the result is a pure function of
  the tree — the §9 contract, asserted by an array-permutation test (§6.3).

Duplicate ids in the array are a write-time **422**, not a deduplicated
tolerance: naming a feature twice is authoring nonsense, and silently accepting
it would leave the user's intent (twice? once?) unstated — the mistake v1 made.

### 8.2 Typed per-feature errors (strict-prefix, never a 500)

All are per-feature `FeatureError`s pinned to the mirror, with
`upstream_feature_id` set to the offending selected feature so the UI can name
the true cause; the mirror is `error`, downstream features are `skipped`, and the
**last-good body** is tessellated (feature-tree §4.3).

| code | when |
| --- | --- |
| `mirror_feature_unsupported` | the named kind has no reflectable contribution (§4.3/§4.4/§4.6) |
| `mirror_feature_unreachable` | a reflected cut tool removes nothing (§4.2 — the explicit-intent replacement for v1's union fallback) |
| `mirror_feature_other_body` | tools recorded against a non-active body (§4.4, §MB-0) |
| `mirror_feature_not_evaluated` | no tools recorded for the named feature — defensive: an errored predecessor already makes the mirror `skipped` |
| `mirror_failed` | the OCCT reflection/boolean failed, emptied the body, or changed the lump count on a cut (v1's code, unchanged) |
| `reference_unresolved` | the named id is absent from this prefix / not body-affecting (documents 422s first; this is the geometry backstop) |

**Suppression:** a selected feature that is **suppressed** contributes nothing
and is **skipped silently** — not an error — because the composition matrix locks
"suppress == delete" and a deleted feature simply is not in the selection's
effective set. A `features` scope whose every member is suppressed degrades to
"reflect nothing," which must therefore be a typed error rather than a silent
no-op (`mirror_feature_not_evaluated` with a message naming the suppression), by
the same no-silent-no-op rule as §3.1's `min_length=1`.

### 8.3 Multi-body

Unchanged posture: the reflection applies to the **active body** only, and §4.4's
`mirror_feature_other_body` generalises v1's `last_cut_body_id` guard so material
never crosses bodies. A reflected additive tool may create a new lump of the
active body (§4.1); a reflected cut may not change the lump count (§4.2).

---

## 9. Cost — performance and memory, honestly

- **Wall clock:** k selected features cost k exact reflections + k booleans.
  Booleans on the reference plate measured ~7 ms (GEOMETRY-QA 2026-07-25, the
  CM-3 probe measurement), so a k=5 selection adds ~35 ms against the 2000 ms
  CI rebuild ceiling — comfortably inside budget, and *cheaper* than v1's union
  path on a large body, since a tool is smaller than the body it cuts.
- **Memory — the real cost.** v1 retains exactly **one** tool list (the most
  recent cut). v2 must retain tools for every feature some mirror might name, so
  naive recording grows with tree length × tool complexity, held for the whole
  evaluation.
- **Mitigation, with precedent:** record **opt-in**. The feature list is known
  before evaluation starts, so a pre-pass collects the set of ids named by any
  `features`-scope mirror in the tree and only those features retain their tools
  (plus the single existing cut slot for the v1 readers). This is exactly the
  `body_history` posture provenance.py adopted for per-face attribution
  ("OPT-IN, so only the overlay path funds it" — engineering audit H4). A tree
  with no `features`-scope mirror therefore pays **zero** additional memory,
  which also means the widening cannot regress existing documents' rebuild cost.
- **Budget assertion:** the implementation item carries a rebuild-time assertion
  on the new goldens, per the standing performance gate — not a claim in prose.

---

## 10. What this does NOT solve

Recorded so the next reader does not over-read the decision:

1. **Mirrored modifiers.** `fillet` / `chamfer` / `shell` / `draft` and the
   sheet-metal fold family remain unmirrorable (§4.3). The shipped limit "a
   crossing mirror erases an asymmetric modifier" **STANDS** — the BACKLOG's
   claim that this work retires it is wrong and is corrected in §12.
2. **Symbolic mirrored references** (§7.2). No "the mirror image of face F";
   symmetric authoring is not expressible; v3 needs a `MirroredSubshapeRef`.
3. **Tools whose extent was derived from the body.** A tool sized against the
   body at its own evaluation (a cut whose depth was resolved from the body's
   extent) reflects that **historical** extent. On a body symmetric about the
   mirror plane this is exact; on an asymmetric one the reflected tool may
   under-reach, and `removal_reaches_body` catches "removed **nothing**", not
   "removed **less** than the reflection of what was removed." Honest limit; a
   candidate follow-up is to re-derive extent-dependent tools against the
   reflected side, which is a step toward 2c.
4. **Sheet-metal mirror**, which has its own flat-pattern semantics (a mirrored
   bend must unfold consistently) and deserves its own decision.
5. **Assembly-level mirror** (mirroring an instance / a sub-assembly): a
   different pillar, not touched.
6. **A "mirror everything" convenience** (§3.3): refused, by design, not
   deferred by accident.
7. **Multi-body selection.** v2 mirrors into the active body only; a
   `kind: "bodies"` scope is the additive slot if that becomes a real request.

---

## 11. Open questions (owned by the implementing items; none blocks endorsement)

1. **v3 scope boundary for approach 2c.** Which modifier graduates first
   (`fillet` on a selection that also reflects the material carrying its edges is
   the narrowest useful case), and does it require `MirroredSubshapeRef` (§7.2)
   or can it re-pick from the reflected body? Owned by the v3 item; gated on
   §7.3's handedness resolution.
2. **UI affordance for the scope choice.** Two radio buttons ("Mirror: body /
   features") plus a feature-tree multi-select is the obvious shape, but the
   default a novice lands on is a product decision (`frontend-design` skill +
   the mirror authoring item). Defaulting the *UI* to `features` while the
   *schema* defaults to `body` is a legitimate combination and probably the right
   one — new mirrors are explicit, old mirrors are unchanged.
3. **Does `features` scope also want the plane to be reflectable?** Reflecting a
   selection that includes a `datum` feature is refused (§4.4), yet the reflected
   side arguably wants a reflected datum for downstream sketches. Deferred until
   someone asks; a reflected datum is cheap (an isometry of a plane) but its
   x_dir inherits §7.3's trap.
4. **Interaction with undo/redo + suppression toggles at scale.** Suppressing a
   selected feature silently shrinks the effective set (§8.2). Should the UI warn
   ("this mirror reflects 2 of 3 selected features — 1 is suppressed")? A UX
   question with a correctness flavour; owned by the authoring item.
5. **Should `pattern` recording store N instances or the source tool + N
   placements?** Storing placements is smaller and reflects identically
   (§4.5 holds either way). Owned by the implementation; decide on measured
   memory.

---

## 12. Implementation + doc corrections

Filed as a BACKLOG item (P2, L) rather than built here, carrying the acceptance
criteria a builder needs: the DTO + before-validator, the `op`-tagged opt-in tool
store with the v1 readers provably unchanged (§6.2), the per-kind dispatch and
typed refusals of §4.7, tree-order application (§8.1), the three new goldens of
§6.3, the `CM1_BOSS_UNMIRRORED` rewrite of §5, and the ROADMAP/BACKLOG tick.

Two corrections this design owes other docs:

- **BACKLOG** — the CM-1-residual item claims the selected-features semantic
  "also retires the 'a crossing mirror erases an asymmetric modifier' limit." It
  does not (§4.3/§10.1); the item text is corrected in the same commit as this
  doc.
- **RESEARCH §9** — the mirror's determinism contract now includes "a
  `features`-scope mirror applies its reflected tools in tree order, never array
  order" (§8.1); noted there because it is a determinism rule a caller can
  observe, not an implementation detail.
