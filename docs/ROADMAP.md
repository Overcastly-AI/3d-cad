# Roadmap

Where we are and what comes next. The orchestrator keeps "Now" true; the
`product-manager` owns the rest. The detail lives in `docs/BACKLOG.md`.

## Now (2026-10-22)

B1-B7 build from the Build group alone and are priced; B7, a 24 x 16 ft
house, prices to the last line once long members are spliced
(integrating, with carpenter notation in length fields). Next, in order:
- a bare number in a formula read in the part's unit, so `wall + 1/2` in
  an inch part adds half an inch, not half a millimetre (a fix);
- one outline sketch for a house's walls and floor, with the roof on the
  walls, so making B7 4 ft longer is one dimension, not 8 edits;
- openings measured from either wall end, so they stay put when a wall
  grows;
- a cut list that fits the screen, grouped by floor, walls and roof.

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
6. Building generators beyond B1-B6: slabs, steel studs, stairs, roof
   sheathing and window and door units, driven by B7's gaps (RESEARCH §23).

## Later

Versions for assemblies and drawings, version-pinned references, realtime
collaboration,
Helm/HA deployment, SSO/OIDC, a whole-house assembly, and
third-party plugins.
