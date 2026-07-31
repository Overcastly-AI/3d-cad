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

* **(S) There is no gzip middleware anywhere in the stack.** Adding
  `GZipMiddleware` (or letting the gateway compress) is measured at **5.2x on
  the tray and 11.8x on the heat sink** — 1 117 KiB → 216 KiB, 1 064 KiB →
  90 KiB. This is a one-line change on the hottest binary route.
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

## Budget log

Wall-clock ceilings to track over time. A >10 % regression against the
"measured" column is a filed defect even though nothing here is CI-enforced.

| operation | part | measured 2026-07-31 | note |
| --- | --- | ---: | --- |
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
| STEP import (service path) | 500-fin sink (2 006 F) | 18 440 ms | **92 % of the 20 s CPU ceiling** |
| STL export | tray N=200 | 76 ms / 1 546 KiB | |
