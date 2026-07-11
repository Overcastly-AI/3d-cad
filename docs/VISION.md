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
| Sketching & constraints | ❌ | Big jump this cycle, still short of parity — kept ❌, not flipped to ➖. The full 6-new-kind relational vocabulary the row's own prior note named as its gap now ships and is solver-verified: tangent/perpendicular/parallel (commits d214c9d/d41d51a) and equal/symmetric/concentric (a968dbe/9554273), each with a keyboard verb, an in-viewport engineering-notation glyph (∥/⊥/T/=/⟷/◎), and planegcs solves that hit 0.0 deviation (line-arc tangency at center-to-line == radius, equal length/radius, symmetric-about-a-construction-centerline, concentric) — worked e2e (`constraints.spec.ts`) proves the solved geometry actually moves, not just that the request returns 200. Construction geometry (313c44f/8592ae2) also shipped: entities can be marked reference-only (N verb, dashed render), participate in the solve, and are excluded from the extrude profile — the standard incumbent pattern for centerlines/symmetry axes. Combined with the base 6 (coincident/horizontal/vertical/distance/radius/fixed), the sketcher now has all 12 constraint kinds a daily-driver solver needs for the common relational cases, and a real engineer can now rough out tangent-arc-rounded profiles and symmetric parts (about a construction centerline) that were flatly impossible before this cycle. That is the core reason this stays ❌ and not ➖: the constraint *solver* is genuinely closer to parity, but a daily-driver sketcher is judged on a full sketching session, not the solver alone, and the session-every-time authoring/editing tools are still entirely absent — no trim/extend (draw-rough-then-clean-up, the incumbents' default workflow, isn't possible; every vertex must be placed exactly), no offset (no parallel-curve-at-distance, used constantly for ribs/webs/wall profiles), no sketch-level mirror/pattern (symmetric profiles with more than a couple of point-pairs mean hand-adding one `symmetric` constraint per pair instead of one mirror op), no splines (no free-form/organic profiles at all — a hard capability gap, not an ergonomics one), no dedicated sketch fillet/chamfer (a rounded corner requires manually placing a tangent arc and constraining it twice, not a one-click corner-round), and conflict diagnosis is still an index-only flag (`sketch_conflicting`), not the incumbents' redundant-vs-conflicting classification with a suggested fix. Net: the relational-constraint gap this row named as its blocker is closed; the profile-authoring/editing-tool gap is not, and that second gap is what a working engineer hits in literally every real sketch session. |
| Part modeling (features, history) | ❌ | Biggest jump yet, still short of parity. The full authoring loop is now real and QA-verified end-to-end: sketch → extrude(add/cut) → fillet/chamfer → edit-dimension-live → rollback → render-in-viewport → export, proven in a real browser by the Phase 1 exit-gate e2e (commit ff6b226) and an independent code-review pass that returned APPROVE with no 🔴/🟡 findings. This is a real leap from a72c36b's "nothing renders" state: bodies render (mesh proxy, commit 8680502), the feature tree has select/edit/rollback UI (commit e80e378), and fillet + chamfer both ship with goldens at 0.0 and 1.26e-10 STEP round-trip (commits 56eebb0/02b6e9c). Stays ❌, not ➖: only 3 features exist (extrude/fillet/chamfer) against the daily drivers' dozens — no revolve, sweep, loft, dedicated hole feature, linear/circular pattern, shell, or draft, so anything that isn't built from prismatic extrusions (shafts, ribs, lofted surfaces, bolt-circle patterns) can't be modeled at all; fillet/chamfer select edges by geometric predicate (`all_edges`/`axis_parallel`), not click-a-specific-edge (Phase 2 topological naming/`SubshapeRef`), so an engineer can't selectively round one edge and leave its neighbor sharp — most real parts need exactly that; and it's single-body only, no multi-body booleans. The core prismatic block-with-rounded-edges loop is real and usable today; breadth and edge-selection precision for a general part are not. |
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

Last re-scored 2026-07-11 (vision-steward), second pass this cycle, against
git log through 9554273 (equal/symmetric/concentric verbs+glyphs, 4b) plus
`docs/GEOMETRY-QA.md` and the worked e2e in `apps/web/e2e/constraints.spec.ts`
+ `construction-geometry.spec.ts`. **Sketching re-scored and held at ❌** (not
flipped to ➖): the row's named gap — tangent/perpendicular/parallel/equal/
symmetric/concentric constraints — is now fully shipped (commits
d214c9d/d41d51a/a968dbe/9554273) with 0.0-deviation solver tests and e2e proof
the geometry moves, plus construction geometry (313c44f/8592ae2). That closes
the *relational-constraint* gap the row previously called its blocker. It
stays ❌ because a daily-driver sketcher is judged on a full session, not the
solver alone, and trim/extend, offset, sketch-level mirror/pattern, splines,
and dedicated sketch fillet/chamfer — tools an engineer reaches for in
essentially every real sketch in SolidWorks/Fusion/Onshape/FreeCAD — are still
entirely unbuilt; over-constraint diagnosis is also still index-only, not the
incumbents' redundant-vs-conflicting classification. Verdict: real, verified
progress on the solver; the row doesn't flip until profile-authoring/editing
tools (trim/offset/mirror at minimum) land. Earlier this cycle: Part modeling
got its biggest jump since the project started — a real, QA-verified
sketch→extrude→fillet/chamfer→edit→rollback→render→export loop (commit
ff6b226, independent code-review APPROVE, no 🔴/🟡) — but stays ❌: 3 features
with predicate-only edge selection, no revolve/hole/pattern/shell/draft, and
single-body-only can model prismatic blocks, not most real parts. Interop
stays ❌ too: export now covers the modeled tree (not just bare primitives) at
0.0-to-1.26e-10 STEP round-trip, but import still doesn't exist and ➖ needs
both directions. Phase 1 MVP is complete end-to-end; nearest flips for Phase
2: trim/offset/mirror on Sketching, widen feature breadth (revolve/hole/
pattern) and move to click-specific edge selection on Part modeling, then
Interop-import (Phase 4).

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
