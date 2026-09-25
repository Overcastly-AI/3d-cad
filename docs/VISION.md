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

| Part                                                                                     | Exercises                                                   | Last run                                                                                                      |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Helical gear: m2, 24 teeth, 15° helix, bore + keyway (`reference-parts/helical-gear.py`) | helix construction, sketcher precision, pattern, parameters | 2026-09-24 @ `95dd9cd`: built and correct, but about 45 min in the UI with workarounds and nothing parametric |
| Mounting bracket: plate, 4 bolt holes, boss on a face, picked-edge fillets               | sketch on face, multi-loop profiles, edge picks             | 2026-07-13: clean                                                                                             |
| Enclosure housing: draft, open-top shell, rim fillet                                     | draft, shell, fillet order                                  | 2026-07-13: clean                                                                                             |
| Flanged duct: round-to-square loft, offset datum, flanges on both ends                   | loft, datums, sketch on face                                | 2026-07-13: clean                                                                                             |
| Pulley/hub: revolve, lightening holes, rim fillet                                        | revolve, cut patterns                                       | 2026-07-13: clean                                                                                             |

Add a sheet-metal bracket and a bolted two-part assembly when those areas are
next in line.

## Daily-driver scorecard

Graded against SolidWorks, Fusion 360 and Onshape: ✅ better, ➖ parity,
❌ behind. Grades are from 2026-09-16. Re-grade a row only from a
reference-part run or a live-app check.

| Area                        | Grade | Why                                                                                            |
| --------------------------- | ----- | ---------------------------------------------------------------------------------------------- |
| Sketching and constraints   | ➖    | Solid solver. Missing: trig in expressions, point-to-point dimensions, named parameters.       |
| Part modelling              | ➖    | Core features compose on real parts. Twist sits on Extrude instead of Sweep.                   |
| Selection and picking       | ➖    | Face and edge picks work on real geometry. No loop or tangent-chain selection.                 |
| Assemblies                  | ➖    | Five mate types, interference, assembly STEP. Performance at scale is unmeasured.              |
| Interop (import and export) | ➖    | STEP round-trips on foreign parts. No IGES, and no recovery for a zero-solid import.           |
| Drawings                    | ➖    | Views, sections, dimensions, PDF/DXF. No detail views.                                         |
| Sheet metal                 | ➖    | Flanges, hems, flat-pattern DXF.                                                               |
| Workspace and documents     | ➖    | Parts, assemblies and drawings register. No versioning.                                        |
| Performance on real parts   | ❌    | A cold rebuild hits a wall near 50 features (about 26 s at 200). Big imports are slow to pick. |
| Collaboration and versions  | ❌    | No document versions, no realtime presence.                                                    |
| Scripting API               | ➖    | `loft-script` shipped.                                                                         |
| Agent access (MCP)          | ❌    | Not started. It is the one gap no incumbent can answer.                                        |
| Free and unlimited          | ✅    | Air-gap claim gated by `check-air-gap.py`.                                                     |
| Your data, your files       | ✅    | Backup and restore drill runs in CI.                                                           |

## Not building (for now)

- CAM, simulation/FEA and rendering, until the modelling core is a daily
  driver. The scripting API is the answer for these.
- A native desktop app. Loft is browser-first.
- Cloud SaaS billing. Self-hosting comes first.
