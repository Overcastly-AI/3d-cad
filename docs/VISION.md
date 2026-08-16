# Vision (North Star)

> This is the *why* and *where we're going*. The **how/when** lives in
> `docs/ROADMAP.md`; the **next actions** live in `docs/BACKLOG.md`. This file is
> owned by the **vision-steward** agent: the founder dreams in plain language,
> the steward formalizes ideas here and hands them to the build loop.

## Working name

**Loft** (working title — a CAD term, evocative of cloud). Branding is a
founder decision; the vision-steward owns getting it confirmed or replaced.
Nothing else in the repo should hard-couple to the name.

## Brand hierarchy

1. **Overcastly AI** (https://overcastly.com) — the maker and company.
   Attribution belongs here ("Built by Overcastly AI").
2. **Loft** (working name) — the product: an open-source, MIT-licensed,
   cloud-native parametric 3D CAD platform. Its own identity, not
   white-labelled to Overcastly's visual language.
3. **Self-hoster branding** — a per-instance override layer (later phase).

## The thesis

**Build the best open-source parametric 3D CAD in the world — browser-based,
cloud-native, self-hostable — and compete with the industry leaders by doing
what a per-seat-licensed, file-format-locked, desktop-era product structurally
cannot.**

We don't win by out-checklisting SolidWorks' 30-year feature list. We win on
**structural advantages the incumbents can't match**:

1. **Free & unlimited.** Incumbent seats run $2,000–$4,500/yr, and the "free"
   tiers (hobbyist Fusion 360, Onshape free) hold your documents hostage —
   public-only files, export limits, features gated. Ours runs on your
   hardware; the marginal seat is $0.
2. **Your data, your files, your compute.** Open document format, direct DB
   access, STEP-first interop, no cloud lock-in. A regulated or IP-sensitive
   shop can run the whole stack air-gapped — the one thing no incumbent cloud
   CAD sells at any price.
3. **Open & extensible.** MIT license. Python is not a bolted-on macro
   language — the modeling API *is* Python, the same code path the UI uses.
   Code-level extensibility instead of a marketplace tax.
4. **AI-native & agent-native.** Built in the agent era: an MCP server lets a
   coding agent create sketches, run features, and export STEP directly.
   Parametric modeling is a language-shaped problem; no incumbent exposes
   their kernel to agents as a first-class surface. (This product is itself
   built by a team of AI agents — we dogfood the workflow.)

If a capability doesn't exploit one of those four advantages, it's table
stakes we ship to be credible — not where we differentiate.

## The operating question

Every roadmap decision, backlog item, and code review answers one question:

> **"Would a working engineer model a real part in this today?"**

Not "is it a promising demo" — a daily-driver bar. Where the honest answer is
"no," the scorecard row below says why, and that gap is the next thing we
build.

## Daily-driver scorecard

Rated against the incumbent daily drivers (SolidWorks / Fusion 360 / Onshape)
and the open-source incumbent (FreeCAD). Legend: ✅ better · ➖ parity ·
❌ behind. Re-scored by the vision-steward each audit cycle — honestly.

| Dimension | Status | Notes |
|---|---|---|
| Sketching & constraints | ➖ | **Flipped ✅→➖ 2026-08-16 (see the dated correction at the foot of this Notes cell) — held here rather than at the top because the cell preserves its full prior-pass history below, oldest reasoning last.** **Flipped ➖→✅ this pass**: the three residual gaps this row's own prior Notes named as the remaining shortfall — over-constraint diagnosis, dimension expressions/driving-vs-driven, non-constrainable splines — all ship end-to-end this run, each backend+frontend, each independently reviewed and e2e-proven on the real stack (verified directly: `git show`/`git log` on every cited commit, `pytest` on the touched backend suites, `tsc --noEmit` + `vitest` on the touched frontend files, all green; e2e spec bodies read, not assumed). **(1) Over-constraint diagnosis** (`b28dffc`→`c527063`→`c4527f6` backend, `4e6e429` frontend): `sketch_conflicting` and the solved-but-redundant payload both carry a TYPED `SketchConstraintDiagnosis` — `classification` (redundant vs conflicting), `removable`, named offending ids, and a `suggested_fix` ("Remove constraint N") — matching the incumbents' diagnostic-not-just-error-message UX. The frontend reads the typed field directly; the brittle regex `parseConflictIndices` over the human message string is deleted outright (confirmed: only a code-comment mentioning its removal remains in the tree). Proven in `test_evaluate_tree.py` and e2e `constraints.spec.ts`. **(2) Dimension expressions + driving/driven** (`72ad936` backend, `398fb12` security hardening, `196c89c` frontend): a dimension value is a literal, a named-dimension reference, or a `+ - * / ( )` expression, evaluated by a safe recursive-descent parser (`geometry/sketch/expression.py` — confirmed no `eval` call anywhere in the module) with cycle/unknown-ref/div-zero detection; a code-review 🔴 (RecursionError on a pathological expression escaping as a 500) was found and closed with a request-boundary length cap plus depth guards on both the parser and the AST evaluator. `driving`/`driven` dims are distinct: driven dims are excluded from the solver and render read-only in parentheses, measured back from solved geometry. Proven in `test_sketch_expression.py` (`width=20, height="width/2"→10`, driven-tracks-without-over-constraining) and e2e `dimension-expressions.spec.ts`; founder screenshots (`dimension-expression-*.png`) show the brass "= 10 mm" resolved echo and the driven `(20)` reference readout live in the sketcher. **(3) Constrainable splines** (`dda86eb` backend, `5e7311e` review hardening, `6dde1c9` frontend): a spline's fit points are addressable solver points (`EntityPointRef.point:"fitN"`); coincident/fixed/symmetric apply directly, distance/H/V via a coincident-linked line; only *referenced* fit points enter the solver so an unconstrained spline stays byte-identical (backward-compat golden green). e2e `spline-constraint.spec.ts` and its screenshots show a fit point pulled onto a fixed line endpoint, visibly reshaping the curve. This closes the prior pass's literal wording — "splines are v1 non-constrained" is no longer true. **Held at ✅, not pushed to "no residuals"** — three honest, narrower items remain, none of which block the daily-driver session the way the closed gaps did: (a) spline **tangency** (G1 continuity to a line/arc) is explicitly deferred pending a native spline primitive in planegcs — real, and the one incumbent-standard spline capability still missing, but positional/coincidence constraining (the more load-bearing case: closing a loop, anchoring a fit point to the rest of the profile) now works, and most of Loft's target mechanical parts (brackets/housings/ducts) use splines sparingly and rarely need tangent-blended curves the way industrial-design surfacing does; (b) distance/H/V directly between two fit points has no dedicated point-pair constraint kind and must go through the linked-line gesture — a workaround, not a wall; (c) dimension expressions cover arithmetic only, no trig/units/named functions — covers the overwhelming majority of real parametric relationships (spacing, halving, ratios) but not gear/angle-driven formulas. These are parity-plus items for the forward backlog, not blockers — the same standard applied when Part modeling flipped ➖→✅ with multi-body boolean left open as a scope boundary, not a hold. **Correction (this pass, 2026-08-16, vision-steward) — FLIPPED ✅→➖.** Three code-verified gaps in the CORE draw/constrain loop, read directly against source, not inferred from a commit subject — qualitatively different from the three residuals just above, which are missing incumbent niceties; these are silently-wrong-geometry on the *ordinary* path, DIM-1's own class. **(1) RECT-1 (new, filed P0):** a plain rectangle drawn WITHOUT typing a value into the draw-time dimension cell is four topologically DISCONNECTED lines, not a closed profile. Verified: `apps/web/src/sketch/drawDimensions.ts:288` (`if (typed.length === 0) return [];`) skips `rectangleRigidity` — the only call site anywhere in `apps/web/src/sketch/**` that authors the four corner `coincident` constraints; `tools.ts`'s `rectangleLines` stores each corner as a raw `{x,y}` pair with no id-sharing between adjacent lines; no server-side point-merge exists in `services/geometry/src/geometry/sketch/**` (grepped, none found). Draw a rectangle, don't type, dismiss the cell (`dismissDrawDimensions`/Escape) — a later horizontal/vertical dimension on any ONE edge moves that edge alone; the other three stay put and the rectangle tears at its corners on the first re-drive. This is the single most common closed-profile gesture, and until yesterday's DIM-1 fix (`a810524`) typing during draw did not even register keystrokes, so most rectangles drawn against this build to date took exactly this untyped path. **(2) SNAP-2 (already Ready, P0) has an un-taken general case that is the same defect on the second-most-common gesture — closing a hand-drawn profile.** SNAP-2's own text names it ("the general entity-snap case") but scopes the fix to the datum frame only; snapping a new point onto an ALREADY-DRAWN entity's endpoint (the way you close a loop drawn edge-by-edge) copies the coordinate with the identical no-constraint gap. SolidWorks documents automatic-coincident-on-point-over-point-during-a-line-draw as baseline behavior ([SOLIDWORKS Sketch Relations Guide](https://www.goengineer.com/blog/solidworks-sketch-relations-guide), corroborated at [SOLIDWORKS Forums](https://forum.solidworks.com/thread/33622)) — table stakes Loft doesn't ship for anything but the datum frame, and doesn't ship there yet either. **(3) MIRROR-1 (new, filed P1):** the mirror-axis picker explicitly excludes datum entities — `withoutDatums(store.entities)` at the one call site, `SketchScene.tsx`'s `pickMirrorAxis` branch — so mirroring a profile about the sketch centerline (ordinary for any symmetric bracket) is flatly unavailable, even though SKETCH-2 (`5ceed6e`, two days old) made the datum axis a fully real, selectable, constrainable `kind:"line"` entity that `axisLinePoints` would otherwise accept. None of the three block DRAWING a part; all three make an ordinary LATER edit silently wrong, or a common gesture flatly unavailable — precisely the "no, and they would not know why" class the operating question is written to catch. Held at ➖, not ❌: constraint kinds, splines, over/under-constraint diagnosis, trim/offset/fillet/pattern all remain genuinely shipped and daily-usable — the gap is specifically "does the tool hold together what it just drew," not breadth of what it can draw. |
| Part modeling (features, history) | ✅ | **Flipped ➖→✅ this pass**: the prior pass held this row short of ✅ on four named blockers — predicate-only edge selection, no shell, no draft, single-body-only. Three are now closed with QA evidence; the fourth is a real, honestly-scoped scope boundary, not a hole in the daily-driver workflow. **Click-specific edge selection** (`71e771d` backend + `c18453c` UI, both reviewed APPROVE): a stage-1 edge `SubshapeRef` lets an engineer click ONE edge and fillet/chamfer it while its neighbours stay sharp — e2e-proven (`fillet-edge-pick.spec.ts`: a single-edge fillet on a 20 mm cube adds exactly one face, 6→7, vs. 26 for an all-edges fillet; re-resolves after reload via the rebuild-surviving signature). The `all_edges`/`axis_parallel`-only limitation named last pass is closed. **Shell** (`617fc7f` backend + `6cf7a75` UI, reviewed): hollows a body to a uniform wall thickness with picked faces left open, reusing the same `SubshapeRef` face machinery sketch-on-face proved. GEOMETRY-QA's `shell-open-top-box-40x25x10-t2` golden is exact to 1e-9 and — notably — the review process found and closed a real correctness risk: OCCT's `MakeThickSolid` can silently return the un-hollowed body on a bad thickness, so `shell_thickness_too_large` is a load-bearing material-removed invariant guard, not a cosmetic error path (GEOMETRY-QA 2026-07-13). **Draft** (`caec623` backend + `a663db7` UI, reviewed): tapers picked faces by an angle about a neutral plane. Golden `draft-frustum-box-40x40x20-5deg` reproduces the hand-derived analytic frustum to 1e-9, and the review swept the full ±angle range through `BRepCheck_Analyzer` and confirmed draft's failure mode is always a hard OCCT raise, never shell's silent-bad-body risk — so no extra guard was needed, and that finding is itself recorded evidence the row isn't being taken on faith. Combined with holes (multi-loop cut, prior pass) and multi-plane/sketch-on-face (prior pass), the feature set for a SINGLE connected solid is now genuinely comprehensive: sketch → extrude/revolve/sweep/loft → fillet/chamfer(click-specific-edge) → pattern → shell → draft → holes, on origin planes, offset planes, or a picked model face, with a real (stage-1) topological-naming reference surviving rebuilds throughout. That is what a working engineer models the overwhelming majority of real mechanical parts with — brackets, housings, shafts, plates, ducts, enclosures — because most real parts are one connected solid with local features, not an assembly-of-bodies collapsed into one file. **Correction (this pass, 2026-07-19):** the gap this row named as its one remaining hole — booleans between independently-built bodies — is now CLOSED, and the note describing it as unbuilt is stale. Multi-body modeling shipped end-to-end since: `396dbcd` (MB-0 plumbing — a part can end with >1 body via `merge=False`), `d148f4d`/`c9729aa` (MB-1 union, backend+UI), `fa8a147`/`bb8d990` (MB-2 subtract/intersect, backend+UI), `7ed2dd8` (MB-3 downstream fillet on a boolean-created edge, independently geometry-QA'd PASS — `10eac54`), `e77da29`/`fa70eef` (MB-4a/c multi-lump bodies + opt-in disjoint union, geometry-QA'd PASS — `0514117`), `919ebcf` (MB-4b multi-solid STEP import as one multi-lump body). A casting merged with a separately-modeled boss, or a subtractive multi-tool cut, is now buildable — union/subtract/intersect between independently-built bodies, with downstream features (fillet, pattern) correctly resolving against the boolean result. Verified this pass via `git show` on every cited commit plus both geometry-QA PASS docs read in full. Multi-body doesn't earn its own scorecard row — the incumbents don't split it out as a separate daily-driver dimension either, it's part of "Part modeling" breadth — so this is a Notes correction, not a new row; the row was already ✅ and stays ✅. Two history-editing niceties remain unshipped, unchanged from last pass: reorder/suppress/patch-a-mid-tree-feature, and edge selection still lacks a compound multi-edge picker. |
| Assemblies & mates | ➖ | **Flipped ❌→➖ this pass**: the v1 MVP shipped end-to-end and is independently reviewed + QA'd at every stage. **Document model** (`fab5115` + `4a9716c` hardening): assembly/instance/mate tables, `py_kit.schemas.assemblies`, owner-auth'd CRUD with OCC + write-time acyclicity, a per-owner advisory lock closing a TOCTOU on concurrent mate-cycle checks, cross-document 409-on-delete-with-dependents. **Mate solver** (`c010ee1` + `c962f73` hardening): our OWN deterministic 3D rigid-body solver — no GPL dependency (SolveSpace/py-slvs are GPLv3, deliberately rejected) — quaternion 6-DOF, a closed-form tree fast path plus a numpy-only damped LM fallback, BLAS pinned for byte-identical cross-machine determinism, and the same well/under/over/conflicting diagnosis vocabulary as the sketch solver. **Resolution** (`40e895f`): mates reference real geometry via the SAME `PlanarFaceSignature`/`EdgeSignature` topological-naming machinery sketch-on-face proved, producing the first real bolted solve at ~1e-8. **Evaluation** (`05f6aa1` + `3cc5c4f` never-500 fix): the full pipeline — evaluate each unique part once → resolve mate geometry → solve → shared-mesh tessellation — with the `assembly-two-plates-bolted` golden **independently geometry-QA'd PASS** (`2d8c82f`: solved pose and mass roll-up re-derived from scratch, not read from `expected.json`; worst deviation 1.18e-8 vs. a 1e-6 bound; byte-deterministic across fresh interpreters; shared-mesh dedup confirmed to one mesh id). **Gateway** (`cc72d23`): CRUD + evaluate proxies, every route auth-gated (parametrized 401-per-route). **Viewport** (`e8ecce9`): assembly mode renders multiple instances at solved transforms with shared-mesh dedup, mate authoring by picking faces/holes (coincident/concentric/lock) with a snap-on-solve animation, and a solve-status/DOF readout; e2e `assembly.spec.ts` passes live against the real stack (instance a part twice, author mates, assert seed-apart→bolted), founder screenshots at `docs/screenshots/assembly-{seed-apart,bolted}-{desktop,laptop}.png`. **Held at ➖, not ✅ — the real residuals, two corrected this pass (2026-07-19):** the prior Notes said only 3 of 5 schema'd mate types were wired and there was no BOM; both are stale. **All 5 mate types are now wired**: distance (`56d457d` — signed-gap convention pinned along face A's outward normal, golden `assembly-two-plates-gap` lands two real plates exactly 5 mm apart) and angle (`56d457d` — `acos(n_A·n_B)` convention, re-conditioned residual for a stable LM solve, a NaN-free degenerate-parallel fallback) shipped backend with analytic goldens; `5457910` shipped the frontend authoring (pick two faces, enter mm/deg in the mate HUD, e2e-proven). **A BOM now exists**: `901dad1` ships a flat read-model (`GET /api/v1/assemblies/{id}/bom` — direct instances grouped by referenced document, quantity = shared-reference count, a deleted reference surfaces honestly as a `missing` line rather than a 500 or silent drop) and `cf617c8` a SOLVE/PARTS toggle panel rendering it as a title-block parts list, UI-reviewed PASS with two P3 follow-ups (`a061c19`). **Correction (this pass, 2026-07-24 — FINDINGS #25 stale-in-the-good-direction fix):** two named residuals are now CLOSED. **Interference/collision detection** shipped (`e46db16` pairwise `BRepAlgoAPI_Common` clash over solved instance bodies, hardened against a false-negative boolean-failure edge case at `c131d46`; UI `49f01ba` — a Check-interference command + Clash inspector listing each pair's exact overlap volume, red clash tint on DOM+WebGL) — geometry-QA'd PASS, no P0/P1 (`docs/GEOMETRY-QA.md` 2026-07-23 entry). **Assembly STEP is now BIDIRECTIONAL**: export (`b7408fd` — AP214 product structure, each instance a named PRODUCT at its solved world placement, geometry-QA'd PASS with a rotation-convention guard `d980764`) and import (`f75fb26` XCAF product-structure reader + `7ca0df5` wiring an uploaded assembly STEP into a real Loft assembly document + `f37eb9c` DoS-bound hardening) — geometry-QA'd PASS, no P0/P1/P2 (`docs/GEOMETRY-QA.md` 2026-07-23 entries, nested sub-assembly composition independently re-derived against a Rodrigues oracle). What's STILL genuinely missing: no exploded views; the BOM is FLAT — direct instances only, no recursive/indented sub-assembly rollup; instances reference a part's current TIP, not a pinned version, so an edit to a shared part silently reflows every assembly that instances it — deterministic evaluation of a FROZEN assembly, not yet deterministic across part history (immutable part versioning is a separate, unbuilt item); sub-assemblies are rigid-only (no nested-assembly mate re-solve). A working engineer can genuinely bolt real parts together, dimension the joint parametrically, check for interference, and pull a parts list today — that clears the daily-driver bar for the common few-part assembly — but on the above it sits below SolidWorks/Fusion/Onshape assembly parity, which is exactly what ➖ means. |
| Interop (STEP/IGES/STL) | ➖ | **Flipped ❌→➖ this pass**: the prior Notes named the flip as "gated entirely on import" — import now ships end-to-end, so both directions work. **Kernel** (`4964fab`): an external STEP part comes in as a body-affecting BASE `import` feature (inline params); round-trip golden `import-step-box-10x20x30` asserts import ≡ inverse-of-export at tol 1e-7, **measured 0.0 deviation**, byte-deterministic across interpreter restarts (docstring honesty-corrected at `250ac4e`). **Gateway** (`4b453f1`): `POST /api/v1/parts/{id}/features/import` — auth-gated, 16 MiB cap enforced at 422 BEFORE the body is buffered/parsed, a prior-body guard (import must be the base feature), contracts regenerated. **UI** (`a015f4e`): "Import STEP" leads the Create strip (a base-only move, disabled once a body exists); a file-picker lands the external part as the base body, rendered in the viewport and measurable (OCCT mass-props: 6,000 mm³ / 10×20×30), re-exportable, and reload-persistent. Playwright e2e on the real stack (`import-step.spec.ts`, 5 specs green): valid STEP → body in tree+viewport+reload-persist; non-STEP file → legible error, no body; oversize file → rejected client-side before upload; desktop + 1280×800 screenshots (`docs/screenshots/import-step-*`). Combined with export (already shipped, prior pass), a working engineer can now bring a real external STEP part IN, model on it (fillet/shell/sketch-on-face all work via the existing topological-naming machinery), and export it back OUT. **Held at ➖, not ✅ — the honest gaps, residual (3) corrected this pass (2026-07-19):** (1) STEP-only, no IGES either direction; (2) inline-only representation — large files bloat the feature-tree JSON, the blob-backed `kind:"blob"` successor is seeded in the design doc but unshipped; (3) ~~single-solid only~~ **CLOSED — multi-solid STEP now imports** (`919ebcf`, MB-4b): a file with ≥2 solids assembles as ONE lump-sorted multi-lump body (deterministic regardless of OCCT's non-contractual reader order — golden `import-step-two-disjoint-boxes`, byte-identical GLB+STEP in-process and across a fresh interpreter restart); touching/overlapping solids are kept as separate lumps and never fused (import is not a boolean). Only a genuinely EMPTY (0-solid) file is now rejected; the error was renamed `import_not_single_solid`→`import_no_solid` to match, rippled through contracts/ts-client, and a stale docstring the review caught was fixed the same day (`0cbdbf6`). What's still missing at the assembly level: named product-structure (PRODUCT/ASSEMBLY entities, part names/hierarchy) is not read — a multi-solid file becomes one anonymous multi-lump BODY, not a Loft assembly document with named instances; that's a real, larger gap than "rejected," and is why this correction alone doesn't move the row. (4) no mesh/sew/repair healing for messy real-world CAD (v1 is "one legible solid or a clear error," not a healing pipeline); (5) the untrusted-parse wall-clock/DoS bound is a tracked **P1** fast-follow — the 16 MiB cap bounds memory, not parse time, so an adversarial STEP file can still pin a worker. IGES + healing + assembly-structure import remain genuinely missing, which is why the row HOLDS at ➖ rather than moving to ✅. |
| Drawings & documentation | ➖ | **Flipped ❌→➖ this pass**: Drawings v1 shipped end-to-end since the last re-score, closing the product audit's honest #2. **Document model** (`03f2319`): `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables, owner-scoped CRUD, dimensions naming model geometry via the reused `EdgeSignature` (no parallel taxonomy). **HLR projection** (`5c4b080`, geometry-QA `d28d557`, review fix `cdf7e60`): exact `HLRBRep_Algo` → canonically-ordered visible/hidden 2D edges, byte-deterministic across an interpreter restart, 4 analytic goldens (a box's front view is exactly a 40×10 rectangle; a through-hole projects a TRUE circle, not a facet fan). **Evaluate endpoint** (`d65caff`) + **gateway proxy** (`1dc1c60`): the part body evaluated once, projected per view, every route auth-gated. **Dimension measurement + provenance** (`5e16f9d`, independently geometry-QA'd `8b1b47f`, hardened `6f90c19`): each sharp projected edge tagged back to its originating model `EdgeSignature` by geometric re-matching (HLR's own output compounds carry no per-edge tag — a documented OCP-wheel finding, not a shortcut); `linear`/`diameter`/`radius`/`angular` dimensions measure the MODEL-true value off the exact B-rep, with an honest `foreshortened` flag and typed never-a-500 errors. **Frontend sheet editor** (`6671ec4`, layout fix `86dd0ec`, spot-audited `3a8fd03`): one action auto-lays-out the standard four (front/top/right third-angle + iso) as scale-correct SVG on the "paper on the bench" surface. **Dimension authoring** (`78ae196`, UI-reviewed `919d272`, fixed `00e1d1b`): pick a dimensionable edge → gated type menu → persists → renders as a real drafting annotation (extension/dimension lines, arrowheads, MODEL-true value). **SVG export** (`4b8d975`) was v1's client-side-only architecture. **Correction (this pass, 2026-07-19) — two of this row's named residuals are now closed:** **(1) server-composed export shipped.** Design doc Approach C (`43f993b`, "one placement source") replaced it: `eff3bf1` (DE-0/1a) ports the placement math server-side into `geometry.drawings.compose.place_sheet`, byte-stable across a fresh interpreter; `3dfdb35`/`a77bf77`/`84bf9d3` (DE-2a/b/c) add a reportlab PDF serializer with determinism-pinned metadata (e2e-proven: click Export PDF, catch a real `%PDF-` download); `6c82325`/`42af0d1` (DE-3a/b) add an ezdxf DXF serializer emitting REAL model-space entities (a hole is a CIRCLE a CAM tool can path, not a facet fan), version-pinned R2000 for cross-seed byte stability (verified across 14 `PYTHONHASHSEED` values); `4644f49`/`03f07e4` (DE-1b/1c) then cut the FRONTEND over to render from the server's `ComposedSheet` and delete the browser's duplicate placement engine outright (`layout.ts`/`dimensions.ts` lose hundreds of lines — confirmed via `git show --stat`), closing the design doc's explicitly time-boxed "two-engine window." All three formats (SVG/PDF/DXF) now share one server placement source; the sheet-metal pillar's flat-pattern view reuses this same composer (`67097ec`). **(2) angular + point-to-point dimension authoring shipped** (`981c42f`, UI-reviewed `cabda9c` — 2 P2/1 P3 filed, not blocking) — the measurement backend already supported both types; the sheet now authors them (second-edge pick for angular, precise vertex-handle pick for point-to-point), e2e-proven. **Correction (this pass, 2026-07-24 — FINDINGS #25 stale-in-the-good-direction fix):** section views are now CLOSED end-to-end (previously named as a missing residual). Kernel (`137a929`: planar full section on any principal or offset-principal plane + composed hatch fill) — an independent geometry-QA audit found a 🔴 P0 correctness defect (the front/XZ-datum section silently kept the eye-side half instead of removing it, `docs/GEOMETRY-QA.md` 2026-07-23), root-caused to a single sign-derivation bug and fixed same-day (`57dca7a`: single-sourced the removed-half sign through `resolve_section_frame`, keyed off the standard-view eye rather than the datum's raw `z_dir` sign; the fix also closed a related inexact-corner hatch bug), then verified trustworthy-green in a quiet window — 14/14 adversarial tests, full geometry pytest + `just e2e` (geometry gates 153 + Playwright 191) EXIT=0 (`b895f73`). Web authoring (`06fc019`): a `drawing-section` command-band action (`S` shortcut) reuses the sketcher's own plane-picker vocabulary to pick a cutting plane + which half is removed, persists, and renders the on-screen hatch from the same server compose the PDF/DXF/SVG exports draw from (one palette, two renderers). **Held at ➖, not ✅ — the honest residuals that remain:** no assembly drawings (part drawings only — the projection pipeline already handles a compound per the design doc, but it's unwired); no detail/broken/auxiliary views (orthographic + iso + section only); no auto-dimensioning; no GD&T/tolerances/surface-finish/weld symbols; no drag-to-place (dimensions auto-place at a fixed offset). A working engineer can genuinely hand a machinist a shop-ready, server-composed PDF or DXF print of a single real part today, including a cut section through a bored/cored feature — that clears the daily-driver bar for the single-part case, which is exactly what ➖ means, not below-bar ❌ nor incumbent-parity ✅ (assembly drawings and GD&T are real incumbent staples still missing). Full design doc: `docs/design/drawings.md`.  **2026-07-30 — the DELIVERABLE regressed while the feature list grew, and this mark is under review by the vision-steward.** Product audit `245f4a9` measured two P0s on the print rather than the editor: (N1) a dimension on an edge is DESTROYED by the edit it measures — widen a plate 100→120, the part rebuilds clean, and the dim becomes `subshape_unresolved` printed as a 2.6 mm dashed circle containing `!`, so a print revision is a re-dimensioning job; (N2) auto-layout does not re-flow on model change and shipped an iso view overlapping the top view by 6.33 × 60.00 mm with 82.8 mm of sheet empty, measured off the exported SVG. Associative drawings exist so a design change propagates. **BOTH CLOSED the same day (`7fde5d2`), so the mark HOLDS at ➖ on its standing residuals rather than being under review.** N1's root cause was an asymmetry, not a dimension bug: a picked FACE has had a resilient second matching tier since FINDINGS #3, a picked EDGE had only the strict signature (endpoints AND midpoint AND length), and every field of that signature is a function of the edge's own extent — so any change to the measured edge was fatal, and a dimension is by definition attached to what the designer is about to change. Edges now get the same two-tier treatment (`geometry.drawings.anchor`, topological-naming §11): strict first, then a re-match on the curve kind's rebuild invariant — a line's supporting line plus overlapping span, a circle's centre plus angular station — so the widened plate's dimension re-measures to 120.000 and the wire reports that it re-anchored. Placement consumes the re-anchored name too, because re-measuring the VALUE alone still left the annotation dropped from the sheet. Refusals stay refusals: a MOVED hole is an honest error, never re-anchored onto a different circle. N2: the 0.70 mm pre-edit clearance WAS the diagnosis — the iso anchor was derived only from the front/top/right extents, so it shrank as the isometric grew; it now accounts for its own extent, clearance is 6.0 mm, and the serializers stamp layout issues on the print rather than exporting a sheet a shop cannot read. What still holds the row at ➖ is unchanged and unrelated: no assembly drawings, no detail/broken/auxiliary views, no auto-dimensioning, no GD&T. |
| Sheet metal | ➖ | **Flipped ❌→➖ this pass (2026-07-19):** the founder-scoped v1 pillar (`docs/design/sheet-metal.md`, corrected before build at `41b7299`) shipped end-to-end and was independently QA'd twice. **Kernel** (`fb555cc` base flange, `46c05ae` edge flange): `SheetMetalBaseFlangeParamsV1`/`SheetMetalEdgeFlangeParamsV1` reuse the shipped `extrude`/`sweep` primitives verbatim (no new kernel geometry for the flat body) plus a new additive `CylindricalFaceSignature` (sibling of `PlanarFaceSignature`) that tags a bend region's provenance so the unfold can re-find it after a rebuild. **Unfold** (`46c05ae`, tractability proven first at `d95c851` Spike 0): `unfold_sheet_metal` is a provenance-driven, depth-1 PARALLEL bend-star algorithm — bend allowance BA = angle·(r + K·t), default K-factor 0.44 — verified at 45/60/90/120° (`5ed73c0`: the non-90° gap explicitly closed, BA scales with the MEASURED fold angle, not a hardcoded π/2, Δ≤2.6e-14), with area conservation (shared base counted once) and byte-determinism across `PYTHONHASHSEED` 0/12345 plus a fresh interpreter restart. **Flat pattern as a drawing view + bend table**: backend (`94db476`) → server-composed (`67097ec`, reusing the shipped Drawings placement composer — one placement source, not a forked path) → rendered (`645f236`: a dashed-blue fold-line token shared byte-for-byte between the server compose and the on-screen SVG, a columnar BEND/ANGLE/RADIUS/DIR/ALLOW bend table). **QA, independently, twice:** geometry-qa (`5ed73c0`) ran the whole pillar — bend allowance across 4 angles, area conservation, determinism, a STEP round-trip of an authored folded body (volume Δ≤8.2e-12, single connected solid, `test_sheet_metal_step_roundtrip.py`), byte-pinned SVG/PDF/DXF compose goldens — PASS, no P0/P1; frontend-qa (`f82b813`) spot-checked the UI ship-it, catching one real P2 (the server PDF/DXF bend table diverged in layout/precision from the on-screen SVG — a WYSIWYG break on the actual shop deliverable) closed the same day (`24b1c53`: one shared `_bend_row_cells` helper, all three serializers now byte-consistent, DRY-locked by a cross-serializer test, plus a 120° regression golden), and three P3 a11y/token nits closed the same day too (`2ba4df4`: a text-accessible `BendSchedulePanel` twin of the `role="img"` sheet, token-driven legend dash, de-magic'd column offsets). Founder screenshots: `docs/screenshots/sheet-metal-flat-pattern-{l,u}-{1440,1280}.png` (confirmed present). Verified this pass via `git show`/`git show --stat` on every cited commit, `docs/GEOMETRY-QA.md`'s and `docs/UI-REVIEW.md`'s 2026-07-19 entries read in full, and `docs/design/sheet-metal.md` re-read for scope claims. **Judged ➖, not ✅ — the scope boundary is real and load-bearing, not cosmetic.** The shipped algorithm is explicitly a **depth-1 bend star** (design doc §4.3/§7): every flange must attach directly to the ORIGINAL base face — a flange-on-a-flange (a bend CHAIN, the shape an enclosure, chassis, or multi-wall bracket needs) is out of scope, deferred behind locked, asserted boundaries (`UnfoldStarError`, `_split_base_moving` no-base-match) rather than silently wrong output. There is also no hem, jog, miter flange, tab, or corner relief — SolidWorks/Fusion sheet-metal's other core flange types — and no gauge/material rule table (K-factor is one part-level default, not looked up per-material/thickness) or import-as-sheet-metal recognition. That is a materially narrower slice of the sheet-metal DOMAIN than what Part modeling ✅ covers of general solid modeling: there, only the orthogonal multi-body-boolean case was deferred (and has since shipped); here, the thing deferred — chaining bends into a real multi-wall enclosure — is close to sheet metal's defining competency. Weighed against the operating question: a working engineer CAN model a real single-bend L-bracket or two-bend U-channel today and walk away with a shop-ready flat blank and bend table, verified correct by an independent geometry audit — genuinely useful, and decisively clears the ❌ bar — but a working sheet-metal engineer's daily bracket/enclosure work routinely needs a third bend off an already-bent edge, a hem for a safety edge, or a tab, none of which exist yet, so incumbent parity (✅) is not yet earned. **Nearest flips** (named in `docs/design/sheet-metal.md` §10): multi-bend/bend-graph unfold (removes the depth-1 ceiling) and hem/miter/tab. |
| Workspace & document management | ➖ | **New row, added 2026-07-30** — the independent product audit (`245f4a9`) rated this 1/10 and noted the scorecard had no row for it at all, which is the more telling half: a dimension nobody scores cannot flip, and a missing row reads as "fine" rather than "unexamined." Measured on the running app: a FLAT namespace with no folders or projects; creating a part whose name already exists returns `409 part_name_taken` with no disambiguation; there is NO search; and there is no copy/duplicate, so the ordinary engineering move of "start from the last bracket" has no path. Exports compound it — files download under UUID names, so a directory of downloads is unidentifiable. None of this is a modelling gap, which is exactly why it stayed invisible: every part of it is between the user and their OWN work rather than between the user and geometry. **Correction (this pass, 2026-08-16) — FLIPPED ❌→➖.** Three of the four named gaps are closed by work that landed after this doc's last touch (`0d3ea59`, 2026-07-31): **folders** (`17404ab`, "folders backed by a real tree") — parts/assemblies/drawings all scope into a real hierarchy now, not a flat list; **search/sort/rename/duplicate** (`e5c72eb`, 2026-08-01) — verified directly in `apps/web/src/routes/PartsPage.tsx` and `apps/web/src/api/parts.ts:duplicatePart`: a header filter field, numeric-collated NAME/LAST WORKED/FILED sort, inline rename under optimistic-concurrency versioning, and a real per-kind duplicate endpoint that copies a part's whole feature tree with every intra-tree id reference rewritten onto the copy; **export filenames** (`3cf6650`, 2026-08-01) — the download carries the document's own name, not a UUID. The fourth (name-collision disambiguation) is materially better without being fully closed: names are now unique PER FOLDER (`apps/web/src/api/parts.ts:416`), not globally, though the create-time UX on a collision wasn't re-tested live this pass. Real residual, confirmed absent: **no thumbnails** — grepped `PartsPage.tsx`, no thumbnail rendering exists — so the list still can't show which part is solved/errored/stale at a glance, the exact state-at-a-glance gap FLOW-1's own parts-page ask already names as open. Held at ➖, not ✅: thumbnails/state-at-a-glance and nested-folder-depth UX are unverified/unshipped. |
| Performance on real parts | ➖ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. **Correction (this pass, 2026-08-16) — FLIPPED ❌→➖.** That claim is now false: `docs/PERF.md` (first entry 2026-07-31, read in full) benchmarks a 360×240×20 shelled tray lid across N=10/25/50/100/200 features — a realistic mixed vocabulary (pockets, through/blind holes, picked-edge fillets, shell, revolves, a pattern-cut vent, a mirror) — plus a 6-feature/8–500-fin heat sink for face-count scaling, opt-in via a `benchmark` marker + env var (deliberately not a CI timing gate — a false-red perf gate is worse than none). Measured, not extrapolated: rebuild time grows N^1.85 — 263 ms at 10, 2.1 s at 25, 7.5 s at 100, 27 s at 200 — "fine at 25, a modeller waits at 50, painful at 100, unusable at 200," with correctness (BRepCheck-valid, byte-deterministic, STEP round-trip) unaffected at every size. `ed325a4`/`b4261a7` (2026-08-01) add a real four-concurrent-user load benchmark and ship what it found: session affinity by rendezvous hash (wall 30.6 s sticky vs 64.9 s random), a bounded admission queue (0/16 requests inside a 30 s deadline before → 11/16 after), and a timeout that reports truthfully (504 naming work still running, never a silent hang). Five perf defects the benchmark itself found (PERF-1..PERF-5: no rebuild cache — a face pick costs 29 s at scale; a validity-gate tax; STEP-import-of-own-export scaling faces^2.4; uncompressed mesh transport; per-face provenance going dark past ~110 features) remain OPEN and are the row's real residual — a working engineer can now model and MEASURE a realistically-sized part, and the ceiling is honestly documented rather than unknown, but the ceiling itself (unusable at 200 features; a 29 s face-pick once the rebuild cache PERF-1 asks for doesn't exist) is below a daily driver's bar for a genuinely large part. Held at ➖, not ✅: no CI-enforced regression gate at this scale (deliberate) and PERF-1..5 open. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

This table no longer starts near-all-❌: two pillars are ✅ (Part modeling,
Price/freedom), seven hold at ➖ — genuinely usable daily-driver capability,
short of incumbent parity on named residuals (Sketching, Assemblies, Interop,
Drawings, Sheet metal, Workspace & document management, Performance on real
parts) — and three are still ❌, honest Phase-5+ surfaces not yet built
(Collaboration, Extensibility, Agent access). The loop's job is to keep
flipping rows and never let this table go stale.

Last re-scored 2026-08-16 (vision-steward), twelfth pass this cycle, against
git log through `10714a6` — the first pass since `0d3ea59` (2026-07-31), a
16-day gap the founder flagged directly ("is our idea agent finding new ideas
from plasticity and fusion? We are not progressing new features"). **Three
rows flip this pass, two UP on shipped/measured evidence, one DOWN on a
re-derivation this pass performed itself from source, not inherited from a
commit subject.** **Workspace & document management ❌→➖** and **Performance
on real parts ❌→➖**: folders/search/sort/rename/duplicate/named-exports
(`17404ab`, `e5c72eb`, `3cf6650`) and a real 10–200-feature benchmark plus a
4-concurrent-user load suite (`docs/PERF.md`, `ed325a4`, `b4261a7`) all
shipped in the gap, verified directly against source and the doc, not
assumed from subjects. **Sketching ✅→➖ — the flip against the grain of "more
shipped."** Three code-verified gaps in the core draw/constrain loop (RECT-1
new, SNAP-2's own named-but-unscoped general case, MIRROR-1 new — full
mechanism and citations in the row's own Notes) mean the tool can silently
hand back a topologically-open profile from the single most common
draw-a-rectangle gesture, or flatly refuse to mirror about a sketch's own
centerline — a different and more severe class than the three residuals
(spline tangency, fit-point-pair distance, expression grammar) that held the
row at ✅ last pass. Every claim above was re-derived directly this pass:
`git log`/`git show` on every cited commit, and for the three new Sketching
gaps the actual source read and traced line-by-line, not inferred from a
BACKLOG description — `drawDimensions.ts`, `tools.ts`, `mirror.ts`,
`SketchScene.tsx`, `datum.ts`. Four founder-flow fixes landed in the same
window that do **not** move a scorecard row on their own (UX/flow
correctness, not new capability) but are worth naming since they were the
founder's own 2026-08-01 complaints, now closed: the dimension cell keeps
what you type (DIM-1, `a810524`), a saved sketch re-opens (SKETCH-1,
`30a9f3f`), orbit reaches a mouse and a trackpad while sketching (VP-1
`43c703c`, VP-1a `32e5b87`), and the origin/axes became real
selectable/constrainable geometry (SKETCH-2, `5ceed6e`) — the last of which
is also the precondition for MIRROR-1 even being reachable (the axis wasn't
pickable at all before SKETCH-2). No other row was re-derived this pass —
Part modeling, Assemblies, Interop, Drawings, Sheet metal, Collaboration,
Extensibility, Agent access, Price/freedom are carried forward UNCHANGED from
the 2026-07-24 pass below and have NOT been re-verified this cycle; flagged
as stale-but-unaudited, out of this pass's time budget, not asserted current.

---

Prior pass (2026-07-24, eleventh pass this cycle, against
git log through `6ddbb45` (assembly-views-end-to-end, the commit FINDINGS.md's
2026-07-24 hard audit ran against). **This pass is a targeted truth-only
correction (FINDINGS.md #25), not a full re-audit** — no row's score changed;
two rows' Notes were stale in the *good* direction (naming as missing three
capabilities that had actually shipped since the tenth pass) and are now
corrected with evidence. **Assemblies** (stays ➖): interference/collision
detection (`e46db16` clash detection + `c131d46` false-negative hardening,
`49f01ba` UI) and bidirectional assembly STEP (export `b7408fd`, import
`f75fb26`/`7ca0df5`/`f37eb9c`) both shipped and are both geometry-QA'd PASS
(`docs/GEOMETRY-QA.md` 2026-07-23 entries, independently re-derived, no
P0/P1/P2) — the row's real residuals (exploded views, flat-not-recursive
BOM, no version pinning, rigid-only sub-assemblies) are unchanged and it
still correctly holds short of ✅. **Drawings** (stays ➖): section views are
now fully end-to-end (kernel `137a929`, a P0 wrong-half defect an
independent geometry-QA audit caught and same-day fixed at `57dca7a`, web
authoring `06fc019`, verified trustworthy-green `b895f73`) — the row's real
residuals (assembly drawings, detail/broken/auxiliary views, auto-dim, GD&T)
are unchanged and it still correctly holds short of ✅. Full evidence in the
row Notes above. Verified directly this pass: `git log`/`git show` on every
cited commit, `docs/GEOMETRY-QA.md`'s three 2026-07-23 PASS entries (assembly
interference, assembly STEP export, assembly STEP import) and its section-view
wrong-half-bug-then-fix entries read in full, `docs/FINDINGS.md` §P3 item #25
read for the exact claim being corrected. No other row touched — Sketching,
Part modeling, Interop, Sheet metal, Performance, Collaboration,
Extensibility, Agent access, Price/freedom unchanged from the tenth pass.

---

Prior pass (2026-07-19, tenth pass this cycle, against
git log through `46788d9` (README status sync). Re-verified every claim
directly: `git show`/`git show --stat` on every commit cited below,
`docs/GEOMETRY-QA.md` and `docs/UI-REVIEW.md`'s 2026-07-19 entries read in
full, `docs/design/sheet-metal.md` re-read for the depth-1-bend-star scope
claim, and the founder-screenshot files confirmed present on disk (not just
referenced). **Sheet metal flips ❌→➖ — the headline event this pass.** The
v1 pillar named "not started" last pass shipped completely end-to-end since:
base flange (`fb555cc`) → edge flange + provenance unfold (`46c05ae`,
`CylindricalFaceSignature`) → flat-pattern drawing view + bend table, backend
(`94db476`) → server-composed (`67097ec`) → rendered (`645f236`) — then
independently geometry-QA'd PASS on bend allowance/area-conservation/
determinism/STEP-round-trip/byte-pinned exports (`5ed73c0`) AND frontend-QA'd
ship-it with a real P2 (screen-vs-export bend-table divergence) closed same
day (`24b1c53`) plus three P3 a11y/token nits closed same day (`2ba4df4`).
Judged ➖ rather than ✅ because the shipped algorithm is an explicit
**depth-1 bend star** — flange-on-a-flange (bend chains, the shape a real
enclosure needs) is out of scope, alongside hem/miter/jog/tab/gauge-tables —
a materially narrower slice of the sheet-metal domain than what earned Part
modeling its ✅. Full evidence and the ✅-vs-➖ reasoning are in the row above;
this is the honest underclaim-over-overclaim call the duty asks for. **Four
other rows had stale residuals from work that shipped since the last VISION.md
edit (`09eb8fc`, 2026-07-17) that this pass corrects, none changing their
score:** Part modeling's "no booleans between independently-built bodies" gap
is CLOSED (multi-body pillar MB-0…MB-4c, geometry-QA'd PASS twice) — Notes
corrected, stays ✅. Assemblies' "only 3 of 5 mate types" and "no BOM" residuals
are CLOSED (distance/angle mates `56d457d`/`5457910`; flat BOM `901dad1`/
`cf617c8`, UI-reviewed PASS `a061c19`) — real residuals remain (collision
detection, exploded views, recursive BOM, assembly STEP IO, version pinning,
rigid sub-assemblies), stays ➖. Interop's "single-solid only" residual is
CLOSED (multi-solid STEP import as one multi-lump body, `919ebcf` MB-4b,
reconciled `0cbdbf6`) — IGES, healing, and named assembly-structure import
remain missing, stays ➖. Drawings' "no server-composed export" and "angular/
point-to-point authoring unbuilt" residuals are CLOSED (server placement
composer + PDF `eff3bf1`/`3dfdb35`/`a77bf77`/`84bf9d3`, DXF `6c82325`/
`42af0d1`, frontend cutover `4644f49`/`03f07e4`; dimension authoring `981c42f`)
— assembly drawings, section/detail views, auto-dimensioning, and GD&T remain
missing, stays ➖. Sketching, Performance, Collaboration, Extensibility, Agent
access, Price/freedom unchanged.

---

Prior pass (2026-07-17, ninth pass this cycle, against
git log through `b8f4bf2` (Drawings v1 export loop closed). **Drawings
flipped ❌→➖**: v1 shipped end-to-end since the eighth pass (document model
`03f2319` → HLR projection `5c4b080`/`d28d557` → evaluate endpoint `d65caff`
→ gateway proxy `1dc1c60` → dimension measurement+provenance `5e16f9d`/
`8b1b47f` → frontend sheet editor `6671ec4` → dimension authoring `78ae196`/
`919d272`/`00e1d1b` → SVG export `4b8d975`), each stage independently
code-reviewed/geometry-QA'd/UI-reviewed and the whole loop e2e-proven live
(`drawings.spec.ts`). Held at ➖, not ✅ — five honest residuals: no
server-composed export (PDF/DXF/byte-stable stored artifact — v1 SVG is a
client-side download), no assembly drawings, no section/detail/auxiliary
views, angular + point-to-point dimension authoring unbuilt (measurement
backend supports both), no GD&T/auto-dimensioning. Full evidence in the row
above. **Sheet metal is a new row this pass, added at ❌**: the founder asked
"anything for sheet metal?" — there is nothing today. Scoped (not built) in
`docs/design/sheet-metal.md`: the flat-pattern unfold is named as the
pillar's genuine kernel risk (OCCT has no turnkey unfold, verified by a live
OCP module probe), with a v1 cut (one provenance-tracked bend, reusing the
shipped extrude/sweep primitives) that avoids the harder general bend-graph
and import-recognition problems. This preps the pillar for a founder
green-light; it does not move the roadmap by itself. No other rows moved
this pass — verification for the re-score was direct: every cited Drawings
commit read via `git show`/`git log`, `apps/web/e2e/drawings.spec.ts` read to
confirm it exercises the real claim against the live stack, and
`docs/design/sheet-metal.md`'s OCP probes re-run live in this session's
geometry `.venv` before being cited (not assumed from prior knowledge).

---

Prior pass (2026-07-15, eighth pass this cycle, against git log through
`e8ecce9`, assembly-mode frontend). **Assemblies flipped ❌→➖**: the v1 MVP landed end-to-end this batch — document model (`fab5115`,
`4a9716c`) → mate solver (`c010ee1`, `c962f73`) → resolution (`40e895f`) →
evaluation (`05f6aa1`, `3cc5c4f`) → gateway (`cc72d23`) → viewport (`e8ecce9`)
— each stage independently code-reviewed and the golden independently
geometry-QA'd (`2d8c82f`, re-derived from scratch, PASS). Verification for
this re-score was direct: every cited commit read via `git show`, the
`assembly-two-plates-bolted` golden and its independent-verification doc
read in full, `apps/web/e2e/assembly.spec.ts` read to confirm it exercises
the real claim against the live stack (not a stub), and the founder
screenshots (`docs/screenshots/assembly-{seed-apart,bolted}-*.png`) opened to
confirm the viewport genuinely renders the multi-instance solve. Held at ➖,
not ✅ — six honest residuals: only 3 of 5 mate types wired (distance/angle
schema'd but unimplemented), no interference/collision detection, no
exploded views, no BOM export, no assembly-level STEP IO, instances track a
part's live tip rather than a pinned version (no immutable part versioning
yet, so a shared part's edit reflows every assembly instancing it), and
sub-assemblies are rigid-only. That is a below-incumbent-parity but genuinely
usable bar — a working engineer can bolt real parts together and see it
solve today — which is exactly what ➖ means, not ✅. No other rows moved
this pass. **Drawings remains the other headline ❌** (product audit's
honest #2, smaller build than Assemblies, next up once Assemblies v1 has
landing room or Ready runs dry). Nearest flips: distance/angle mates +
part-version pinning on Assemblies (➖→ parity-plus candidates before ✅ is
even in reach — collision detection and BOM are the harder parity bar);
spline tangency + fit-point-pair constraint + richer expression grammar on
Sketching; IGES + multi-solid/assembly + blob storage on Interop; multi-body
booleans + feature-tree reorder/suppress on Part modeling; Drawings remains
not-started (Phase 4).

---

Prior pass (2026-07-15, seventh pass this cycle, against git log through
`6dde1c9`, constrainable-spline frontend leg): **Sketching flipped ➖→✅** —
the sixth pass's own Notes named the row's residual as three gaps —
over-constraint diagnosis index-only, no dimension expressions/driving-vs-
driven, non-constrainable splines — and all three shipped backend+frontend
that pass, each independently reviewed (one 🔴 RecursionError-to-500 found
and fixed on the expression evaluator, one 🟡 non-exhaustive constraint-kind
match found and fixed on the spline fit-point pre-scan) and each e2e-proven
on the real stack. Held at ✅ with three honest, narrower residuals: spline
tangency (deferred, needs a native planegcs spline primitive), no direct
fit-point-to-fit-point distance/H/V constraint, and dimension expressions
cover arithmetic only (no trig/units/named functions). Part modeling,
Assemblies, Interop, Drawings, Performance, Collaboration, Extensibility,
Agent access unchanged.

---

Prior pass (2026-07-13, sixth pass this cycle, against git log through
`a015f4e`, STEP-import UI): **Interop flipped ❌→➖** — the fifth pass's own
Notes named the row as "gated entirely on import" — import now ships
end-to-end (kernel `4964fab` → gateway `4b453f1` → UI `a015f4e`), completing
the second direction alongside export (shipped two passes prior). Round-trip
golden `import-step-box-10x20x30` measures 0.0 deviation
import-vs-inverse-of-export; the gateway upload endpoint is auth-gated with a
16 MiB cap enforced before buffering and a prior-body guard; the UI's "Import
STEP" affordance lands the external part as the base body, rendered and
measurable in the viewport, with 5 Playwright specs green on the real stack.
Held short of ✅: STEP-only (no IGES), inline-only representation, single-
solid only, no healing for messy files, untrusted-parse wall-clock bound an
open P1. Sketching held at ➖ (unchanged) — three residual gaps named:
over-constraint diagnosis index-only, no dimension expressions/driving-vs-
driven, splines non-constrained. Part modeling, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged.

---

Prior pass (2026-07-13, fifth pass this cycle, against git log through
`a663db7`, draft authoring UI): **Part modeling flipped ➖→✅** — the four
blockers the pass before it named (predicate-only edge selection, no shell,
no draft, single-body-only) closed three-quarters with QA evidence: click-
specific edge selection (`71e771d`/`c18453c`, e2e 6→7 faces vs. 26 for
all-edges), shell (`617fc7f`/`6cf7a75`, golden exact to 1e-9 with a live-OCCT
material-removed guard), draft (`caec623`/`a663db7`, golden exact to 1e-9,
BRepCheck-swept). The fourth — booleans between independently-built bodies —
stayed unbuilt but scoped as an uncommon-workflow boundary, not a blocker on
the single-connected-solid case most real parts are. Multi-body/booleans,
reorder/suppress, and multi-edge-select carried forward as parity-plus items.
Sketching held at ➖ (unchanged); Interop, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged.

---

Prior pass (2026-07-12, third pass this cycle, against git log through
`1e3d422`): **Sketching flipped ❌→➖** — the profile-authoring/editing-tool
cluster the row itself named as its blocker last pass — trim/extend, offset,
mirror, sketch fillet/chamfer, splines — shipped fully, each backend
independently code-reviewed APPROVE and each with a UI + real-stack e2e
(commits `3710ee9`/`79fee47`, `6036200`/`fa97a14`, `7c7dbc5`/`0768977`,
`a0302e4`/`7297e1b`, `18fe6a8`/`f88df01`, id-collision fix `e9e4450`).
Combined with the constraint set and construction geometry from the pass
before, a working engineer can run a full real sketch session — draw rough,
trim, offset, mirror, round a corner, drop a spline, constrain — without
hitting an impossible operation. Held short of ✅: over-constraint diagnosis
is still index-only (no redundant-vs-conflicting classification), sketch
dimensions have no expressions or driving-vs-driven distinction (unbuilt,
filed in COMPETITIVE.md), and splines are non-constrained v1 fixed geometry.

## Design mandate (founder, 2026-07-09)

**Frontend design is a stated founder priority, on par with geometric
correctness.** The product must look and feel premium, distinctive, and
intentional — a tool engineers are proud to live in all day — never
templated. Operationalized as the standing "Design mandate" section in
`CLAUDE.md` (mandatory `frontend-design` skill for all UI work, token-driven
design system, the viewport as hero, screenshots to the founder). Incumbent
CAD UIs are dated and cluttered; design is a real wedge, alongside the four
structural advantages above.

## What we are NOT building (for now)

- CAM, simulation/FEA, rendering — out of scope until the modeling core is a
  daily driver. Extensibility is the answer for these, not core features.
- A native desktop app. Browser-first; the viewport must earn it.
- Cloud SaaS billing. Self-hosted first; hosted offering is a company
  decision later, not a repo concern.
