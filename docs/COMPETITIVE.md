# Competitive feature-map

> Living feature pipeline owned by the **vision-steward** agent. Each cycle it
> reads the public product docs of the tools we're chasing — **Fusion 360**
> (help.autodesk.com) and **Plasticity** (docs.plasticity.xyz) as the primary
> modern references, SolidWorks / Onshape / FreeCAD for the incumbent baseline
> — enumerates the capabilities they ship, maps each against what Loft has
> today (`git log` + ROADMAP), and files the gaps as `[src: competitive]`
> BACKLOG candidates. The **backlog-groomer** restocks its Ready queue from
> here when the pipeline runs thin.
>
> **Rules:** describe capabilities in our own words; cite the source doc URL;
> never paste competitor text/assets. Update this map incrementally — don't
> rewrite it. The operating question governs prioritization: a gap that flips
> a ❌ scorecard row (VISION.md) outranks breadth-for-breadth's-sake.
>
> Loft-status legend: ✅ shipped · 🚧 in progress · ⬜ not started.
> The competitor columns below are **unverified stubs** until the steward's
> first web pass fills them from the cited docs; the Loft column is accurate
> as of the last edit's `git log`.

## Sketching

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Constraints (coincident/H/V/dist/radius/fixed/tangent/perp/parallel/equal/symmetric/concentric) | — | — | ✅ 12 kinds (planegcs) | Shipped Phase 1–2 |
| Construction geometry | — | — | ✅ | Shipped |
| Trim / extend | — | — | ⬜ | Phase 2 — named scorecard gap |
| Offset (parallel curve) | — | — | ⬜ | Phase 2 — named scorecard gap |
| Sketch mirror / pattern | — | — | ⬜ | Phase 2 — named scorecard gap |
| Splines (free-form) | — | — | ⬜ | Phase 2 — hard capability gap |
| Sketch fillet / chamfer (corner-round) | — | — | ⬜ | Phase 2 |
| Redundant-vs-conflicting diagnosis | — | — | 🚧 index-only flag | Phase 2 — upgrade to classified |

## Part modeling (features)

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Extrude (add/cut) | — | — | ✅ | Shipped |
| Revolve | — | — | ✅ | Shipped |
| Fillet / chamfer | — | — | ✅ predicate-only edges | Phase 2 — needs click-specific edge (topo naming) |
| Click-specific edge/face selection | — | — | ⬜ | Phase 2 — gated on topological-naming doc |
| Measurement / distance query | — | — | 🚧 backend + overlay; UI pending | Ready #6 |
| Linear / circular pattern | — | — | ⬜ | Ready #7 |
| Sweep | — | — | ⬜ | Phase 2 |
| Loft | — | — | ⬜ | Phase 2 |
| Shell | — | — | ⬜ | Phase 2 |
| Draft | — | — | ⬜ | Phase 2 |
| Dedicated hole feature | — | — | ⬜ | Phase 2 |
| Multi-body / boolean between bodies | — | — | ⬜ | Phase 2 |
| Datum planes / axes | — | — | ⬜ | Phase 2 |
| Direct-modeling push/pull gestures | — | — | ⬜ | Plasticity's core wedge — investigate |
| Undo/redo across features | — | — | ⬜ | Phase 2 |

## Assemblies, interop, drawings, collaboration

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Assemblies: instances, mates/joints, BOM | — | — | ⬜ | Phase 3 |
| STEP/IGES import + healing | — | — | ⬜ | Phase 4 — flips Interop row to ➖ |
| STEP/STL export | — | — | ✅ | Shipped |
| 2D drawings (views, dims, PDF/DXF) | — | — | ⬜ | Phase 4 |
| Realtime multi-user | — | — | ⬜ | Phase 3 |
| Python scripting API / MCP | — | — | ⬜ | Phase 5 — structural advantage #4 |

## Discovery log

_Dated entries as the vision-steward runs each web pass — what was read (with
URLs), what capabilities were newly enumerated, what BACKLOG items were filed._

- _(no web pass yet — this map is the seeded skeleton; competitor columns fill
  on the first `docs/COMPETITIVE.md` discovery pass.)_
