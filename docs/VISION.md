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
| Sketching & constraints | ➖ | **Flipped ❌→➖ this pass**: the profile-authoring/editing-tool cluster this row's own prior Notes named as the remaining blocker now ships end-to-end, each independently code-reviewed APPROVE with a real-stack e2e. Trim/extend (backend `3710ee9`, UI `79fee47`, e2e `sketch-trim-extend.spec.ts`) ends "every vertex must be placed exactly." Offset (backend `6036200`, UI `fa97a14`, e2e `sketch-offset.spec.ts`) adds the parallel-curve-at-distance used for ribs/webs/walls. Mirror (backend `7c7dbc5`, UI `0768977`, e2e `sketch-mirror.spec.ts`) replaces hand-adding one `symmetric` constraint per point-pair. Sketch fillet/chamfer corner tools (backend `a0302e4` + non-90° coverage `97f9bbb`, UI `7297e1b`, e2e `sketch-fillet-chamfer.spec.ts`) make a rounded corner one click instead of a manually-placed-and-twice-constrained tangent arc. Splines (backend `18fe6a8`, UI `f88df01`, e2e `sketch-spline.spec.ts`) close what the prior pass called "a hard capability gap, not an ergonomics one": an interpolating C2 B-spline through fit points that extrudes into a real curved B-rep face. An id-collision fix (`e9e4450`) hardened trim under reuse. Combined with last pass's full relational-constraint set (tangent/perpendicular/parallel/equal/symmetric/concentric) and construction geometry, a working engineer can now run a complete real sketch session — rough-draw, trim/clean-up, offset a wall, mirror a symmetric half, round a corner, drop in a free-form curve, constrain it — without hitting a flatly-impossible operation. That earns parity, not ✅: two gaps remain, both real but narrower than "half the toolkit is missing." (1) Over-constraint *diagnosis* is still index-only (`sketch_conflicting` reports raw constraint indices; `planegcs_solver.py` does carry `redundant` internally but it isn't surfaced as the incumbents' redundant-vs-conflicting classification with a suggested fix) — an engineer debugging a bad sketch gets a list of numbers, not a diagnosis. (2) Sketch dimensions take only a literal value — no expressions (`width/2`) and no driving-vs-driven distinction (COMPETITIVE.md, unbuilt) — so parametric relationships between dimensions must be hand-solved instead of typed. (3) Splines are v1 non-constrained (fixed geometry once drawn; `18fe6a8`'s own commit message: "planegcs has no spline primitive"). None of these three block *drawing and extruding a real profile* the way the missing tools did; they block *editing it fluently over a session*, which is why this is ➖ (real parity on session tooling) and not ✅ (incumbents still out-diagnose and out-parameterize us). |
| Part modeling (features, history) | ✅ | **Flipped ➖→✅ this pass**: the prior pass held this row short of ✅ on four named blockers — predicate-only edge selection, no shell, no draft, single-body-only. Three are now closed with QA evidence; the fourth is a real, honestly-scoped scope boundary, not a hole in the daily-driver workflow. **Click-specific edge selection** (`71e771d` backend + `c18453c` UI, both reviewed APPROVE): a stage-1 edge `SubshapeRef` lets an engineer click ONE edge and fillet/chamfer it while its neighbours stay sharp — e2e-proven (`fillet-edge-pick.spec.ts`: a single-edge fillet on a 20 mm cube adds exactly one face, 6→7, vs. 26 for an all-edges fillet; re-resolves after reload via the rebuild-surviving signature). The `all_edges`/`axis_parallel`-only limitation named last pass is closed. **Shell** (`617fc7f` backend + `6cf7a75` UI, reviewed): hollows a body to a uniform wall thickness with picked faces left open, reusing the same `SubshapeRef` face machinery sketch-on-face proved. GEOMETRY-QA's `shell-open-top-box-40x25x10-t2` golden is exact to 1e-9 and — notably — the review process found and closed a real correctness risk: OCCT's `MakeThickSolid` can silently return the un-hollowed body on a bad thickness, so `shell_thickness_too_large` is a load-bearing material-removed invariant guard, not a cosmetic error path (GEOMETRY-QA 2026-07-13). **Draft** (`caec623` backend + `a663db7` UI, reviewed): tapers picked faces by an angle about a neutral plane. Golden `draft-frustum-box-40x40x20-5deg` reproduces the hand-derived analytic frustum to 1e-9, and the review swept the full ±angle range through `BRepCheck_Analyzer` and confirmed draft's failure mode is always a hard OCCT raise, never shell's silent-bad-body risk — so no extra guard was needed, and that finding is itself recorded evidence the row isn't being taken on faith. Combined with holes (multi-loop cut, prior pass) and multi-plane/sketch-on-face (prior pass), the feature set for a SINGLE connected solid is now genuinely comprehensive: sketch → extrude/revolve/sweep/loft → fillet/chamfer(click-specific-edge) → pattern → shell → draft → holes, on origin planes, offset planes, or a picked model face, with a real (stage-1) topological-naming reference surviving rebuilds throughout. That is what a working engineer models the overwhelming majority of real mechanical parts with — brackets, housings, shafts, plates, ducts, enclosures — because most real parts are one connected solid with local features, not an assembly-of-bodies collapsed into one file. **The one remaining gap, and it's real:** no booleans between independently-built bodies (union/subtract/intersect two separate solids) — a part that is genuinely multiple lumps combined (e.g. a casting merged with a machined boss modeled as a separate body, or a subtractive multi-tool cut) can't be built. That's a scope boundary on an uncommon workflow, not a blocker on the common one, which is why this earns ✅ rather than holding at ➖ for a gap most parts never hit. Two history-editing niceties also remain unshipped (reorder/suppress/patch-a-mid-tree-feature; edge selection still lacks a compound multi-edge picker) — real but smaller than what closed this pass. Multi-body/boolean, reorder/suppress, and multi-edge-select are the honest ➖-vs-incumbent-parity-plus items, tracked as their own forward BACKLOG, not blockers on this row. |
| Assemblies & mates | ❌ | Not started (Phase 3) |
| Interop (STEP/IGES/STL) | ❌ | Half-flipped, deepened but not flipped. EXPORT now covers what an engineer actually MODELS, not just bare primitives: `POST /api/v1/export/tree` (gateway `POST /api/v1/parts/{id}/export?format=`) evaluates a sketch→extrude→fillet/chamfer tree and exports the last-good body, byte-deterministic, tree goldens round-tripped at 0.0 (extrude/chamfer) and 1.26e-10 (fillet), the download proven through a real browser in the Phase 1 exit-gate e2e (commits aad27d9/ff6b226, GEOMETRY-QA 2026-07-11). IMPORT still doesn't exist (Phase 4) — an engineer cannot bring a real STEP/IGES file from another tool IN, only export what was built here. No IGES either direction. ➖ requires both directions; the flip is gated entirely on import. |
| Drawings & documentation | ❌ | Not started (Phase 4) |
| Performance on real parts | ❌ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

Every row starts ❌ except the structural one. That's the honest baseline;
the loop's job is to flip rows and never let this table go stale.

Last re-scored 2026-07-13 (vision-steward), fifth pass this cycle, against
git log through `a663db7` (draft authoring UI) plus `docs/GEOMETRY-QA.md`
and the e2e suite (`fillet-edge-pick.spec.ts`, `shell.spec.ts`,
`draft.spec.ts`, plus the prior passes' specs). **Part modeling flipped
➖→✅**: the four blockers the prior pass named — predicate-only edge
selection, no shell, no draft, single-body-only — are three-quarters closed
with QA evidence this pass. Click-specific edge selection (`71e771d`/
`c18453c`) lets an engineer round exactly one edge and leave neighbours
sharp (e2e: 6→7 faces vs. 26 for all-edges). Shell (`617fc7f`/`6cf7a75`)
hollows to a wall thickness with a live-OCCT-verified material-removed guard
(golden exact to 1e-9). Draft (`caec623`/`a663db7`) tapers picked faces by an
angle, golden exact to 1e-9, with a BRepCheck sweep confirming OCCT never
silently mis-builds a draft. That closes three of the four named blockers;
the fourth — booleans between independently-built bodies — remains unbuilt,
but is a scope boundary on an uncommon "assembly of separate bodies in one
file" workflow, not a blocker on the common "one connected solid with local
features" workflow the vast majority of real mechanical parts are. The
single-body feature set is now comprehensive end-to-end (sketch → extrude/
revolve/sweep/loft → fillet/chamfer(click-edge) → pattern → shell → draft →
holes, on origin/offset/face-picked planes, with a rebuild-surviving stage-1
naming reference throughout) — enough that a working engineer can model a
real bracket/housing/shaft/duct-class part today, which earns ✅ over holding
at ➖ for a gap most single-part modeling sessions never hit. Multi-body/
booleans, feature-tree reorder/suppress, and multi-edge-select are recorded
as the honest parity-plus items still open, tracked as forward BACKLOG, not
as blockers on this row. **Sketching held at ➖** (unchanged — no
sketching-cluster commits this pass). Interop, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged — no
commits touching those rows this pass. Nearest flips: multi-body booleans +
feature-tree reorder/suppress on Part modeling (✅→superiority candidates,
lower urgency now the row is ✅); over-constraint classification + dimension
expressions on Sketching (➖→✅ candidates); Interop-import (Phase 4);
Assemblies/mates and Drawings (Phase 3/4, not started).

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
