# Roadmap

Where we are and what comes next. The orchestrator keeps "Now" true; the
`product-manager` owns the rest. The detail lives in `docs/BACKLOG.md`.

## Now (2026-10-01)

Twist lives on Sweep; sealed Shell rebuilds deterministically; CI has a
fast per-commit lane (about 8 min) and a full lane on the newest tip. In
flight: Shell must never ship a wrong solid, then sharp shell corners by
default, then the reference-part blockers. After those fixes, testing
climbs the part complexity ladder in `docs/VISION.md` (level 2 once level 1
passes with no wrong-geometry finding), then the reference assemblies,
starting with the A1 hinge (ASM-\* in the backlog).

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
- **Self-hosting:** air-gapped operation, backup/restore drill, licence gates.

## Next

1. The blockers from the reference parts (see `docs/VISION.md`).
2. Sketcher precision for real parts: trig in expressions, point-to-point
   dimensions, and named parameters shared across features.
3. Performance on real parts: the cold-rebuild wall and large imports.
4. MCP server on top of `loft-script`.
5. Assemblies a working engineer can use: drag, limits, component patterns
   and in-context edits, driven by the reference assemblies A1-A3.

## Later

Document versioning and version-pinned references, realtime collaboration,
Helm/HA deployment, SSO/OIDC, and a plugin mechanism.
