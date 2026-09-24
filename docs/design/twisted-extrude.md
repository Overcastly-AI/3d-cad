# Twisted extrude: design note

Status: **IMPLEMENTED** (kernel half, 2026-09-24). The web UI (a twist field and
a gauge on the extrude editor) is a separate follow-up. Scope: the extrude
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
- **The geometric limit depends on the profile.** How tight a twist can be swept
  depends on the profile's distance from the axis relative to the distance
  travelled. Measured: a 20 mm square over 30 mm sweeps cleanly up to 3000°
  (Cavalieri residual ≤ 1.7e-10). At 3600° OCCT returns an **inverted solid**
  (volume −A·d) that `BRepCheck` calls VALID. Without a guard that body reaches
  the user as `ok` (seen: `test_a_twist_too_tight_for_the_profile_is_twist_failed`
  goes green-shaped, all four features `ok`, with the guard mutated out).
- **The Cavalieri guard.** Every slice of a twisted extrusion is a rigid
  rotation of the profile, so the swept tool's volume must equal profile
  area × distance exactly, for any twist. The kernel measures both adaptively
  (the inspector's own `VOLUME_EPS`) and refuses a departure above
  `TWIST_VOLUME_REL_TOL = 1e-6` relative as the feature error **`twist_failed`**
  ("…reduce the twist angle or lengthen the extrusion"). Healthy residuals are
  ≤ 1.7e-10, so the guard is about 6000× clear of them, and the inverted
  failure misses by 2.0. Sweep failures and holed profiles that do not leave
  one solid are also reported as `twist_failed`.

## 5. Contract

`ExtrudeParamsV1` gains two additive-optional fields. Both are null by default
and omitted from a dump while null; the generated TS client leaves them
optional. There is no `param_version` bump:

- `twist_angle_deg: float | None`: the total twist over `distance_mm`. `None`
  or `0` means no twist.
- `twist_center: Point2D | None`: where the axis pierces the sketch plane, in the
  profile sketch's (x, y) mm. `None` means the sketch origin.

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

## 7. Not done here

- The web UI (twist field plus a gauge on the extrude editor): a separate
  follow-up.
- A twist on the SWEEP feature (`SweepParamsV1` still says "NO twist") and a 3D
  helix path. The twisted extrude covers the gear. A sweep twist would reuse
  this module's auxiliary-helix idea along a non-straight spine.
- The pattern boolean cost (§6) is OCCT's. The lever, if it matters, is running
  the tool fusion in parallel, which needs its own determinism evidence first.
