# Pattern Scope — Design

Status: **IMPLEMENTED** (kernel-architect, 2026-08-26) — designed and shipped at
HEAD `eed8729`, as specified, with **two recorded divergences**: §7 gained a
warning the implementation surfaced (params models `extra="ignore"`, so a
misplaced `scope` key is silently the `body` reading), and §8's golden became
`pattern-features-pocket-3x-boss-40x40x20` — a pocket + boss rather than a hole +
fillet, so every expectation is hand-derivable in closed form AND the wrong body
turns out to have identical topology counts, which is a better fixture than the
one designed. Evidence, measured numbers and the mutation runs live in
`services/geometry/tests/test_pattern_scope.py`. Scope: the
**pattern feature's input contract** — what a pattern names as the thing it
repeats. This is the pattern's half of the decision
[`mirror-semantics.md`](./mirror-semantics.md) already made for the mirror, and it
is deliberately the SAME decision: stop inferring the seed from the shape of the
body chain, and let the tree state it.

Three independent product-audit passes have now reported the same defect
(`docs/AUDIT-PRODUCT.md`: "P1 — Feature-scope pattern … currently whole-body
only"). This doc exists because the third report is the point at which "we know"
stops being an acceptable answer.

**The honest headline:** the mechanism is already built and reviewed. A
`features`-scope mirror reflects each selected feature's RECORDED RIGID TOOL
SOLIDS and re-applies that feature's own boolean; a `features`-scope pattern
PLACES those same recorded tools at the pattern's own placements and re-applies
the same boolean. Pattern is the strictly easier of the two — a translation and a
rotation are proper isometries, so §4.5's chirality trap does not exist here —
and every store, capture-set and typed-error mechanism it needs is the one v2
mirror shipped in `edbcee6`/`fa30220`. **The input contract is the whole design.**

Related: RESEARCH §9 (determinism + golden gates — the constraint on selection
ORDER, §6); [`feature-tree.md`](./feature-tree.md) §1.4 (additive param changes do
not bump `param_version`), §2.3 (materialized `feature_dependencies`), §4.3
(strict-prefix failure); [`multi-body.md`](./multi-body.md) §MB-0 (a tool recorded
against body A never applies to body B), §MB-4 (lump ordering);
[`mirror-semantics.md`](./mirror-semantics.md) §2b, §3, §4, §6.2, §8, §9 — read
that document first; this one states only what differs.

---

## 1. The problem, precisely — two measured coin flips, both reporting `ok`

The v1 pattern has ONE field (`params.pattern`) and INFERS what it repeats from
the body chain, in two places:

* `geometry.features.evaluate._pattern_cut_tools` — array the previous feature's
  removal tool **only if** the immediately-preceding body-affecting feature is the
  cut that recorded it, else array the whole body;
* `geometry.kernel.pattern.linear_pattern_cut` / `circular_pattern_cut` — the
  VACUOUS-CUT FALLBACK: if no placed copy of the tool can reach the body, array
  the whole body instead.

Each rule is individually defensible and was individually reviewed. Together they
mean the same dialog, with the same numbers in it, produces two different KINDS of
result, and the feature reports `ok` either way. Both flips below are deterministic
and reproduce from a clean tree; both were measured at `eed8729` on build123d
0.11.1 / OCCT 7.9 (`services/geometry/tests/test_pattern_scope.py` pins them).

### 1.1 Flip A — an unrelated feature between the cut and the pattern

A 40 x 40 x 20 plate, a Ø8 through-hole at (8, 20), then a linear pattern
`{direction: +X, spacing_mm: 12, count: 3}`. The pattern params are BYTE-IDENTICAL
in both trees; the only difference is a corner fillet the user added for an
unrelated reason.

| tree | volume (mm³) | bbox X | faces | every feature |
| --- | --- | --- | --- | --- |
| plate → hole → **pattern** | `28984.071052553798` | 0 … 40 | 9 | `ok` |
| plate → hole → **fillet r3** → **pattern** | `50040.17702849742` | 0 … **64** | 11 | `ok` |

`28984.071052553798` is exactly `32000 − 3·π·4²·20` — three holes, the bolt-row
the user asked for. `50040.177` is the entire plate replicated three times along
+X and fused. The part got 24 mm longer. Nothing said so.

### 1.2 Flip B — one number in the same dialog

The same plate, the Ø8 hole moved to (34, 20) so its tool spans x ∈ [30, 38], and
a `count: 2` linear pattern along +X. Only `spacing_mm` changes — the field a
direct-manipulation drag handle will eventually be wired to.

| `spacing_mm` | volume (mm³) | bbox X | faces | every feature |
| --- | --- | --- | --- | --- |
| 8 | `30798.15119907386` | 0 … 40 | 10 | `ok` |
| 12 | `40594.69035085126` | 0 … **52** | 7 | `ok` |

At 8 the placed tool still overlaps the plate, so the pattern arrays the HOLE. At
12 the placed tool clears the +X face, so the vacuous-cut fallback arrays the
BODY. The honest answer to "put the second hole 12 mm to the right" on a part that
ends 6 mm to the right is an ERROR. Instead the part silently doubles.

### 1.3 Why this is worse than a missing feature

Both results are closed, valid, `BRepCheck`-clean solids, and the part workspace
reports **`Up to date`**. Every downstream check agrees with itself: the mesh is a
correct mesh OF THE WRONG BODY, the STEP round-trip round-trips the wrong body to
1e-9, and the mass properties are exact properties of the wrong body. This is the
silent-wrong-geometry class that FINDINGS #1/#2 and CM-1/CM-2 already cost this
project three fixes; the fixes each removed one wrong inference and left the
INFERENCE ITSELF in place. §1.1 and §1.2 are what remains, and no third heuristic
retires them, because the ambiguity is in the INPUT: "pattern this hole" and
"pattern this plate" are different requests that today have the same spelling.

---

## 2. Decision — the pattern's input contract

`PatternParamsV1` gains `scope`, a `kind`-discriminated union with exactly two
members. This is `MirrorScope` with the words changed, deliberately: two verbs
that ask the same question of the user should not ask it two different ways.

```jsonc
// v1 spelling, still valid, still means what it meant
{ "pattern": { "kind": "linear", "direction": {...}, "spacing_mm": 12, "count": 3 } }

// the same, spelled out
{ "pattern": { ... }, "scope": { "kind": "body" } }

// the v2 reading: repeat THESE features
{ "pattern": { ... },
  "scope": { "kind": "features",
             "features": [ { "kind": "feature", "feature_id": "…hole…" } ] } }
```

* **`{"kind": "body"}`** — the v1 reading, NAMED rather than implied: both
  inference rules of §1 run verbatim, on the same code path, producing the same
  bytes. Every persisted pattern and every shipped pattern golden validates and
  evaluates unchanged.
* **`{"kind": "features", "features": [...]}`** — an explicit, non-empty,
  TREE-ORDERED selection of earlier body-affecting features. Each selected
  feature's recorded rigid tool solid(s) are placed at the pattern's `k = 1 …
  count-1` placements and that feature's OWN boolean (`fuse` / `cut`) is
  re-applied. Nothing is inferred; nothing falls back.

`min_length=1` (an empty selection is authoring nonsense, not a no-op) and
duplicate ids are a 422 rather than silently deduplicated — naming a feature twice
leaves the intent unstated, which is the mistake v1 made. Bounded by
`MAX_PATTERN_SCOPE_FEATURES`, the work-bound twin of `MAX_MIRROR_SCOPE_FEATURES`.

### 2.1 Why this is additive

`param_version` stays 1 (feature-tree §1.4). A params blob with no `scope` key —
i.e. every row in every existing document — normalises to `{"kind": "body"}`
through a `mode="before"` validator, the same idiom `MirrorParamsV1.
_legacy_body_scope` and `DatumFeature._legacy_offset_kind` use. `scope: null` is
normalised too, so a client that round-trips an omitted optional as an explicit
null is not a 422. No migration, no stored-shape change, and the byte identity of
`pattern-linear-3x-bar`, `pattern-circular-4x-quadrant-box`,
`pattern-cut-6hole-boltcircle-60x60x10` and `pattern-cut-hole-feature-3x-60x60x10`
is STRUCTURAL — the `body` branch dispatches to code this work does not touch —
rather than measured.

### 2.2 Refused: making `features` the default, or auto-selecting the tip

The audit's recommendation is "an explicit *features to pattern* selection
defaulting to the tip". The DTO default must stay `body` (§2.1 — anything else
rewrites the meaning of persisted rows), and "the tip" is not knowable inside
`py_kit.schemas`. So the tip default is a UI PRE-FILL, not a DTO default: the
dialog opens with the tip body-affecting feature already in the selection and
SENDS `scope` explicitly on every new pattern. The DTO's job is to make the
request unambiguous; choosing a good starting selection is the dialog's job, and
putting it in the schema would reintroduce exactly the "the tree does not say what
the user meant" property this design removes. §7 states the contract the UI half
builds against.

Also refused, for the same reason mirror-semantics §3.3 refuses it: an automatic
"pattern everything up to here". The natural spelling of "everything" is a
different body than the one `body` scope locks, so it would be a third silent
reading.

---

## 3. What "pattern a feature" means, per kind

Identical to mirror-semantics §4.1–§4.4 and §4.7, with `place` substituted for
`reflect`; that table is not restated. In scope: `extrude`, `revolve`, `sweep`,
`loft`, `hole`, `import` (additive tool contributors → place + `fuse`; subtractive
→ place + `cut`), `pattern`, and a `features`-scope `mirror`. Refused with a typed
`pattern_feature_unsupported`: every MODIFIER (fillet / chamfer / shell / draft and
the sheet-metal fold / flange / relief family — they have a RESULT and no tool),
`boolean`, `sketch`, `datum`, and a `body`-scope `mirror`. §4.3's argument is the
load-bearing one and holds verbatim: approximating a modifier's contribution with a
`before.cut(after)` delta sliver produces a valid, closed, plausible, WRONG body.

Membership is necessary, not sufficient — a selectable feature must ALSO have
recorded tools, which is why a `body`-scope mirror (which records nothing) is
refused by the same check that refuses a fillet.

### 3.1 The chirality argument does not apply, and that is the point

mirror-semantics §4.5 has to reflect a nested pattern's PLACEMENTS rather than
re-derive them from its parameters, because a reflection reverses handedness and a
re-derived ring would wind backwards. A pattern's transforms are a translation and
a rotation — proper isometries — so re-deriving would be harmless here. We place
the recorded tools anyway, through the SAME
`linear_pattern_placements` / `circular_pattern_placements` the `body` path calls,
because one definition cannot drift from itself (CLAUDE.md DRY). The result is that
a `features`-scope pattern OF a pattern composes exactly: the inner pattern's
recorded placements are themselves placed, giving a genuine 2-D grid — which is
also the cheapest available answer to the long-standing "2-direction pattern" gap
(`docs/BACKLOG.md`), though this design does not claim that item.

---

## 4. Typed per-feature errors — the honest end of the fallback

Each is pinned to the offending SELECTED feature via `upstream_feature_id`, so the
UI can name the true cause instead of blaming the pattern (mirror-semantics §8.2):

| code | when |
| --- | --- |
| `reference_unresolved` | the id is not a feature of this evaluated prefix (documents 422s a forward/self/missing ref at write time; this is the backstop) |
| `pattern_feature_unsupported` | the named kind has no placeable contribution (§3) |
| `pattern_feature_other_body` | the tools were recorded against a different body than the active one (§MB-0) |
| **`pattern_feature_unreachable`** | **a placed cut removes nothing — §1.2's flip, as an error** |
| `pattern_feature_not_evaluated` | nothing was recorded for any selected feature, so the pattern would be a silent no-op |
| `pattern_disjoint` / `pattern_failed` | the existing kernel outcomes, unchanged |

`pattern_feature_unreachable` is the whole point of §1.2. The `body` scope keeps
its vacuous-cut fallback (it is guessing between two workflows and a silent no-op
would be worse); an explicit selection has nothing to guess, so the honest answer
is an error. This is exactly the split mirror-semantics §4.2 made between
`mirror_cut`'s fallback and `mirror_feature_unreachable`.

`count == 1` is a documented no-op in BOTH scopes (it is a no-op pattern, not an
empty selection), so it leaves the body unchanged rather than raising
`pattern_feature_not_evaluated`.

---

## 5. Migration and the store

The v1 readers `_pattern_cut_tools` and `_mirror_cut_tools` share ONE recorded-cut
slot with two different documented rules, and mirror-semantics §6.2 calls widening
it the single highest-risk hunk of that work. **This design does not touch it
either.** The `features` scope reads the SEPARATE per-feature store
(`EvaluationState.feature_tools`) v2 mirror added, so the guarantee "the `body`
path returns an identical tool list" stays structural.

One rename, mechanical: the opt-in capture set `EvaluationState.mirror_scope_ids`
/ `_mirror_scope_ids()` becomes `tool_scope_ids` / `_tool_scope_ids()`, because it
now collects the ids named by a `features`-scope mirror OR pattern. A field named
`mirror_scope_ids` holding pattern ids would be a lie, and this file is where the
next reader will look. The set is still opt-in (§9 of mirror-semantics): a tree
with no `features`-scope verb retains nothing extra and pays nothing. It is part of
the rebuild-cache key (`rebuild_cache.prefix_keys(capture_scope=…)`, already a
neutral name), so a cached prefix can never be resumed with the wrong capture set.

---

## 6. Determinism

Selected features apply in TREE order, never array order (mirror-semantics §8.1 —
array order is UI-incidental, so honouring it would make identical models
tessellate to different bytes). `scoped_feature_types` is insertion-ordered by
evaluation, so filtering it IS tree order. Within one feature, its recorded groups
apply in recorded order, and placements are enumerated placement-outer /
source-inner by the shared helpers. No unordered iteration participates; nothing
is seeded because nothing is random.

---

## 7. The contract the UI half builds against

The frontend item owns the dialog and the ghosted preview; this section is the
seam, so that half lands on top of this one without a schema change.

1. **Send `scope` explicitly on every NEW pattern.** Omitting it means "body
   scope" forever (§2.1). A dialog that omits it is authoring the §1 defect.
   **And put it at `params.scope`, not `params.features`** — every params model in
   this repo is pydantic-default `extra="ignore"`, so a payload that spells the
   selection at the wrong level validates, evaluates, and silently gives the
   `body` reading. Measured while writing this: the first draft of
   `test_pattern_scope.py` did exactly that and seven tests passed against the
   wrong scope. There is no server-side guard against it (tightening `extra` is a
   repo-wide decision that would reject persisted blobs carrying stale keys), so
   the contract test on the UI side should assert on the RESULT, not the 2xx.
2. **Pre-fill the selection with the tip body-affecting feature** (§2.2) and show
   it as a removable chip, exactly as the mirror dialog's "features to mirror"
   list does. The user disposes; the tool proposes.
3. **`features` is an array of `FeatureRef`** (`{"kind": "feature", "feature_id":
   "<uuid>"}`), non-empty, no duplicates, every id an EARLIER body-affecting
   feature. All three are 422s at the documents boundary, so the dialog should
   disable the offending selection rather than round-trip an error.
4. **Selectable set** = §3's in-scope kinds that have already evaluated `ok`. The
   tree already knows each feature's `type`; a refused kind should be
   non-selectable in the list, not a post-OK error.
5. **Errors carry `upstream_feature_id`** — surface the offending feature's NAME
   (never the raw UUID, per the audit's M16), not "pattern failed".
6. **A pattern edited from `body` to `features` is a normal params edit** — same
   feature id, same `param_version`. Switching TO `features` materialises
   `feature_dependencies` edges, so deleting a patterned feature afterwards is a
   409-with-dependents; the dialog should expect that, and it is a feature.
7. The preview has no new server surface: a ghosted preview is an evaluation of
   the tree with the candidate params, which is what the existing evaluate route
   already does.

---

## 8. Goldens (new capability ⇒ new golden, same commit)

`pattern-features-pocket-3x-boss-40x40x20` — a 40 x 40 x 20 plate, a 4 x 20 x 10
pocket extrude-CUT at x in [4,8], an 8 x 8 x 5 BOSS on the top face (the unrelated
feature), then `features: [pocket]`, `spacing_mm: 12`, `count: 3`. **29920.0 mm³,
bbox X 0..40.** Delete the `scope` key and the identical tree evaluates to
**51359.99999999999 with bbox X 0..64**, every feature `ok` — it is §1.1's defect
with the seed stated. All-planar, so every expectation is hand-derived in closed
form and the tolerance is the reviewed PLANAR tier (1e-9), never a new epsilon.

The fixture turned out to carry a lesson worth the change from the designed
hole+fillet version: **the wrong body has the SAME face, edge and shell counts
(26 / 60 / 1) as the right one.** Topology does not discriminate them. Volume, the
bounding box and the material positions do, which is why the golden and
`test_pattern_scope.py` assert all three and why "topology counts are exact-match"
is a necessary gate and never a sufficient one.

The four shipped pattern goldens are unchanged and their byte identity is the
§2.1 structural guarantee.

---

## 9. What this does NOT solve

* **The `body` scope still flips.** §1.1 and §1.2 remain true of a scope-less
  pattern, by design — that is what "additive" costs. What changes is that the
  flip is now a documented property of a NAMED legacy reading that the UI never
  authors, instead of the only available spelling. `test_pattern_scope.py` pins
  both flips so a future "improvement" to the inference cannot quietly move a
  persisted document's geometry.
* **Modifiers are still unpatternable** (§3) — the same refusal, and the same
  v3 (re-evaluate the selected features under a transformed frame) as
  mirror-semantics §2c.
* **No 2-direction pattern DTO.** §3.1 makes a pattern-of-a-pattern compose
  correctly, which covers the common grid, but the one-command rectangular pattern
  remains its own backlog item.
* **No pattern of a whole BODY in a multi-body part** (`kind: "bodies"`) — the
  additive third member, unbuilt, exactly as mirror-semantics leaves it.
