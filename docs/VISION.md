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
| Sketching & constraints | ❌ | Real sketcher now exists and closes the loop: plane pick, click-to-place line/rect/circle/arc, 6 constraint kinds (coincident/horizontal/vertical/distance/radius/fixed) with keyboard verbs, live save→solve→render, DOF readout, conflict diagnostics, dimension-edit-moves-corners proven e2e (commits 91fa1d1/75f0214, 25/25 Playwright). Still behind daily-driver parity: no tangent/perpendicular/parallel/equal/symmetric/concentric constraints (nothing to relate an arc to a line — most real parts need these), no trim/extend, no offset, no construction geometry, no mirror/pattern, no sketch fillet/chamfer. An engineer can rough out a simple closed profile; cannot yet sketch the kind of part that needs tangent-constrained fillets or symmetric construction geometry, which is most of them. |
| Part modeling (features, history) | ❌ | Feature tree persists and evaluates server-side; extrude (add/cut) is the first body-affecting feature, shipped end-to-end with a golden (`sketch-extrude-40x25x10`, 1e-9 mass-props tolerance, 0.0-deviation STEP round-trip — commit 11eaa65, GEOMETRY-QA 2026-07-11). Correctness is proven, but the daily-driver loop is still broken: the extruded body does not render in the viewport (mesh-fetch proxy unshipped — an engineer extrudes and sees nothing), there is no feature-tree edit/rollback UI (features are API-only, no way to go back and change a step), no fillet/chamfer (the single most common secondary feature on real parts), and no parts-home UI (workspace is direct-URL-only). Extrude is real geometry, not yet a usable modeling loop. |
| Assemblies & mates | ❌ | Not started (Phase 3) |
| Interop (STEP/IGES/STL) | ❌ | Half-flipped. EXPORT: shipped + QA-verified end-to-end (STEP/STL endpoints byte-deterministic; endpoint-level STEP round-trip 0.0 deviation; real-browser download e2e — commits 12e7b4e/c5e2b1e/8cd63d5, GEOMETRY-QA 2026-07-10). IMPORT: not started (Phase 4). No IGES; only box/cylinder shapes exist to export. Not parity until an engineer can bring a real part IN. |
| Drawings & documentation | ❌ | Not started (Phase 4) |
| Performance on real parts | ❌ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

Every row starts ❌ except the structural one. That's the honest baseline;
the loop's job is to flip rows and never let this table go stale.

Last re-scored 2026-07-11 (vision-steward) against git log + `docs/GEOMETRY-QA.md`
+ the BACKLOG changelog. Sketching and Part modeling both stay ❌ despite real
shipped, QA-verified capability (sketcher authoring/constraints/solve loop;
extrude add/cut with a 0.0-deviation STEP-round-tripped golden) — an
aspirational ➖ would poison prioritization. Sketching is behind on
constraint/editing vocabulary (no tangent/perpendicular/parallel/equal/
symmetric, no trim/offset/construction geometry) that most real parts need;
Part modeling is behind because the one feature that exists doesn't render in
the viewport and can't be edited or rolled back once built. Interop
deliberately stays ❌ despite a QA-verified export path: ➖ means parity with
tools that all import STEP, and import doesn't exist here. Nearest flips:
close the extrude-render/rollback gap on Part modeling, widen the constraint
vocabulary on Sketching, then Interop-import (Phase 4).

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
