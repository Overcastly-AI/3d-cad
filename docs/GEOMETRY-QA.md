# Geometry QA — run log & findings

Maintained by the **geometry-qa** agent. The question this file answers is
not "do the tests pass" but **"is the geometry RIGHT?"** (RESEARCH §9,
`.claude/skills/geometry-gates/SKILL.md`). Entries are dated, evidence-first
(expected vs. actual numbers), newest on top. Tolerance changes are reviewed
decisions recorded here AND in the golden's `expected.json` — never a way to
go green.

## How to run the geometry gates

```bash
# golden-model harness (mass props / topology / mesh / determinism):
uv run pytest services/geometry/tests/test_goldens.py -v

# STEP round-trip fidelity gate (kernel-level):
uv run pytest services/geometry/tests/test_step_roundtrip.py -v

# export gates (endpoint-level STEP round-trip, STL faceting bound,
# STEP/STL byte-determinism, media types, validation envelope):
uv run pytest services/geometry/tests/test_export.py -v

# full geometry service suite (kernel unit tests + API + worker + gates):
uv run pytest services/geometry
```

`just e2e`'s geometry half should invoke the first two commands; the
justfile is platform territory, so wiring it is left to `platform-builder`
(filed as a gap below).

**Adding a golden** requires zero runner changes: create
`services/geometry/goldens/<name>/model.json` (a serialized
`TessellateRequest`) + `expected.json` (hand-derived values, per-model
`tolerance` + `tolerance_rationale`). Both discovery-inventory guard tests
fail loudly if discovery ever breaks. Expectations must be hand-derived or
cross-checked in a second tool — never recorded from harness output.

## Golden inventory

| Golden | Capability locked | Tolerance (mass props) | Topology (F/E/S) | Mesh (V/T) |
| --- | --- | --- | --- | --- |
| `box-10x20x30` | parametric box build, GProp mass properties, exact AABB, 0.1 mm-deflection tessellation to GLB | 1e-7 (CLAUDE.md kernel linear tolerance; measured deviation 0.0) | 6 / 12 / 1 | 24 / 12 |
| `cylinder-r10-h25` | FIRST CURVED golden: GProp integration over an analytic quadric, curved-face tessellation deflection, seam-edge topology, STEP re-approximation of curved surfaces | 1e-9 (curved-geometry ceiling, measured-then-set; observed worst 4.55e-13) | 3 / 3 / 1 | 506 / 500 |

Coverage audit vs. shipped modeling capabilities: `build_box`,
`build_cylinder`, `measure_shape`, `tessellate_glb`/GLB stats, STEP/STL
export — all covered by the inventory (export gates parametrize over it).
No shipped shape kind lacks a golden as of the 2026-07-10 cylinder entry.

---

## 2026-07-10 — First curved golden: `cylinder-r10-h25` (closes gap #1)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), pytest 9.1.1. Suite: 124 passed workspace-wide (~18.6 s); the new
golden flows through every parametrized gate with zero runner changes
(goldens ×4, kernel + endpoint STEP round-trip, STL bound, byte-determinism
×2 — 13 new parametrized test instances) plus 4 kernel unit tests and 5 API
validation tests for the widened shape union.

Shape: `Solid.make_cylinder(10, 25)` — base disc centred at the origin in
the XY plane, axis +Z. Request schema gained `CylinderParams` +
`shape: "box" | "cylinder"` (shape/params pairing enforced by a pydantic
model validator → 422 envelope on mismatch); contracts + ts-client
regenerated, `just gen-check` green.

### Gate 1 — golden mass properties: analytic vs GProp on curved faces

Hand derivation (full text in the golden's `expected.json`): volume
`pi*r^2*h = 2500*pi ≈ 7853.981633974483 mm³`; surface area
`2*pi*r*(r+h) = 700*pi ≈ 2199.114857512855 mm²` (lateral `500*pi` + two
caps `200*pi`); centroid `(0, 0, 12.5)`; AABB `[-10,-10,0]..[10,10,25]`.

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 7853.981633974483 mm³ | 7853.981633974483 | **0.0** | 1e-9 |
| surface area | 2199.114857512855 mm² | 2199.1148575128555 | **4.55e-13** | 1e-9 |
| centroid x/y/z | (0, 0, 12.5) mm | (1.4e-15, −3.3e-16, 12.5+1.8e-15) | ≤ 1.8e-15 | 1e-9 |
| AABB (6 values) | [−10,−10,0]..[10,10,25] | identical | **0.0** | 1e-9 |
| faces/edges/shells | 3 / 3 / 1 | 3 / 3 / 1 | — | exact |
| mesh vertices/triangles | 506 / 500 | 506 / 500 | — | exact |

**Curved-geometry tolerance — measured first, then set (1e-9).** Unlike the
planar box (GProp exact, deviation 0.0), curved faces go through OCCT's
Gauss-quadrature integration, which for analytic quadrics converges to
machine precision but not exact zero: observed worst case 4.55e-13 mm²
absolute on surface area (~2e-16 relative — ulp scale). The documented
ceiling 1e-9 is ~2000× the observed error (headroom for libm/platform
variation in the quadrature's transcendental evaluations across CI hosts)
while staying 100× TIGHTER than the standing planar 1e-7 bound — locking
GProp's curved-surface accuracy is what this golden is for. Recorded in the
golden's `tolerance_rationale`; loosening it is a reviewed decision, never a
fix.

**Topology finding:** OCCT's closed cylinder is 3 faces / **3 edges** / 1
shell — 2 cap circles plus the straight **seam edge** where the periodic
cylindrical surface's parametrization closes. (The naive guess of 2 edges is
wrong; the seam is a real `TopoDS_Edge`, verified against
`Solid.make_cylinder` output. Downstream consumers — e.g. future edge
picking/fillet UIs — must expect seam edges on periodic faces.)

**Mesh derivation (counts pinned exactly):** BRepMesh discretizes the
circular boundary into 126 segments at 0.1 mm / 0.1 rad. Lateral face:
126×2 = 252 triangles, 2 rows × 127 vertices (seam column duplicated in the
parametric unwrap) = 254. Each cap: a 126-gon triangulated with no interior
vertices → 126−2 = 124 triangles, 126 vertices. Totals 500 triangles / 506
vertices (per-face primitives, faceted normals — no cross-face sharing).
STL facet parity confirms 500.

**Harness proven to fail on wrong curved geometry:** perturbing the golden
to volume +0.001 and edges 2 produced exactly 2 failures with
evidence-bearing messages (`volume expected 7853.982633974483, got
7853.981633974483`; `topology expected {'edges': 2,...}, got
{'edges': 3,...}`), then was restored and the suite re-ran green.

### Gate 2 — STEP round-trip: first curved-surface observations

Kernel-level and endpoint-level (HTTP `POST /api/v1/export`) gates, both
against `ROUNDTRIP_TOL` 1e-7 + exact topology:

| Quantity | Original | Re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 7853.981633974483 mm³ | identical | **0.0** |
| surface area | 2199.1148575128555 mm² | 2199.1148575129587 | **1.03e-10** |
| centroid x/y/z | (≈0, ≈0, 12.5) | ≤1.3e-15 apart | ≤ 1.3e-15 |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 3 / 3 / 1 | 3 / 3 / 1 | preserved |

**Finding (observation, not a defect):** the first nonzero round-trip
deviation in the project — surface area moves by 1.03e-10 mm² (~5e-14
relative) across STEP re-encode of the trimmed cylindrical surface. STEP
stores the quadric analytically, so volume/AABB/topology survive exactly;
the area wobble is re-trimming/parameterization noise at double-precision
scale, ~1000× inside the 1e-7 round-trip bound. No action; recorded so a
future regression has a baseline. Artifact: 5,596-byte STEP AP214,
byte-deterministic (sha256 `290994467921c55f…`, in-process + across
interpreter restart, timestamp pinned as decided in gap #4).

### Gate 3 — STL export (curved geometry consumes real slack for the first time)

500 facets (parity with GLB triangles). Enclosed volume (divergence theorem
over re-parsed facets) 7850.727 mm³ vs B-rep 7853.982 mm³ → deviation
**3.255 mm³** (chordal facets inscribe the true surface, so the faceted
volume underestimates), well inside the deflection-derived ceiling 8301.5
mm³ (`surface_area × 0.1 × AABB diagonal 37.75` — the bound predicted at
export first light now carries a real curved data point). 25,084-byte
binary STL, byte-deterministic across restart (sha256 `c98fa24228d5ee6c…`).

### Gate 4 — determinism

In-process double rebuild AND fresh-interpreter rebuild: identical metadata,
byte-identical GLB (16,856 bytes, sha256 `e5c384443d7d0570…`). Same for both
export formats. No flake over the full suite run.

### Gate 5 — performance

Warm build+measure+tessellate for the cylinder: **4.3–5.1 ms** over 5 runs —
same class as the box (3.8–4.3 ms), far inside the 2 s tripwire.

| Date | Golden | Warm rebuild+tessellate | Budget |
| --- | --- | --- | --- |
| 2026-07-10 | box-10x20x30 | 3.8–4.3 ms | < 2 s (tripwire) |
| 2026-07-10 | cylinder-r10-h25 | 4.3–5.1 ms | < 2 s (tripwire) |

Gap #1 below is now marked closed. Remaining curved-geometry risk moves to
where it actually lives: fillet/extrude goldens (Phase 1 Next queue) and
B-spline/NURBS surfaces, which — unlike analytic quadrics — genuinely
re-approximate through STEP.

[kernel-architect]

---

## 2026-07-10 — Export endpoints: endpoint-level STEP round-trip + byte-deterministic STEP/STL (closes gaps #3, #4)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), pytest 9.1.1. Suite: 91 passed workspace-wide (~10.9 s); 15 new export
gate tests in `services/geometry/tests/test_export.py`, parametrized over the
golden inventory (future goldens get export coverage for free).

### Gate — endpoint-level STEP round-trip (gap #3 closed)

`POST /api/v1/export {format: "step"}` over HTTP → `import_step` →
re-measure with the same GProp pipeline, compared against the in-memory
original via the shared `assert_roundtrip_preserved` fixture (same 1e-7
`ROUNDTRIP_TOL` + exact topology as the kernel-level gate, now in
`tests/conftest.py` — single source):

| Quantity | Original | HTTP-exported → re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 6000.0 mm³ | 6000.0 | **0.0** |
| surface area | 2200.0 mm² | 2200.0 | **0.0** |
| centroid x/y/z | 5.0 / 10.0 / 15.0 | identical | **0.0** |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 6 / 12 / 1 | 6 / 12 / 1 | preserved |

Exported artifact: 15,348-byte STEP AP214 part 21, media type `model/step`,
`Content-Disposition: attachment; filename="box.step"`.

### Decision — STEP timestamp pinned for byte-determinism (gap #4 closed)

OCCT stamps every STEP file's `FILE_NAME` record with wall-clock creation
time — the ONE nondeterministic byte range in the output. **Decision:** the
kernel pins it via build123d's `export_step(timestamp=...)` to the sentinel
`geometry.kernel.export.STEP_EXPORT_TIMESTAMP` (2000-01-01T00:00:00). STEP
consumers treat the timestamp as provenance metadata, not geometry; a fixed
sentinel makes identical requests byte-identical (RESEARCH §9, updated this
commit). Evidence:

- Pinned `FILE_NAME` record:
  `FILE_NAME('Open CASCADE Shape Model','2000-01-01T00:00:00',...)` — the
  name field is the fixed writer default (export goes through `BytesIO`, so
  no filesystem path can leak in either).
- Repeated exports: identical sha256 `8124c8cd276400cd…` (15,348 bytes),
  in-process AND across a fresh-interpreter restart probe.
- `test_step_export_timestamp_is_pinned` additionally asserts today's date
  does NOT appear anywhere in the output.
- **Gate proven to fail on wrong bytes** (a gate that can't go red is
  worthless): temporarily removing the `timestamp=` pin made
  `test_step_export_timestamp_is_pinned` fail with the wall-clock date
  leaking into the file, then the pin was restored and the suite re-ran
  green.

### Gate — STL export (faceted round-trip + determinism)

`POST /api/v1/export {format: "stl"}` → binary STL (`model/stl`,
`filename="box.stl"`), 684 bytes = 84-byte header + 12 × 50-byte facets,
sha256 `199a683573665694…` identical across repeated runs and the
interpreter-restart probe (binary STL embeds no timestamps; fixed OCCT
header).

Quality defaults (documented in `py_kit.schemas.geometry` /
`geometry/kernel/export.py`): `linear_deflection` 0.1 mm +
`angular_deflection` 0.1 rad — the SAME values and the SAME
`BRepMesh_IncrementalMesh` call as the GLB tessellation path, so the
exported mesh matches what the viewport shows (facet-count parity asserted:
12 STL facets == 12 GLB triangles).

**STL volume tolerance — derived, not ad-hoc** (STL is faceted; the B-rep
1e-7 cannot apply). Derivation (`stl_volume_tolerance` in test_export.py):
OCCT meshes with *relative* linear deflection (build123d passes
`isRelative=True`), so facet deviation ≤ `linear_deflection × AABB diagonal`
model-wide; the enclosed-volume error is then ≤ `surface_area × that
deviation`. For `box-10x20x30`: 2200 × 0.1 × 37.4166 = **8231.7 mm³
ceiling**; measured enclosed volume (divergence theorem over the re-parsed
facets) = 6000.0 vs B-rep 6000.0 — **deviation 0.0** (planar faces facet
exactly; the bound is a ceiling for future curved goldens, and the
facet-count parity check keeps the gate sharp for planar ones).

### Performance

Warm endpoint wall-clock (TestClient, box golden): STEP export ~20 ms, STL
export ~7 ms — well inside the 2 s tripwire class; no budget rows needed yet.

### Coverage notes

- Validation errors return the py-kit 422 envelope (5 parametrized cases:
  unknown format, missing format, bad shape params, non-positive linear /
  angular deflection).
- Omitted STL quality params are byte-identical to explicit defaults.
- Gaps #3 and #4 below are now marked closed; endpoint gates run in the
  standard suite (`uv run pytest services/geometry`). The gateway proxy +
  web download UI (backlog item 1b) are NOT covered here — browser-level QA
  lands with them.

[kernel-architect]

---

## 2026-07-10 — Golden harness first light (harness + cube golden + STEP round-trip)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT via OCP),
pytest 9.1.1. Suite: 34 passed in ~8.9 s (geometry service total).

### Gate 1 — golden models (`tests/test_goldens.py`)

`box-10x20x30` rebuilt via `evaluate_tessellation` (the shared REST/worker
path), asserted against hand-derived analytic values:

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 6000.0 mm³ | 6000.0 | 0.0 | 1e-7 |
| surface area | 2200.0 mm² | 2200.0 | 0.0 | 1e-7 |
| centroid | (5, 10, 15) mm | (5.0, 10.0, 15.0) | 0.0 each | 1e-7 |
| AABB | [0,0,0]..[10,20,30] | identical | 0.0 each | 1e-7 |
| faces/edges/shells | 6 / 12 / 1 | 6 / 12 / 1 | — | exact |
| mesh vertices/triangles | 24 / 12 | 24 / 12 | — | exact |

Derivation lives in the golden's `expected.json` (`derivation` field).
Tolerance 1e-7 = the standing CLAUDE.md kernel linear tolerance; the box is
planar-exact in GProp so the real deviation is 0.0 — the bound is a ceiling,
not a fit.

**Harness proven to fail on wrong geometry** (a gate that can't go red is
worthless): perturbing the golden to volume 6000.001 and faces 7 produced
`2 failed` with evidence-bearing messages (`volume expected 6000.001, got
6000.0`; `topology expected {'faces': 7,...}, got {'faces': 6,...}`), then
was restored.

### Gate 2 — STEP round-trip (`tests/test_step_roundtrip.py`, kernel-level)

`build_shape` → `export_step` (15,348-byte AP214 part 21 file) →
`import_step` → re-measure with the same GProp pipeline:

| Quantity | Original | Re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 6000.0 mm³ | 6000.0 | **0.0** |
| surface area | 2200.0 mm² | 2200.0 | **0.0** |
| centroid x/y/z | 5.0 / 10.0 / 15.0 | identical | **0.0** |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 6 / 12 / 1 | 6 / 12 / 1 | preserved |

No degradation found — planar B-rep geometry survives STEP exactly at
build123d 0.11.1, so the 1e-7 assertion carries zero slack. No finding to
file. The test is parametrized over the golden inventory: future goldens
(especially curved ones, where STEP re-approximates surfaces) get this gate
for free — if a curved model genuinely degrades, that will be reported as a
finding, not absorbed into the tolerance.

### Gate 3 — determinism (canonical home: `tests/test_goldens.py`)

- In-process: two `evaluate_tessellation` runs → identical metadata,
  byte-identical GLB (3,244 bytes, sha256 `8bb68d16c603bc6d…`). ✅
- Across interpreter restart (worker-restart emulation, new coverage this
  entry): fresh `sys.executable` subprocess rebuild → same GLB sha256, same
  compact metadata JSON. ✅
- Dedupe: `test_kernel.py::test_tessellation_is_deterministic` (identical
  request, in-process only) was strictly subsumed and removed; the module
  docstring redirects here.

### Gate 4 — performance budgets

- Warm build+measure+tessellate for `box-10x20x30`: **3.8–4.3 ms** over 5
  runs (matches the 4–8 ms recorded at kernel first light — no regression).
  Tripwire ceiling 2 s in `test_kernel.py::
  test_build_and_tessellate_performance_budget` (order-of-magnitude alarm,
  not a tight budget).

| Date | Golden | Warm rebuild+tessellate | Budget |
| --- | --- | --- | --- |
| 2026-07-10 | box-10x20x30 | 3.8–4.3 ms | < 2 s (tripwire) |

### Gaps / coverage list for future passes

1. ~~**One golden, one shape type, planar-only.**~~ **Closed 2026-07-10** —
   first curved golden `cylinder-r10-h25` shipped (entry above): curved
   GProp at 1e-9 documented tolerance, seam-edge topology, curved STEP
   round-trip observations recorded. Extrude/fillet still require their own
   goldens in the same commit (geometry-gates skill).
2. **No queue-path coverage.** Gates run `evaluate_tessellation` directly;
   the arq worker leg is still sync-inline in the product (see BACKLOG) and
   unexercised by geometry gates. Revisit when redis/arq runtime lands.
3. ~~**STEP round-trip is kernel-level only.**~~ **Closed 2026-07-10** —
   endpoint-level round-trip gate shipped with `POST /api/v1/export`
   (`tests/test_export.py`; evidence in the entry above).
4. ~~**STEP byte-determinism not asserted.**~~ **Closed 2026-07-10** — STEP
   timestamp pinned kernel-side (`STEP_EXPORT_TIMESTAMP`); byte-determinism
   asserted for STEP and STL, in-process + across interpreter restart
   (entry above).
5. **GLB byte size not pinned in goldens** (deliberate: brittle across
   glTF-writer upgrades with no geometric meaning). It IS asserted
   internally consistent (`glb_bytes == len(glb)`) and byte-deterministic
   within a kernel version. A kernel/build123d upgrade that changes mesh
   counts will still fail exact-match — as it should.
6. **`just e2e` geometry half unwired** (justfile = platform territory).
   Commands are at the top of this file; platform-builder should wire them.
7. **Performance tracking is a single coarse tripwire.** Start per-golden
   budget rows in the table above as the inventory grows; >10% regression
   inside budget is still a filed defect.

Findings filed this pass: none red — all shipped capabilities have golden
coverage and all gates are green with zero measured deviation. Gaps above
are queued as coverage work, not defects.
