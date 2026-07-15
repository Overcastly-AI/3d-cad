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
| Assemblies & mates | ❌ | Not started (Phase 3) |
| Interop (STEP/IGES/STL) | ➖ | **Flipped ❌→➖ this pass**: the prior Notes named the flip as "gated entirely on import" — import now ships end-to-end, so both directions work. **Kernel** (`4964fab`): an external STEP part comes in as a body-affecting BASE `import` feature (inline params); round-trip golden `import-step-box-10x20x30` asserts import ≡ inverse-of-export at tol 1e-7, **measured 0.0 deviation**, byte-deterministic across interpreter restarts (docstring honesty-corrected at `250ac4e`). **Gateway** (`4b453f1`): `POST /api/v1/parts/{id}/features/import` — auth-gated, 16 MiB cap enforced at 422 BEFORE the body is buffered/parsed, a prior-body guard (import must be the base feature), contracts regenerated. **UI** (`a015f4e`): "Import STEP" leads the Create strip (a base-only move, disabled once a body exists); a file-picker lands the external part as the base body, rendered in the viewport and measurable (OCCT mass-props: 6,000 mm³ / 10×20×30), re-exportable, and reload-persistent. Playwright e2e on the real stack (`import-step.spec.ts`, 5 specs green): valid STEP → body in tree+viewport+reload-persist; non-STEP file → legible error, no body; oversize file → rejected client-side before upload; desktop + 1280×800 screenshots (`docs/screenshots/import-step-*`). Combined with export (already shipped, prior pass), a working engineer can now bring a real external STEP part IN, model on it (fillet/shell/sketch-on-face all work via the existing topological-naming machinery), and export it back OUT. **Held at ➖, not ✅ — the honest gaps:** (1) STEP-only, no IGES either direction; (2) inline-only representation — large files bloat the feature-tree JSON, the blob-backed `kind:"blob"` successor is seeded in the design doc but unshipped; (3) single-solid only — multi-solid/assembly/compound STEP files are rejected with a legible error, not imported; (4) no mesh/sew/repair healing for messy real-world CAD (v1 is "one legible solid or a clear error," not a healing pipeline); (5) the untrusted-parse wall-clock/DoS bound is a tracked **P1** fast-follow — the 16 MiB cap bounds memory, not parse time, so an adversarial STEP file can still pin a worker. |
| Drawings & documentation | ❌ | Not started (Phase 4) |
| Performance on real parts | ❌ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

Every row starts ❌ except the structural one. That's the honest baseline;
the loop's job is to flip rows and never let this table go stale.

Last re-scored 2026-07-15 (vision-steward), seventh pass this cycle, against
git log through `6dde1c9` (constrainable-spline frontend leg) plus
`constraints.spec.ts`, `dimension-expressions.spec.ts`, and
`spline-constraint.spec.ts`. **Sketching flipped ➖→✅**: the sixth pass's
own Notes named the row's residual as three gaps — over-constraint diagnosis
index-only, no dimension expressions/driving-vs-driven, non-constrainable
splines — and all three shipped backend+frontend this pass, each
independently reviewed (one 🔴 RecursionError-to-500 found and fixed on the
expression evaluator, one 🟡 non-exhaustive constraint-kind match found and
fixed on the spline fit-point pre-scan) and each e2e-proven on the real stack.
Verification for this re-score was direct, not delegated: every cited commit
read via `git show`, the touched backend suites (`test_evaluate_tree.py`,
`test_sketch_expression.py`, `test_sketch_spline.py`) run and green, frontend
`tsc --noEmit` and the touched `vitest` files (`constraints.test.ts`,
`pick.test.ts`, 62/62) run and green, the three e2e spec bodies read to
confirm they exercise the real claim (not stubs), and the founder screenshots
opened to confirm the UI genuinely renders the driven-dimension parentheses
and the resolved-expression echo. Held at ✅ with three honest, narrower
residuals (not held back for them, same standard as Part modeling's
multi-body-boolean scope boundary): spline tangency (deferred, needs a native
planegcs spline primitive), no direct fit-point-to-fit-point distance/H/V
constraint (routes through the linked-line gesture instead), and dimension
expressions cover arithmetic only (no trig/units/named functions). No other
rows moved this pass — no commits touching Part modeling, Assemblies,
Interop, Drawings, Performance, Collaboration, Extensibility, or Agent
access. Nearest flips: spline tangency + fit-point-pair constraint + richer
expression grammar on Sketching (✅→ parity-plus candidates, tracked BACKLOG
Later, not scorecard-gating); IGES + multi-solid/assembly + blob storage on
Interop; multi-body booleans + feature-tree reorder/suppress on Part
modeling; Assemblies/mates and Drawings remain not-started (Phase 3/4).

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
