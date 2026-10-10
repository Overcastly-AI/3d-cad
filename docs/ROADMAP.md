# Roadmap

Where we are and what comes next. The orchestrator keeps "Now" true; the
`product-manager` owns the rest. The detail lives in `docs/BACKLOG.md`.

## Now (2026-10-09)

Since 10-01: picks carry through early edits (design-intent names, backfilled
on open), named part versions (Ctrl+S, restore, `.loft` 1.1), sketch Project
(P), chained lines, point-to-point dimensions, symmetric extrude, and a first
rebuild-speed pass (200 features 29.4 -> 25.3 s). In flight: rebuild speed
pass 2, then a plane at an angle (tube frames), then sketch plane picking.
Waiting on the founder: dropping the second face-merge (the next ~15 %).
Then a level-1 rerun, the A1 hinge (ASM-\* in the backlog), and level 2.

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

## Later

Versions for assemblies and drawings, version-pinned references, realtime
collaboration,
Helm/HA deployment, SSO/OIDC, and a plugin mechanism.
