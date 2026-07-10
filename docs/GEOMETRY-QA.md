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

# STEP round-trip fidelity gate:
uv run pytest services/geometry/tests/test_step_roundtrip.py -v

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

Coverage audit vs. shipped modeling capabilities (commits d136b29/7b39a27):
`build_box`, `measure_shape`, `tessellate_glb`/GLB stats — **all covered by
golden #1**. No shipped feature type lacks a golden as of this entry.

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

1. **One golden, one shape type, planar-only.** Curved geometry (cylinder /
   sphere / fillet) exercises GProp integration, tessellation deflection,
   and STEP surface re-approximation in ways the box cannot. First curved
   golden should land with the next kernel capability (Phase 1 extrude/
   fillet each require one in the same commit — geometry-gates skill).
2. **No queue-path coverage.** Gates run `evaluate_tessellation` directly;
   the arq worker leg is still sync-inline in the product (see BACKLOG) and
   unexercised by geometry gates. Revisit when redis/arq runtime lands.
3. **STEP round-trip is kernel-level only.** No export endpoint exists yet
   (Phase 1 "STEP/STL export endpoints"); endpoint-level round-trip
   (HTTP-export → re-import) must be added when it ships.
4. **STEP byte-determinism not asserted** — STEP embeds a creation
   timestamp. `export_step` accepts `timestamp=` for pinning; decide when
   STEP export becomes a product feature (determinism gate currently covers
   GLB only, which is the artifact users receive today).
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
