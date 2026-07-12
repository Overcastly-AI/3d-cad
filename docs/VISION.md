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
| Part modeling (features, history) | ❌ | Feature breadth roughly doubled this pass — now 8 body-affecting features (extrude, revolve, fillet, chamfer, linear/circular pattern, sweep, loft) against the prior pass's 3, each golden-covered and reviewed: pattern (backend `ec3f4f7`, UI `5777656`), sweep — profile along an open path wire (backend `e1a8a1e`, UI `e2b8532`, e2e `sweep.spec.ts`), loft — solid through ≥2 ordered sections including loft-to-apex (backend `f287aa1`, golden `loft-pyramid-sq20-h30`). Still ❌, and the gap is now sharper than "few features": (1) edge selection is still predicate-only (`all_edges`/`axis_parallel`), not click-a-specific-edge — gated on topological naming (Phase 2), so an engineer still can't selectively round one edge and leave its neighbor sharp; (2) no hole/shell/draft feature and single-body only, no booleans between independent bodies; (3) a newly-surfaced foundational limit blocks most real multi-plane parts: sketches can only be placed on the 3 origin datum planes — confirmed in code, `apps/web/src/sketch/plane.ts`'s `DATUM_PLANES` is hardcoded to `["XY","XZ","YZ"]`, and `services/geometry/src/geometry/features/evaluate.py` explicitly rejects a feature-referenced sketch plane ("Sketch planes must be datum planes (XY/XZ/YZ) in v1"). No offset or on-face plane exists, which is also *why loft shipped with no UI this pass* — you can't sketch the second/third section anywhere a real loft needs it (offset from the base, or on a face) without this. A pyramid running through the three origin planes proves the kernel op; a real loft (e.g. a duct transition between two non-coplanar faces) still can't be authored end-to-end. The core loop (sketch→extrude→fillet/chamfer→edit→rollback→export) plus the wider feature set are real and usable for parts built entirely on the 3 origin planes; anything requiring an offset/face-based sketch plane — most real parts — cannot be modeled today. |
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

Last re-scored 2026-07-12 (vision-steward), third pass this cycle, against
git log through `1e3d422` (splines draw tool + screenshot refresh) plus
`docs/GEOMETRY-QA.md` and the worked e2e suite (`sketch-trim-extend.spec.ts`,
`sketch-offset.spec.ts`, `sketch-mirror.spec.ts`, `sketch-fillet-chamfer.spec.ts`,
`sketch-spline.spec.ts`, `sweep.spec.ts`, `pattern.spec.ts`). **Sketching
flipped ❌→➖**: the profile-authoring/editing-tool cluster the row itself
named as its blocker last pass — trim/extend, offset, mirror, sketch fillet/
chamfer, splines — is now fully shipped, each backend independently
code-reviewed APPROVE and each with a UI + real-stack e2e (commits `3710ee9`/
`79fee47`, `6036200`/`fa97a14`, `7c7dbc5`/`0768977`, `a0302e4`/`7297e1b`,
`18fe6a8`/`f88df01`, id-collision fix `e9e4450`). Combined with last pass's
relational-constraint set and construction geometry, a working engineer can
now run a full real sketch session — draw rough, trim, offset, mirror, round
a corner, drop a spline, constrain — without hitting an impossible operation.
Held short of ✅: over-constraint diagnosis is still index-only (no
redundant-vs-conflicting classification), sketch dimensions have no
expressions or driving-vs-driven distinction (unbuilt, filed in
COMPETITIVE.md), and splines are non-constrained v1 fixed geometry. **Part
modeling re-scored, held at ❌** despite feature count roughly doubling (3→8:
+pattern, +sweep, +loft — commits `ec3f4f7`/`5777656`, `e1a8a1e`/`e2b8532`,
`f287aa1`): still predicate-only edge selection (gated on topological
naming), no hole/shell/draft, single-body-only, and a newly-surfaced
foundational blocker — sketches can only be placed on the 3 origin datum
planes (`apps/web/src/sketch/plane.ts` `DATUM_PLANES`; `evaluate.py` rejects
any feature-referenced plane), which is why loft shipped backend-only with no
UI this pass and why most real multi-plane parts still can't be authored.
Interop and Measurement: export-only interop is unchanged (➖ still gated on
import, Phase 4); the transient distance/angle measure tool (commits
`0bdc434`/`ee8f89f`/`47a4188`) shipped full-stack but measurement isn't a
scorecard row of its own — it's read into the Part modeling/Sketching
narrative above as workflow-support evidence, not a row flip. Nearest flips
for Phase 2: over-constraint classification + dimension expressions on
Sketching (➖→✅ candidates); offset/face datum planes + click-specific edge
selection on Part modeling (❌→➖ candidates); Interop-import (Phase 4).

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
