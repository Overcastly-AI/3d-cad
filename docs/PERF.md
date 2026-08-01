# Loft — Performance at real part size

**Owner: `geometry-qa`.** Companion to `docs/GEOMETRY-QA.md` (correctness gates)
— this file answers the one question the golden suite structurally cannot:
**at what size does this tool stop feeling like a tool?**

Everything below is measured, in this repo, at the commit named in each run
heading. Nothing here is estimated, and no verdict is softened.

---

## 2026-07-31 — First real-part benchmark (founder item: "performance on a genuinely big part")

**Why this run exists.** Every golden and every e2e part in the repo is 3-8
features and under 100 faces. `tests/test_benchmarks.py` (the two-tier perf gate
shipped 2026-07-19) times *real operations* — but only on those toys. So the
shipped CI ceilings (1000 ms light / 2000 ms heavy) were calibrated against
parts ~100x smaller than the thing a working engineer opens on a Tuesday, and
nothing in the repo had ever measured a part at that size.

### Machine and method

| | |
| --- | --- |
| Machine | Linux container, **nproc = 4**, **MemTotal = 15.7 GiB** |
| Python | 3.12, single process, in-process kernel calls (no HTTP hop) |
| Kernel | OCCT via OCP + build123d, as shipped |
| Samples | **3 per point, median reported**, after one untimed warmup |
| Harness | `services/geometry/tests/test_scaling_benchmarks.py` (opt-in) |
| Parts | `services/geometry/tests/_big_part_builders.py` |

Reproduce:

```bash
LOFT_SCALING_BENCH=1 uv run pytest \
  services/geometry/tests/test_scaling_benchmarks.py -m benchmark -s
```

**This is NOT a CI gate and must not become one.** The sweep is double-gated:
`benchmark`-marked (excluded by the root `addopts = "... -m 'not benchmark'"`,
so `just test` never runs it) *and* `LOFT_SCALING_BENCH=1` (the
`LOFT_MINIO_SMOKE=1` idiom, so `just bench` stays a few-minute human-watched
run). It asserts nothing about time. A timing gate on a shared runner is a
false-red machine, and a false-red perf gate is worse than no perf gate.

What *is* always-on in the default suite, because it is a **correctness**
question and not a timing one, are four unmarked gates in the same file: a big
part rebuilds to a `BRepCheck`-valid solid, its STEP round-trips within the
shared `ROUNDTRIP_TOL` (1e-7) with exact topology, two rebuilds are
byte-identical, and the provenance budget arithmetic is pinned. They run at the
small end (29 features / 32 fins, ~6 s total).

**Two parts, two independent axes** — because tree cost and topology cost are
different machinery:

* **Axis A — feature count.** A 360 x 240 x 20 mm **shelled tray lid**: outer
  sketch, extrude, whole-body Z-edge fillet, shell (bottom face open, 6 mm
  wall), then a repeating 8-motif cycle of blind pockets + a picked-edge corner
  fillet, through holes, blind holes, cylindrical bosses, slots, revolved
  turrets on their own datums, a linear-**pattern**-cut vent, and a
  **mirror** with an explicit `features` scope. `housing_tree(n)` returns the
  first `n` features of ONE canonical sequence, so **every sweep point is a
  strict prefix of every larger one** and the points are directly comparable.
  Not 200 fillets — a real mix, and every single feature evaluates `ok` at
  every point.
* **Axis B — face count.** A **finned heat sink** at a *fixed six features*
  whose fin count drives topology: 4 faces per fin. Face count scales while
  tree length does not, which isolates tessellation / matcher / export cost
  from feature-tree cost. 500 fins is `MAX_PATTERN_COUNT`, the shipped work
  bound — the largest body this vocabulary can express in one pattern feature.

Run-to-run precision: the N=200 rebuild median was measured three separate
times across the session at **27 269 / 25 331 / 25 677 ms** — a 7.6 % spread on
a shared 4-core container. Read every number below as ±8 %. No conclusion in
this document turns on less than a 2x difference.

### Axis A — feature count (shelled tray lid, mixed vocabulary)

| part | feats | rebuild ms | tess ms | dominant feature | faces | edges | tris | GLB KiB | GLB gz KiB | STEP ms | STEP KiB | STL ms | STL KiB | overlay ms | prov | RSS MiB |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| N=10 | 10 | 263 | 21 | hole (45 %, 2x) | 28 | 69 | 2 208 | 77 | 16 | 9 | 88 | 11 | 108 | 335 | yes | 523 |
| N=25 | 25 | 628 | 47 | hole (37 %, 4x) | 60 | 141 | 4 308 | 152 | 28 | 23 | 178 | 23 | 210 | 735 | yes | 526 |
| N=50 | 50 | 2 098 | 157 | extrude (36 %, 12x) | 117 | 273 | 7 740 | 277 | 54 | 39 | 344 | 28 | 378 | 2 356 | yes | 533 |
| N=100 | 100 | 7 456 | 481 | hole (38 %, 18x) | 219 | 504 | 15 816 | 557 | 111 | 112 | 647 | 74 | 772 | 8 403 | yes | 550 |
| N=200 | 200 | **27 269** | 921 | hole (39 %, 38x) | 442 | 1 014 | 31 656 | 1 117 | 216 | 177 | 1 322 | 76 | 1 546 | **29 242** | **NULL** | 619 |

`overlay ms` is the **interactive face-pick round trip** (`POST /api/v1/overlay`:
recompute + per-face provenance + pick geometry) — what a user pays per click.
`prov` is whether per-face feature provenance was computed or silently degraded
to `null`. RSS is process resident set (points run ascending in one process;
the OCCT baseline is ~500 MiB).

**Derived — this is the finding:**

| band | rebuild ratio | for a 2x in N | **exponent** | marginal ms per added feature |
| --- | ---: | ---: | ---: | ---: |
| 10 → 25 | 2.39x | (2.5x) | 1.0 | 24 |
| 25 → 50 | 3.34x | 2x | **1.74** | 59 |
| 50 → 100 | 3.55x | 2x | **1.83** | 107 |
| 100 → 200 | 3.66x | 2x | **1.87** | 198 |

**Rebuild time grows as N^1.85 — effectively quadratic in feature count.** The
mechanism is unambiguous and visible in the table: face count grows *linearly*
in N (28 → 442, ~2.2 faces per feature), and every per-feature operation is a
**whole-body** pass, so per-feature cost grows linearly too, and the product is
N². The marginal cost of the 200th feature is **198 ms**, 8x the cost of the
25th.

### Axis B — face count (finned heat sink, 6 features throughout)

| part | feats | rebuild ms | tess ms | dominant feature | faces | edges | tris | GLB KiB | GLB gz KiB | STEP ms | STEP KiB | STL ms | STL KiB | overlay ms | prov | RSS MiB |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 8 fins | 6 | 106 | 8 | pattern (80 %) | 38 | 108 | 140 | 20 | 2 | 14 | 123 | 7 | 7 | 135 | yes | 618 |
| 32 fins | 6 | 354 | 29 | pattern (93 %) | 134 | 396 | 524 | 70 | 7 | 51 | 454 | 30 | 26 | 468 | yes | 618 |
| 64 fins | 6 | 768 | 73 | pattern (97 %) | 262 | 780 | 1 036 | 138 | 14 | 126 | 915 | 46 | 51 | 923 | yes | 627 |
| 128 fins | 6 | 1 589 | 90 | pattern (99 %) | 518 | 1 548 | 2 060 | 273 | 27 | 273 | 1 837 | 78 | 101 | 2 138 | yes | 660 |
| 256 fins | 6 | 3 952 | 241 | pattern (99 %) | 1 030 | 3 084 | 4 108 | 547 | 50 | 715 | 3 685 | 190 | 201 | 4 801 | yes | 714 |
| 500 fins | 6 | 9 827 | 519 | pattern (100 %) | **2 006** | 6 012 | 8 012 | 1 064 | 90 | **1 689** | **7 354** | 414 | 391 | 11 693 | yes | 829 |

Face-count scaling is **much healthier than feature-count scaling**: rebuild
grows as roughly `fins^1.2`, tessellation and the face matcher are near-linear,
and 2 006 faces rebuild in under 10 s from six features. The one clearly
superlinear column is STEP export (below).

| quantity | 256 → 500 fins (1.95x faces) | exponent |
| --- | ---: | ---: |
| rebuild | 2.49x | 1.36 |
| tessellation | 2.15x | 1.15 |
| STEP export | **2.36x** | **1.28** |
| STL export | 2.18x | 1.17 |
| overlay − rebuild (matcher) | 2.20x | 1.18 |

### Per-feature-type cost, N=200 tray (one instrumented rebuild)

Measured by wrapping `geometry.features.evaluate.FEATURE_HANDLERS`.

| feature type | calls | total ms | ms/call | share |
| --- | ---: | ---: | ---: | ---: |
| hole | 38 | 10 404 | 273.8 | 40.0 % |
| extrude | 47 | 8 436 | 179.5 | 32.4 % |
| fillet | 11 | 2 081 | 189.2 | 8.0 % |
| mirror | 9 | 1 922 | 213.6 | 7.4 % |
| pattern | 9 | 1 837 | 204.2 | 7.1 % |
| revolve | 9 | 1 253 | 139.3 | 4.8 % |
| sketch | 57 | 64 | 1.1 | 0.2 % |
| shell | 1 | 26 | 26.4 | 0.1 % |
| datum | 19 | 5 | 0.3 | 0.0 % |

No single verb is pathological — **every body-affecting verb costs 140-275 ms
on a 442-face body and ~25 ms on a 28-face one.** The cost is not in the verb,
it is in the size of the body each verb touches. Sketch solving (planegcs) is
free at this scale: 57 sketches, 64 ms total.

### Where the time actually goes (A/B counterfactual, same measurement protocol)

Two whole-body guards run **once per body-affecting feature**, so both are
O(N x faces) = O(N²):

| variant | N=100 rebuild ms | N=200 rebuild ms | cost |
| --- | ---: | ---: | ---: |
| as shipped | 6 354 | 25 331 | — |
| `body_is_valid` stubbed to `True` | 4 787 | 19 680 | **22-25 % of the rebuild** |
| `clean_shape`'s two GProp integrations stubbed | — | 24 316 (of 25 677) | **5.3 %** |
| both off | 5 083 | 19 114 | 25 % |

* **`EvaluationState._admit`** (`services/geometry/src/geometry/features/evaluate.py:529`)
  runs `body_is_valid` — a full `BRepCheck_Analyzer` over the **entire body** —
  every time a feature installs a body. 125 whole-body analyses in one N=200
  rebuild, ~53 ms each: **5.65 s of the 25.3 s**.
* **`geometry.kernel.healing.clean_shape`** (`healing.py:203-210`) takes a
  `BRepBuilderAPI_Copy` of the whole body and integrates its volume **twice**
  (before/after `clean()`) per boolean: 343 `VolumeProperties_s` calls,
  **1.36 s**. Its docstring quotes "~0.6 ms ... plus two GProp integrations
  (~1.3 ms)" — measured on the CM-6 toy. At 442 faces one integration is 5.8 ms,
  so the documented cost is size-blind by ~9x.

**Both guards exist for good reasons and neither should be deleted** — CM-6 is
exactly the "silently shipped an invalid body" P0 this project promises not to
repeat. The fix is to make them *incremental* (check what the boolean actually
`Modified`/`Generated`, plus one whole-body check at publish), not to remove
them. And note the honest arithmetic: with **both** guards off, N=200 still
takes 19.1 s. The guards are a 25 % tax on top of a structurally quadratic
rebuild; the quadratic is the real problem.

### The multiplier nobody has priced: there is no rebuild cache

`evaluate_tree` re-runs the **entire tree from feature 0** on every call. The
only cache in the service is `geometry.step_cache` (STEP *imports*). So on a
200-feature part:

* editing feature #3 costs 27 s — unavoidable, the prefix really did change;
* editing feature #199 **also costs 27 s**, when only one feature's worth of
  work is new;
* moving the timeline travel stop costs 27 s;
* **one face pick costs 29 s** (`/overlay` = full rebuild + history snapshots);
* `/measure`, `/tessellate`, `/export` and drawings compose each pay their own
  full rebuild.

`/overlay` minus `/evaluate` is only 72 / 107 / 258 / 947 / 1 973 ms across the
Axis-A sweep — **the hash-indexed face matcher (audit H4) is fine and stayed
fine**; at 2 006 faces it adds 1 866 ms, ~0.93 ms/face, linear. The interactive
route is slow because it rebuilds the world, not because it matches faces.

### Provenance goes dark at ~110 features, and the docstring says it does not

`attribute_faces` skips attribution entirely (returns all-`null`) when
`len(final faces) + sum(len(snapshot faces))` exceeds `MAX_PROVENANCE_FACES`
(8 000). That budget sums over **every** snapshot, so it is spent by
`features x faces` — quadratic in part size, not linear in face count.

| features | provenance budget | of 8 000 | overlay faces | attributed | overlay ms |
| ---: | ---: | ---: | ---: | --- | ---: |
| 10 | 166 | 2 % | 28 | yes | 217 |
| 25 | 562 | 7 % | 60 | yes | 655 |
| 50 | 2 047 | 26 % | 117 | yes | 2 142 |
| 75 | 4 416 | 55 % | 168 | yes | 4 601 |
| 100 | 7 242 | **91 %** | 219 | yes | 7 602 |
| 150 | 15 971 | **200 %** | 331 | **NULL** | 15 223 |
| 200 | 28 552 | **357 %** | 442 | **NULL** | 29 096 |

**Crossing point: ~105-110 features** (219-240 faces). Past it, clicking a
feature in the tree stops highlighting that feature's faces and silently falls
back to whole-body selection.

`py_kit/schemas/overlay.py:55-57` says: *"An authored part is nowhere near the
bound (tens of body-affecting features x tens-to-low-hundreds of faces each), so
a working engineer never feels it."* By its own arithmetic that product is
50 x 150 = 7 500 — i.e. the stated typical part is at **94 % of the bound.** The
measured tray hits 91 % at 100 features. The claim is wrong, and it is wrong in
the direction that matters.

### Payload: a 2 000-face body ships a 1 MiB uncompressed mesh

Fitting `GLB bytes = a x triangles + b x faces` to the two largest points
(N=200 tray: 31 656 tris / 442 faces / 1 143 808 B; 500 fins: 8 012 tris /
2 006 faces / 1 089 536 B) gives:

* **a ≈ 30 bytes per triangle** — correct and unremarkable (position + normal +
  index).
* **b ≈ 425 bytes per B-rep FACE** of pure glTF JSON overhead.

`tessellate_glb` emits **one glTF primitive per B-rep face** (by design — the
viewport relies on primitive ordinal == face ordinal for picking). At 2 006
faces that is ~850 KiB of JSON before a single vertex, and **2 006 draw calls**
in the viewport unless the frontend merges them.

And nothing compresses it: there is **no `GZipMiddleware` anywhere** in
`services/geometry`, `services/gateway` or `py-kit`, and the mesh route returns
a raw `Response(content=glb, media_type=GLB_MEDIA_TYPE)`. Measured gzip level 6:

| part | GLB | gzipped | ratio |
| --- | ---: | ---: | ---: |
| N=200 tray | 1 117 KiB | 216 KiB | **5.2x** |
| 500-fin sink | 1 064 KiB | 90 KiB | **11.8x** |

A one-line middleware is a 5-12x payload cut on the hottest binary route in the
product.

> **FIXED — see "PERF-4 landed" below.** Compression now lives in py-kit's
> `create_app`, so every service gets it once. The ratios above held on the
> real route (5.2x / 11.9x); the surprises were that Starlette's default
> `compresslevel=9` is *worse than 6* on these payloads, and that the gateway
> had to stop asking geometry for gzip.

### Correctness under size — this part is clean

Measured at the largest point of each axis (not a CI gate; these numbers are the
evidence):

| | N=200 tray | 500-fin sink |
| --- | --- | --- |
| features not `ok` | **0** | **0** |
| `BRepCheck_Analyzer` | **valid** | **valid** |
| volume | 614 643.782 627 637 3 mm³ | 1 775 999.999 999 913 mm³ |
| STEP re-import volume | 614 643.782 627 640 3 | 1 775 999.999 999 913 |
| Δvolume | **3.03e-09 mm³** (4.9e-15 relative) | **exactly 0.0** |
| Δsurface area | 3.49e-10 mm² | exactly 0.0 |
| topology out → back | 442 F / 1 014 E / 1 shell → identical | 2 006 F / 6 012 E / 1 shell → identical |
| GLB byte-identical across rebuilds | **yes** | **yes** |
| mass properties identical across rebuilds | **yes** | **yes** |

Both are inside the shared `ROUNDTRIP_TOL` (1e-7). **No tolerance was widened
for this run.** Loft is not producing fast wrong answers at size — it is
producing correct answers slowly. That is the right failure mode to have, and it
means every fix below is a pure performance fix with no correctness risk to
trade off.

One asymmetry worth flagging, though: exporting the 2 006-face part to STEP took
**1.73 s** and reading it back took **19.07 s** (raw `import_step`) / **18.44 s**
through the real bounded-worker service path `import_step_solid` — see fix #4.

---

## VERDICT — where the wall is

Blunt, per size, for the tray (a mixed real-part vocabulary):

| part size | rebuild | face pick | verdict |
| --- | ---: | ---: | --- |
| **10 features** | 0.26 s | 0.34 s | **Fine.** Feels instant. This is the size every golden and demo is. |
| **25 features** | 0.63 s | 0.74 s | **Fine.** Under the RESEARCH §9 2 s ceiling with room. A modeller does not notice. |
| **50 features** | 2.1 s | 2.4 s | **A modeller waits.** Already *at* the 2 s rebuild ceiling. Every parameter tweak is a two-second pause; every click is a two-second pause. Tolerable, clearly not good. |
| **100 features** | 7.5 s | 8.4 s | **Painful and no longer a tool.** Seven seconds to change a dimension. Feature-localized selection highlighting is at 91 % of its budget and about to vanish. This is where a working engineer closes the tab. |
| **200 features** | **27 s** | **29 s** | **Unusable.** Half a minute per edit, per pick, per measure. Provenance is off. Nobody models like this. |

For the heat sink (few features, many faces):

| part size | rebuild | verdict |
| --- | ---: | --- |
| **≤ 262 faces** (64 fins) | 0.77 s | **Fine.** |
| **518 faces** | 1.6 s | **Fine.** |
| **1 030 faces** | 4.0 s | **A modeller waits**, but this is a 6-feature part — the wait is one pattern feature. |
| **2 006 faces** (`MAX_PATTERN_COUNT`) | 9.8 s | **The ceiling is the real limit here, not the clock.** You cannot express more than 500 instances in one pattern feature at all. |

**The headline: Loft's wall is at roughly 50 features and it is a hard wall by
100.** Face count is *not* the wall — 2 000 faces is comfortable. Feature count
is, and specifically the fact that every operation, every click and every export
re-runs the whole tree over the whole body.

Against the daily-driver question — *would a working engineer model a real part
in this today?* — a real machined bracket is 40-80 features and a real housing
is 150-400. **Loft handles the bracket and cannot hold the housing.**

---

## RANKED — what to fix first

Ranked by (measured cost removed) x (breadth of routes affected) / (risk).

### 1. Cache the evaluated prefix — `evaluate_tree` has no cache at all (P1, L)

**Code path:** `services/geometry/src/geometry/features/evaluate.py:3010`
`evaluate_tree` + every caller (`api.py` evaluate / overlay / measure /
tessellate / export, drawings compose, assembly per-instance).

Every route rebuilds from feature 0. **This is the single biggest multiplier in
the product** because it turns an O(N²) rebuild into an O(N²) *per interaction*.
Editing the last feature of a 200-feature tree costs the same 27 s as editing
the first. A content-addressed body cache keyed on the hash of the feature
prefix (the tree is already required to be deterministic — RESEARCH §9 — so a
prefix hash is a sound key) collapses the common cases: appending a feature
becomes one feature's work, and a face pick after an evaluate becomes ~0 s.

Expected effect: append/pick on a 200-feature part **27 s → ~0.2 s**. Nothing
else on this list comes close.

### 2. Make the CM-6 validity gate incremental (P1, M)

**Code path:** `evaluate.py:529` `EvaluationState._admit` → `healing.py:214`
`body_is_valid`.

**Measured: 5.65 s of a 25.3 s N=200 rebuild (22 %), 125 whole-body
`BRepCheck_Analyzer` passes at ~53 ms each.** O(N x faces).

Do **not** delete it — it is the CM-6/QA-1 guard. Make it proportional to the
change: `BRepCheck_Analyzer` accepts any `TopoDS_Shape`, so check the faces the
boolean reports as `Modified`/`Generated` plus their neighbours, and keep ONE
whole-body check at publish time (`evaluate.py:3117` already does exactly that).
That preserves "no invalid body reaches the viewport, mass properties or STEP"
while making the per-feature cost O(new faces).

Expected effect: ~22 % off every rebuild, growing with N.

### 3. Compress the mesh route; stop paying 425 bytes of JSON per face (P2, S+M)

**Code path:** `services/geometry/src/geometry/api.py:529`
(`Response(content=glb, media_type=GLB_MEDIA_TYPE)`) and
`geometry/kernel/tessellate.py:37`.

Two parts:

* **(S) ~~There is no gzip middleware anywhere in the stack.~~ LANDED** —
  measured at **5.2x on the tray and 11.9x on the heat sink** on the real
  route. Full numbers in "PERF-4 landed" below.
* **(M) One glTF primitive per B-rep face costs ~425 bytes of JSON per face and
  one draw call per face** (2 006 draw calls on the heat sink). The per-face
  split is *required* for picking (primitive ordinal == face ordinal), so the
  fix is not to merge blindly — it is to carry the face id in a vertex attribute
  or a compact side-table and emit one primitive per *material*, letting the
  viewport pick by attribute. Frontend-coupled, hence P2.

### 4. STEP import of Loft's own large export is at 95 % of its DoS budget (P1, M)

**Code path:** `services/geometry/src/geometry/kernel/imports.py:100`
`DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S = 20.0`.

Measured **through the real bounded-worker path** (`import_step_solid`, i.e. the
subprocess with `RLIMIT_CPU` that the evaluate handler uses — not just raw
`import_step`), on STEP files **Loft itself exported**:

| part | STEP size | export | **import** | exponent |
| --- | ---: | ---: | ---: | ---: |
| 1 030-face sink | 3.60 MiB | 0.72 s | **3.66 s** | — |
| 2 006-face sink | 7.18 MiB | 1.73 s | **18.44 s** | **2.42** |

Import scales as `faces^2.4` and 18.44 s sits at **92 % of the 20 s CPU
ceiling**. Extrapolating that exponent, a part only **~4 % larger** (≈2 080
faces) trips it.

The docstring justifying the ceiling says *"a legit parse consumes ~1 s of CPU —
this 20 s ceiling is ~20x that"*; that was calibrated on the toy goldens (10-23
ms round trips). The real headroom on a part Loft itself can produce is
**1.08x**.

The consequence is not a slow import, it is a **wrong refusal**: a real customer
STEP a little larger than one Loft can already export comes back as
`import_parse_timeout` — "we think your file is hostile." The bound is right in
*kind* (CPU-time, not wall-clock — that part was well designed); its *value* was
fitted to toys. Two things are needed: re-derive the ceiling against a real-part
corpus, and root-cause the `faces^2.4` import curve (a 10.7x export/import
asymmetry at 2 006 faces is not normal for a reader).

### 5. Fix the `MAX_PROVENANCE_FACES` claim and the budget's shape (P2, M)

**Code path:** `packages/py-kit/src/py_kit/schemas/overlay.py:55-65`,
`services/geometry/src/geometry/kernel/provenance.py:180-183`.

The budget sums faces over **every** snapshot, so it is `O(features x faces)`
and is crossed at **~110 features** (measured: 91 % at N=100, 200 % at N=150) —
not at some exotic imported body. The docstring's "nowhere near the bound" is
false by its own arithmetic (50 x 150 = 7 500 of 8 000).

Two independent things to do: (a) correct the docstring, today, because a wrong
comment is how the next person mis-sizes this; (b) stop paying for snapshots at
all — attribution only needs each snapshot's *fingerprints*, not a retained
B-rep, so fingerprint each snapshot as it is produced and keep `list[fingerprint]`
instead of `list[BodyShape]`. That also removes the memory the `record_history`
path retains.

### 6. Raise or tier `MAX_PATTERN_COUNT` (P3, S)

**Code path:** `packages/py-kit/src/py_kit/schemas/features.py:88`
(`MAX_PATTERN_COUNT = 500`).

At 500 instances the pattern is a 9.8 s sequential fuse loop and produces
2 006 faces — the bound is binding *before* anything breaks, and a 500-hole
perforated panel is an ordinary part. Not urgent (nothing is wrong, and the
bound is doing its DoS job), but it is a real ceiling on expressible geometry
and should be revisited once the fuse loop is not sequential.

### Not on the list, and why

* **Tessellation is not a bottleneck** — 921 ms of a 27 s rebuild at N=200
  (3.4 %), 519 ms at 2 006 faces. Leave it alone.
* **The face matcher is not a bottleneck** — 0.93 ms/face, linear. The audit-H4
  hash index did its job and is still doing it. `/overlay` is slow because of
  the rebuild underneath it, not the matcher.
* **Memory is not a wall** — 619 MiB RSS at N=200, 829 MiB at 2 006 faces, over
  an ~500 MiB OCCT baseline.
* **The sketch solver is not a bottleneck** — 57 sketches, 64 ms total, 0.2 %.
* **STL export is fine** — exactly 50 bytes/triangle, 76 ms for 31 656
  triangles.

---

## 2026-07-31 — PERF-4 landed: response compression (the RANKED-3 "(S)" half)

Fix for "Payload: a 2 000-face body ships a 1 MiB uncompressed mesh" above.
Compression is wired **once**, in `packages/py-kit/src/py_kit/app.py`
(`create_app`), so all three services inherit it — no per-service registration.

### Method — this run is over HTTP, unlike the run above

The benchmark above is in-process (no HTTP hop). These numbers are the **real
route**: three services booted natively (geometry `:8102`, documents `:8101`,
gateway `:8100`), the two PERF-4 parts pre-seeded into the mesh store, and
`GET /api/v1/meshes/{id}` fetched over loopback with a warm connection —
**15 samples, median, 3 warmups dropped**. "Added ms" is gzip minus identity
wall time on the same route, so the *saved* transfer time is already netted out
of it (i.e. it understates raw compression CPU slightly, which is the honest
direction). Same machine as the run above (nproc = 4).

### Bytes and time — at geometry (`GET /api/v1/meshes/{id}`)

| part | raw B | gzip B | ratio | identity ms | gzip ms | added ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N=200 tray | 1 143 600 | 220 873 | **5.2x** | 2.65 | 23.27 | **+20.62** |
| 500-fin sink | 1 089 348 | 91 837 | **11.9x** | 2.66 | 15.11 | **+12.46** |
| small box mesh | 3 408 | 696 | 4.9x | 1.64 | 1.82 | +0.18 |

### Bytes and time — end-to-end through the gateway (what the browser sees)

| part | raw B | gzip B | ratio | identity ms | gzip ms | added ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N=200 tray | 1 143 600 | 220 873 | **5.2x** | 9.60 | 31.44 | +21.84 |
| 500-fin sink | 1 089 348 | 91 837 | **11.9x** | 11.11 | 20.39 | +9.28 |
| small box mesh | 3 408 | 696 | 4.9x | 5.05 | 6.36 | +1.31 |

### Which hop compresses: the GATEWAY, and geometry must not

The browser talks only to the gateway, and the gateway **buffers** every
upstream body (`Response(content=upstream.content, ...)`) rather than streaming
it. httpx advertises `gzip, deflate` by default, so the naive "middleware
everywhere" config made each mesh fetch pay **compress at geometry → inflate at
the gateway → re-compress for the browser**. Measured cost of that internal
round trip on the N=200 tray: 20.6 ms to compress upstream plus 3.6 ms to
inflate, to save **2.6 ms** of loopback transfer — a ~24 ms net loss on
geometry CPU, which is the scarcest resource in the stack (rebuild is CPU-bound;
see the run above).

So `create_upstream_client` now sends `accept-encoding: identity`. Effect on the
end-to-end gateway fetch, same harness:

| part | gzip-to-browser, gzip upstream | gzip-to-browser, **identity** upstream | saved |
| --- | ---: | ---: | ---: |
| N=200 tray | 57.82 ms | **31.44 ms** | **-26.4 ms (-46 %)** |
| 500-fin sink | 33.90 ms | **20.39 ms** | -13.5 ms (-40 %) |

This is the right answer for a k8s split too: 1.1 MiB over an intra-cluster
1 Gbps link is ~9 ms, still cheaper than the ~24 ms of CPU to avoid it.

### `compresslevel = 6`, not Starlette's default 9

Level 9 is **strictly dominated** on these payloads — it produces *more* bytes
than level 6 (its larger match window is a pessimisation on interleaved float
streams) while costing 4-9x the CPU:

| part | L1 | L4 | **L6** | L9 |
| --- | ---: | ---: | ---: | ---: |
| tray bytes | 235 617 | 223 854 | **220 873** | 221 553 |
| tray compress ms | 7.3 | 10.2 | **17.4** | 73.4 |
| sink bytes | 114 649 | 98 502 | **91 837** | 92 180 |
| sink compress ms | 4.3 | 5.4 | **10.0** | 89.5 |

L1 is a defensible alternative (most of the ratio for half the CPU); L6 was
chosen because it is where the ratio actually plateaus and it keeps the 11.9x on
the sink, where L1 gets only 9.5x.

### `minimum_size = 1500`, not Starlette's default 500

One Ethernet MTU. Below ~1 500 B the body rides in a single TCP segment either
way, so compression cannot save a round trip — it only spends CPU on both ends
and adds a `Vary: Accept-Encoding` that fragments caches. Measured on every
small route the gateway actually serves:

| route | raw B | gzip B | packets raw → gzip | served |
| --- | ---: | ---: | --- | --- |
| `/healthz` | 15 | 35 (**bigger**) | 1 → 1 | identity |
| `/readyz` | 58 | 65 (**bigger**) | 1 → 1 | identity |
| `/api/v1/auth/me` | 125 | 128 (**bigger**) | 1 → 1 | identity |
| `/api/v1/parts` | 405 | 254 | 1 → 1 | identity |
| `/api/v1/materials` | 469 | 218 | 1 → 1 | identity |
| `/openapi.json` | 396 963 | 94 727 | 265 → 64 | **gzip** |

Three of these get *larger* under gzip (framing overhead), and none of the rest
saves a packet. Note `/openapi.json` at **4.2x** — a free win for the
`ts-client` fetch and the docs UI.

### What a `Content-Encoding` could have broken — checked, not assumed

* **`metadata.mesh.glb_bytes == len(response.content)`**
  (`services/geometry/tests/test_api.py`) and the golden-suite twins — safe:
  httpx inflates transparently, so `.content` is the original bytes.
* **`parseAs: "arrayBuffer"`** in `apps/web/src/api/{mesh,tessellate}.ts` and the
  e2e `byteLength` assertions — safe, `fetch` inflates transparently.
* **`Content-Length` guards** (`gateway/step_import.py`) — unaffected: they
  bound *request* bodies; gzip only touches responses.
* **Contract generation** — unaffected: `scripts/gen-contracts.py` calls
  `factory().openapi()` in-process, never over HTTP.
* **Streaming/SSE** — none exists in the codebase (no `StreamingResponse`, no
  websocket routes yet), so the chunked-fallback hazard does not apply today.
  When SSE lands it will need an exemption.
* **`Content-Length` on compressed responses is preserved**, because gzip is
  registered *inside* the request-id `BaseHTTPMiddleware`. Registered outside it
  the middleware only ever sees a stream and falls back to chunked, dropping the
  header the browser uses for download progress on a multi-megabyte mesh. Both
  orders were measured; `test_compressed_response_keeps_content_length_and_request_id`
  pins the working one.

### Not done here (still open, deliberately)

The **~425 bytes of glTF JSON per B-rep face** (RANKED-3's "(M)" half) is
untouched: it needs a face-id vertex attribute and a viewport change. Note
compression blunts it — the sink's 850 KiB of per-face JSON is highly
repetitive, which is exactly why it hits 11.9x — but the *draw calls* (2 006 on
the sink) are unaffected by gzip.

---

## Budget log

Wall-clock ceilings to track over time. A >10 % regression against the
"measured" column is a filed defect even though nothing here is CI-enforced.

| operation | part | measured 2026-07-31 | note |
| --- | --- | ---: | --- |
| **append a feature** | tray N=200 | **1 019 ms** | warm (PERF-1, 2026-07-31c); 26x |
| **append a feature** | tray N=100 | **430 ms** | warm; 16x |
| **repeat evaluate / measure / export** | tray N=200 | **162 ms** | warm; 164x |
| **repeat evaluate / measure / export** | tray N=100 | **63 ms** | warm; 109x |
| rebuild | tray N=25 | 628 ms | under the RESEARCH §9 2 s ceiling |
| rebuild | tray N=50 | 2 098 ms | **at** the 2 s ceiling |
| rebuild | tray N=100 | 7 456 ms | 3.7x over |
| rebuild | tray N=200 | 27 269 ms | 13.6x over |
| rebuild | 500-fin sink | 9 827 ms | 6 features, 2 006 faces |
| overlay (face pick) | tray N=100 | 8 403 ms | |
| tessellation | tray N=200 | 921 ms | 31 656 triangles |
| tessellation | 500-fin sink | 519 ms | 2 006 faces |
| STEP export | 500-fin sink | 1 689 ms / 7 354 KiB | |
| STEP import (service path) | 256-fin sink (1 030 F) | 3 660 ms | `import_step_solid` |
| STEP import (service path) | 500-fin sink (2 006 F) | 18 440 ms | was **92 % of the 20 s CPU ceiling**; **PERF-3 fixed → 3 819 ms / 3.46 CPU s** |
| STEP import (service path) | 256-fin sink, post-PERF-3 | 2 217 ms | 1.92 CPU s |
| STEP import (service path) | two 500-fin sinks (14.6 MiB) | 5 726 ms | 5.16 CPU s — near the 16 MiB upload cap |
| STL export | tray N=200 | 76 ms / 1 546 KiB | |
| mesh fetch (gateway, gzip) | tray N=200 | 31 ms / 216 KiB | was 1 117 KiB raw; PERF-4 |
| mesh fetch (gateway, gzip) | 500-fin sink | 20 ms / 90 KiB | was 1 064 KiB raw; PERF-4 |

---

## 2026-07-31b — PERF-3 landed: the STEP import curve was one OCCT repair pass

Fix for RANKED-4 ("STEP import of Loft's own large export is at 95 % of its DoS
budget"). The headline of that finding — *import scales as `faces^2.4`* — turned
out to be **the wrong model of the wrong cost**, and the ceiling question
largely dissolved once the real cost was named.

### Root cause, profiled and named

`TransferRoots` is the entire cost (`ReadFile` is near-linear and 5 % of it):

| part | faces | `ReadFile` | `TransferRoots` | BREP write |
| --- | ---: | ---: | ---: | ---: |
| 64-fin sink | 262 | 0.07 s | 0.13 s | 0.006 s |
| 128-fin sink | 518 | 0.16 s | 0.42 s | 0.014 s |
| 256-fin sink | 1 030 | 0.40 s | 2.04 s | 0.027 s |
| 500-fin sink | 2 006 | 1.05 s | **17.47 s** | 0.053 s |

Sampling the native stack of a live 18 s import with `gdb` (8 samples, 1 s
apart) returned the **same stack 8 times out of 8**:

```
NCollection_BaseSequence::Find
ShapeExtend_WireData::Edge
ShapeFix_IntersectionTool::FixSelfIntersectWire
ShapeFix_Wire::FixSelfIntersection
ShapeFix_Wire::Perform  →  ShapeFix_Face  →  ShapeFix_Shell  →  ShapeFix_Solid
ShapeFix_Shape::Perform
ShapeProcess::Perform  →  XSAlgo_ShapeProcessor::ProcessShape
STEPControl_ActorRead::TransferEntity
```

OCCT's STEP transfer is not just a read: after `StepToTopoDS` builds the
topology, `STEPControl_ActorRead` runs a full `ShapeFix_Shape` over the result.
One operation in that sequence — `ShapeFix_Wire::FixSelfIntersection` — tests a
wire's edges **pairwise** and reaches each edge through
`ShapeExtend_WireData::Edge(i)`, a *positional* index into an
`NCollection_Sequence`. Its cost is therefore super-quadratic in **edges per
wire**.

**It was never a face-count law.** The benchmark heat sink's two comb faces each
carry ONE wire of `4 × fins + 4` edges, so its worst wire grew *with* the part
and the import curve inherited that growth (the fitted exponent even rises with
size: 2.27 from 518→1 030 faces, **3.22** from 1 030→2 006 — a pure `faces^2.4`
model cannot do that). Measured wire distribution:

| part | faces | max wires/face | **max edges/wire** |
| --- | ---: | ---: | ---: |
| tray N=200 | 442 | 1 | 8 |
| 400-hole perforated plate | 406 | 401 | 4 |
| 500-fin heat sink | 2 006 | 1 | **2 004** |

Ruled out along the way, each in a fresh process on the 2 006-face file (none
moved the number by more than noise): `read.step.resource.name`,
`read.surfacecurve.mode` (2 and 3), `read.precision.mode`,
`read.maxprecision.mode`, `read.stdsameparameter.mode`. OCCT ≥ 7.8 no longer
reads shape-processing settings from resource files at all — the only live knob
is the `SetShapeFixParameters` API.

### The fix

`geometry/kernel/_step_parse_worker.py` binds one shape-processing parameter,
`FixShape.FixSelfIntersectionMode = 0`, on the reader **after `ReadFile`** (the
map is forwarded to the transfer *actor*, which does not exist until `ReadFile`
has initialised the work session — calling it earlier is silently a no-op:
measured 2.07 s vs 0.53 s on the same file). The assembly XCAF worker gets the
same bound from the same helper.

The transferred shape is **byte-identical**: same BREP sha256, same volume, same
face and edge counts, at every corpus size. That is expected — the operation
repairs *malformed* wires, so on well-formed input it is pure cost — and it is
now a gate (`test_step_import_scaling.py`), not a claim. On malformed input a
self-intersecting wire is imported as authored instead of silently repaired,
which is the contract `kernel/imports.py` already documents; the downstream
guard is unchanged and real (`body_is_valid` admits every body, so a broken
import is a clean per-feature error, never a silently wrong body). It also
*tightens* the DoS posture: a hostile file previously needed just one long wire
to burn the whole CPU budget inside OCCT's repair pass.

### Before / after, through the real bounded worker

`import_step_solid` — the subprocess with `RLIMIT_CPU` that the evaluate handler
uses. "child CPU" is `RUSAGE_CHILDREN` around the call, i.e. **exactly what the
ceiling bounds**; wall-clock is reported alongside because that is what a user
waits.

| part | faces | worst wire | STEP MiB | CPU before | CPU after | wall before | wall after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tray N=100 | 219 | 8 | 0.63 | 1.12 s | 1.24 s | 1 190 ms | 1 361 ms |
| tray N=200 | 442 | 8 | 1.29 | 1.24 s | 1.41 s | 1 422 ms | 1 470 ms |
| plate 200 holes | 206 | 4 | 0.87 | 1.18 s | 1.21 s | 1 264 ms | 1 321 ms |
| plate 400 holes | 406 | 4 | 1.75 | 1.77 s | 1.53 s | 2 050 ms | 1 740 ms |
| 256-fin sink | 1 030 | 1 028 | 3.60 | 3.25 s | **1.92 s** | 3 383 ms | 2 217 ms |
| 500-fin sink | 2 006 | 2 004 | 7.18 | **18.58 s** | **3.46 s** | 19 224 ms | **3 819 ms** |
| two 500-fin sinks | 4 012 | 2 004 | 14.62 | n/m | **5.16 s** | — | 5 726 ms |

**5.4x on CPU and 5.0x on wall-clock at 2 006 faces, and the curve is linear.**
Small parts are unchanged (their ~0.9 s is the child's OCP cold import, which
dominates everything else at that size); the ±0.1 s wobble there is noise.

### The ceiling, re-derived — and why it does not move

`DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S` stays **20.0 s**, but for a reason that can
now be stated instead of a "~20x headroom" fitted to 10-23 ms toy goldens
(measured headroom at the time: **1.08x**).

Fit across the corpus: **~1.0 s fixed** (the child's OCP cold import) +
**0.23-0.36 CPU s per MiB**, linear. Face count does *not* predict cost — a
442-face tray and a 406-face plate cost the same as each other and a sixth of a
2 006-face sink — **input bytes do**, which is what a DoS bound should key on and
what the existing 16 MiB inline upload cap already limits. So:

* a file at the **full 16 MiB cap** costs ~6-7 CPU s → the ceiling is **~3x** the
  worst file the upload cap can admit;
* the largest part Loft can express (2 006 faces, `MAX_PATTERN_COUNT`) costs
  3.46 s → **5.8x**;
* the new cliff sits at **~55 MiB of STEP**, i.e. **the upload cap binds first
  and this ceiling is now unreachable by any accepted file** at the measured
  rate.

What can still reach it is a file whose *topology* is pathological for some
other OCCT pass — which is what the bound is for, and why it stays.

## 2026-07-31b — PERF-5: the provenance budget, measured and re-derived

`MAX_PROVENANCE_FACES` **8 000 → 30 000**, and the docstring that said an
authored part is "nowhere near the bound" is gone.

### The measured crossing point (the number the old docs did not have)

Per-fingerprint cost is unchanged from the ~186 us the bound was fitted to
(**134-237 us**, an exact-B-rep GProp area + centroid), so the pass is honest
about *its* cost; the budget's SHAPE is what was wrong. It sums over every
snapshot, so it is spent by `features × faces`, and the crossing point is a
FEATURE COUNT:

| features | faces | snapshots | budget | `attribute_faces` ms | attributed (old 8 000) |
| ---: | ---: | ---: | ---: | ---: | --- |
| 25 | 60 | 15 | 562 | 107 | yes |
| 50 | 117 | 31 | 2 047 | 485 | yes |
| 75 | 168 | 47 | 4 416 | 681 | yes |
| 100 | 219 | 61 | 7 242 | 968 | yes |
| **105** | 237 | 65 | **8 180** | — | **NULL** |
| 125 | 282 | 77 | 11 326 | 1 746 | NULL |
| 150 | 331 | 92 | 15 971 | 2 147 | NULL |
| 200 | 442 | 124 | 28 552 | 4 112 | NULL |
| 205 | 449 | 126 | 29 452 | — | (new: yes) |
| 210 | 467 | 130 | 31 310 | — | (new: NULL) |

**Old crossing: N ≈ 103 features (~232 faces). New crossing: N ≈ 207.** The
2026-07-31 run bracketed it at "~105-110"; this pins it.

### Why 30 000 and not 10 000

The old value was sized to keep one pass inside the RESEARCH §9 2 s interactive
ceiling. That premise is **moot at the sizes where the bound binds**: at N=125,
the first size 8 000 refused, the same `/overlay` request already pays ~11 s of
rebuild underneath it (PERF-1, no rebuild cache), and the attribution pass is a
steady **11-16 % of the request at every measured size** (968 ms of 8 403 at
N=100; 2 147 ms of 15 223 at N=150). Refusing it spent the *point* of the request
to save a sixth of it. 30 000 admits every part size that rebuilds at all today
(N=200 = 27 s) at a worst-case pass of ~4.0-7.1 s, while still degrading the
pathological case audit H4 named — a 20 000-face imported body is one snapshot,
budget 40 000.

### Not done here: the budget is still the wrong SHAPE (PERF-5b, filed)

Raising a quadratic ceiling buys headroom, not a fix. Attribution needs each
snapshot's **fingerprints**, not a retained B-rep: fingerprinting at production
time would make the pass `O(final faces)`, delete the quadratic, and drop the
retained snapshot memory with it. That change lives in
`features/evaluate.py` (`EvaluationState.body_history` at :380 / :2907, appended
at :3099) — another agent's territory this slice, so it is filed with the exact
call sites rather than half-done here.

---

## 2026-07-31c — PERF-1 + PERF-2 landed: the rebuild cache, and a proportional validity gate

Two fixes from the RANKED list above, measured on the same parts, the same
harness and the same machine as the 2026-07-31 baseline. **That baseline is the
"before" column and is not rewritten.**

### What shipped

* **PERF-2 — the CM-6 validity gate is now proportional to what changed.**
  `EvaluationState._admit` ran a whole-body `BRepCheck_Analyzer` per
  body-affecting feature (O(features × faces), measured at 22 % of an N=200
  rebuild). It now checks only the faces the op CREATED
  (`geometry.kernel.healing.new_geometry_is_valid`), with the whole-body check
  kept for a body being started (first extrude / `merge=False` / import) and at
  publish time.
* **PERF-1 — `evaluate_tree` has a rebuild cache.** A bounded, thread-safe,
  in-process LRU (`geometry.rebuild_cache`) keyed on the rolling content hash of
  the feature prefix, holding the evaluator's own state. A request whose leading
  features hash identically resumes there.

### The cache in one paragraph, because the design is the interesting part

Entries are **owned, not copied**: a hit REMOVES the entry and hands the
resuming evaluation the very shapes a cold rebuild would have built, and a
checkpoint is only offered back to the cache when the `TreeEvaluation` that owns
those shapes is released (a `weakref.finalize`), so no second request can ever
resume from shapes a first is still reading. That is not fastidiousness, it is
forced by measurement — see "why a copy is not an option" below — and it has one
honest consequence: the cache holds **one checkpoint per lineage** (the
frontier), so it serves APPEND and REPEAT and does **not** serve an edit in the
middle of a long tree.

### Why a copy is not an option (measured, on the N=25 tray)

The natural design — store a copy, hand out copies — was tried first and
rejected on evidence:

| re-materialisation | volume | STEP bytes | GLB bytes |
| --- | --- | --- | --- |
| `BRepBuilderAPI_Copy` (build123d `deepcopy`) | **bit-identical** (ΔV = 0.0) | identical | **differs** (16 B of 155 800: one accessor bound, `0.02` vs `0.020000000000000004`) |
| the same, `copyGeom`/`copyMesh` in all 4 combinations | bit-identical | — | differs, and all four agree with each other |
| BREP write→read (the `step_cache` idiom) | **bit-identical** (ΔV = 0.0) | — | **differs** (68 B) |
| ownership transfer (what shipped) | bit-identical | identical | **identical** |

Two controls rule out the easy explanations: two fresh rebuilds separated by
heavy OCCT churn stay byte-identical (so it is not allocation nondeterminism),
and the drift persists when the copy shares its geometry handles (`copyGeom=False`),
so it is not surface copying either. Resuming from a copy would therefore make
`mesh_glb_id` — a documented content hash of a deterministic GLB — depend on
**cache state**. That is a determinism regression traded for speed, and the
trade is refused.

One more thing had to be true, and was not at first: a checkpoint's bodies are
`BRepTools::Clean`ed on the way into the cache. A body still carrying the
triangulation its previous consumer's tessellate/STL/STEP call left on it meshes
DIFFERENTLY once another boolean is applied — measured, appending one feature to
an already-tessellated N=25 body moved the final GLB; cleaning made it byte-exact
at every prefix length tried.

### What is in the key, and what is deliberately not

In: every feature of the prefix verbatim (id, type, params, `suppressed`) and
their order; `linear_deflection` (handlers read it); the **mirror capture scope**
(a `features`-scope mirror makes earlier features retain their tools, so the
state after *k* features genuinely depends on the suffix — found by measurement:
a prefix evaluated without it turns the later mirror into
`reference_unresolved`); `record_history` (a prefix with no snapshots cannot
serve per-face provenance, and two keys let the evaluate and overlay lineages
BOTH stay cached instead of ping-ponging); a version salt.

Out, under one rule — *a checkpoint stores only evaluator state, and every
artifact is re-derived on every call, so anything consulted after the dispatch
loop cannot change what a hit means*: `part_id`, `tree_version` (keying on it
would defeat the cache entirely — it changes on every edit — while protecting
nothing) and `materials` (densities, read only by the post-loop measurement; the
memoised artifacts are additionally guarded on the resolved per-body material).

### Not cached, and why

* **A tree that failed.** A failed op may have rewritten its argument in place
  (CM-6b), so its last-good state is not something to build on.
* **A tree whose publish-time re-check found the body invalidated.** Same reason,
  plus it is a state that publishes nothing.
* **Mid-tree edits.** Only frontier checkpoints exist (see above). The follow-up
  is filed: `warm_rebuild_cache()` — the prefetch seam that ships with this,
  bounded and cancellable, returning an `int` so a speculative body can never be
  published — is exactly what a background re-warm of the consumed prefix would
  use.
* **Anything durable.** Per worker, in memory, never a correctness dependency:
  a miss re-evaluates.

### Axis A re-run — the cold rebuild, same points, same harness

`LOFT_SCALING_BENCH=1 uv run pytest services/geometry/tests/test_scaling_benchmarks.py
-m benchmark -s`, 3 samples per point, median, one untimed warmup — and the
harness now empties the prefix cache before every sample (`_cold_rebuild`), or
every sample after the first would be a cache hit and the table would report
artifact reuse as though it were a rebuild.

| feats | rebuild ms 2026-07-31 (before) | rebuild ms now (after) | change |
| ---: | ---: | ---: | ---: |
| 10 | 263 | 220 | −16 % |
| 25 | 628 | 626 | −0.3 % |
| 50 | 2 098 | 2 361 | **+13 %** |
| 100 | 7 456 | 6 577 | −12 % |
| 200 | 27 269 | 25 711 | −6 % |

**Say it plainly: the cold rebuild did not materially improve, and the exponent
did not move.** Per-doubling exponents after: 1.92 (25→50), 1.48 (50→100), 1.97
(100→200) — mean **1.79**, against 1.81 before. N=50 came back *slower*. Every
one of these deltas is inside the ±8 % run-to-run spread this document already
documents (the baseline's own N=200 median was measured at 27 269 / 25 331 /
25 677 ms across one session), so the sweep cannot resolve PERF-2's saving at
all. The saving is real and is measured directly instead, in the same process,
alternating implementations on the same tree: **21.5 ms → 6.3 ms per
body-affecting feature at 219 faces**, i.e. 1 310 ms → 385 ms over an N=100
rebuild. It is ~13 % of a rebuild, it is flat in body size where the old gate
was linear in it — and it is nowhere near enough to matter on its own.

**Loft's wall is still `N^1.8`, and PERF-2 moved the constant by about a
tenth.** That is the disappointing half of this run and it is the half a reader
needs first.

### What DID move: what a modeller pays per interaction

`LOFT_SCALING_BENCH=1 uv run pytest services/geometry/tests/test_rebuild_cache_benchmarks.py
-m benchmark -s`, same machine, same quiet window, 3 samples per point, median.
**append** = the tree evaluated at N−1 and released, then evaluated at N (add one
feature). **repeat** = the same tree again — the `/measure`, `/tessellate`,
`/export` or drawings call that follows an `/evaluate`.

| feats | cold rebuild ms | append ms | repeat ms | append | repeat |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 232 | 66 | 6 | 3.5x | 40x |
| 25 | 632 | 136 | 18 | 4.6x | 35x |
| 50 | 1 967 | 216 | 38 | 9.1x | 51x |
| 100 | 6 896 | 430 | 63 | 16x | 109x |
| 200 | 26 587 | **1 019** | **162** | **26x** | **164x** |

Against the VERDICT table above, which said a 100-feature part is "painful and
no longer a tool" at 7.5 s and a 200-feature part is "unusable" at 27 s:

| part size | rebuild (unchanged) | add a feature | measure / export / re-tessellate |
| --- | ---: | ---: | ---: |
| 50 features | 2.0 s | **0.22 s** | **0.04 s** |
| 100 features | 6.9 s | **0.43 s** | **0.06 s** |
| 200 features | 26.6 s | **1.0 s** | **0.16 s** |

The append floor is not the rebuild any more — at N=200 the one new feature is
~200 ms and the other ~800 ms is **tessellating the 442-face result**, which
every evaluate must do. So the next lever on append is the mesh path (RANKED-3b),
not the tree. The repeat floor (162 ms at N=200) is the publish-time whole-body
`BRepCheck` (~53 ms) plus hashing 200 features' JSON for the prefix key.

What this does NOT fix, stated as plainly as the wins: **the first rebuild of a
tree the worker has not seen** (a page load, a cold worker, a document opened by
another user) still costs the full 27 s, and **a mid-tree edit** — change feature
#39 of 200 — still misses, because only frontier checkpoints exist. Face picks
alternate on their own lineage, so the first pick after an edit is cold and every
pick after that is warm.

### Memory

The cache is bounded at 8 checkpoints. Measured at N=100 (219 faces) with eight
distinct lineages resident: **+2 MiB of RSS per retained checkpoint** past the
first, so a full cache is tens of MiB against OCCT's ~500 MiB baseline
(extrapolating the 442-face body, ~4 MiB each at N=200). RSS does not fall when
the cache is cleared — glibc keeps the arena — so the number is measured as a
marginal cost, which is the honest way to state it.

### Correctness — what was run

* The full geometry suite (`uv run pytest services/geometry`) green, including the
  CM-6/QA-1 regressions: the welded-void chain still fails closed with identical
  statuses (`ok` x6 + `error`), the identical `invalid_body` code, and every
  artifact withheld.
* `tests/test_rebuild_cache.py` (new, always-on, 22 gates): a feature mutated
  DEEP in a warm tree is never served from a stale prefix; suppress / delete /
  reorder / deflection / a later scoped mirror each invalidate; appends at three
  lengths are byte-identical to a cold rebuild including `mesh_glb_id`; a failed
  tree is not a resume point; an entry is never lent while its evaluation is
  alive; three concurrent rebuilds of one tree all return the cold answer.
* Goldens unchanged, byte-for-byte — a cache that moved one would be a bug in the
  cache.

---

## 2026-08-01 — PERF-1b landed: prefetch, so a mid-tree edit stops paying for the whole tree

PERF-1's cache keeps ONE checkpoint per lineage — the frontier — so it serves an
APPEND and a REPEAT and nothing else. Two things stayed cold, and both are the
ones a modeller feels: a **mid-tree edit** (nothing exists for the prefix before
the edited feature) and the **first face pick after an edit** (picks carry
`record_history` in the key, so they are their own lineage; repeat picks were
warm, the first was not). This wires the seam PERF-1 left behind
(`warm_rebuild_cache`, which returns an `int` and therefore cannot publish) to
the only two events in the product that are genuine declarations of intent.

**Triggers, and only these two.** An **open feature editor** declares features
`1..N-1` settled for as long as the dialog is open (`POST
/api/v1/geometry/prefetch`, `kind: feature_edit` → the whole tree plus a
`prefix_length`). The **timeline travel stop** — dragged, or at rest with its
backward neighbour warmed — is a shorter tree in its own right (`kind:
travel_stop` → the truncated tree, no prefix length; the two hash DIFFERENTLY,
because the mirror capture scope in the key header is computed over the whole
feature list, so only the right one is ever a hit). Register/document hover
prefetch is deliberately not here: it is ordinary TanStack Query work and worth
nothing against a rebuild curve.

### Measured (housing tray, this container, 4 cores under sibling load)

Wall-clock seconds; each pair runs back-to-back from the same starting state
(the part is OPEN, so the frontier checkpoint exists) so the ratio is the honest
part. CPU seconds in the last column are load-independent.

| part | edit at | commit, cold | commit, warmed | first pick, cold | first pick, warmed | warm cost (CPU s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N=100 | #50 (mid) | 9.27 | **7.04** | 9.64 | **6.97** | 2.3 + 2.3 |
| N=100 | #92 (late) | 9.19 | **1.58** (5.8x) | 8.72 | **1.57** (5.6x) | 7.1 + 7.4 |
| N=200 | #100 (mid) | 35.18 | **25.87** | 33.22 | **24.70** | 7.7 + 8.0 |
| N=200 | #192 (late) | 33.68 | **4.80** (7.0x) | 34.73 | **4.39** (7.9x) | 28.9 + 30.0 |

Travel stop, rolling BACK from the tip to half the tree:

| part | stop | cold | warmed | warm cost (CPU s) |
| --- | ---: | ---: | ---: | ---: |
| N=100 | 50 features | 2.87 | **0.23** (12x) | 2.1 |
| N=200 | 100 features | 8.19 | **0.50** (16x) | 7.4 |

**The mid-tree ceiling is the curve, not the implementation.** Rebuild is
`N^1.85`, so warming prefix `k` can remove at most `(k/N)^1.85` of the work: 27 %
at the halfway point, 91 % at `k = 0.95N`. The measured 24-28 % at `#50/#100` and
7x at `#192` are that law, not a tuning failure. Prefetch hides latency; it does
not bend the exponent, and nothing short of incremental topology will.

### Budget and cancellation

* **One warm per worker, ever** (`WarmScheduler`, a single daemon thread). This
  is the DoS answer: speculation costs at most one core no matter how many
  clients declare intent. Doing it as "an evaluate nobody awaits" on FastAPI's
  threadpool would have scaled the burn with the client count.
* **A newer ticket supersedes; an explicit cancel retires.** Both are observed
  BETWEEN features — one OCCT call is not interruptible — so a warm stops within
  ~200 ms of the editor closing or the stop moving. A stopped warm keeps what it
  built: a shorter prefix is still a legitimate resume point.
* **`DEFAULT_WARM_BUDGET_S = 30`**, shared across a ticket's lineages in priority
  order (`evaluate` — the commit — before `provenance` — the pick). Fitted to the
  table above: the first value tried was 10 s, which delivered the full win at
  N=100 and truncated N=200, i.e. exactly the part the fix exists for.
* **The pessimal case, measured:** a user opens an editor on the 200-feature part
  and closes it having typed nothing. Cost = the seconds they sat in the dialog
  (cancel is immediate), bounded by 30 CPU s on ONE core; at N=100 a *complete*
  wasted warm of both lineages is 14.4 CPU s. And if they do commit, none of it
  was waste — it is the commit's own work, moved earlier.

### A warm cannot be published — how that is enforced, not just intended

* `warm_rebuild_cache` returns an `int`. The wire reply (`WarmTreeResult`) has
  two fields, a ticket and a boolean; there is no field a body, a mesh id or a
  mass property could travel in, at either hop.
* **`tests/test_prefetch.py` asserts there is nothing to serve:** after warming a
  tree, the `mesh_glb_id` that a real evaluate of that very tree publishes does
  not resolve in the mesh store. A warm derives no artifact, so no id exists —
  the id becomes fetchable only once a real evaluate produced it, and it is the
  same id, because the resume is transparent.
* A warmed prefix is reachable ONLY through the ordinary content-addressed key:
  editing a feature inside the warmed prefix MISSES (asserted), a 12-feature
  checkpoint cannot answer the 9-feature tree that precedes it (asserted), and a
  plain-lineage warm cannot serve a provenance rebuild (asserted). Every answer
  is compared to a COLD rebuild down to the GLB bytes.
* Goldens unchanged, byte-for-byte.

### Still cold after this

* **The first open of a part.** A cold worker still pays the full `N^1.85`
  rebuild — 27 s at N=200. Prefetch cannot help; only incremental topology can.
* **A deep edit on a 200-feature tree, partially.** The 30 s budget covers the
  commit lineage (28.9 CPU s at `#192`) and leaves the provenance lineage short,
  so the measured 7.9x on the first pick is what a *complete* warm gives; under
  the budget the pick is warmed to whatever prefix the remaining seconds reach.
* **A warm that RESUMES a checkpoint holds it** (ownership transfer — `take`
  removes the entry), so a real request for that same checkpoint mid-warm misses.
  Bounded by the budget and by cancellation, impossible for the editor trigger (a
  prefix warm can only take checkpoints at or before `prefix_length`, and the
  frontier is past it), and possible only for a travel stop already visited.
* **Multi-worker deployments dilute it**, exactly as PERF-1 does: the cache and
  the scheduler are per-process, so `--scale geometry=N` divides the hit rate.

---

## 2026-08-01 — CONCURRENCY: what happens when more than one person uses it

**Why this run exists.** Every number above this line is **one user, one
process, mostly in-process**. The first question a self-hosting operator asks is
*"can my team of four use this at once?"*, and until today nothing in the repo
could answer it — `docs/OPERATIONS.md` §6 answered it by REASONING (one worker
per host, because the rebuild cache is a per-process LRU with no session
affinity). That inference is now measured. **Half of it was right and the
conclusion drawn from it was wrong**; §6 has been corrected to match.

### Machine and method

| | |
| --- | --- |
| Machine | Linux container, **nproc = 4**, **MemTotal = 15.7 GiB** |
| Commit | `99b6975` (includes PERF-1b prefetch) |
| Topology | Native boot, no containers: gateway `:8510`, documents `:8511`, geometry `:8512`-`:8515`, SQLite, Redis `:6390` for the rate limiter |
| Harness | `scripts/concurrency-load.py` + `scripts/load-stack.sh` |
| Part | `housing_tree(50)` — the Axis-A tray, the size §6 calls "comfortable" |
| Load model | Closed loop, **zero think time**: N users = N requests in flight |
| Window | Load average 0.27 at start; no sibling agent running heavy work |

Reproduce:

```bash
scripts/load-stack.sh up 4
uv run python scripts/concurrency-load.py --users 4 --size 50 --loops 3 \
  --workers http://127.0.0.1:8512 http://127.0.0.1:8513 \
            http://127.0.0.1:8514 http://127.0.0.1:8515 \
  --dispatch sticky --json out.json
scripts/load-stack.sh down
```

Each simulated modeler is a thread with its own connection **on its own part**
(the tray's corner-round radius carries a per-user micrometre salt, so no two
users share a cache lineage — four modelers are four parts, not one), running
the real loop: *edit a dimension → re-evaluate → pick a face (`/overlay`) →
measure two edges (`/measure`)*. Requests go over real HTTP to the geometry
service. Cache hit rate is **scraped** from each worker's `/metrics`
(`loft_rebuild_cache_{hits,misses}_total`), never inferred from timings.

**Validity control, because a load generator that is itself the bottleneck
reports its own limits as the server's:** the harness records summed worker CPU
(`/proc/<pid>/stat`) and its own `getrusage` every run. The harness never
exceeded **0.04 cores**; every number below is the server's.

### CORRECTNESS FIRST — nothing crossed, in any configuration

The brief's top question. Every evaluate under load banks its
`(mesh_glb_id, volume)`; after the load each tree is re-evaluated **alone** and
compared. `mesh_glb_id` is a content hash of the GLB and `volume` comes off the
exact B-rep, so two crossed evaluations cannot agree by accident.

| configuration | responses audited | mismatches |
| --- | ---: | ---: |
| 8 users, 1 worker, 8 different parts | 32 | **0** |
| 8 users, 4 workers, random dispatch (max LRU churn) | 32 | **0** |
| 8 users, 1 worker, **all on the SAME part** (adversarial: one contended checkpoint) | 32 | **0** |

Zero errors and zero 5xx in all of them. **The system degrades honestly: it gets
slow, it does not get wrong.** That is the right failure mode and it is now
pinned by an always-on gate — `services/geometry/tests/test_concurrent_modelers.py`
(four threads, four different parts, two rounds, compared against serial
baselines; plus the evaluate/overlay lineage pair under contention).

One harness defect worth recording because it is the class this repo keeps
naming: the first version read `properties.volume_mm3`, a field that does not
exist, so that half of the check silently compared `None` to `None` for an hour.
The field is `volume`. **A gate is only as honest as its input.**

### 1. One geometry worker uses ONE core, whatever you throw at it

This is the finding everything else follows from.

| users | wall s | ops/s | **cores used** | cache hit | cold open p50 | edit p50 | edit p95 | face pick p50 | measure p50 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 15.2 | 0.66 | **1.13** | 0.40 | 2 284 | 2 113 | 2 212 | 2 705 | 56 |
| 2 | 34.7 | 0.58 | **1.12** | 0.40 | 5 022 | 4 644 | 5 328 | 6 348 | 124 |
| 4 | 71.2 | 0.56 | **1.13** | 0.40 | 9 702 | 9 747 | 11 183 | 13 052 | 244 |
| 5 | 104.5 | 0.48 | **1.14** | **0.28** | 12 639 | 11 903 | 13 271 | 16 655 | **618** |
| 8 | 201.1 | 0.40 | **1.15** | **0.125** | 20 233 | 19 440 | 21 714 | 27 833 | **19 189** |

**Throughput is flat and latency is linear in user count.** Four modelers do not
go four times faster on a four-core box — they take four times longer each. The
mechanism is not queueing policy, it is the GIL: OCP/pybind11 does not release it
around OCCT calls, so the FastAPI threadpool gives concurrency in name only.
Confirmed directly, watching one worker while N cold evaluates are in flight:

| concurrent requests | wall s | worker CPU s | **cores** | OS threads live |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2.74 | 2.87 | 1.05 | 11 |
| 2 | 5.33 | 5.89 | 1.10 | 12 |
| 4 | 11.34 | 12.74 | 1.12 | 14 |
| 8 | 21.32 | 22.97 | 1.08 | 18 |

Eighteen threads, one core. **A 4-core host running one geometry worker is
running at 25 % of the machine, by construction, and no amount of load changes
that.** §6's "(a) more cores let you serve more concurrent modelers" was true
only in the sense that more cores let you run more *processes*.

### 2. The cache-capacity cliff is at the FIFTH user, and it is sharp

`REBUILD_CACHE_CAPACITY = 8`, and a working modeler occupies **two** lineages
(the evaluate lineage and the `record_history` overlay lineage). So four users
fit exactly, and the fifth evicts somebody:

| users on one worker | cache hit rate | measure p50 (a warm repeat) |
| ---: | ---: | ---: |
| 1-4 | **0.40** | 56 - 244 ms |
| 5 | 0.28 | **618 ms** |
| 6 | 0.15 | **14 890 ms** |
| 8 | 0.125 | **19 189 ms** |

The column that matters is the last one. `/measure`, `/export` and
re-tessellation are the operations PERF-1 made nearly free (the "0.06 s" column
in §6's table) — they are free *only while the checkpoint survives*. Past four
concurrent users on a worker they become full cold rebuilds, a **79x**
regression on the cheapest thing in the product.

### 3. Worker fan-out: the ops doc's mechanism was right, its conclusion was not

Same 4 users, same part, three routing policies. `sticky` pins each user to one
worker (what session affinity would do deliberately, and what a keep-alive
connection does by accident); `roundrobin` is balanced but affinity-free;
`random` is what a shared listening socket and compose DNS actually give you.

| workers | dispatch | wall s | ops/s | cores | **cache hit** | edit p50 | face pick p50 | measure p50 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | — | 71.2 | 0.56 | 1.13 | 0.40 | 9 747 | 13 052 | 244 |
| 2 | sticky | 35.9 | 1.11 | 2.11 | 0.40 | 4 688 | 6 612 | 129 |
| 2 | random | 62.0 | 0.65 | 1.56 | **0.225** | 5 306 | 8 795 | 352 |
| 4 | **sticky** | **19.0** | **2.11** | **3.66** | **0.40** | **2 559** | **3 352** | **62** |
| 4 | roundrobin | 34.5 | 1.16 | 3.01 | **0.125** | 2 916 | 3 432 | 2 693 |
| 4 | random | 58.9 | 0.68 | 1.89 | **0.075** | 4 753 | 4 818 | 3 689 |

Read the sticky row against the single-user row of table 1 (edit 2 113 ms, pick
2 705 ms, measure 56 ms): **four modelers on four workers with affinity pay what
one modeler pays on an idle machine.** 3.7x the throughput, 3.66 of 4 cores, and
the cache hit rate does not move at all.

**The dilution the ops doc predicted is real and close to 1/N** — 0.40 → 0.225
at two workers → 0.075-0.125 at four. That half of the inference stands.
**What does not stand is the conclusion.** Fan-out multiplies throughput in
*every* policy measured, including the worst:

| | speedup vs. one worker | cost of losing affinity |
| --- | ---: | --- |
| 4 workers, sticky | **3.75x** | — |
| 4 workers, round-robin | 2.06x | 1.8x lost to cache dilution alone |
| 4 workers, random | 1.21x | a further 1.7x lost to queueing imbalance |

Two independent penalties, separated by the round-robin row: dilution costs
1.8x, and *un*balanced dispatch costs another 1.7x on top — because a worker
with no internal parallelism cannot absorb two simultaneous arrivals, so a
random pile-up on one process is dead time on the other three.

So the shipped guidance — *"prefer ONE geometry worker per host, sized to the
cores you have, until the number of concurrent modelers exceeds the number of
cores"* — is wrong twice over: one worker cannot use the cores you sized it for,
and the second modeler doubles everyone's latency immediately rather than at the
core count. Corrected in `docs/OPERATIONS.md` §6.

### 4. The mixed case nobody had tried: one big cold open against three small edits

Three modelers on 25-feature parts, one worker, then a fourth opens a
200-feature part cold.

| | edit p50 | face pick p50 | measure p50 |
| --- | ---: | ---: | ---: |
| the three, alone | 2 554 - 2 717 ms | 3 039 - 3 300 ms | 97 - 173 ms |
| the three, while the 200-feature part opens | **3 640 - 3 923 ms** | **5 006 - 5 448 ms** | 221 - 323 ms |
| degradation | **+45 %** | **+64 %** | +100 % |
| the fourth user | cold open **48.6 s**, first face pick **41.6 s** | | |

**The small edits stall, but they stall fairly.** Nothing blocks for the length
of the big rebuild: the GIL is released between OCCT calls, so the worst
single stall is one feature's work (~200 ms on a 442-face body) and the core is
shared roughly in proportion. The whole episode lasts 91 s, during which
everyone is ~1.5x slower and the person who opened the big part waits 49 s.

That is a defensible degradation curve — and it is the answer to "do the small
edits stall?": **yes, by about half again, for as long as the big part is being
worked.** Two workers would have removed it entirely (put the big part on its
own process).

### 5. What breaks first: the 30-second gateway ceiling, and it lies about why

`GEOMETRY_TIMEOUT_S = 30.0` (`services/gateway/src/gateway/geometry.py:65`) is a
hard read timeout on every geometry call the browser makes. Measured on a
**single user, idle machine**, cold trees, through the real gateway with real
auth:

| part | `/overlay` through the gateway | result |
| --- | ---: | --- |
| 100 features | 10.2 s | 200 |
| 150 features | 21.3 s | 200 (71 % of the budget) |
| **200 features** | **30.0 s** | **502 `upstream_unavailable`** |

The 502's message is *"Geometry service is unreachable."* It is not: it is
working, and it finishes the same request in 40.3 s measured directly. The user
is told the service is down, the completed answer is discarded, and the CPU is
spent anyway. Retrying does not immediately help, because the abandoned
rebuild's checkpoint only enters the cache once its evaluation is released:

| attempt | result | cache |
| ---: | --- | --- |
| 1 | 502 after 30.0 s | miss, no store yet |
| 2 | 502 after 30.0 s | miss, previous attempt's checkpoint stored mid-flight |
| 3 | **200 after 22.7 s** | hit |

**Three clicks and two "the service is unreachable" errors to pick one face on a
200-feature part, on an idle machine, with one user.** Under load it never
succeeds: at 8 users on a *50-feature* part the face-pick p95 is 30.0 s, right
on the line (2 of 80 operations over it).

Everything else held:

* **Rate limiter** (Redis-backed, 120 requests / 60 s per user): first 429 at
  request 119 of a 140-request burst, `Retry-After: 56`, correct envelope. Not
  the binding constraint — a modeler issues 3-4 compute calls per edit and each
  edit takes seconds — but note it is **per user**, so it is not backpressure
  against N users.
* **Memory**: 563-706 MiB resident per geometry worker after the whole sweep
  (one worker grew 525 → 601 MiB across an 8-user run). Four workers plus
  gateway and documents = 3.3 GiB of 15.7. §6's "budget ~1 GiB per worker"
  holds; memory is not the wall.
* **Connection pools**: nothing exhausted. Neither is *configured*, which is the
  problem — the gateway's httpx client takes httpx's default 100 max
  connections, so it will cheerfully pile 100 requests onto a worker that can
  meaningfully serve one.

### 6. There is no admission control, so overload becomes total loss

The consequence of the previous two points, measured. Sixteen cold 50-feature
evaluates issued simultaneously at one worker:

```
wall 40.9 s
completions (s): 29.3 35.2 36.4 37.4 37.9 39.2 39.4 39.4 39.4 39.5
                 39.5 39.5 39.5 39.5 39.6 39.6
```

Thirteen of sixteen finish within 0.4 s of each other, at the end. That is
**processor sharing, not queueing**: every request progresses slowly together
rather than one finishing while the others wait. Against the 30 s gateway
ceiling that turns into:

| policy | requests delivered under a 30 s ceiling |
| --- | ---: |
| as shipped (processor sharing) | **1 of 16** |
| a FIFO queue on identical hardware | **11 of 16** |

**Overload does not degrade the service, it deletes it.** Same CPU, same work,
94 % more useful output from admission control alone. Nothing in the stack
bounds concurrent geometry work: httpx defaults to 100 connections, anyio's
threadpool to 40 workers, and the one effective core is shared among all of
them.

### 7. The PERF-1b prefetch needs a head start it usually gets, and hurts when it does not

The prefetch landed 45 minutes before this run, so it is measured here rather
than assumed. One user, idle worker, 50-feature tray, editing the last feature —
`POST /api/v1/warm` with `prefix_length = N-1`, then the commit after a gap:

| gap between the warm and the commit | evaluate |
| --- | ---: |
| no warm at all | 2 589 ms |
| warm, commit **immediately** | **4 742 ms** (1.8x WORSE) |
| warm, 1 s | 3 259 ms (still worse) |
| warm, 2 s | **312 ms** (8.3x better) |
| warm, 3 s | 359 ms |
| warm, 5 s | 342 ms |

The threshold is the rebuild time itself (~2.3 s here): below it the speculation
and the real request race for the single core and both lose; above it the
resume is nearly free. That is a good trade for its designed trigger — a feature
dialog is open for seconds — but the required head start **scales with part size
AND with user count**: on a 200-feature part the rebuild is 26 s idle, and under
4-user load the effective rebuild is ~4x longer again.

Under concurrency the second-order cost shows up on the cache. Four users, one
worker, warm issued immediately before each commit:

| | wall s | cache hit | evictions | edit p50 |
| --- | ---: | ---: | ---: | ---: |
| no prefetch | 82.3 | 0.40 | 24 | 9 724 |
| prefetch | 90.3 | **0.31** | **35** | 11 964 |

Eleven extra evictions. `rebuild_cache.py`'s own docstring says *"a warm must
never evict a checkpoint a live request is about to use"* — with four users the
LRU is exactly full, so on a shared worker every warm does. The scheduler's
"one warm per worker" bound is the right shape; it bounds CPU, not cache slots,
and one core is not one *spare* core.

### 8. Append still works, which is worth saying

Not everything degrades. The case PERF-1 was built for holds up under load
(`--mode append`, one worker):

| users | append p50 | append p95 | cache hit |
| ---: | ---: | ---: | ---: |
| 1 | 249 ms | 312 ms | 0.85 |
| 4 | 816 ms | 1 331 ms | 0.85 |

Four users share one core, so 3.3x is the arithmetic working correctly, not a
regression. The hit rate does not move, because an append re-stores its frontier
and four users' two lineages is exactly the LRU's capacity.

And the single-user per-operation breakdown, over HTTP, for reference — note
which lines are misses:

| what the modeler does (50-feature part) | | |
| --- | ---: | --- |
| open the part | 2 310 ms | miss |
| re-evaluate the same tree | **41 ms** | hit |
| measure two edges | **58 ms** | hit |
| pick a face (first after an edit) | 2 743 ms | miss |
| pick another face | 570 ms | hit |
| **edit a dimension → re-evaluate** | **2 443 ms** | **miss** |
| pick a face after that edit | 2 784 ms | miss |

**An edit is a full cold rebuild** unless the prefetch warmed it (§7). §6's
"add a feature 0.22 s" column is the *append* number, and appending is not what a
modeler spends the day doing.

---

## VERDICT — how many simultaneous modelers can one self-hosted Loft support?

**One geometry worker supports exactly one modeler.** Not four, not "up to the
core count" — one. The second concurrent user doubles everyone's latency, the
fourth quadruples it, and the fifth also knocks over the rebuild cache and turns
the cheap operations into 15-second ones. A worker uses 1.1 cores no matter how
many people are on it, so there is no headroom to share.

**With one worker per core AND sticky routing, one host supports one modeler per
core at full single-user speed.** Measured: 4 users on 4 workers on 4 cores paid
2 559 ms per edit against 2 113 ms for a lone user on an idle machine. That is
the configuration to ship.

**Without affinity you get somewhere between a fifth and half of that** (1.21x
random, 2.06x round-robin, against 3.75x sticky), because the cache dilutes 1/N
*and* an unbalanced arrival pattern idles workers that cannot absorb bursts.

So, plainly, for a 4-core self-hosted box:

| configuration | comfortable simultaneous modelers | note |
| --- | ---: | --- |
| 1 worker (the current recommendation) | **1** | 75 % of the machine is idle |
| 4 workers, no affinity (today's compose `--scale`) | **1-2** | most of the fan-out is thrown away |
| 4 workers + sticky routing (**not shipped**) | **4** | full single-user latency each |
| any of the above, parts > ~150 features | **0** | the gateway 502s before the answer arrives |

**What the operator should do today:** run one geometry worker per core (with
`S3_URL` set, so the mesh store is shared — the in-process LRU refuses
multi-worker for good reason), keep parts under ~100 features, and understand
that without affinity the extra workers buy about 20-100 % rather than 300 %.

**What we should ship, in order of value per unit of work:**

1. **Session affinity** (CONC-1, P1) — a consistent hash on part id at the
   gateway. Measured worth: **1.8x** on top of any fan-out, and it costs no CPU.
2. **Admission control** (CONC-2, P1) — a bounded queue in front of geometry.
   Measured worth: **1 → 11 of 16** requests delivered under overload.
3. **A truthful, part-size-aware upstream timeout** (CONC-3, P1) — 30 s is
   below the shipped cost of a 200-feature face pick on an *idle* machine, and
   the resulting 502 blames the wrong component.
4. **A bigger, per-user-aware rebuild cache** (CONC-4, P2) — 8 entries is 4
   modelers; the fifth costs everyone 79x on `/measure`. **LANDED, see the next
   section.**
5. **Release the GIL around OCCT** (CONC-5, P3, likely upstream) — the only
   fix that makes one worker use one machine. Everything above is working
   around it.

### Addendum — CONC-1/2/3 shipped the same day (measured by the backend agent,
relayed here because this file has one owner)

Their window was **not quiet either** (load average 4.2-5.3 on 4 cores, partly
the dwell run below), so these are back-to-back A/B ratios, and they explicitly
declined to publish the 1-worker vs 4-worker gateway walls (52.1 s vs 57.0 s) as
noise rather than a result.

* **Admission control** (CONC-2), 16 simultaneous cold 50-feature evaluates on
  one worker: before, 45.4 s wall and **0 of 16** delivered inside 30 s —
  fourteen completions bunched within six seconds of each other at the end,
  textbook processor sharing. Shipped defaults: 22.6 s and **8 of 16**, with 8
  shed as 503 + `Retry-After`. Depth 16 / wait 60 s: 41.6 s and **11 of 16**,
  none shed — the FIFO number this file predicted.
* **Session affinity** (CONC-1), 4 users / 4 workers with the queue active:
  sticky 30.6 s wall, cache hit 0.40, `/measure` p50 **81 ms**; random 64.9 s,
  cache hit 0.10, `/measure` p50 **3 284 ms**. 2.1x on wall, 4x on hit rate,
  **41x on measure**.
* **The upstream timeout** (CONC-3) is now 90 s, and the 504 says the request is
  still working and its progress is cached. In-flight work is deliberately NOT
  cancelled, so an abandoned rebuild banks its checkpoint and the retry resumes
  from it: **40.3 s cold → 22.7 s**. That checkpoint is live work, and the
  eviction rule below is what stops a warm displacing it.

---

## 2026-08-01b — CONC-4 + CONC-6 + PERF-1c: what the prefetch is worth to a USER

**Why this run exists.** Three findings converged on one thing: the rebuild
cache and its speculation were sized and triggered for one person doing one
thing. The founder asked the question that started it — *"is this the numbers
users are experiencing, or just what happens under the hood without them
noticing?"* — about PERF-1b's table, which was measured with the warm run to
COMPLETION. A real edit is "open the editor, type 12, Enter" in three to five
seconds, and nobody had measured that.

### Method, and the honest caveat about the window

In-process, one thread of real work, same tray builder as every other run here
(`services/geometry/tests/_big_part_builders.py`), driving the SHIPPED seam —
`geometry.warm.warm_work` on a real `WarmScheduler`, not a hand-rolled
imitation. One scenario is one modeler: open the part (a real evaluate, so the
frontier checkpoint exists), select the last editable feature (the prefetch goes
out), sit in the dialog for D seconds, commit the edit, pick a face.

**The window was NOT quiet.** A sibling agent's Playwright suite and a
concurrency load run were live for most of it (load average 3.3-5.3 on 4 cores).
So absolutes here run ~10 % above the quiet numbers earlier in this file (a cold
N=200 commit measures 34.7-37.5 s here against 33.7 s on 2026-08-01), and every
comparison below is a **back-to-back A/B inside one scenario** rather than a
cross-run absolute. Where a single number carried the argument, it was
re-measured interleaved with its own baseline.

### 1. The prefetch was a 2x PESSIMISATION when it did not get its head start

CONC-6 measured this over HTTP at N=50; it reproduces in-process at every size,
and it gets worse in absolute terms as the part grows. "Race" is the pre-fix
behaviour: the warm keeps working while the commit runs, and with one effective
core per worker (CONC-5 — OCP does not release the GIL) they simply halve each
other.

| part | commit, no prefetch | commit, warm racing it | |
| --- | ---: | ---: | --- |
| N=50 | 2 723 ms | **5 492 ms** | 2.0x WORSE |
| N=100 | 8 965 ms | **20 509 ms** | 2.3x WORSE |
| N=200 | 37 498 ms | **77 633 ms** | 2.1x WORSE |

The first face pick after the commit pays it twice: 2 341 → 4 403 ms at N=50,
9 931 → 20 487 ms at N=100. **A feature meant to hide latency was doubling it**,
and the only reason it did not show in PERF-1b's table is that the table let the
warm finish first.

### 2. The fix: speculation loses to live work, on the core AND in the cache

Two rules, both structural, both now enforced by code rather than by a docstring
asking nicely:

* **The core.** `evaluate_tree` marks itself live for its duration
  (`LiveWorkGate`, a counter — never a lock, so real rebuilds still run
  concurrently). A warm checks it between features and, when real work is in
  flight, **banks the prefix it has built and waits**. It resumes from its own
  checkpoint when the worker goes idle.
* **The cache.** A warm's checkpoint is stored SPECULATIVE: it is always the
  first eviction victim, and a speculative store that would have to evict a live
  checkpoint is **refused outright** (the warm achieved nothing — the acceptable
  failure). Before this, on a full LRU every warm evicted somebody's live
  checkpoint: measured 2026-08-01 at four users, evictions 24 → 35 and hit rate
  0.40 → 0.31. This is also what protects an *abandoned* rebuild's checkpoint —
  CONC-3's 90 s timeout deliberately lets in-flight work finish so its checkpoint
  is banked for the retry, and that checkpoint is live work by exactly this rule.

Result — the same "commit immediately after opening the editor" case, gated:

| part | no prefetch | prefetch, commit immediately | |
| --- | ---: | ---: | --- |
| N=50 | 2 254 ms | **2 369 ms** | +5 % (was +102 %) |
| N=100 | 7 773 ms | **7 586 ms** | -2 % (was +129 %) |
| N=200 | 35 007 ms | **35 567 ms** | +1.6 % (was +107 %) |

**The worst case is now "the speculation achieved nothing", never "the user
waited longer"** — which is the property CONC-6 asked for. The N=200 row is the
mean of an INTERLEAVED pair (baseline, warmed, warmed, baseline, run back to
back) because a single sample of it came out +37 % in a contended window and a
single sample is not evidence: the spread on the baseline alone across that pair
is 32.3-37.7 s, i.e. ±15 %, which swallows the difference being claimed. The
other two sizes are cheap enough to be repeated and moved by <10 % between runs.

**Banking the prefix on the way out is load-bearing, not tidiness.** Work a warm
is still holding is invisible: a request can only resume from something in the
CACHE. The first version of this fix paused without storing, and at N=100 with a
15 s dwell the face pick that arrived while the warm sat mid-provenance paid the
full **9 227 ms** — fifteen seconds of speculation bought nothing. With the
prefix banked at the pause the same pick resumes from it (2 204 ms, and 480 ms
once the loop below was also fixed).

**And the yield's own bookkeeping can BE the bug.** The first pause loop
re-banked every 50 ms slice, running `BRepTools::Clean` over a 442-face body
twenty times a second for the whole pause — the commit it had stepped aside for
came out **12 % slower than with no prefetch at all**. Caught by measuring the
fix rather than by trusting it. The loop now waits without churn.

### 3. The dwell table: EXPECTED win beside the ceiling (PERF-1c)

Commit latency after D seconds in the editor, each row against its own
back-to-back cold baseline. "Ceiling" is PERF-1b's number: the warm run to
completion (or, at N=200, to its 30 s budget).

| part | cold commit | D = 2 s | D = 5 s | D = 15 s | ceiling |
| --- | ---: | ---: | ---: | ---: | ---: |
| N=50 | 2 254 ms | 2 347 ms (1.0x) | **321 ms (7.0x)** | **302 ms (7.5x)** | 7.5x |
| N=100 | 7 773 ms | 8 499 ms (1.0x) | 8 388 ms (1.0x) | **483 ms (16x)** | 16x |
| N=200 | 34 681 ms | 39 024 ms (1.0x) | 36 498 ms (1.0x) | 35 424 ms (1.0x) | **18.8x** (D ≥ 30 s) |

And the first face pick after that commit — the second thing the warm buys:

| part | cold pick | D = 5 s | D = 15 s | ceiling |
| --- | ---: | ---: | ---: | ---: |
| N=50 | 2 224 ms | **341 ms (6.5x)** | **304 ms (7.3x)** | 7.3x |
| N=100 | 7 479 ms | 7 994 ms (1.0x) | **480 ms (15.6x)** | 15.6x |
| N=200 | 36 387 ms | 36 538 ms (1.0x) | 33 757 ms (1.0x) | 1.0x — the 30 s budget never reaches this lineage |

**THE WIN IS A STEP, NOT A RAMP, and the step is the warm's own completion.**
A partial prefix cannot help the request that is already running (it probed the
cache before the warm banked anything), so the commit is either resumed or cold.
The step lands at **~0.85x the cold rebuild per lineage** — measured warm
completion 2.0 s against a 2.25 s rebuild at N=50, 7.1 s against 7.8 s at N=100 —
because a warm does the same features without tessellating or measuring. Both
lineages (the commit's, then the pick's) is **~1.7x the rebuild**.

So the required dwell, which is the number a user actually feels:

| part | dwell for the COMMIT win | dwell for the PICK too | realistic edit? |
| --- | ---: | ---: | --- |
| N=50 | ~2.5 s | ~4.5 s | **yes** — a typed dimension takes that long |
| N=100 | ~8 s | ~14 s | only if you stop to think |
| N=200 | ~30 s | never (budget) | **no** |

**One thing the app does that the table above leaves out, measured because it
changes the answer:** selecting a feature row also fires the feature-localized
selection overlay (`PartPage`, a real provenance evaluate of the tree as it
stands), so the warm's first ~one-rebuild of head start is spent waiting for it.
At N=50 that pushes the commit threshold from ~2.5 s to ~4.5 s — and a 5 s dwell
still lands the full win (**332 ms, 7.1x**), while the pick gets a partial one
(**1 302 ms vs 2 373 cold**) from the provenance prefix banked when the warm
stepped aside. At 8 s both are complete (347 / 380 ms). This is the clearest
demonstration that banking on the yield is worth its complexity: without it that
1.3 s pick is a full 2.4 s cold rebuild.

**The honest headline, replacing PERF-1b's:** the prefetch delivers 7x on a
50-feature part at a realistic 3-5 second edit, and **nothing at all** on a
200-feature part, where the published 7.0x needs a dwell longer than the
rebuild it is hiding. It is not wasted — a banked prefix is a legitimate resume
point and the work is the commit's own, moved earlier — but the number to quote
to a user is the dwell table, not the ceiling. Above ~100 features only
incremental topology helps; prefetch cannot bend `N^1.85`.

### 4. The trigger did NOT move, and the measurement says why

PERF-1c asked whether the trigger should fire earlier than editor-open — on
feature-row selection, "which precedes the dialog by a beat". Two findings:

1. **It already does.** `FeatureTreePanel` fires `usePrefetchIntent` off
   `selectedFeatureId`, and `PartPage.selectFeature` sets the selection and opens
   the editor in the same handler. There is no beat between them to reclaim.
2. **No trigger nudge could pay.** The deficit at N=100 is ~3 s and at N=200
   ~25 s of missing dwell. The only earlier signal is HOVER, which is (a) a
   guess rather than a declaration and (b) actively harmful here: one warm slot
   per worker means a hover-scrub down the tree would supersede the warm the
   user's real selection is waiting on.

**No dwell TIMER either, and this is a reversal of the hypothesis in CONC-6.**
The idea was that warming should not start until it can plausibly pay for
itself. The measurement says the pessimisation was *contention*, not earliness —
with contention removed, starting early costs the committing user nothing (table
in §2), while a start delay would push the completion step further out and
strictly REDUCE the win. The break-even is published (the dwell table) rather
than enforced.

### 5. `REBUILD_CACHE_CAPACITY` 8 → 32, priced against the worker budget

Eight entries was exactly four modelers, because a working modeler holds two
lineages (the plain one an edit rebuilds, and the `record_history` one a face
pick uses), and the fifth user cost everyone 79x on `/measure` (244 ms → 19 189
ms). The new number is derived, not chosen:

| input | value | source |
| --- | ---: | --- |
| lineages per working modeler | 2 | §2 of the concurrency run |
| modelers a host is sized for | 8 | docs/OPERATIONS.md §6 |
| live checkpoints one worker must hold (no affinity) | **16** | 8 x 2 |
| speculation + an assembly's per-part trees | headroom | one warm ticket is ≤2 entries |
| **capacity** | **32** | 16 + headroom, rounded to a power of two |

The price, measured rather than assumed: **+2 MiB of RSS per retained checkpoint
at 219 faces, ~4 MiB at 442**. A completely full cache of big parts is therefore
~128 MiB (32 x 4 MiB), ~64 MiB of mid-sized ones, against the **~1 GiB per
geometry worker** budgeted in docs/OPERATIONS.md §6 whose floor is OCCT's ~500
MiB plus the resident part. **Up to ~13 % of a worker's budget to stop the fifth
user costing everyone 79x** — a ceiling and not a reservation, since one modeler
occupies two entries and RSS only grows if 32 distinct large lineages are
genuinely live.

### What this does NOT fix

* **The cold open.** Untouched, and it is the biggest number on the page: 34 s
  at N=200 in this window. Prefetch cannot help a tree nobody has evaluated.
* **A mid-tree edit on a big part.** The dwell table's N=200 row is the honest
  statement: at any dwell a human produces, the prefetch is a no-op there.
* **The 30 s warm budget at N=200.** It covers the commit lineage (28.9 CPU s)
  and never reaches the provenance one, so the first face pick after a deep edit
  on a 200-feature part is cold whatever the user does. Raising it trades a
  bigger DoS surface for a case the dwell table says nobody reaches anyway.
* **Multi-worker dilution.** The cache and the scheduler are per-process, so
  `--scale geometry=N` still divides the hit rate N ways (CONC-1's affinity is
  the fix, and it landed the same day).
