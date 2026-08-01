# QA review — end-to-end, on the real artifact

Independent QA of the shipped product: the real stack, a real browser, real
modelling flows, desktop **and** touch. Geometric correctness is
`docs/GEOMETRY-QA.md`'s beat; this file records what a working engineer would
hit while USING the thing, including geometry that reaches a user through a
shipped flow (a wrong solid on screen is a QA defect no matter whose code made
it).

Severity: **P0** silently wrong artifact or data loss · **P1** a daily flow is
blocked or lies · **P2** a real flow is worse than it should be · **P3** polish.

---

## 2026-08-01 — dogfooding pass #3: the imported-STEP remix (interop)

The recurring **Model-a-REAL-part gate**, third pass (WB-64 and TB-1 were
#1/#2). Scenario: *a vendor ships you a STEP, you remix it into your own
bracket, then the vendor ships rev B.* Chosen because the day's two perf
commits both live on that path — `d8a4126` (PERF-4b, glTF per-face primitives
FUSED below 12 tris/face with the partition in a side table) and `dd8b2ba`
(PERF-5b, face provenance fingerprinted at production time instead of retaining
snapshot B-reps). An imported body is dense, so it exercises the UNFUSED side;
a milled plate is sparse and exercises the FUSED side. Both were driven.

**The part.** A NEMA 17 stepper front end-plate — the thing you actually
download from a motor supplier and build a mount around. 42.3 mm square with
4× 5 mm corner chamfers, 8 mm thick, Ø22×2 pilot boss, Ø5.2 shaft bore, 4× Ø3
on a 31 mm square. Authored OUTSIDE the app with build123d and committed as
`apps/web/e2e/fixtures/nema17-front-plate.step`, so the app sees an opaque
B-rep with no feature tree behind it. Closed form: 13 914.32 + 102.4π =
**14 236.019087727595 mm³**, 17 faces, 42 edges.

**Method.** Native container-free stack on isolated ports (gateway :8010,
documents :8011, geometry :8012, Vite :5199; fresh SQLite via
`metadata.create_all`). Playwright in a real browser plus direct API drives.
New probes: `apps/web/e2e/import-remix.spec.ts` (5 tests, desktop + a `hasTouch`
project). Regression slice re-run on the same stack: 46/46 green
(`feature-selection`, `import-step`, `drawing-reanchor`, `repick-face`,
`fillet-edge-pick`, `hole`, `sketch-on-face`, `export`, `preselection`).

**Verdict: PASS on numbers, FAIL on ergonomics.** Every geometric result was
exact — nothing silently wrong, nothing off by a digit, in seven independent
closed-form comparisons and an export round trip. But the flow the scenario
names is not actually completable in the UI: you cannot put a hole where you
want it on an imported face, and you cannot locate a sketch against imported
geometry at all. One measured consequence was a part 0.065 mm out of
concentricity with every number on screen correct.

### The numbers (app vs closed form, to the digit)

| step | app returned | closed form | Δ (mm³) |
|---|---|---|---|
| import as authored | 14 236.019087727622 | 13 914.32 + 102.4π | +2.7e-11 |
| + 5th Ø3 through hole | 14 179.470419963 | prev − 18π | +3.1e-11 |
| + Ø30/Ø10 × 4 register ring | 16 692.744542835 | prev + 800π | +1.5e-11 |
| + 1 mm chamfer, ring OD | 16 646.667850582 | prev − (44/3)π *(Pappus)* | −1.6e-10 |
| vendor **rev B** (8 → 10 thick) | 20 012.087683200 | 17 392.9 + 833.71333π | +2.9e-11 |
| vendor **rev C** (chamfer 5 → 6) | 16 470.667850582 | 13 738.32 + 869.73333π | 0 (12 s.f.) |
| STEP export → re-import | 16 646.667850582 | identical | −2.0e-10 |

The chamfer row is the interesting one: a 1 mm × 45° chamfer on a circular edge
of radius 15 removes, by Pappus, `0.5 · 2π · (15 − 1/3)` = **46.076692253 mm³**;
the app removed **46.076692253 mm³**. Topology held throughout: 17/42 on
import, 24 faces / 57 edges after the remix, and 24/57 again after the
export → re-import round trip.

**Rev B and rev C are the headline strength.** Patching the import feature's
STEP payload in place re-anchored ALL FIVE downstream remix features — a hole
on a signature-matched face, a datum on that face, a sketch on the datum, an
extrude, and a chamfer on a circular edge — with the volume exact to twelve
significant figures and identical topology. That is the hardest thing in this
scenario and it works.

**glTF face ordinals, both encodings.** For the remixed body, every one of the
18 glTF face ordinals resolves to the same B-rep face as `body.faces()[N]`:
per-face mesh area matches the exact B-rep area to ≤4.1e-4 relative, and the
area-weighted mesh centroid matches the GProp mass centroid to **0.0000 mm** on
all 18. On the fused side, an 11-face milled plate arrives in 6 primitives and
the viewport recovers all 11 (`data-total-faces` = 11). No ordinal slip in
either codec.

### QA3-1 — P1 · the Hole command cannot place a hole where you need one

`HolePointOverlay` offers exactly two placements: the face's **area centroid**
("Centre of face") and the face's **corner vertices**. `hole-position` is a
read-only readout; its "Change" button re-arms the same two-choice pick. There
is no numeric entry and no snap to the body's own circles or edges.

On this plate the seeded centroid is inside the Ø5.2 shaft bore, so the default
action fails, and the only alternatives are the eight octagon corners. **Adding
a 5th mounting hole to this vendor plate is therefore impossible through the
UI.** (The 5th hole in every number above was authored through the API.)

Repro — `import-remix.spec.ts` "the Hole command's seeded point on a bored
plate fails HONESTLY": import the fixture → Hole → pick the z = 0 face → drill.
Result `hole_off_body`, last-good body preserved. The ERROR is exemplary: typed,
per-feature, names the cause, keeps the good body. The message even says "Move
the point onto solid material on the face" — but there is no control that moves
the point. That failure is now pinned as a passing gate, so the day a numeric
position lands the spec goes red and the assertion gets rewritten.

Note the workaround exists and is what a user will end up doing: datum-on-face →
sketch a circle → extrude cut. Which makes the Hole command's own placement gap
the thing to close, not the capability.

### QA3-2 — P1 · a sketch on an imported face has NO reference to the import

Two facts compound:

1. A datum-on-face's plane ORIGIN is the face's **area centroid**
   (`geometry.kernel.faces._face_plane`), which for an asymmetric face is not
   the part origin and not any feature of the part.
2. `apps/web/src/sketch/snap.ts` snaps only to the sketch's OWN entities and the
   grid — never to a body edge, a hole centre, or projected geometry — and there
   is no way to dimension a sketch entity to imported geometry.

So on an imported face you draw in an unnamed frame whose origin is an
accident of the face's outline, with nothing to measure against.

**Measured consequence.** A Ø30/Ø10 register ring drawn at sketch (0, 0) on the
plate's back face — intended concentric with the vendor's shaft bore — came out
**0.065111070 mm** eccentric, because the 5th hole had already shifted that
face's area centroid by exactly

    15.5 · π·1.5² / (1739.29 − 15.76π − π·1.5²) = 0.065111070 mm

Prediction and measurement agree to nine decimals, so the mechanism is certain.
A motor register is a ±0.02 mm feature: that is a scrap part. Every number the
app reported about it was correct — the volume, the area, the extents, the
centroid — and nothing on screen said the ring was off the bore axis.

Not P0 only because the app faithfully built what was specified; the defect is
that there is no way to specify what was meant, and no way to see the error.

### QA3-3 — P2 · selecting a hole lights the whole plate

Selecting the 5th hole lights 3 faces of 18 — its Ø3 wall (75.4 mm²) plus the
plate's entire top (1 323.8 mm²) and back (1 682.7 mm²) faces, because the bore
re-cut both. On screen the "feature-localized" highlight reads as *this Ø3 hole
owns the vendor's entire top surface*. Fusion and SolidWorks light the bore wall
and its edges, not the host face.

This is the documented rule working as written (`provenance.py`: the earliest
feature after which the face exists in its FINAL form), but it defeats the
purpose FINDINGS #9 states — "highlight ONLY a selected feature's faces … instead
of clay-swapping the whole part" — on any part where a small cut meets a large
face, i.e. every real part. Worth a rule that distinguishes a face a feature
CREATED from one it merely re-bounded.

`feature-selection.spec.ts` cannot see this or any regression near it: it asserts
only `0 < lit < total` and `litA !== litB`, which 3-of-18 satisfies whatever the
3 are. `import-remix.spec.ts` asserts the exact counts (3 / 15 / 18 imported,
6 / 5 / 11 fused) against closed-form topology instead.

### QA3-4 — P3 · the published overlay contract is stale after PERF-4b

`OverlayFace.feature_id`'s description (py-kit → `packages/contracts/
gateway.openapi.json`, so it is the PUBLISHED interface) still tells clients
"each face's `index` is its `body.faces()` ordinal (== the GLB primitive ordinal,
one glTF primitive per B-rep face)". Since `d8a4126` that equality holds only on
the unfused encoding; below 12 triangles/face the ordinal must be recovered from
`extras.LOFT_face_triangles`. The web app does this correctly; a third-party
client written to the contract would mis-highlight on every sparse part.
Measured: 11 B-rep faces arriving in 6 primitives.

### QA3-5 — P3 · small features are tessellated ~200× finer than asked

Every cylindrical face gets **126 circumferential segments regardless of
radius** — the angular criterion is radius-independent and swamps
`DEFAULT_LINEAR_DEFLECTION = 0.1 mm` on anything smaller than ~20 mm. Measured
max chord error on the remixed plate:

| feature | r (mm) | tris | max chord error | vs the 0.1 mm budget |
|---|---|---|---|---|
| Ø3 mount hole | 1.5 | 252 | 0.000467 mm | 214× finer |
| Ø5.2 shaft bore | 2.6 | 252 | 0.000808 mm | 124× finer |
| Ø10 ring bore | 5.0 | 252 | 0.001554 mm | 64× finer |
| Ø22 pilot boss | 11.0 | 252 | 0.003419 mm | 29× finer |

The 24-face remixed plate meshes to **4 846 triangles**, ~1 500 of them in six
cylinders totalling under 6 cm². It also pushes such a part to 202 triangles per
face, well past PERF-4b's threshold of 12, so it declines the fusion that would
otherwise have removed its 24 primitives of JSON. A real vendor STEP with a
hundred tapped holes pays this on every hole.

### QA3-6 — P3 · `data-camera-pos` reads like a live camera hook and is not

It is stamped only on a programmatic view SETTLE (fit / view command), never on
a user orbit or pan. A touch-orbit probe that WORKS therefore looks broken —
that cost a false positive here before it was root-caused. `import-remix.spec.ts`
asserts on a canvas raster fingerprint instead. Either stamp it on control
change or rename it to say what it means.

### Friction log — what a working engineer would swear at

1. **You cannot drill where you want.** (QA3-1.) Two placements, both
   accidents of the face's outline.
2. **The sketch has no idea the imported part exists.** (QA3-2.) No projected
   geometry, no snap to a hole centre, no dimension to a model edge. On a part
   you authored you can at least reach back to the sketch that made it; on an
   imported one there is nothing to reach for.
3. **The sketch plane's origin is a moving target.** Add a feature that changes
   a face's outline and every future sketch on that face starts from a different
   point. Nothing names the frame or draws its origin against the part.
4. **One part = one imported body.** A second `import` is a typed 422
   (`import_with_prior_body`) and the toolbar disables with "only the first body
   can be imported". Documented v1 scope, but it means the commonest interop job
   — combine two purchased components into one machined part — has no home in a
   part document.
5. **Selecting a feature EDITS it.** A tree click opens the feature's editor and
   puts the app in command mode, so "show me what this feature owns" and "change
   this feature" are the same gesture; you must Escape before the next command.
6. **The drawing arrives blank of dimensions and mostly blank of sheet.** Four
   views of a 42 mm part on A3 at 1:1 occupy about an eighth of the page, and
   every dimension is a manual edge click. No hole table, no centre marks, no
   bolt-circle callout — the three things a mounting-plate drawing is FOR.
7. **`?format=` is a query parameter** on both export routes while every other
   write takes a JSON body; the mistake costs a 422 whose `loc` is the only clue.
8. **Part names are unique per owner**, so a second "Bracket" is a 409
   (`part_name_taken`) even in a different folder.

### What is genuinely good

* Vendor-revision swap re-anchoring (rev B and rev C, five downstream features,
  exact to 12 s.f.). Nothing in the scenario is harder.
* Every error on the unhappy path was typed, per-feature, named its cause, and
  preserved the last-good body. Not one 500, not one silent wrong solid.
* STEP + STL + a four-view A3 drawing + PDF/DXF/SVG all come out the other end
  for a part whose base body was imported, with the document's name on the file.
* Touch: one-finger orbit works on the imported body and the face census is
  identical to desktop.

---

## 2026-07-30 — wave review of the day's ~20 commits

**Method.** Native container-free stack on isolated ports (gateway :8070,
documents :8071, geometry :8072, Vite :5193; fresh SQLite files). Playwright
against that stack in two projects, `desktop` (1600x1000) and `touch`
(hasTouch, same viewport). New probes live in
`apps/web/e2e/qa-wave-0730.spec.ts`; the four defects below are pinned there as
`test.fail()` gates, so each one flips the suite RED the day it is fixed — that
is the signal to delete the marker.

**Verdict: FAIL.** Four defects, one of them a silent wrong solid. Six probes
pass on both projects, and the regression sweep is clean (63 shipped specs).

### QA-1 — P0 · a body-scope mirror WELDS a void that straddles the plane

The reflection fills the void instead of reflecting it, every feature reports
`ok`, and the body OCCT itself calls invalid is tessellated, measured and
exported.

Repro (API or UI, same result — `qa-wave-0730.spec.ts` "G"):

1. Sketch a 40x40 rectangle on XY; extrude 10 mm, `add`.
2. Sketch on XZ: a construction line `(8,-5)-(8,20)` plus a rectangle
   `x 12..16, y 2..10`.
3. Revolve that profile 360° about the construction line, `operation: cut` —
   an annular groove centred on the XZ plane. Body = **15,396.8142 mm³**
   (= 16,000 − π·192, exact).
4. Mirror, `plane: XZ`, `scope: {kind: body}`.

| | value |
|---|---|
| observed | **31,865.9587 mm³**, 12 faces, `Shape.is_valid` **false** |
| expected | **30,793.6284 mm³** (= 2 × 15,396.8142 = 32,000 − π·384) |
| error | **+1,072.330 mm³ — 3.48 % too much material**, silently |

Two controls prove it is the mirror and not the model:

- the same final solid built DIRECTLY (an 80-long block with the full ring cut)
  gives **30,793.6284** — the analytic value, 11 faces;
- the same chain with the ring moved CLEAR of the mirror plane (axis at x = 20,
  mirror about YZ) gives a ratio of **2.0000000000000004** — correct.

Root cause, traced in-process:

```
PATH: mirror_cut   ntools=1  tool volume 1206.3716
  reaches body?  False          -> MirrorUnreachableError -> mirror_union
  FUSED volume   30793.628421021516
  CLEANED volume 31865.95871344683      <- clean() inflates
```

Because the cut is already in the body, `removal_reaches_body` is False and
`mirror_cut` falls back to `mirror_union`, whose `fuse` + `clean()` weld the two
half-voids shut. (In a pure build123d repro of the same revolved ring the `fuse`
itself already returns 31,865.9587 with `is_valid` false, so the inflation moves
between `fuse` and `clean` with the shape's provenance — either way the result
is invalid and **nothing in the pipeline checks it**.)

**Regression from `6c9c432`** ("a body-scope mirror after a revolve/sweep/loft
cut filled the void it should have reflected"). That commit closed the
tool-recording half of CM-5. The straddling-void half is still open, and it
fails the same way, through a different door.

### QA-2 — P1 · changing a plate's thickness destroys every hole on its face

The commonest revision in CAD. It TRANSLATES the top face, and the picked-face
reference is resolved by absolute centroid, so the hole drilled in that face is
lost and everything after it is stranded.

Repro (`qa-wave-0730.spec.ts` "A", second test):

1. Build: 60x40 sketch → extrude 10 `add` → Ø6 through hole on the top face
   (signature `area 2400, centroid (30,20,10), normal +Z`) → linear pattern
   x3 @ 60 → mirror about XZ → fillet R1 on all edges. Solves,
   **142,020.953 mm³**, exports a clean STEP.
2. Select Extrude1, retype the distance 10 → **16**, Enter.

| | observed | expected |
|---|---|---|
| Hole1 | `subshape_unresolved` — "No planar face of the current body matches the stored face signature" | ok |
| Pattern1 / Mirror1 / Fillet1 | `skipped` | ok |
| body | **38,400 mm³** — a featureless 60x40x16 brick | ≈ 227,000 mm³ |
| STATUS / EXPORT | `Partial` / blocked | `Up to date` / `Ready` |

The face is the SAME face by every invariant except position: same area (2400),
same normal, same plane orientation, translated z 10 → 16. `7fde5d2` states a
picked face "has had a two-tier matcher since FINDINGS #3 … a resilient re-match
on the strongest invariant alone"; that tier does not survive a translation,
which is exactly what a depth edit does to every face on the far side. The
product audit's "revision wall" is therefore still standing for holes.

### QA-3 — P1 · a diameter dimension the revision never touched is destroyed

Repro (`qa-wave-0730.spec.ts` "B", second test):

1. 40x25 sketch with a Ø10 circle → extrude 10. Create a drawing, select the
   part, auto-lay-out the four standard views.
2. Pick the hole's circle in the TOP view → Diameter. Sheet stamps `Ø10.000`.
3. Back to the part; retype Extrude1's distance 10 → 16. Re-project the drawing.

| | observed | expected |
|---|---|---|
| Dimensions panel row | `diameter · unresolved` | `diameter · Ø10.000` |
| the sheet | annotation **gone** | `Ø10.000` |

The hole's diameter did not change — only the plate's depth did. The circle's
tier-2 re-anchor ("centre plus angular station") keys on the 3-D centre, which a
depth change translates in z.

Worth stating plainly, because it is the good half of the same test: the LINEAR
dimension on the thickness edge **did** follow the edit, `10.000 → 16.000`. The
N1 line fix works. Incomplete rather than wrong: **`7fde5d2`**, one curve kind
over.

### QA-4 — P1 · a lost dimension leaves NO trace on the print

Same repro as QA-3, then export.

| surface | observed | expected |
|---|---|---|
| exported `.svg` | no `REFERENCE LOST`, no marker, no annotation | `DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE` |
| on-screen sheet | nothing | the same caption |
| Dimensions panel | `unresolved` | (correct — but it is a side panel, not the drawing) |

`7fde5d2`'s own account: "A reference that genuinely cannot be re-anchored now
prints WORDS beside the view … in SVG/PDF/DXF", implemented at
`drawings/compose.py::_DIM_ERROR_PHRASE` / `dimension_error_caption`. On this
path nothing is stamped on either surface, so a shop receives a print that has
silently lost a dimension and looks complete. (Whether the web never forwards
the unresolved dimension to the composer, or the composer declines to stamp it,
is for the builder — QA measured only that neither surface says a word.)

### Verified good — the probes that passed, desktop AND touch

- **Rollback + export together.** Before the click the strip carries
  `data-export-state="partial"` and a sentence saying the file will be marked
  partial; the download's filename contains `-partial` and the content is real
  ISO-10303-21. `TO TIP` returns the strip to `ready` and the next filename is
  clean. (`b4e075f`, `1a27804`.)
- **A failed feature reads the same on five surfaces.** SOLVE `Failed`, STATUS
  `Partial` + "Hole1 failed · built to Extrude1", the tree's error row carries
  `hole_off_body` with the friendly sentence, the viewport notice repeats it,
  the export gate is `feature-error` and a FORCED click on the gated cell
  produces no file — and the **parts register next door** agrees
  (`part-health data-health="failed"`, "Broken"). The one cell `partBuild.ts`
  does not reach was the one worth checking, and it holds.
- **Undo/redo across the timeline.** Chips 3 → 2 → 3 across undo/redo; the stop
  reports `aria-valuetext "After Extrude1 — 2 of 3 built"`; after an undo that
  removes the tip feature the stop stays inside `aria-valuemax`, so it never
  points past the end of the tree.
- **The shell refusal reaches the user.** t = 2 on the SH-1 4 mm rib gives
  `shell_thickness_too_large` in the tree with the whole actionable sentence
  ("…an internal wall of this body is exactly 4.0 mm thick … Change the
  thickness so it is not exactly half that wall — a little thinner leaves a thin
  cavity…"), and the last-good body is untouched at **14,400 mm³** with STATUS
  "built to CornerFillets". (`5af2f6b`.)
- **Materials report absence, not zero.** With no material assigned,
  `properties.mass_g` and `properties.center_of_mass` are `null`, and each
  `bodies[]` entry carries `material: null, mass_g: null`. Never `0`.
  (`78ad8a4`.)
- **Services fail closed on default datastore credentials.** With `LOFT_ENV`
  unset, `POSTGRES_URL=postgresql://loft:loft-dev-only@db:5432/loft` raises
  naming the variable, the defect and both remedies; an empty password likewise;
  `LOFT_ENV=dev` warns and boots. (`c695b11`.)
- **Regression sweep clean.** 39 shipped specs on desktop (drawings,
  drawing-sheets, drawing-place-view, shell, mirror, undo-redo, full-flow,
  export, p2-register-health, preselection, repick-face) and 24 on touch
  (viewport-gestures, timeline, body-status, sketcher, parts-home) — all pass.

### Observations (not defects)

- `shell_thickness_too_large` has no entry in
  `apps/web/src/features/featureErrors.ts`, so the raw server message is what a
  modeler reads. It happens to be excellent; noting it only because the friendly
  table is where that guarantee is supposed to live.
- Nothing in `apps/web` imports `src/api/materials.ts`, and the body inspector
  has no mass row — mass is API-only today, so "MASS PROPERTIES can report mass"
  is true of the service and not yet of the panel named in the sentence.
- The credential guard is an allowlist (`KNOWN_DEV_CREDENTIALS`), so a password
  equal to the project's own name (`loft:loft`) passes. Correct as scoped —
  worth knowing before someone reads it as an entropy check.
