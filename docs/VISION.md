# Vision

Owned by the `product-manager`. The founder decides.

## What Loft is

The best open-source parametric 3D CAD: browser-based, self-hostable,
MIT-licensed, made by Overcastly AI (https://overcastly.com). "Loft" is a
working name.

We will not beat SolidWorks on a 30-year feature list. We compete on four
things a per-seat, cloud-locked incumbent structurally cannot offer:

1. **Free and unlimited.** It runs on your hardware, so an extra seat costs
   nothing, and no document is held hostage.
2. **Your data, your files, your compute.** STEP-first, an open document
   store, and it runs fully air-gapped.
3. **Open and extensible.** The modelling API is Python (`loft-script`), the
   same code path the UI uses.
4. **Agent-native.** An MCP server lets a coding agent build and edit parts.

Everything else is table stakes we ship to be credible.

## The question

> **Would a working engineer model a real part in this today?**

People switch to escape Fusion's licensing, cost and lock-in. They stay only
if modelling does not cost them time. So:

- **Follow mainstream CAD conventions.** A feature, option or gesture goes
  where Fusion 360, SolidWorks and Onshape users expect it (for example, twist
  is a Sweep option, not an Extrude option). Diverge only for a reason written
  down here.
- **Flow comes first.** The next step is visible from where the user is. A
  drag handle is the primary control and a typed value is the precise
  fallback. There are no dead ends.
- **The viewport is the hero.** The chrome stays quiet and keyboard-first, and
  the tool should feel like Fusion or Plasticity.

## Base tooling and plugins

Base tooling is the core that Fusion 360, SolidWorks and Onshape share:
sketch, extrude, revolve, sweep, loft, hole, fillet, chamfer, shell, draft,
pattern, mirror, datums and assemblies. Loft does not build niche or legacy
features into it. A feature outside that core is deprecated and will live in
a future plugins package (PLUGINS-PACKAGE in `docs/BACKLOG.md`). A deprecated
feature keeps loading and rebuilding every stored part unchanged (read-only
legacy), but it cannot be authored again. If a part relies on one, rebuild
the part with base tooling. The first is the extrude twist: a twisted prism
is a Sweep with twist along a straight path, as in Fusion and SolidWorks
(founder, 2026-10-09).

## Reference parts

These drive priority. `qa-tester` models them end to end in the real app
about once a week, and whatever blocks them goes to the top of
`docs/BACKLOG.md`.

| Part                                                                                     | Exercises                                                   | Last run                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Helical gear: m2, 24 teeth, 15° helix, bore + keyway (`reference-parts/helical-gear.py`) | helix construction, sketcher precision, pattern, parameters | 2026-09-30 @ `9767a90`: built and exact (a true helicoid through Sweep Twist; STEP: 24 teeth, twist 12.2959°, tooth 3.2524 mm), 21 min, ~90 gestures, every point typed. Two typed-entry bugs cost redraws. Still not parametric |
| Mounting bracket: plate, 4 bolt holes, boss on a face, picked-edge fillets               | sketch on face, multi-loop profiles, edge picks             | 2026-09-30 @ `9767a90`: built and exact (56 615.35 mm³), 9 min, ~60 gestures. A face click in plane-pick sketched on XY; Enter un-picks the last edge                                                                            |
| Enclosure housing: draft, open-top shell, rim fillet                                     | draft, shell, fillet order                                  | 2026-09-30 @ `9767a90`: built, exact after rework (29 550.51 mm³). The first pass filleted 2 inner rim edges unseen (overlapping pick marks), and a fillet edit cannot re-pick. 6 min + 20 min rework                            |
| Flanged duct: round-to-square loft, offset datum, flanges on both ends                   | loft, datums, sketch on face                                | 2026-09-30 @ `9767a90`: built and exact (63 738.62 mm³) by a workaround: Shell fails on the loft (OCCT), so an inner loft cut. The datum plane is not drawn. 17 min, ~75 gestures                                                |
| Pulley/hub: revolve, lightening holes, rim fillet                                        | revolve, cut patterns                                       | 2026-09-30 @ `9767a90`: built and exact (100 316.87 mm³), 5.5 min, ~70 gestures. The Line tool now chains (LINE-CHAIN: 13 clicks for the 12-segment profile, was 24)                                                                               |

Add a sheet-metal bracket and a bolted two-part assembly when those areas are
next in line.

### Hard parts

Run 2026-10-01 @ `ab31825` by `qa-tester`, headless Chromium at 1280x800,
every value typed. Each part was STEP-exported, re-read and checked against an
independent build123d script, then an early dimension was edited
(`docs/screenshots/hard-parts-2026-10-01/`).

| Part                                                                                                         | Result                                                                                                                                                                                                                    | Time, gestures                   | Top blocker                                                                                    |
| ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------- |
| Moulded enclosure half: 120x80x35, 1.5° draft, 2 mm open shell, lip, 4 bosses, 4 ribs, screw holes           | Partial. Built (49 623.6 mm³, script 49 622.9), but the screw holes are extrude cuts, the lip corners are sharp and the rib roots are not filleted. Width 120 -> 130: Fillet1 lost its edges and 23 features were skipped | over 60 min (two sessions), ~650 | DESIGN-INTENT-REFS. Also SKETCH-FILLET-UNTRIM, HOLE-BLIND-FALSE-DEEP and MULTI-PROFILE-EXTRUDE |
| Sheet-metal bracket: 60x40x2 base, two 90° flanges, a centred 45° flange with reliefs, hem, hole near a bend | Partial. Built (11 529.75 mm³, matches the hand calculation), but the flat pattern is refused. Base 60 -> 70: Hole1 became ambiguous                                                                                      | 6.5 min, 68                      | FLAT-PATTERN-PARTIAL                                                                           |
| Duct transition: Ø60 to 80x40 loft over 100 mm, 2 mm wall, R80 swept bend, bolted flanges at both ends       | Built and exact (121 842.32 mm³), using an inner loft and sweep cut because Shell fails (LOFT-SHELL). Ø60 -> Ø64 rebuilt exact (190 661.57), and the flange on the swept end followed                                     | 13.5 min, 188                    | LOFT-SHELL                                                                                     |
| Turned shaft: Ø60/30/25/20 revolve, 2 circlip grooves, keyway, 0.5 mm chamfers, 6-hole flange, cross hole    | Built and exact (72 532.21 mm³). A dimension on the typed profile tore it open and all 11 features failed. The PCD and cross-hole datum edits rebuilt correctly                                                           | 7.3 min, 131                     | TYPED-POLYLINE-UNJOINED                                                                        |
| Impeller: Ø40 hub, twisted ruled-loft blade x7, R1 root fillets, Ø12 bore with keyway                        | Built and exact (29 488.49 mm³). Hub Ø40 -> Ø44: the root fillet lost all 14 edges                                                                                                                                        | 7.6 min, 133                     | DESIGN-INTENT-REFS                                                                             |

**Re-run 2026-10-01 @ `7916a63`** (DESIGN-INTENT-REFS step 1; impeller also
at `1942b0f`, step 2), on fresh parts
with the same dimensions and the same headless setup
(`docs/screenshots/hard-parts-rerun-2026-10-01/`). The enclosure now has a
rounded lip (R7/R6 sketch fillets) and real blind holes, and it has no
rib-root fillets.

| Part      | Before edit (app, check)                                                                            | Edit           | After edit                                                                                                                               | Check                                              |
| --------- | --------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Enclosure | 49 606.57 mm³, 18 features; STEP 49 606.51 against script 49 606.65, empty boolean difference      | width 120->130 | All 18 rebuilt. Draft1 (4 faces), Fillet1 (4 edges), Fillet2 (8 edges), Shell1, Plane1 and Hole1 all resolved through the named tier     | 52 639.35 against script 52 639.50, empty boolean difference |
| Bracket   | 11 529.75 mm³, matches the hand calculation                                                         | base 60->70    | Hole1 SUBSHAPE_AMBIGUOUS ("2 planar faces match"), and Edge flange1 shows "edge moved". As expected, because step 3 is not in             | flanges and hem 12 597.41, matches the hand calculation |
| Impeller  | 29 488.49 mm³; STEP equals script, empty boolean difference | hub Ø40->Ø44 | Fillet1 SUBSHAPE_UNRESOLVED on all 14 edges, which carry no names. Re-checked on a fresh part at `1942b0f` (step 2): all 14 picks now carry names and it still fails (`impeller-step2-after-hub44.png`) | unfilleted body 34 277.28, matches the script |

Since the morning run, EDGE-MARK-OVERLAP is fixed on the lip: clicks on the 4
outer-corner marks picked those 4 edges and no stray, even where an inner-edge
mark is topmost (`enclosure-lip-fillet-picks.png`). Sketch fillets on the typed,
dimensioned 118x78 lip kept every trim across all 8 corners, and typed
polylines now get their coincident constraints. HOLE-BLIND-FALSE-DEEP is fixed:
a Ø2.5x25 blind hole builds on the boss.

**Re-run 2026-10-02 @ `fbaaa6c`** (main `aab2b34`: DESIGN-INTENT-REFS steps
1-3 and the fillet guard), on fresh parts with the same dimensions and the same
headless setup (`docs/screenshots/hard-parts-rerun-2026-10-02/`). The enclosure
is its 6-feature core (sketch, extrude, 1.5° draft, R8 and R3 fillets, 2 mm
shell), with no lip, bosses or holes. All three edits now pass.

| Part      | Before edit (app, check)                                                                 | Edit           | After edit                                                                                                                                         | Check                                                    |
| --------- | ---------------------------------------------------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Bracket   | 11 529.75 mm³; STEP equals the hand calculation                                          | base 60->70    | All 7 rebuilt with no warning. Hole1 stays on Edge flange1 (Ø5 at z 8 through x 42..44 and -34..-32), and the hem runs x -30..40                    | 12 518.87, equals the hand calculation                   |
| Impeller  | 29 488.49 mm³; STEP equals script, empty boolean difference                              | hub Ø40->Ø44   | All 13 rebuilt. Fillet1 keeps all 14 named edges, and no blade root is sharp (0 of 14 hub edges over 5°; the unfilleted body has 14)                | 34 323.59 against script 34 323.59, empty boolean difference |
| Enclosure | 42 638.25 mm³; STEP 42 638.15 against script 42 638.24, empty boolean difference         | width 120->130 | All 6 rebuilt, and Draft1, Fillet1 (4 edges), Fillet2 (8 edges) and Shell1 kept their picks                                                        | 45 490.69 against script 45 490.79, empty boolean difference |

**Tangent chains are refused.** An R1 fillet on ONE outer rim edge of the
130-wide enclosure fails: "a face farther than the fillet can reach is missing
or changed". OCCT carries that one pick round the whole 8-edge tangent loop and
builds exactly the 8-pick body (45 397.08 mm³, empty difference), so the guard
refuses a correct result where Fusion would round the chain. Picking all 8 edges
builds and matches the script (`enclosure-rim-loop-*.png`). On the impeller, an
R0.5 on one blade-top blend edge is refused as well, but plain OCCT fails there
too: the chain turns from convex to concave at the hub. That refusal is right,
but its message ("the radius may be too large") is not
(`impeller-tangent-chain-*.png`).

## Part complexity ladder and reference assemblies

Parts get harder in five levels, with 3-4 fully dimensioned parts per level
(`docs/reference-parts/ladder.md`). A part **passes** when it is built in the
app without a workaround, a named early-dimension edit rebuilds every later
feature, and its volume and key dimensions match an independent script to
1e-4. A level is attempted only once the previous one passes with no open
wrong-geometry finding.

1. The five reference parts above.
2. Workshop parts: pillow block, sheet-metal tray, hydraulic manifold, ribbed bracket.
3. Moulded, formed and swept: drafted and ribbed housing, 1U rack chassis, 3D bent tube, two-body knob.
4. Commercial, 100+ features: guide-rail grip, parametric heat sink, edited imported STEP, gearbox housing.
5. Hardest: ISO 4762 design-table family, area-law pump volute, four-runner intake manifold.

**Status (2026-10-09):** level 1 is built 5/5 but has not passed. Its two
wrong-geometry findings (EDGE-MARK-OVERLAP, SHELL-WRONG-SOLID) are fixed, but
no rerun has checked the five edits since, and the gear cannot be edited from
one value until PARAMETERS lands.

Reference assemblies (`docs/reference-parts/assemblies.md`) pass the same
way and are attempted in order. Loft follows Fusion and Onshape here: joints
pick a joint origin on each part, plus a motion type (ASM-JOINTS).

- **A1 butt hinge:** 2 parts, a revolute joint limited to 0-180°.
- **A2 bench vice:** 7 parts, 12 instances, a slider, BOM, interference and a drawing.
- **A3 linear stage:** 16 parts, 73 instances, a sub-assembly, fastener patterns, an in-context edit and time budgets.

## Daily-driver scorecard

Graded against SolidWorks, Fusion 360 and Onshape: ✅ better, ➖ parity,
❌ behind. Grades are from 2026-09-16. Re-grade a row only from a
reference-part run or a live-app check. The "Why" text was checked against
main `01e49e2` on 2026-10-09 (commits and tests; no grade changed).

| Area | Grade | Why |
| --- | --- | --- |
| Sketching and constraints | ➖ | Solid solver. Lines chain, points dimension to points and lines, and body edges project into a sketch (not splines). Missing: trig in expressions, named parameters. |
| Part modelling | ➖ | Core features compose on real parts, twist is on Sweep, and Extrude is one-sided or symmetric. Shell fails on a round-to-square loft; no plane at an angle, closed-path sweep or Through All extrude. |
| Selection and picking | ❌ | Overlapping edge marks fixed (2026-10-01 rerun) and one pick rounds its tangent chain. No face or loop selection, and a fillet edit could not re-pick (2026-09-30 run, not rechecked). |
| Assemblies | ➖ | Five mate types, interference, BOM, assembly STEP. No move handle, drag, limits, motion or component patterns (code read 2026-10-01; re-grade from A1). |
| Interop (import and export) | ➖ | STEP round-trips on foreign parts. No IGES, and no recovery for a zero-solid import. |
| Drawings | ➖ | Views, sections, dimensions, PDF/DXF. No detail views. |
| Sheet metal | ➖ | Flanges, hems, flat-pattern DXF. The hard-parts bracket's flat pattern is refused. |
| Workspace and documents | ➖ | Parts, assemblies and drawings register; duplicates keep their materials. Parts keep named, restorable versions (Ctrl+S); assemblies and drawings have none. |
| Performance on real parts | ❌ | A cold rebuild grows about N^2: 25.3 s at 200 features, 6.3 s at 100 (2026-10-09, loaded host; was 29.4 and 7.0). OCCT booleans dominate; RESEARCH §15a plans the rest. |
| Collaboration and versions | ❌ | Named part versions only: no automatic history, branches or compare (Onshape, Fusion), no version-pinned references, no realtime presence. |
| Scripting API | ➖ | `loft-script` shipped, versions included. |
| Agent access (MCP) | ❌ | Not started. It is the one gap no incumbent can answer. |
| Free and unlimited | ✅ | Air-gap claim gated by `check-air-gap.py`. |
| Your data, your files | ✅ | Backup and restore drill runs in CI. A part and its named versions export and import as a `.loft` file (format 1.2; docs/FILE-FORMAT.md). |

## Not building (for now)

- CAM, simulation/FEA and rendering, until the modelling core is a daily
  driver. The scripting API is the answer for these.
- A native desktop app. Loft is browser-first.
- Cloud SaaS billing. Self-hosting comes first.
