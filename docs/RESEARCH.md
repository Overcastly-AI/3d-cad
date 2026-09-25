# Architecture decisions

The live decisions, each with its reason. Change one only by updating this
file in the same commit. Section numbers are stable, because code comments cite
them. The full history of each decision, and the design notes for shipped
features that code comments cite (`docs/design/*.md`), are in git:
`git show 5b6fd28:docs/RESEARCH.md` and `git show 5b6fd28:docs/design/<name>.md`.

## 1. Geometry kernel: OCCT via OCP, with build123d

**Decision.** OCCT 7.x through the OCP bindings, with build123d as the
modelling layer, used only inside `services/geometry`.

**Why.** OCCT is the only mature open-source B-rep kernel (solids, fillets,
booleans, STEP, meshing). OCP is complete, and build123d saves us writing the
topology plumbing. FreeCAD is an application rather than an embeddable kernel,
SolveSpace is GPL and limited, SDF kernels are not B-rep, and truck is
immature.

**Licence.** OCCT is LGPL-2.1 with an exception; OCP and build123d are
Apache-2.0.

**Helical construction.** Twist is `BRepOffsetAPI_MakePipeShell` along a
straight spine, in auxiliary-spine mode with a helix about that spine: an
exact screw motion. It is checked against the Cavalieri identity
(volume = area x distance), because OCCT can return an inverted solid that
`BRepCheck` accepts. The flanks are meshed with surface-deflection refinement
off, and a twist whose estimated cost exceeds 4.5 s is refused
(`twist_failed`). See `docs/design/twisted-extrude.md`. Twist moves to Sweep
next (BACKLOG TWIST-TO-SWEEP).

## 2. Sketch solver: planegcs

**Decision.** FreeCAD's PlaneGCS via the `planegcs` PyPI package (LGPL-2.1+),
behind the `SketchSolver` protocol (`geometry.sketch.solver`). Callers never
import `planegcs`. SolveSpace (`py-slvs`, `python-solvespace`) is GPLv3 and
forbidden.

Rules the solver keeps:

- **Deterministic.** Same sketch and constraints give a bitwise-identical
  result, asserted over a sequence of solves.
- **An under-constrained solve holds the author's geometry.** After the solve
  converges, it pins every free coordinate and radius back to the author's
  value and re-solves (the "settle"), so a dimension edit moves only what it
  names.
- **A settle refines the plain solve and never re-orients it.** If any entity
  would run backwards relative to the plain solve, the plain solve is used.
- **Every constraint is verified against the shipped geometry** by an
  independent residual (`geometry.sketch.residual`). planegcs's own status is
  not evidence. A violated constraint is reported as `sketch_conflicting` and
  the input is returned untouched.
- **A collapse (zero radius or length) that the constraints do not force is
  retried** from the author's pose; one the constraints do force is refused.
- Spline fit points can take point constraints; spline tangency is deferred
  until there is a native spline primitive.

## 3. Monorepo of services, contract-first

**Decision.** One monorepo: `apps/web`; `services/{gateway,geometry,documents}`;
`packages/{loft-wire,py-kit,loft-script,contracts,ts-client,design}`.

- **One source of truth for types.** Pydantic models (`loft-wire` and service
  DTOs) generate OpenAPI (`packages/contracts`), which generates the TS client.
  Hand-written duplicates are defects. Cross-service boilerplate lives once in
  `py-kit`.
- **Service boundaries.** Geometry never touches the database, documents
  never imports the kernel, and the web app talks only to the gateway.

## 3a. The scripting API is a gateway client

`packages/loft-script` (`import loft`) calls only gateway routes the browser
can call, and imports no kernel or database. The MCP server will be a thin
adapter over it. It is enforced by a generated operation table
(`loft/_operations.py`, from the gateway contract only), a transport that
refuses undeclared request shapes, and a static parity test over every call
site (`tests/test_contract_parity.py`). Python imports the wire types directly;
only the routing is generated.

## 3b. Wire types are their own distribution

`packages/loft-wire` depends only on `pydantic` and `email-validator`, so
`pip install loft-script` does not pull in a web server, ORM or queue.
`py-kit` and `loft-script` depend on it, never the reverse. This is enforced by
`test_wire_dependency_closure.py` and `test_install_weight.py`. Metrics are
wired through an observer registry (`loft_wire.instrument`).

## 4. Data and messaging

PostgreSQL 16 holds users, documents and feature trees. Redis 7 + arq is used
for rate limiting and the job queue. Meshes and exports go to S3-compatible
object storage, content-addressed. Without `S3_URL` the geometry service uses
an in-process LRU.

## 5. Frontend

React 19 + Vite + TypeScript SPA; TanStack Router and Query; Tailwind; three.js
through react-three-fiber and drei; zustand for editor state. There is no SSR,
because a CAD client is long-lived and stateful. Meshes arrive as GLB from the
server, and the client never runs the kernel.

- **Content-addressed meshes** are auth-gated but not scoped to an owner. This
  is safe only because the id is a content hash. Do not reuse the pattern for
  any artifact that is sensitive to its owner.
- **Design system** (`packages/design`): tokens, primitives and fonts in a
  source-only package, consumed by both the Tailwind preset and the WebGL
  scene, so there is one palette for two renderers.

## 6. Tooling

uv workspaces (ruff, pyright strict, pytest); pnpm workspaces (eslint,
prettier, vitest, Playwright); a root `justfile`; GitHub Actions (`ci`, `e2e`,
`deploy-path`).

## 7. Cloud-native posture

Twelve-factor: config via env, one Dockerfile per service, `/healthz` and
`/readyz` from `py-kit`, JSON logs, stateless services. Docker Compose is the
dev and small self-host path; Helm comes later.

## 8. Licensing

The app is MIT. MIT, BSD, Apache and LGPL (dynamically linked) dependencies
are allowed, as is OCCT's LGPL with its exception. **GPL and AGPL are
forbidden.** Two points follow; details are in `docs/LICENSING.md`:

1. Shipping images makes us a distributor. LGPL §6 then requires the licence
   text, notice and an offer of corresponding source (§6(d)).
2. Package metadata lies. The OCP wheel declares Apache-2.0 but vendored GPL
   jbigkit. The licence gate (`scripts/check-licences.py`, in `just lint`)
   reads the binaries, and jbigkit is stripped from our images.

## 9. Geometry QA strategy

The correctness gates, run in CI and by `geometry-qa`:

- **Golden models** (`services/geometry/goldens*/`): rebuild from the feature
  tree. Mass properties must match within the golden's documented tolerance,
  and topology and mesh counts must match exactly. A part with no material
  reports no mass: null, never 0.
- **Determinism:** two in-process rebuilds and one in a fresh interpreter give
  byte-identical GLB and metadata. Where a feature names a set of features,
  they are applied in tree order, never request order.
- **STEP round-trip:** export, re-import and compare, within `ROUNDTRIP_TOL`
  (1e-7) unless a golden records a measured override. A body is made
  conformal before export, but only when `BRepCheck` rejects it, and never if
  the heal moves the volume.
- **Export byte-determinism** in every format, in-process and across
  restarts: the STEP timestamp is pinned, writer counters are canonicalised,
  and 3MF UUIDs are derived. We drive OCCT's STEP writer ourselves for correct
  names and provenance. Each format declares its own units (`EXPORT_UNITS`):
  STEP, STL and 3MF are in mm; glTF is in metres, Y-up.
- **Volume integration** lives in one place (`properties.volume_properties`).
  Spline-swept faces are integrated through exact NURBS twins, and offset
  faces through our own Gauss-Legendre per knot span.
- **Refuse, do not heal, missing material:** zero-width slits
  (`find_zero_width_slits`) and degenerate parameters become typed feature
  errors.
- **A simplification may not change material:** `clean_shape` discards any
  `clean()` that moves the volume. `BRepCheck` validity is checked when a body
  is admitted and again at publish time, and an invalid body is never
  measured, meshed or exported.
- **An assembly STEP instances its parts** (solid count equals unique part
  count).
- **Artifacts for a machine are checked against the part**, not against
  themselves. For example, each flat-pattern DXF is checked for isometry,
  handedness and one cut per through hole.
- **Performance budgets:** wall-clock tripwires run in `just test`, and the
  detail is in `just bench`.

## 9a. Materials and mass

A body has a material with a density. Mass is derived in the kernel, in
grams, and is null when there is no material. Materials ride
`EvaluateTreeRequest.materials`, and a change bumps `tree_version`. A roll-up
(multi-body or assembly) is null unless every contributor has a material. The
library is served (`GET /api/v1/materials`), not duplicated in the client.

## 10. Assemblies

An assembly is its own document type in `services/documents`: instances plus
mates, referencing parts by id. It resolves to the part's tip until part
versioning exists (`ref_pinned_version` is already in the schema). **The mate
solver is our own**: rigid bodies (translation and a unit quaternion), with
damped Gauss-Newton or LM seeded from the authored placements, no random
restarts, and a closed-form fast path for trees. It is deterministic and sits
behind an `AssemblySolver` protocol. SolveSpace is GPL; OndselSolver is a
possible future spike. Mates reference geometry through the same face and edge
signatures features use. Geometry evaluates each unique part once and returns
a shared mesh plus a solved transform for each instance.

## 11. Drawings

A drawing is its own document type that references parts and assemblies by
id. Projection is OCCT **exact HLR** (`HLRBRep_Algo`), with a canonical edge
sort for determinism, a per-view budget and a typed `view_projection_failed`.
Polygonal HLR is the lower-fidelity fallback. **Dimensions reference model
edges** through the topological-naming signatures, never projected 2D edges,
so a part edit gives an honest `subshape_unresolved` rather than a wrong
number. Geometry composes SVG, PDF (reportlab, BSD) and DXF (ezdxf, MIT) as
content-addressed artifacts. The neutral `ViewGeometry` DTO drives the
client-side sheet editor.

## 12. Datum-plane conventions (scripting trap)

| Datum | x_dir | y_dir | normal (extrude direction) |
| ----- | ----- | ----- | -------------------------- |
| `XY`  | +X    | +Y    | +Z                         |
| `XZ`  | +X    | +Z    | **-Y**                     |
| `YZ`  | +Y    | +Z    | +X                         |

`y_dir = z_dir x x_dir` always. An offset datum slides along its parent's own
normal (off `XZ` by +5 lands at y = -5); `flip` negates the normal and keeps
`x_dir`. An on-face datum sits at the face's area centroid with the outward
normal, and `x_dir = deterministic_x_dir(normal)`, which is the world axis
least aligned with the normal. A midplane between parallel sides takes side
A's normal. Scripts should read the resolved plane back rather than guess a
sign.

## 13. Sessions and tokens

Access tokens are HS256 JWTs (1 h) carrying `sub` and `sid`. Refresh tokens
are random 256-bit values in an `HttpOnly; Secure; SameSite=Strict` cookie
scoped to `/api/v1/auth`. They rotate on use, and reusing an old one revokes
the whole session. Sessions time out after 24 h idle (sliding) and 7 days
absolute. Without TLS on a host other than localhost, the limit is a hard 1 h.
