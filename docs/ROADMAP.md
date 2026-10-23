# Roadmap

Where we are and what comes next. The orchestrator keeps "Now" true; the
`product-manager` owns the rest. The detail lives in `docs/BACKLOG.md`.

## Now (2026-10-23)

B7, a 24 x 16 ft house, builds from one outline sketch, prices to the last
line, and grows 4 ft by one dimension. In flight: openings measured from
either wall end, a cut list that fits the screen, and hip roofs on sheathed
walls. Next, in order: an opt-in update for stored roofs whose tails pass
through the sheathing (a fix), then priced window and door units, 3-ply
headers in 2x6 walls, and floor joists that span the short way however the
outline was drawn.

## Shipped

- **Foundation and MVP:** monorepo, three FastAPI services, generated
  contracts, compose stack, sketch, extrude, STEP/STL export.
- **Parametric core:** constraint sketcher (planegcs), feature tree with
  rollback and undo/redo, extrude, revolve, sweep, loft, fillet, chamfer,
  shell, draft, hole, patterns, mirror, datum planes, multi-body, materials
  and mass, and topological naming for faces and edges.
- **Assemblies v1:** instances, five mate types, interference, BOM, assembly
  STEP.
- **Interop and drawings:** STEP import, STEP/STL/3MF/GLB export, drawings
  with views, sections, dimensions and PDF/DXF.
- **Sheet metal v1:** base and edge flanges, hems, flat pattern, DXF.
- **Scripting:** the `loft-script` Python API (`import loft`).
- **Files and versions:** the `.loft` part file (format 1.2) and named,
  restorable part versions.
- **Self-hosting:** air-gapped operation, backup/restore drill, licence gates.

## Next

1. The blockers from the reference parts (see `docs/VISION.md`).
2. Sketcher precision for real parts: trig in expressions and named
   parameters shared across features.
3. Performance on real parts: the cold-rebuild wall and large imports.
4. MCP server on top of `loft-script`.
5. Assemblies a working engineer can use: joints, drag, limits, component patterns
   and in-context edits, driven by the reference assemblies A1-A3.
6. Building generators beyond B1-B7: sheets and splices counted as a yard
   quotes them, slabs, stairs, steel studs and roof sheathing (RESEARCH §23).

## Later

Versions for assemblies and drawings, version-pinned references, realtime
collaboration,
Helm/HA deployment, SSO/OIDC, a whole-house assembly, and
third-party plugins.
