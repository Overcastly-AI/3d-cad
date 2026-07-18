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
| Sketching & constraints | ✅ | **Flipped ➖→✅ this pass**: the three residual gaps this row's own prior Notes named as the remaining shortfall — over-constraint diagnosis, dimension expressions/driving-vs-driven, non-constrainable splines — all ship end-to-end this run, each backend+frontend, each independently reviewed and e2e-proven on the real stack (verified directly: `git show`/`git log` on every cited commit, `pytest` on the touched backend suites, `tsc --noEmit` + `vitest` on the touched frontend files, all green; e2e spec bodies read, not assumed). **(1) Over-constraint diagnosis** (`b28dffc`→`c527063`→`c4527f6` backend, `4e6e429` frontend): `sketch_conflicting` and the solved-but-redundant payload both carry a TYPED `SketchConstraintDiagnosis` — `classification` (redundant vs conflicting), `removable`, named offending ids, and a `suggested_fix` ("Remove constraint N") — matching the incumbents' diagnostic-not-just-error-message UX. The frontend reads the typed field directly; the brittle regex `parseConflictIndices` over the human message string is deleted outright (confirmed: only a code-comment mentioning its removal remains in the tree). Proven in `test_evaluate_tree.py` and e2e `constraints.spec.ts`. **(2) Dimension expressions + driving/driven** (`72ad936` backend, `398fb12` security hardening, `196c89c` frontend): a dimension value is a literal, a named-dimension reference, or a `+ - * / ( )` expression, evaluated by a safe recursive-descent parser (`geometry/sketch/expression.py` — confirmed no `eval` call anywhere in the module) with cycle/unknown-ref/div-zero detection; a code-review 🔴 (RecursionError on a pathological expression escaping as a 500) was found and closed with a request-boundary length cap plus depth guards on both the parser and the AST evaluator. `driving`/`driven` dims are distinct: driven dims are excluded from the solver and render read-only in parentheses, measured back from solved geometry. Proven in `test_sketch_expression.py` (`width=20, height="width/2"→10`, driven-tracks-without-over-constraining) and e2e `dimension-expressions.spec.ts`; founder screenshots (`dimension-expression-*.png`) show the brass "= 10 mm" resolved echo and the driven `(20)` reference readout live in the sketcher. **(3) Constrainable splines** (`dda86eb` backend, `5e7311e` review hardening, `6dde1c9` frontend): a spline's fit points are addressable solver points (`EntityPointRef.point:"fitN"`); coincident/fixed/symmetric apply directly, distance/H/V via a coincident-linked line; only *referenced* fit points enter the solver so an unconstrained spline stays byte-identical (backward-compat golden green). e2e `spline-constraint.spec.ts` and its screenshots show a fit point pulled onto a fixed line endpoint, visibly reshaping the curve. This closes the prior pass's literal wording — "splines are v1 non-constrained" is no longer true. **Held at ✅, not pushed to "no residuals"** — three honest, narrower items remain, none of which block the daily-driver session the way the closed gaps did: (a) spline **tangency** (G1 continuity to a line/arc) is explicitly deferred pending a native spline primitive in planegcs — real, and the one incumbent-standard spline capability still missing, but positional/coincidence constraining (the more load-bearing case: closing a loop, anchoring a fit point to the rest of the profile) now works, and most of Loft's target mechanical parts (brackets/housings/ducts) use splines sparingly and rarely need tangent-blended curves the way industrial-design surfacing does; (b) distance/H/V directly between two fit points has no dedicated point-pair constraint kind and must go through the linked-line gesture — a workaround, not a wall; (c) dimension expressions cover arithmetic only, no trig/units/named functions — covers the overwhelming majority of real parametric relationships (spacing, halving, ratios) but not gear/angle-driven formulas. These are parity-plus items for the forward backlog, not blockers — the same standard applied when Part modeling flipped ➖→✅ with multi-body boolean left open as a scope boundary, not a hold. |
| Part modeling (features, history) | ✅ | **Flipped ➖→✅ this pass**: the prior pass held this row short of ✅ on four named blockers — predicate-only edge selection, no shell, no draft, single-body-only. Three are now closed with QA evidence; the fourth is a real, honestly-scoped scope boundary, not a hole in the daily-driver workflow. **Click-specific edge selection** (`71e771d` backend + `c18453c` UI, both reviewed APPROVE): a stage-1 edge `SubshapeRef` lets an engineer click ONE edge and fillet/chamfer it while its neighbours stay sharp — e2e-proven (`fillet-edge-pick.spec.ts`: a single-edge fillet on a 20 mm cube adds exactly one face, 6→7, vs. 26 for an all-edges fillet; re-resolves after reload via the rebuild-surviving signature). The `all_edges`/`axis_parallel`-only limitation named last pass is closed. **Shell** (`617fc7f` backend + `6cf7a75` UI, reviewed): hollows a body to a uniform wall thickness with picked faces left open, reusing the same `SubshapeRef` face machinery sketch-on-face proved. GEOMETRY-QA's `shell-open-top-box-40x25x10-t2` golden is exact to 1e-9 and — notably — the review process found and closed a real correctness risk: OCCT's `MakeThickSolid` can silently return the un-hollowed body on a bad thickness, so `shell_thickness_too_large` is a load-bearing material-removed invariant guard, not a cosmetic error path (GEOMETRY-QA 2026-07-13). **Draft** (`caec623` backend + `a663db7` UI, reviewed): tapers picked faces by an angle about a neutral plane. Golden `draft-frustum-box-40x40x20-5deg` reproduces the hand-derived analytic frustum to 1e-9, and the review swept the full ±angle range through `BRepCheck_Analyzer` and confirmed draft's failure mode is always a hard OCCT raise, never shell's silent-bad-body risk — so no extra guard was needed, and that finding is itself recorded evidence the row isn't being taken on faith. Combined with holes (multi-loop cut, prior pass) and multi-plane/sketch-on-face (prior pass), the feature set for a SINGLE connected solid is now genuinely comprehensive: sketch → extrude/revolve/sweep/loft → fillet/chamfer(click-specific-edge) → pattern → shell → draft → holes, on origin planes, offset planes, or a picked model face, with a real (stage-1) topological-naming reference surviving rebuilds throughout. That is what a working engineer models the overwhelming majority of real mechanical parts with — brackets, housings, shafts, plates, ducts, enclosures — because most real parts are one connected solid with local features, not an assembly-of-bodies collapsed into one file. **The one remaining gap, and it's real:** no booleans between independently-built bodies (union/subtract/intersect two separate solids) — a part that is genuinely multiple lumps combined (e.g. a casting merged with a machined boss modeled as a separate body, or a subtractive multi-tool cut) can't be built. That's a scope boundary on an uncommon workflow, not a blocker on the common one, which is why this earns ✅ rather than holding at ➖ for a gap most parts never hit. Two history-editing niceties also remain unshipped (reorder/suppress/patch-a-mid-tree-feature; edge selection still lacks a compound multi-edge picker) — real but smaller than what closed this pass. Multi-body/boolean, reorder/suppress, and multi-edge-select are the honest ➖-vs-incumbent-parity-plus items, tracked as their own forward BACKLOG, not blockers on this row. |
| Assemblies & mates | ➖ | **Flipped ❌→➖ this pass**: the v1 MVP shipped end-to-end and is independently reviewed + QA'd at every stage. **Document model** (`fab5115` + `4a9716c` hardening): assembly/instance/mate tables, `py_kit.schemas.assemblies`, owner-auth'd CRUD with OCC + write-time acyclicity, a per-owner advisory lock closing a TOCTOU on concurrent mate-cycle checks, cross-document 409-on-delete-with-dependents. **Mate solver** (`c010ee1` + `c962f73` hardening): our OWN deterministic 3D rigid-body solver — no GPL dependency (SolveSpace/py-slvs are GPLv3, deliberately rejected) — quaternion 6-DOF, a closed-form tree fast path plus a numpy-only damped LM fallback, BLAS pinned for byte-identical cross-machine determinism, and the same well/under/over/conflicting diagnosis vocabulary as the sketch solver. **Resolution** (`40e895f`): mates reference real geometry via the SAME `PlanarFaceSignature`/`EdgeSignature` topological-naming machinery sketch-on-face proved, producing the first real bolted solve at ~1e-8. **Evaluation** (`05f6aa1` + `3cc5c4f` never-500 fix): the full pipeline — evaluate each unique part once → resolve mate geometry → solve → shared-mesh tessellation — with the `assembly-two-plates-bolted` golden **independently geometry-QA'd PASS** (`2d8c82f`: solved pose and mass roll-up re-derived from scratch, not read from `expected.json`; worst deviation 1.18e-8 vs. a 1e-6 bound; byte-deterministic across fresh interpreters; shared-mesh dedup confirmed to one mesh id). **Gateway** (`cc72d23`): CRUD + evaluate proxies, every route auth-gated (parametrized 401-per-route). **Viewport** (`e8ecce9`): assembly mode renders multiple instances at solved transforms with shared-mesh dedup, mate authoring by picking faces/holes (coincident/concentric/lock) with a snap-on-solve animation, and a solve-status/DOF readout; e2e `assembly.spec.ts` passes live against the real stack (instance a part twice, author mates, assert seed-apart→bolted), founder screenshots at `docs/screenshots/assembly-{seed-apart,bolted}-{desktop,laptop}.png`. **Held at ➖, not ✅ — the real residuals:** only 3 of 5 schema'd mate types are wired (lock/coincident/concentric; distance/angle are schema-present but unimplemented, a fast-follow not a redesign); no interference/collision detection; no exploded views; no BOM export; no STEP import/export at the assembly level (single-part STEP only); instances reference a part's current TIP, not a pinned version, so an edit to a shared part silently reflows every assembly that instances it — deterministic evaluation of a FROZEN assembly, not yet deterministic across part history (immutable part versioning is a separate, unbuilt item); sub-assemblies are rigid-only (no nested-assembly mate re-solve). A working engineer can genuinely bolt two real parts together and watch it solve today — that clears the daily-driver bar for the common two-or-three-part case — but on the above it sits below SolidWorks/Fusion/Onshape assembly parity, which is exactly what ➖ means. |
| Interop (STEP/IGES/STL) | ➖ | **Flipped ❌→➖ this pass**: the prior Notes named the flip as "gated entirely on import" — import now ships end-to-end, so both directions work. **Kernel** (`4964fab`): an external STEP part comes in as a body-affecting BASE `import` feature (inline params); round-trip golden `import-step-box-10x20x30` asserts import ≡ inverse-of-export at tol 1e-7, **measured 0.0 deviation**, byte-deterministic across interpreter restarts (docstring honesty-corrected at `250ac4e`). **Gateway** (`4b453f1`): `POST /api/v1/parts/{id}/features/import` — auth-gated, 16 MiB cap enforced at 422 BEFORE the body is buffered/parsed, a prior-body guard (import must be the base feature), contracts regenerated. **UI** (`a015f4e`): "Import STEP" leads the Create strip (a base-only move, disabled once a body exists); a file-picker lands the external part as the base body, rendered in the viewport and measurable (OCCT mass-props: 6,000 mm³ / 10×20×30), re-exportable, and reload-persistent. Playwright e2e on the real stack (`import-step.spec.ts`, 5 specs green): valid STEP → body in tree+viewport+reload-persist; non-STEP file → legible error, no body; oversize file → rejected client-side before upload; desktop + 1280×800 screenshots (`docs/screenshots/import-step-*`). Combined with export (already shipped, prior pass), a working engineer can now bring a real external STEP part IN, model on it (fillet/shell/sketch-on-face all work via the existing topological-naming machinery), and export it back OUT. **Held at ➖, not ✅ — the honest gaps:** (1) STEP-only, no IGES either direction; (2) inline-only representation — large files bloat the feature-tree JSON, the blob-backed `kind:"blob"` successor is seeded in the design doc but unshipped; (3) single-solid only — multi-solid/assembly/compound STEP files are rejected with a legible error, not imported; (4) no mesh/sew/repair healing for messy real-world CAD (v1 is "one legible solid or a clear error," not a healing pipeline); (5) the untrusted-parse wall-clock/DoS bound is a tracked **P1** fast-follow — the 16 MiB cap bounds memory, not parse time, so an adversarial STEP file can still pin a worker. |
| Drawings & documentation | ➖ | **Flipped ❌→➖ this pass**: Drawings v1 shipped end-to-end since the last re-score, closing the product audit's honest #2. **Document model** (`03f2319`): `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables, owner-scoped CRUD, dimensions naming model geometry via the reused `EdgeSignature` (no parallel taxonomy). **HLR projection** (`5c4b080`, geometry-QA `d28d557`, review fix `cdf7e60`): exact `HLRBRep_Algo` → canonically-ordered visible/hidden 2D edges, byte-deterministic across an interpreter restart, 4 analytic goldens (a box's front view is exactly a 40×10 rectangle; a through-hole projects a TRUE circle, not a facet fan). **Evaluate endpoint** (`d65caff`) + **gateway proxy** (`1dc1c60`): the part body evaluated once, projected per view, every route auth-gated. **Dimension measurement + provenance** (`5e16f9d`, independently geometry-QA'd `8b1b47f`, hardened `6f90c19`): each sharp projected edge tagged back to its originating model `EdgeSignature` by geometric re-matching (HLR's own output compounds carry no per-edge tag — a documented OCP-wheel finding, not a shortcut); `linear`/`diameter`/`radius`/`angular` dimensions measure the MODEL-true value off the exact B-rep, with an honest `foreshortened` flag and typed never-a-500 errors. **Frontend sheet editor** (`6671ec4`, layout fix `86dd0ec`, spot-audited `3a8fd03`): one action auto-lays-out the standard four (front/top/right third-angle + iso) as scale-correct SVG on the "paper on the bench" surface. **Dimension authoring** (`78ae196`, UI-reviewed `919d272`, fixed `00e1d1b`): pick a dimensionable edge → gated type menu → persists → renders as a real drafting annotation (extension/dimension lines, arrowheads, MODEL-true value). **SVG export** (`4b8d975`): the rendered sheet serializes client-side to a standalone, scale-correct `.svg` — an explicit, honest architecture call (design doc §4.1a) to reuse the shipped renderer rather than build a second Python drafting composer, deferring server-composed PDF/DXF. Every stage e2e-proven on the real stack (`drawings.spec.ts`), founder screenshots present. **Held at ➖, not ✅ — the honest residuals:** no server-composed export (PDF/DXF, or a content-addressed byte-stable stored artifact — v1 SVG is a client-side download only); no assembly drawings (part drawings only — the projection pipeline already handles a compound per the design doc, but it's unwired); no section/detail/broken/auxiliary views (orthographic + iso only); angular and point-to-point-linear dimension AUTHORING is unbuilt in the UI though the measurement backend supports both types; no auto-dimensioning; no GD&T/tolerances/surface-finish/weld symbols; no drag-to-place (dimensions auto-place at a fixed offset). A working engineer can genuinely hand a machinist a dimensioned print of a single real part today — that clears the daily-driver bar for the single-part case, which is exactly what ➖ means, not below-bar ❌ nor incumbent-parity ✅. Full design doc: `docs/design/drawings.md`. |
| Sheet metal | ❌ | **New row this pass.** Not started — no base/edge flange, no bend, no flat-pattern unfold, no bend table. Matters because sheet metal (brackets, enclosures, chassis) is a large share of real mechanical parts and today has zero answer — a working engineer modeling a bracket that needs to be laser-cut-and-bent from a real gauge of steel has nothing here. **Scoped, not built**: `docs/design/sheet-metal.md` (vision-steward, 2026-07-17) names the genuine kernel risk plainly — OCCT ships no turnkey flat-pattern unfold (verified: no `Unfold`/`Sheet`/`Develop`/`Flatten` module in OCP, live probe) — and proposes a v1 scoped to a single provenance-tracked bend (base flange + one edge flange, reusing the shipped `extrude`/`sweep` kernel primitives) with an analytic unfolded-length + area-conservation golden, deferring multi-bend graphs, miter/hem/jog/tab, gauge tables, and import-recognition. Not yet endorsed or sequenced onto the roadmap — a candidate for founder green-light. |
| Performance on real parts | ❌ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

Every row starts ❌ except the structural one. That's the honest baseline;
the loop's job is to flip rows and never let this table go stale.

Last re-scored 2026-07-17 (vision-steward), ninth pass this cycle, against
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
