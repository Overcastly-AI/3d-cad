# Roadmap

Where we are and what comes next. The orchestrator keeps "Now" true; the
`product-manager` owns the rest. The detail lives in `docs/BACKLOG.md`.

## Now (2026-10-16)

Since 10-09: part parameters, a plane at an angle, sketch plane picking,
closed-path sweeps, assembly joints with drag and limits, nested
sub-assemblies, component patterns and in-context edits (A3). Next, in order:
a failed part named in API exports, Pipe and Plane Along Path (bike tube
frames), the plugin registry and its Build toolbar (the B1 deck), and one
face-merge per boolean (rebuild speed). Waiting on the founder: the object
store.

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
6. Plugins as custom features, then building generators (deck, stud walls,
   hosted windows and doors, roof) with lumber materials and a cut list,
   driven by the reference buildings B1-B2 (RESEARCH §23).

## Later

Versions for assemblies and drawings, version-pinned references, realtime
collaboration,
Helm/HA deployment, SSO/OIDC, timber framing, a whole-house assembly, and
third-party plugins.
