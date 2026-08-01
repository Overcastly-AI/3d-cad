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
