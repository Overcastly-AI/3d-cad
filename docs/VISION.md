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
| Pulley/hub: revolve, lightening holes, rim fillet                                        | revolve, cut patterns                                       | 2026-09-30 @ `9767a90`: built and exact (100 316.87 mm³), 5.5 min, ~70 gestures. The Line tool does not chain (24 clicks for a 12-segment profile)                                                                               |

Add a sheet-metal bracket and a bolted two-part assembly when those areas are
next in line.

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

**Status (2026-10-01):** level 1 is built 5/5 but has not passed
(EDGE-MARK-OVERLAP and SHELL-WRONG-SOLID are open, and the gear edit is
unchecked).

Reference assemblies (`docs/reference-parts/assemblies.md`) pass the same
way and are attempted in order. Loft follows Fusion and Onshape here: joints
pick a joint origin on each part, plus a motion type (ASM-JOINTS).

- **A1 butt hinge:** 2 parts, a revolute joint limited to 0-180°.
- **A2 bench vice:** 7 parts, 12 instances, a slider, BOM, interference and a drawing.
- **A3 linear stage:** 16 parts, 73 instances, a sub-assembly, fastener patterns, an in-context edit and time budgets.

## Daily-driver scorecard

Graded against SolidWorks, Fusion 360 and Onshape: ✅ better, ➖ parity,
❌ behind. Grades are from 2026-09-16. Re-grade a row only from a
reference-part run or a live-app check.

| Area                        | Grade | Why                                                                                                                                                     |
| --------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sketching and constraints   | ➖    | Solid solver. Missing: trig in expressions, point-to-point dimensions, named parameters.                                                                |
| Part modelling              | ➖    | Core features compose on real parts, and twist is on Sweep. Shell fails on a round-to-square loft (2026-09-30 run).                                     |
| Selection and picking       | ❌    | On a 2 mm wall, overlapping edge marks pick the wrong edge unseen, and a fillet edit cannot re-pick (2026-09-30 run). No loop selection.                |
| Assemblies                  | ➖    | Five mate types, interference, BOM, assembly STEP. No move handle, drag, limits, motion or component patterns (code read 2026-10-01; re-grade from A1). |
| Interop (import and export) | ➖    | STEP round-trips on foreign parts. No IGES, and no recovery for a zero-solid import.                                                                    |
| Drawings                    | ➖    | Views, sections, dimensions, PDF/DXF. No detail views.                                                                                                  |
| Sheet metal                 | ➖    | Flanges, hems, flat-pattern DXF.                                                                                                                        |
| Workspace and documents     | ➖    | Parts, assemblies and drawings register. No versioning.                                                                                                 |
| Performance on real parts   | ❌    | A cold rebuild hits a wall near 50 features (about 26 s at 200). Big imports are slow to pick.                                                          |
| Collaboration and versions  | ❌    | No document versions, no realtime presence.                                                                                                             |
| Scripting API               | ➖    | `loft-script` shipped.                                                                                                                                  |
| Agent access (MCP)          | ❌    | Not started. It is the one gap no incumbent can answer.                                                                                                 |
| Free and unlimited          | ✅    | Air-gap claim gated by `check-air-gap.py`.                                                                                                              |
| Your data, your files       | ✅    | Backup and restore drill runs in CI.                                                                                                                    |

## Not building (for now)

- CAM, simulation/FEA and rendering, until the modelling core is a daily
  driver. The scripting API is the answer for these.
- A native desktop app. Loft is browser-first.
- Cloud SaaS billing. Self-hosting comes first.
