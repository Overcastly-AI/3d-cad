# Pre-selection / hover feedback — design spec (vision-steward, 2026-08-01)

Founder brief, verbatim: *"When picking a point on the screen there are too
many to see what you are clicking. Take a look at how fusion or plasticity
handles this. They almost have a snapping pointer that allows you to select
and the body face highlights with small axis showing direction."*

Filed the same night, separately: a sketch line that **"wouldn't even
select,"** face picking that is **"very difficult,"** a cut that **"misses
everything going a different way."** One diagnosis covers all three: Loft
never tells you what you are about to act on before you commit the click. A
mis-aim is invisible until it's expensive. This spec is the fix, scoped to
**hover / pre-selection feedback only** — not a click-to-select redesign, not
the broader touch-target-size P2 already filed (`docs/UI-REVIEW.md` "touch/
tablet ergonomics are unmet product-wide").

## Scope boundary

In scope: what highlights before a click, at what granularity, how it reads
distinct from committed selection, how the app disambiguates when several
things are under the cursor, and the hovered-face direction indicator. Out of
scope: authoring a new click-to-select-geometry→tree binding (none exists
today — `ModelMesh` takes no `onClick`; that is a separate, larger feature),
and the general touch-target-size floor (already tracked).

## What already exists — build on this, don't re-derive it

Loft's picking machinery is more mature than the symptom suggests, and this
spec's job is mostly to **unify and extend** it, not invent from nothing:

- **`apps/web/src/viewport/ModelMesh.tsx`** — default-mode hover is
  **body-granularity** (`BodyHighlight = "none"|"hover"|"selected"|"feature"`,
  line 37). The pointer handler (`faceOrdinalOf`, line 335) **already resolves
  the exact face ordinal under the cursor** — it's used once to skip a hidden
  face, then discarded. The hard part (raycast → B-rep face ordinal) is done;
  it's just not surfaced.
- **`apps/web/src/viewport/FacePickOverlay.tsx`** / **`EdgePickOverlay.tsx`** —
  armed pick commands (datum plane, hole, shell, draft, sketch-on-face /
  fillet, chamfer) already highlight the **individual** face/edge under the
  cursor: a translucent brass patch laid on the face's own plane
  (`viewport.facePick.hover/selected`), or the edge's true polyline
  (`measure.edgeHover/edgeSelected`) — real topology, not a bounding box. The
  face patch is already built from `signature.centroid` + `signature.normal`
  (line 53) — the normal is already flowing through the code, just not drawn.
- **`apps/web/src/sketch/snap.ts`** (UI-W5, shipped 2026-07-31) — while
  *drawing*, a candidate snap names itself at the cursor before the click: a
  glyph (`SNAP_MARKS`) + the word (`SNAP_LABELS`), strict class-priority
  ranking (endpoint > mid/centre > intersection > tangent/perpendicular).
  This is the exact vocabulary the founder is describing — it just doesn't
  run while *selecting* existing geometry, only while placing new geometry.
- **`apps/web/src/sketch/pick.ts`** — entity **selection** (not drawing) has
  its own tolerance-based candidate resolution (`pickCandidates`,
  `PICK_TOLERANCE_PX = 8`) and an already-implemented cycling rule
  (`toggleSelection`: repeated clicks at the same spot walk the stacked
  candidates). The mechanism is right; nothing on screen shows it exists.
- **`packages/design/src/primitives/PickNode.tsx`** — every pickable entity in
  an armed overlay gets a real, focusable, screen-reader-named DOM button, but
  it also paints a **visible reticle at rest, always**, not only on hover.
  `docs/UI-REVIEW.md`'s 2026-07-24 P2 ("pre-pick affordances are still
  DOM-square blankets... ~22 white squares and diamonds scattered over a
  six-face plate the moment Measure is armed") is still open — this is
  measured evidence the founder's "too many to see" complaint is not a
  one-off impression.
- **A structural cause behind "face picking is very difficult":** the face
  patch highlight looks like real topology, but the **click target is a
  fixed 24 px `PickNode` button at the face's area centroid** (`Html
  position={face.signature.centroid}`), not the face's actual boundary. You
  cannot click anywhere on a face — only within 24 px of its centroid. On a
  dense hole pattern (the audit's "7 squares for a hole's face pick") several
  centroids sit close together, which *is* "too many to see what you're
  clicking," literally. Fusion/Plasticity raycast the real solid — click
  anywhere on the face selects it.
- **Gizmo / ViewCube:** already shipped (`viewport.gizmo` tokens, `GizmoHelper`
  in `Viewport.tsx`) — mandate 3a's table-stakes nav element is not part of
  this gap.

## 1 — Entity hover model

**Default rule: hover granularity matches the finest thing a raycast can
resolve, not a fixed body/face split.** Concretely:

- **Solid body, default select tool, mouse/pen:** hover resolves to the
  **face ordinal** under the cursor (continuous raycast — extend
  `ModelMesh`'s pointer handler from `onPointerOver`/`onPointerOut`-only to
  also track `onPointerMove`, since r3f only re-fires `onPointerOver` when the
  pointer *enters* the mesh, not when it crosses from one face to another of
  the *same* mesh). The result: **only the one face under the cursor lights**,
  using the SAME localized-highlight machinery the "feature selected" state
  already uses (`setFaceMaterials` routes the hovered ordinal to its own draw
  group; boundary edges of just that face get `subsetEdges` + a hover-tinted
  line, exactly as `featureEdges` already does for the selected feature). The
  rest of the body keeps its studio matcap untouched — "addressed face under a
  worklight," the same read `featureSelect` already established for selection,
  now extended to hover. **Tokens: reuse, don't add.** Face tint =
  `viewport.facePick.hover` / `hoverOpacity` (0.16, already exists); face
  boundary edges = `viewport.hover` (brass-hover, already exists). This is a
  visual-language extension, not a new palette.
- **Graceful fallback:** when the mesh can't be partitioned into faces (no
  `OverlayFace` data loaded, or a body that can't be split), hover falls back
  to today's whole-body glow — never a dead/invisible hover. Same posture the
  per-body view state already takes (`perBodyFaces === null` → single-state
  mesh).
- **Whole-BODY hover stays whole-body** wherever the *consumer* is body-grain
  by construction: a tree row for a body, an assembly instance, a "pick a
  body" step of a future boolean-operand UI. Granularity is drawn from what
  the context will actually consume, not a fixed rule — this is the same
  contract `FacePickOverlay`/`EdgePickOverlay` already apply to armed
  commands; this spec generalises it to the **unarmed default** state too.
- **Armed face/edge pick commands (datum, hole, shell, draft, sketch-on-face,
  fillet, chamfer):** keep the existing patch/segment highlight language
  unchanged. What changes is the **hit-test**: the continuous mesh raycast
  (now wired for default hover) becomes the PRIMARY hit-test for mouse/pen —
  click anywhere on the face or edge, not just within 24 px of its
  centroid/midpoint. The `PickNode` DOM grid remains, but demoted to a
  SECONDARY role: keyboard focus target + screen-reader name + touch tap
  target (§5). This is the direct fix for "face picking is very difficult."
- **Sketch mode:** unchanged grain (point > curve, `pick.ts`) — the gap there
  is disambiguation and vocabulary (§2/§3), not granularity.
- **Hover is always visually distinct from selected**, already true and kept:
  hover = quiet warm-up (`hoverOpacity`/`hoverInk`/`edgeHover`, held close to
  neutral), selected = full-strength brass (`selectedOpacity`/`selectedInk`/
  `edgeSelected`). Nothing in this spec changes that contrast; it only adds
  the missing face-grain layer underneath it.
- **Missing token to add:** none for the face-hover core (fully covered by
  existing `facePick`/`hover` tokens). One new token group IS needed for §4
  (the normal indicator) — named there.

## 2 — Snap-point vocabulary (sketch mode)

The glyph vocabulary built for **drawing** (`sketch/snap.ts`'s `SNAP_MARKS` +
`SNAP_LABELS`: endpoint, midpoint, centre, intersection, tangent,
perpendicular, plus the axis locks) is correct and stays exactly as shipped
— **do not fork it.** The gap is that the **select tool** (`sketch/pick.ts`)
resolves a winning candidate but never names it. Fix: extend the existing
`SnapMarker` component to also render for `hoverPick` (select-mode) using one
shared kind→glyph mapping:

| `pick.ts` candidate | Marker |
|---|---|
| point, `start`/`end` | `SnapEndpointIcon` / "Endpoint" |
| point, `center` | `SnapCenterIcon` / "Centre" |
| point, `fitN` (spline fit point) | `SnapEndpointIcon` / "Fit point" (endpoint-class — a spline fit point is a defining vertex, same visual class) |
| entity (curve) | **new glyph**, labelled with the entity's own kind — "Line" / "Circle" / "Arc" / "Spline" (already known from `entity.kind`; more informative than a generic "Curve" at zero extra cost) |

**New glyph needed:** an "on-curve" mark for the entity case — a short tick
perpendicular to the curve at the pick point (the drafting "pick" tick,
visually distinct from the round endpoint/centre dots and the diamond/X
intersection marks already in the set). Add it beside the existing icons in
`icons.tsx`; no new color — same `text-brass-hover` ink the drawing marker
uses.

**No 3D solid-hover glyph vocabulary.** In 3D, the *shape* of the highlight
already says what kind of entity it is — a lit patch is a face, a lit
polyline is an edge, a lit point is a vertex — so a glyph would be redundant
chrome layered over a highlight that is already legible (`SnapMarker`'s own
existing rationale: "a symbol only informs someone who already learned it").
Glyphs are a 2D-sketch-plane device only, where geometry is infinitely thin
and needs the extra word.

## 3 — Disambiguation (the founder's literal complaint)

Two genuinely different problems hide behind "too many to see what you are
clicking" — treat them differently, argued below:

**(a) Real stacked candidates — sketch selection, and dense armed-pick
overlays.** Sketch entities are infinitely thin and armed-pick `PickNode`
targets are fixed-size DOM buttons, so two of either can legitimately overlap
on screen (two endpoints at a corner; two adjacent small hole faces). This is
the founder's complaint, literally. **Keep the existing click-to-cycle rule
unchanged** (`toggleSelection`: repeat-click walks the stack) — it matches
industry precedent (Onshape: `` ` `` cycles the candidate list under the
cursor, `Shift+` `` ` reverses — [cad.onshape.com/help/Content/Home/
select_other.htm](https://cad.onshape.com/help/Content/Home/select_other.htm);
SolidWorks: right-click → **Select Other** opens a list of every entity under
the pointer in encounter order, Tab or the middle-mouse wheel — or repeated
right-click — walks it —
[blogs.solidworks.com/tech/2018/10/select-other-tool.html](https://blogs.solidworks.com/tech/2018/10/select-other-tool.html)).
Loft's click-cycle is the same idea via the primary mouse button instead of a
side menu — no new interaction to learn. **What's missing is discoverability**
— nothing today tells the user cycling is even possible. Fix, two additions
riding the §2 marker:
  1. **Name the winning candidate** before the click (§2's extended
     `SnapMarker`).
  2. **A stacked-candidate count badge** — when `pickCandidates(...).length >
     1`, a small round chip (reuse the existing "balloon" idiom —
     `radius.full`, the app's one other round-badge convention) beside the
     marker reading `+N`, with the marker's `aria-label` stating "N more
     here — click again to select the next." Zero new tokens (chip styling =
     `bg-anvil`/`border-hairline`/`text-mist`, identical to the marker's
     existing label chip).
  For **armed face/edge overlays**, the same count applies when the raycast
  hit and a nearby `PickNode` centroid disagree within tolerance — surfaced
  the same way, at the raycast hit point.

**(b) Default 3D face hover — NOT a stacking problem, a granularity problem.**
A mesh raycast against an opaque solid returns exactly one frontmost
triangle — there is no ambiguity to disambiguate. What reads as "too many
candidates" here is really "the whole body lights up and I can't tell which
face," which §1 already fixes at the source. **Deliberate divergence from
Fusion/SolidWorks:** neither this spec nor v1 ships a 3D "Select Other" list
for coincident/hidden geometry (e.g. an edge sitting exactly on a face plane,
or picking a face fully occluded from the current view) — real gaps in
Fusion/SolidWorks parity, but a smaller and separable problem from tonight's
three complaints, and orbiting to see the target is the more honest fix for
"it's occluded" than a menu that pretends you can select what you can't see.
Filed as a named residual (SEL-6, §7), not silently dropped.

## 4 — Hovered-face axis / normal indicator

**What it shows:** a single directional arrow (shaft + head, not a full
3-axis triad — the founder's "small axis" is answered by one clear vector,
not three competing ones) drawn at the addressed face's centroid, along its
outward normal (already computed for planar faces via `signature.normal`;
for a non-planar/curved face under default hover, use the picked triangle's
face normal — available from the same raycast intersection that already
resolves the ordinal, no extra geometry work).

**When it appears:**
- **Passive (informational):** on hover of any face, in default select mode
  or an armed face-pick command — quiet, brass-hover, no interaction. This
  alone answers "which way is out," the direct fix for orientation confusion
  during authoring.
- **Active (direction control):** the moment Extrude or Cut is ARMED and a
  profile/face is chosen, the single arrow becomes a **pair**: the current
  `direction` ("normal") drawn solid and full-strength brass, its opposite
  ("reverse") drawn dashed and dim (`viewport.gizmo`-weight, not brass, until
  hovered). Clicking either arrow sets the editor's existing `direction`
  field (`ExtrudeEditor`'s `"normal"|"reverse"` toggle already exists — this
  makes it a viewport control, not just a text option nobody looks at while
  aiming the model). This is the direct fix for "a cut misses everything
  going a different way": the user sees which side removes material before
  committing, instead of discovering it from the result.

**Staying legible without clutter:**
- Only the ONE addressed face ever carries an arrow — never one per face,
  never one per body. Same "only what's under the cursor" discipline as the
  rest of this spec.
- **World-space length**, not screen-space-fixed: `clamp(0.3 * sqrt(area),
  3mm, 40mm)` — scales with the face's own footprint (mirrors the exact
  formula `FacePatch` already uses for its disc radius, §1's reused pattern),
  clamped so a tiny hole face doesn't vanish and a large plate face doesn't
  spawn a room-filling arrow. World-space (not screen-space/`sizeAttenuation`
  off) is deliberate: this is a 3D directional fact about the model, and it
  should read with real depth/perspective — a Plasticity-style studio object,
  not a flat HUD sticker (design mandate 3a).

**New token group needed** (nothing existing covers a directional arrow):
`viewport.faceNormal` in `packages/design/src/tokens.ts` —
```
faceNormal: {
  /** Passive hover — informational only. */
  hover: color.brassHover,
  /** Chosen direction while an extrude/cut is armed. */
  forward: color.brass,
  /** Alternate direction — quiet until hovered, never brass at rest
   *  (brass means "this is what will happen," and the alternate hasn't). */
  reverse: color.etch,
  reverseHoverColor: color.brassHover,
  /** Shaft + head geometry (px-independent, world mm at 1x — see length
   *  formula above). */
  shaftWidthMm: 0.6,
  headLengthMm: 3,
  headWidthMm: 2,
}
```

## 5 — Touch and accessibility

**Touch has no hover**, so the two-phase pattern this spec relies on (preview,
then commit) has to be re-created explicitly rather than inherited for free.
*I could not verify Fusion's or Plasticity's tablet/touch pre-selection
behaviour from their public docs* (Plasticity is desktop-only; Fusion's
touch/tablet mode wasn't in the material this pass reviewed) — the following
is Loft's own considered default, not a copied pattern, and should be read as
such:

- **Unambiguous tap (single candidate, or a face raycast hit) commits
  immediately** — no needless double-tap tax for the common case, matching
  how a touchscreen normally behaves.
- **Ambiguous tap (`pickCandidates(...).length > 1`, or two `PickNode`
  targets within touch tolerance) previews instead of committing:** the
  marker + count badge from §3 appears at the tap point, selection does not
  change. A second tap in the same small radius within ~400 ms (or an
  explicit tap on the badge itself) commits the top candidate; tapping
  elsewhere dismisses the preview. This is the direct touch analogue of
  mouse hover-then-click, applied only where ambiguity genuinely exists.
- **The normal-arrow pair (§4) is tap-target-sized on touch** (≥24 px hit
  area per arrow, the existing `target.dense` floor) since it's a real commit
  action (sets extrude/cut direction), not decoration.

**Keyboard equivalence.** Where hover already gates a required action, an
equivalent already exists and must be preserved: every armed-pick `PickNode`
wires `onFocus`/`onBlur` to the same state setter as `onPointerOver`/`Out`
(confirmed in `FacePickOverlay`/`EdgePickOverlay` today), so Tab-cycling
already previews for keyboard users exactly as mouse hover does. The §2/§3
marker and count badge must read off **focus, not just pointer position**, so
a keyboard user gets the same name + count a mouse user gets.

**Named, not solved, residual:** the sketch **select tool** (`pick.ts`) has
no keyboard path at all today — it resolves purely from pointer coordinates,
with no Tab-reachable target for an existing entity or point. This is a
real, pre-existing a11y gap this spec does not close (a proper fix means
giving every sketch entity/point a focusable `PickNode`-style target, the
same lift `FacePickOverlay`/`EdgePickOverlay` already paid for 3D picks) —
named honestly rather than implied-fixed. Filed SEL-6 below.

## 6 — Acceptance criteria (QA-drivable)

| # | Criterion | Founder complaint it would have caught |
|---|---|---|
| A1 | Hovering a multi-face body in default select mode lights exactly ONE face (patch + localized boundary edges), not the whole body; QA hook reports a hovered-face ordinal + the body's total face count so this is provable without reading pixels (mirrors the existing `onFaceSelectionChange` pattern). | "face picking is very difficult" |
| A2 | Clicking anywhere within an armed face/edge's true boundary (not just within 24 px of its centroid/midpoint) hits it — proven by clicking near a face's EDGE, far from its centroid, in a dense-hole-pattern fixture. | "face picking is very difficult" |
| A3 | Hovering a sketch line with no closer point present shows the extended `SnapMarker` naming the entity kind before the click; the click selects exactly the named candidate. | "a sketch line that wouldn't even select" |
| A4 | Two coincident sketch endpoints at a corner produce a `+1` count badge on the marker; two successive clicks in the same spot select each in turn (regression-proves `toggleSelection` is unchanged while the badge is new). | "a sketch line that wouldn't even select" |
| A5 | Hovering any face shows the passive normal arrow, world-space-sized between the stated clamps at both a small (≤5mm) and large (≥200mm) face. | "cut misses everything going a different way" |
| A6 | With Extrude/Cut armed on a chosen face, both direction arrows render (forward solid, reverse dashed); clicking the reverse arrow flips the editor's `direction` field and the live ghost preview's side, matching the arrow that was clicked. | "cut misses everything going a different way" |
| A7 | `PickNode` rest-state opacity is measurably reduced from today's fully-opaque reticle (pixel census, mandate 3c) while hover/focus/selected states are unchanged — proves the "DOM-square blanket" P2 is closed by mechanism, not by screenshot cherry-picking. | "too many to see what you are clicking" (root-cause finding, §"what already exists") |
| A8 | Touch: an unambiguous tap on a face commits immediately (no double-tap needed); an ambiguous tap (two adjacent `PickNode`s within touch tolerance) previews first and requires a second tap or badge tap to commit. | touch parity for all three complaints |
| A9 | Tab-focusing an armed face/edge `PickNode` shows the same marker/badge a mouse hover would at that target. | a11y equivalence (§5) |

## 7 — What this spec does NOT close (named, not hidden)

- Click-to-select geometry→tree (out of scope, §"Scope boundary").
- A 3D "Select Other" list for coincident/occluded geometry (§3b — deliberate
  v1 divergence, argued).
- Keyboard-reachable sketch entity/point picking (§5 — real, named gap).
- The broader touch-target-size floor across the whole product (already
  tracked, `docs/UI-REVIEW.md` P2, not re-filed here).

## Sources consulted (competitive research)

- Fusion 360 pre-selection highlighting exists on hover for body/face/edge/
  component and cannot currently be disabled (confirmed via forum, not
  primary Autodesk docs — `help.autodesk.com`'s own selection pages returned
  HTTP 403 to this session's fetcher both directly and via the search
  pipeline, so the *exact* hover-vs-selected colour values and any
  normal-indicator affordance on Fusion's side are **not independently
  verified** here and are not asserted as fact anywhere above):
  [forums.autodesk.com/.../how-to-turn-off-pre-selection-highlighting-on-fusion-360](https://forums.autodesk.com/t5/fusion-design-validate-document/how-to-turn-off-pre-selection-highlighting-on-fusion-360/td-p/10214969).
  Fusion's selection-priority filters (restrict picking to one entity class at
  a time) are documented at `help.autodesk.com?guid=SLD-SELECTION-PRIORITY-FILTERS`
  (title/summary only, page body also 403'd to this session).
- Plasticity's snapping system (Control-Vertex / Curve / Region / Edge / Face
  / Measurement snap types, a small on-screen indicator at the snap target,
  tip-help text on hover, selection sharing the same raycast data as
  snapping) — summarised from `doc.plasticity.xyz/plasticity-essentials/
  plasticity-interface/snap` via search indexing; the **primary doc page
  itself returned HTTP 403** to direct fetch this session, so exact glyph
  shapes/colours are **not verified** and nothing above claims to reproduce
  them pixel-for-pixel — Loft's glyph vocabulary (§2) is our own design,
  informed by but not copied from Plasticity's. Plasticity's Move/Rotate
  gizmos have a documented "Normal" orientation mode that aligns to a
  surface's normal at pickup (adjacent evidence that face-normal-awareness is
  a Plasticity idiom, though this is a manipulation gizmo, not a pre-select
  indicator, and the two should not be conflated):
  [doc.plasticity.xyz/common/move.en](https://doc.plasticity.xyz/common/move.en),
  [doc.plasticity.xyz/common/rotate](https://doc.plasticity.xyz/common/rotate).
- Onshape's **Select Other** (`` ` `` cycles the candidate list under the
  cursor, `Shift+` `` ` reverses; right-click on an entity offers the same
  command) — [cad.onshape.com/help/Content/Home/select_other.htm](https://cad.onshape.com/help/Content/Home/select_other.htm).
- SolidWorks' **Select Other** dialog (right-click → a list of every entity
  under the pointer in encounter order; Tab or the middle-mouse wheel, or
  repeated right-click, cycles it) —
  [blogs.solidworks.com/tech/2018/10/select-other-tool.html](https://blogs.solidworks.com/tech/2018/10/select-other-tool.html).
- `help.solidworks.com`'s own Select-Other reference page also returned HTTP
  403 to direct fetch this session; the description above is sourced from the
  GoEngineer/SolidWorks-blog secondary coverage cited, not the primary page,
  and is stated at that confidence level.

Every description above is written in Loft's own words from these sources;
no competitor text, markup, or screenshots are reproduced.
