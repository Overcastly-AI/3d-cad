# Twisted extrude: design note

Status: **IMPLEMENTED** (kernel 2026-09-24; high-twist cost bound 2026-09-25,
§6.1). The web UI landed in `737137e` (the Twist field and its axis),
`865a0d4` (a client-side twisting ghost and the `twistGaugeTrack` arc) and
`aa2e108` (the `twist_failed` copy). Scope: the extrude
feature's `twist_angle_deg` / `twist_center` parameters, the OCCT mechanism
behind them, and how they compose with the other extrude options. Closes the
kernel side of helical-gear gap #1 (`docs/qa/helical-gear-2026-09-24.md`, G1).

Related: RESEARCH §1 (OCCT via OCP + build123d; no new dependency) and §9
(goldens, determinism, STEP round trip); `feature-tree.md` §1.4 (an additive
param does not bump `param_version`).

## 1. Problem

Loft had no helical construction. The founder's helical-gear test could only
approximate the tooth gap with a ruled loft between hand-drawn rotated sections.
A ruled loft joins corresponding section points with straight chords, which
sag inside the true helicoid. With 2 sections the tooth was 0.11 mm thin at
mid-face (3.141 mm against 3.252 mm), the root was 0.13 mm deep, and the volume
was 0.61 % low. More sections shrink the error by about N², but they cost one
hand-drawn sketch each and multiply the face count (150 faces at 2 sections,
1230 at 11). Every incumbent has a helical route, and most do it with a twist
along a straight path.

## 2. Mechanism

A twisted extrusion is a **screw motion** of a planar profile. The section at
height `z` along the extrusion direction is the profile rotated by
`twist * z / distance` about an axis parallel to that direction. Every profile
point traces an exact helix. No B-spline represents a screw-swept curve exactly
(a helix is transcendental), so every mechanism approximates. The choice is
about where the approximation lives and how small it is.

| Option | Verdict |
| --- | --- |
| Ruled loft through N rotated sections (the only route before this) | Rejected. Chord sag of order N⁻², and faces grow with N. |
| Smooth (B-spline) loft through N rotated sections | Rejected. It interpolates between sections rather than following the helix. The error falls with N but never reaches the fit tolerance, and every section is still a sketch. |
| `BRepOffsetAPI_MakePipeShell` + `SetLaw` | Not applicable. OCCT pipe-shell laws SCALE the section; they do not rotate it. |
| Sweep along a HELIX path (Frenet or corrected-Frenet trihedron) | Rejected. The section plane follows the helix tangent, so it tilts by the helix angle. A gear's tooth is defined in the transverse (axial-normal) plane, and the tilt depends on each point's radius. That is a different solid. |
| **`BRepOffsetAPI_MakePipeShell` along a straight spine, auxiliary-spine mode with a helix about the same line (chosen)** | Exact screw motion; approximation only in fitting each swept face, at a tolerance we choose. |

How the chosen mode works: `SetMode(AuxiliarySpine, CurvilinearEquivalence =
False)`. At each spine point P, the section's normal is PQ, where Q is the point
at which the plane through P normal to the spine meets the auxiliary helix. For
a straight spine that plane is a constant-height slice, so Q turns at exactly
the twist rate, and the section is carried by the screw motion with no drift.
The spine is the twist axis itself: the line through `twist_center` along the
extrusion direction, `distance` long. `MakeSolid` caps both ends with planar
faces.

Why not call build123d's `Solid.extrude_linear_with_rotation`? It uses the same
mechanism, but it:

- keeps OCCT's default 1e-4 mm fit, which leaves 2.7e-4 mm³ of volume error
  on the golden, a thousand times our fit (§3);
- returns whatever the sweep produced with no check. §4 shows the sweep can
  return an inverted, `BRepCheck`-valid solid;
- raises raw OCCT errors rather than a feature error.

`geometry.kernel.twist` is about 60 lines of OCP around the same idea, with the
tolerance, the guard and the error taxonomy owned here.

**Profiles with holes.** A pipe shell sweeps one wire. Each boundary of the
profile face is swept separately, and the swept holes are cut from the swept
outer boundary. This is the same as build123d's approach.

## 3. Accuracy (measured 2026-09-24, build123d 0.11.1 / OCCT 7.9)

Fit tolerance `TWIST_SWEEP_TOLERANCE_MM = 1e-7` (mm), chosen by sweep on the
golden `extrude-twist-square20-hole-r3-h30-30deg`. That golden is a 20 mm square
with an off-axis r3 hole, extruded 30 mm with a 30° twist. Every value in it is
analytic, including a closed form for the helicoidal flank area.

| Fit tolerance | Volume − analytic (mm³) | Area − analytic (mm²) | Wall (s) |
| --- | --- | --- | --- |
| 1e-4 (OCCT default) | −4.26e-3 | not measured | not measured |
| 1e-5 | +2.70e-4 | +3.6e-5 | 0.185 |
| 1e-6 | +2.70e-4 | +3.6e-5 | 0.18 |
| **1e-7** | **+2.74e-7** | **+4.3e-8** | 0.196 |
| 1e-8 | +2.74e-7 (identical body) | +4.3e-8 | 0.21 |

The fit saturates at 1e-7. The centroid matches its analytic value (which
carries the handedness in its y component) to 5.7e-12 mm.

Deviation of the gear tooth-gap's swept flanks from the exact screw motion,
sampled 11×11 per face and measured by un-rotating each point back to z = 0
and taking its distance to the profile: 9.5e-7 mm at a 1e-6 fit, **6.7e-9 mm
at 1e-7**. The auxiliary helix's radius does not matter (1, 10 and 30 mm give
the same surface to 1e-15 mm), because it sets only a direction.

**The helical gear through `loft-script`** (`docs/qa/helical-gear.py --twisted`:
one tooth-gap sketch with 12-fit-point involute splines, one twisted extrude
cut, a feature-scope circular pattern ×24, then the bore and keyway). Checked
against the report's analytic true-helical values:

| Check | Truth | Ruled loft, 2 sections | **Twisted extrude** |
| --- | --- | --- | --- |
| Volume (mm³) | 36 470.374 | 36 247.566 (−0.611 %) | **36 470.392 (+0.017 mm³, +4.7e-7)** |
| Twist z = 0.05…19.95 (deg) | 12.2959 | 12.2964 | **12.2959** |
| Worst angular deviation from the helix along the face | 0 | 0.0095° | **< 0.000005° (prints +0.00000)** |
| Tooth thickness on the pitch circle at mid-face (mm) | 3.25242 | 3.1408 | **3.25242 (error < 5e-6 mm)** |
| Deepest root radius (mm) | 22.3466 | 22.2168 | **22.3466** |
| Faces | — | 150 | 150 |
| STEP round trip (adaptive volume, topology) | identical | — | **Δ 7e-10 mm³, 150/444/1 both sides** |

The remaining +0.017 mm³ (4.7e-7 relative) comes from the 12-point spline
standing in for the involute, which the analytic value integrates exactly. One
spline gap cut from the blank removes 298.1571 mm³ against the analytic
298.1578, and 24 × 0.0007 = 0.017. It is not the twist: the twisted gap tool
alone satisfies the Cavalieri identity (§4) to 1.2e-10 relative. The report's
probe printed its STEP re-read volume with build123d's fixed-order `.volume`,
which is 0.63 mm³ (1.7e-5) low on these flanks. That is the integrator, not a
round-trip loss, and the probe now reads the volume adaptively.

## 4. Limits and refusals

- **Request validation:** `|twist_angle_deg| <= 3600` (ten turns),
  `allow_inf_nan=False`, and a finite `twist_center`, else 422. This is a sanity
  bound, not the geometric limit.
- **A vanishing twist is NO twist, not a refusal.** `|twist| < 1e-9` deg
  (`MIN_TWIST_ANGLE_DEG`) is normalised to absent by the wire model rather
  than rejected with a 422. It is a legal number whose geometry cannot be told
  from zero: 1e-9 deg is 1.75e-11 rad, which moves a point 5.7 m from the axis
  by 1e-7 mm, the kernel's linear tolerance. Refusing it would make a user or
  script that types `1e-12` fix something that is not wrong. Normalising is
  also what closed a hang (review of `d823af9`). The aux helix's pitch is
  `360 / |twist| * distance`. A sub-normal twist (5e-324 deg) made it
  infinite, and `Edge.make_helix` never returned. There is no evaluate
  timeout, and the stored row re-hung every rebuild of the part.
- **The kernel guards the pitch for any caller.** `twisted_extrude_face`
  refuses a pitch that is not finite or exceeds `MAX_AUX_HELIX_PITCH_MM = 1e150`
  as `twist_failed`. It checks this before building the helix, and the helix
  is built inside the error-mapping `try`. Measured: a twist of 1e-300 or
  1e-160 deg escaped as a bare `ZeroDivisionError` (build123d normalises
  `(2 pi, pitch)`, whose length overflows past about 1.3e154), and 1e-9 deg
  over 1e150 mm raised a raw `StdFail_NotDone`. From the API, with the 1e-9
  floor, the bound is reached only by a distance beyond about 1e138 mm.
  `test_a_vanishing_twist_cannot_hang_a_worker` runs both guards in a child
  process under a 120 s timeout. With the kernel guard mutated out it fails
  on `TimeoutExpired`. With the normalisation mutated out, the 5e-324
  response differs from the untwisted one.
- **Inside-out sweeps are re-oriented, not refused (geometry QA F3).** At
  some twists OCCT returns the swept solid **inside-out**: every face
  reversed, volume -A·d, and `BRepCheck` calls it VALID. Examples are a 20 mm
  square over 30 mm at -3000°, +3100° and +3600°, and a 40 mm square at
  -3250°. The geometry is exact (the turned vertices sit on the boundary to
  1.2e-8 mm); only the orientation is wrong. As first shipped, the guard below
  refused these as "too tight", which told the user something false and left
  holes in the accepted range. `twist.orient_closed_solid`
  (`BRepLib::OrientClosedSolid`) now runs on every swept solid, before the
  guard. Measured afterwards: squares of half-width 5, 10, 20 and 50 mm over
  30, 5 and 1 mm, at -3600, -3000, 1800, 3100 and 3600°, ALL sweep, with a
  Cavalieri residual of at most 9e-8 relative. The sweep is scale-invariant,
  and no tested input reaches the guard any more. What does limit a high
  twist is its cost (§6.1).
  Their STEP was always right, face for face, but OCCT's reader turned it
  inside out again on re-import (its `ShapeFix_Solid` classifies a point at
  infinity by ray cast, which returns IN on these helicoids). Both STEP
  readers now turn a solid of negative volume right side out (review B1,
  `9ca5401`).
- **The Cavalieri guard stays, as the net under the sweep.** Every slice of a
  twisted extrusion is a rigid rotation of the profile, so the swept tool's
  volume must equal profile area × distance exactly, for any twist. The kernel
  measures both adaptively (the inspector's own `VOLUME_EPS`) and refuses a
  departure above `TWIST_VOLUME_REL_TOL = 1e-6` relative as the feature error
  **`twist_failed`** ("…did not sweep cleanly (its volume is not profile area x
  distance)…"). Without it, an inverted tool reached the user as `ok`: seen at
  `d823af9`, and again now with the guard mutated out of
  `test_a_sweep_that_comes_back_wrong_is_twist_failed`. That test turns an
  oriented quarter-turn tool inside out on purpose, so it does not depend on
  which twists OCCT inverts (review N2). Sweep failures,
  and holed profiles that do not leave one solid, are also `twist_failed`.

## 5. Contract

`ExtrudeParamsV1` gains two additive-optional fields. Both are null by default
and omitted from a dump while null; the generated TS client leaves them
optional. There is no `param_version` bump:

- `twist_angle_deg: float | None`: the total twist over `distance_mm`. `None`,
  `0`, `-0` and any `|twist| < 1e-9` mean no twist, and are all normalised to
  absent (§4).
- `twist_center: Point2D | None`: where the axis pierces the sketch plane, in the
  profile sketch's (x, y) mm. `None` means the sketch origin. With no twist it
  is dropped (normalised to absent), so a leftover centre cannot make an
  untwisted row differ from one that never had a twist.

**Zero twist is byte-identical.** `_extrude_tool` in `features/evaluate.py` is
the single branch point for ADD and CUT. No twist never leaves `extrude_face`,
so the evaluate response of every existing extrude, mesh id included, is
unchanged. `test_no_twist_is_byte_identical_to_the_plain_extrude` covers the
field absent, `null`, `0` and `-0`, the latter three with a non-default
`twist_center`. Every existing golden passes unchanged. The serialized form
does not change either. Both fields carry `exclude_if` (omitted while null), so
an untwisted extrude's stored row, API response and rebuild-cache key are byte
for byte what they were. The documents suite's verbatim row round trip is the
witness: it went red when the fields dumped as `null`, and it is green now with
no edit.

**Sign convention: right-handed about the direction of TRAVEL.** A positive
twist is a right-hand helix whichever way `direction` points, because
handedness belongs to the part, not to the direction toggle. On an XY sketch
with `direction: normal`, positive is counter-clockwise seen from +Z. With
`reverse` it is clockwise seen from +Z, which is still right-handed about −Z.
Test: `test_twist_is_right_handed_about_the_direction_of_travel`, over all four
sign and direction combinations. The golden's off-axis hole puts the handedness
into `centroid.y`, so a mirrored helix fails the golden by 0.156 mm.

**Composition with the other extrude options:**

| Option | With a twist |
| --- | --- |
| `direction: normal / reverse` | Supported (the sign convention above). |
| `operation: add` | Supported, including profiles with holes (golden). |
| `operation: cut` | Supported: the helical gear's tooth gap. Multi-region CUT sketches twist every region about the same axis, and a region's holes leave helical material standing (`test_twisted_cut_of_disjoint_regions_and_a_holed_region`). |
| `merge: false` | Supported: the twisted prism starts a new body. |
| Symmetric / two-sided | **Nothing to combine: extrude has no symmetric or two-sided option today.** When one lands it must choose between one twist spanning the whole distance, with the sketch plane at mid-twist (recommended: one continuous helix, so a symmetric helical gear stays a single helix), or a twist per side. It must not fall back silently to either. |
| Mirror / pattern (features scope) | Supported with no change. The recorded tool IS the twisted solid, so a mirror or pattern replicates it exactly. The gear's ×24 pattern is this path. A mirror reverses the helix's handedness, as a mirror should. |
| Draft / taper | Not offered; extrude has no taper. A combined twist and taper would need a scaling law on the same pipe shell (`SetLaw`), a later item if asked for. |

**Topology.** A twist changes the surfaces, never the topology. It gives the
same face, edge and shell counts as the untwisted prism, with the lateral faces
B-spline instead of planar. Face signatures of the caps are unaffected. A
downstream fillet or chamfer that named a lateral face of a formerly-straight
extrude will see a non-planar face after a twist is added, and resolves or
reports it as it would any changed face.

**Edge geometry: the caps are analytic again (review of `d823af9`).** A pipe
shell rebuilds even its start and end sections as B-spline fits. As first
shipped, a twisted body therefore had no LINE or CIRCLE edge at all, and
everything that keys on edge type missed its rims:

- the assembly mate axis (`assembly/resolve.py`, circle only), so a bore in a
  twisted body could not be a mate axis;
- the measure direction (`kernel/measure.py`, line only);
- drawings (`drawings/project.py`, `anchor.py`);
- the durable edge re-match (`kernel/edges.py`, line/circle only).

`twist._restore_cap_edges` now gives every edge lying in the start or end
plane back its exact analytic curve. The candidate is OCCT's
`GeomConvert_CurveToAnaCurve`, accepted only if the edge stays within 1e-6 mm
of it at 16 points. The edge's pcurves are then RE-PROJECTED onto its faces
(`ShapeFix_Edge::FixAddPCurve`), which is what a STEP reader does.
Re-parametrising the old pcurves with `BRepLib::SameParameter` was tried
first. It left the in-memory golden 1.0e-7 mm³ from its own STEP re-import, and
the round-trip gate caught it. Re-projection holds the round trip to 4e-9,
the same as the unconverted body. The work is done on a copy, which is
discarded if `BRepCheck` or the volume disagrees.

Effect on the golden: 8 cap LINES, 2 cap CIRCLES, and 5 B-spline edges (the 4
helical corners and the tube seam). The topology did not move, and the mass
properties moved by less than 1e-8 (the area by 6e-9). The mesh counts moved
(3751/6874 → 3557/6554), because a line is
discretised with fewer nodes than its fit.
`test_cap_edges_are_lines_and_circles_and_a_rim_is_a_mate_axis` asserts that
census and resolves the far rim as a mate axis at (4 cos 30°, 4 sin 30°, 30),
direction ±Z. With the restoration mutated out, the census reads 15 B-splines.

What stays B-spline, as a documented limit:

- The helical lateral EDGES and FACES. They genuinely are not lines, planes or
  cylinders, with one exception: a circle centred exactly on the twist axis
  sweeps a true cylinder, which is still returned as a B-spline surface, so a
  face-based cylinder query would miss it. Every consumer listed above is
  edge-based, so the rim circles cover them.
- Edges a later BOOLEAN computes where a twisted body meets other material
  part-way along its length. Example: a twisted boss entering a plate at
  z = 5, where helicoid ∩ plane is computed by OCCT as a B-spline even when it
  is geometrically a line or circle. The twisted body's own end caps, where the
  rims of a hole drawn in the profile and a boss's top edges live, are analytic.

## 6. Cost

**Caveat:** every timing here was taken on a shared 4-core container at load
average 8-10, with other agents' suites running. Between runs of the same build
the numbers moved by about 20 %. Treat them as ratios, not budgets.

The helical gear through `loft-script`, on the native stack, measured in the
same session as the loft route. The report's own numbers were 6.2 s to build
and 5.3-9.2 s to rebuild after a β edit.

| Step | Ruled loft, 2 sections (1 run) | Twisted extrude (2 runs) |
| --- | --- | --- |
| Gap geometry + cut + evaluate | 0.58 s (2 sketches + loft) | 0.38-0.43 s (1 sketch + twisted cut) |
| Circular pattern ×24 + evaluate | 4.01 s | 5.63-6.00 s |
| Bore + keyway cut + evaluate | 2.44 s | 4.68-6.44 s |
| **Total build** | **7.13 s** | **10.9-13.1 s** |
| β 15° → 20° edit, rebuild | 6.71 s | 5.82-8.76 s |

A cold whole-tree evaluate in-process (best of 2, cache reset each time) gives
the same ratio: the pattern prefix takes 4.8 s for the loft and 6.8-10.1 s for
the twist, and the single twisted gap cut takes 0.44 s against the loft's
0.20 s.

The extra cost is the 23-tool variadic boolean against helicoidal B-spline
flanks, which cost more to intersect than the loft's ruled (degree-1) ones. It
does not depend on the fit tolerance: in-process the pattern cut measured
4.5-6.3 s at fits from 1e-4 to 1e-7, within noise, with flanks of 2-14 × 5-6
poles either way. Accuracy per second still favours the twist heavily. A
5-section loft builds in 13.9 s and an 11-section loft in 33.5 s (report), and
both are less accurate than the twisted build.

### 6.1 High twists: bounded meshing and a cost guard (geometry QA F4, DONE)

QA found that twists inside the accepted ±3600° tied up a worker for minutes.
A 20 mm square over 30 mm took 59 s at 1800° and 415 s at -3600°, and the
gateway gives up at 90 s while the worker keeps meshing. Measured then, at the
production 0.1 mm linear / 0.1 rad angular deflection:

| Profile, distance, twist         | Sweep  | Mesh    | Triangles |
| -------------------------------- | ------ | ------- | --------- |
| square 20, 30 mm, 360°           | 0.04 s | 0.98 s  | 121 732   |
| square 20, 30 mm, 720°           | 0.09 s | 4.22 s  | 373 838   |
| square 20, 30 mm, 1080°          | 0.11 s | 20.35 s | 673 812   |
| square 20, 10 mm, 720°           | 0.07 s | 14.79 s | 597 810   |
| square 20, 100 mm, 720°          | 0.06 s | 0.82 s  | 107 048   |
| square 20, 300 mm, 3600°         | 0.43 s | 28.89 s | 956 480   |
| square 2 at r = 10, 20 mm, 3600° | —      | 22.23 s | 696 792   |
| slot 0.2 × 20 at r 10..30, 3600° | —      | 1.47 s  | 69 924    |

What those measurements showed (the first draft of this section, kept because
they decided the fix): the angular criterion drives the cost, not the fit or
the linear deflection. On the 720° square BRepMesh gave 367 774 triangles in
10.1 s at 0.1 mm / 0.1 rad, 12 900 in 0.16 s at 0.1 mm / 0.5 rad, and still
320 000 at 1.0 mm / 0.1 rad; QA saw fits of 1e-4 and 1e-7 mesh equally slowly.
And the cost is no function of the twist alone: it depends on each edge's
offset from the axis (a thin radial slot at 10 turns 1.5 s, a 2 mm square at
r = 10 over the same 10 turns 22 s) and did not collapse to the lead angle
(1 turn over 10 mm 2.9 s, 3 turns over 30 mm 20 s). So a flat bound small
enough to guarantee "a few seconds" would have refused useful geometry, and
the fix bounds the mesh instead; the guard below only catches what is still
over budget once it is bounded.

**What shipped.** Three mechanisms, all confined to trees that contain a
twisted extrude (`evaluate.tree_has_twist`). Every other tree tessellates and
exports through exactly the calls it always did.

1. **Bounded meshing of the helicoidal flanks** (`twist.mesh_helicoidal_faces`,
   called by `tessellate_glb(..., twisted=True)` and by STL/GLB export). Each
   B-spline face whose estimated cell count `(Tu/a) x (Tv/a)` is at least
   `HELICOID_MESH_ESTIMATE_MIN = 500` is meshed alone, before the ordinary
   mesher, with the production parameters (same linear and angular deflection,
   relative, parallel) except `ControlSurfaceDeflection = False`. Tu and Tv are
   the normal's total turning along each parameter, sampled on a 25 × 25 grid,
   and `a` is the angular deflection. The ordinary mesher then keeps those
   triangulations and meshes every other face as before.
   The estimate costs about 2 ms per B-spline face (planes and analytic
   faces are skipped), so an extrapolated 0.3 s per tessellation of a 24-tooth helical
   gear's 144 flanks.
   - **Why that switch and not `AngleInterior`.** The brief proposed relaxing
     the interior angular deflection. Measured, it is not enough: at 1.0 rad
     one stress case still took 128 s, and at 1.5 rad the chord error reached
     0.22 mm. The cost is BRepMesh's
     surface-deflection refinement loop, which on a surface whose normal turns
     along BOTH parameters keeps inserting nodes. Switching the loop off keeps
     the initial grid, which the linear and angular deflection still set.
   - **Result**, square 20 over 30 mm: 360° 1 220 triangles (was 121 732),
     720° 2 436 (was 373 838), 1800° 6 180, 3600° 12 356. Chord error
     (triangle centroids and edge midpoints projected on the true surface):
     0.209 mm on the bounded 360° and 720° flanks, against 0.227 mm on the
     production mesh of the 30° twisted square. That is what the production
     mesher already ships for a twisted flank: with the relative deflection
     the 0.1 mm is not an absolute chord bound on these faces.
     `test_bounded_mesh_is_as_close_as_the_production_twist_mesh` pins it.
   - **The goldens are unchanged.** The 30° golden's flanks estimate 18 cells,
     far below 500, so no face of it is pre-meshed and its counts stay
     3557 / 6554. With the threshold mutated to 0 the golden's mesh-count test
     fails.
2. **3MF of a dense twist is refused** (`export_mesh_too_dense`, a 422).
   lib3mf's writer (build123d `Mesher`) meshes a deep COPY of the body, so the
   bounded pre-mesh never reaches it and the copy is meshed at full cost
   (14 s at 720°). A twisted body whose pre-meshed faces sum to more than
   `THREE_MF_TWIST_ESTIMATE_BUDGET = 8000` cells is refused; STL, GLB and STEP
   of the same body work. A one-turn square (5 656 cells) still exports.
3. **A pre-sweep cost guard** (`twist.twist_cost_estimate_s`, checked first
   in `twisted_extrude_face`). Some accepted geometry still cost more than the
   budget with bounded meshing. The time then goes to the sweep, the Cavalieri
   and mass-property volume integrals and the production mesh of narrow
   ribbons. A 48-point star at 3600° took 9.4 s; a circle about the axis at
   3600° 6.0 s. A twist whose estimate exceeds `TWIST_COST_LIMIT_S = 4.5` s is
   refused as `twist_failed` ("…is too many turns for this profile to build
   in reasonable time (estimated N s, limit 4.5 s); reduce the twist angle or
   give the profile fewer edges.") before anything is swept. The refusal
   returns in 0.01-0.2 s.

**Assemblies (TWIST-ASSEMBLY-MESH-COST-1).** An assembly evaluates each part
through the part path, so the cost guard and the bounded viewport mesh
already applied there. The assembly MESH exports did not: they place each
instance with a deep copy that carries no triangulation, and then meshed a
twisted part at full cost. A 20 mm square twisted 720° over 30 mm, beside
one plate, took 10.4 s (STL, GLB) and 15.0 s (3MF); at 1800° the STL took
99 s. Now each `AssemblyComponent` carries `twisted` (its part's features
have a twisted extrude, `evaluate.features_have_twist`). A twisted instance
is pre-meshed with the bounded mesher AFTER placement for STL and GLB, and a
3MF too dense for lib3mf's full-cost re-mesh is refused
(`export_mesh_too_dense`, 422), as for one part. Measured: 720° 0.45 s STL
and GLB. 1800° 1.66 s STL and 1.83 s GLB, against 1.70 s for the same part's
own tree export. 3600° 6.0 s, against 5.8 s for the part alone. STEP is
unchanged at 0.3 s. An assembly without a twisted part exports
byte-for-byte what the plain placed composition produces
(`test_twist_assembly_cost.py`).

**The budget and what was measured.** Budget `TWIST_COST_BUDGET_S = 5` s end
to end (sweep, guard, mass properties, mesh) on this 4-core box. The estimate
is a hand-fitted model of that cost, which §6.1's first draft said it would
have to be. It is fitted by non-negative least squares on relative error over
a 50-case stress set: polygons of 3-48 edges, stars, off-axis and scaled
profiles, circles and holes, the gear tooth gap, 0.05-9.4 s. Per edge, with
`T` turns:

- `T x` a per-turn base by edge kind (line 0.0136 s, circle or arc 0.0165 s,
  spline or other 0.195 s);
- `T² x` a quadratic part. The swept B-spline's pole count grows with the
  turns, and so does every evaluation on it, so one square flank's bounded
  mesh takes 0.17 s at 5 turns and 0.63 s at 10. By edge: 0.00017 s for every
  edge; for a WIDE line flank (one the bounded mesher takes) 0.00118 s plus
  0.00256 s per radian the edge subtends at the axis; for a NARROW line flank
  0.00175 s × its length over its largest distance from the axis; for a circle
  or arc 0.0086 s × its normal turning × min(1, max(0.25, r / 5 mm)). Circles
  under 5 mm mesh coarser under the absolute deflection: r 1 mm 1.5 s, r 5 mm
  and r 50 mm 6 s, all at 10 turns.

Prediction / actual across the set is 0.78-1.25 for all but four cases. Two
are conservative (a 10 mm square over 100 mm, 1.65; an r 2 mm circle, 1.36)
and two under-predict (a radial slot, 0.73 at 1.5 s; a six-point star scaled
10×, 0.58 under load and 0.82 re-timed quiet). The limit sits at 4.5 s, below
the 5 s budget, to absorb under-prediction down to 0.8×; the slot below that
builds in 1.5 s. Measured with the guard live:

- **Worst accepted:** two circular holes in a square at 2400°, 4.34-4.96 s
  (estimate 3.47). Next are the 8-gon at 3600° (4.33 s), the gear gap at
  3000° (4.34 s) and a 16-gon at 3000° (4.25 s, estimate 4.43).
- **Fastest refused:** a 20-gon at 2880°, 4.3-4.5 s unguarded (estimate
  4.93), then a 24-point star at 3600° (4.7 s). Every other refusal took 5.8 s
  or more unguarded: 12-gon and gear gap at 3600° (5.8-6.0 s), holed square at
  3600° (6.6 s), 48-point star at 2400° and 3600° (7.4 and 9.4 s), circles of
  r ≥ 5 mm at 3600° (6.0 s).
- **QA F4's own cases** (square 20 over 30 mm): 720° 0.22 s, 1800° 0.92 s,
  2700° 1.53 s, ±3600° 3.2 s. All accepted.

`test_twist_cost.py` pins both sides: five accepted cases up to 4.3 s,
including a 16-gon 0.07 s under the limit, and five refused cases from 4.3 s.
A refused case proves no sweep ran by replacing the sweep with an assertion.
Mutating the limit, the wiring, the bounded mesher, the 3MF check or the
twist gating turns the matching tests red.

**For the UI: the threshold is in TURNS, not turns per distance.** Distance
barely moves the cost. At 10 turns a 20 mm square takes 3.2 s over 30 mm, 1.6 s
over 100 mm and 3.0 s over 300 mm (scaled 10×). What decides the cost is the
number of turns `T = |twist| / 360` and the profile's edges. A client-side
warning can use this conservative upper bound of the kernel's estimate, from
the sketch's entity counts alone:

    upper(T) = T x (0.0136 L + 0.0165 C + 0.195 S)
             + T² x (0.0094 L + 0.0002 S + sum over arcs of (0.0002 + 0.0086 θ))

`L`, `C` and `S` are the profile's line, circle-or-arc and other (spline)
edge counts, and `θ` is each circle's or arc's angle in radians (2π for a full
circle). The quadratic terms take each line as wide and fully wrapped and each
arc as at least 5 mm in radius. The kernel refuses only when its own estimate
exceeds 4.5 s, so `upper(T) > 4.5` means "may be refused". `upper(T)` never
under-states the kernel's estimate for the stress set, but it can over-state
it about 2× on many-sided polygons. Rough reach before `upper` passes 4.5: a
square (L = 4) 10.2 turns, a hexagon 8.2, a 12-gon 5.6, one full circle 9.0,
and the gear gap (L 2, C 2 short arcs, S 2) about 7. The kernel accepts the
12-gon to about 9.5 turns and the gear gap to about 9. The kernel's own
refusal is the authority; a UI hint should say "may be slow or refused", not predict it.

## 7. Not done here

- A twist on the SWEEP feature (`SweepParamsV1` still says "NO twist") and a 3D
  helix path. The twisted extrude covers the gear. A sweep twist would reuse
  this module's auxiliary-helix idea along a non-straight spine.
- A cost PREFLIGHT the UI could ask for before saving (the §6.1 estimate
  exposed on the API). The UI's bound in §6.1 covers the warning until then.
- The pattern boolean cost (§6) is OCCT's. The lever, if it matters, is running
  the tool fusion in parallel, which needs its own determinism evidence first.
