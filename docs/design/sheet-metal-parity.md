# Sheet Metal — Incumbent-Parity Checklist

Owner: **vision-steward**. Status: **living tracker**, re-scored each pass
against `git log` + `docs/GEOMETRY-QA.md` + `docs/UI-REVIEW.md` — never
re-derived from scratch. This is the yardstick `docs/VISION.md`'s Sheet
metal scorecard row is held to; the founder's standing ask is **full
incumbent parity, then keep it "on par"** as the incumbents evolve, so this
doc exists specifically so parity is *measured*, not asserted.

**Companion docs:** `docs/design/sheet-metal.md` (the v1 architecture
decision doc — kernel scoping, the depth-1/depth-≥2 unfold algorithm, the
signature/provenance model; **do not edit here**, a corner-relief agent owns
it concurrently). `docs/COMPETITIVE.md` (the cross-pillar feature map; has a
one-row pointer to this doc, §"Sheet metal" table). `docs/BACKLOG.md` /
`docs/ROADMAP.md` (sequencing — this doc's §Parity roadmap is *input* to the
next groom, not itself the backlog).

Legend: ✅ shipped & QA'd · 🟡 partial (real but scoped/narrow) · 🔨 in
flight (another agent has code/design in progress right now, 2026-07-19) ·
❌ missing, no code.

**Verified against the repo at HEAD (`a1c6a21`)** by reading
`services/geometry/src/geometry/sheet_metal/{base_flange,edge_flange,
unfold,resolve,flat_pattern}.py`, `packages/py-kit/src/py_kit/schemas/
features.py` + `drawings.py`, `docs/design/sheet-metal.md` (the shipped
implementation notes through §10), `docs/GEOMETRY-QA.md`'s 2026-07-19
entries, `docs/VISION.md`'s Sheet metal scorecard row.
**UPDATE 2026-07-19:** the sheet-metal feature-authoring UI has since landed —
base + edge flange (`47c88f4`), then closed hem + corner relief (this slice) —
so `apps/web/src` now has a SHEET METAL toolbar group + editors and all four
features are drivable in-app by clicking, not only via the documents/geometry API.
The hem + corner-relief editors were **frontend-qa spot-checked 2026-07-19
(verdict: SHIP IT, tool-grade)** — design-system adherence + WCAG-AA verified,
the corner-relief two-select (Bend A/Bend B) affordance validated as an
acceptable v1 (keyboard-reachable; a viewport bend-pick stays a roadmap
follow-up); one P2 fast-follow (highlight the picked flange in-scene on select
when 3+ flanges make the selects "blind") + P3 a11y nits filed to
`docs/UI-REVIEW.md` + `docs/BACKLOG.md` (SM-relief-ui-1), none blocking.

---

## 1. Flanges / walls

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Base flange / tab** (profile sketch → constant-thickness body) | SolidWorks: insert a sketch profile, extrude to material thickness — [Design a Sheet Metal Part from the Flattened State](https://help.solidworks.com/2022/english/SolidWorks/sldworks/t_design_sheet_metal_flattened.htm). Fusion: Sheet Metal workspace base feature driven by a per-design rule (thickness/bend radius/relief) — [Sheet metal rule reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF) | ✅ | `SheetMetalBaseFlangeParamsV1` reuses the shipped `extrude` thicken path verbatim, carries `thickness_mm`/`k_factor`/`bend_radius_mm` as part-level defaults — kernel-complete. | — |
| **Edge flange** (new flange off a straight edge, length/angle/radius) | SolidWorks Edge-Flange PropertyManager: pick edge, set length/angle/bend radius/bend-allowance type — [Edge Flanges](https://help.solidworks.com/2024/English/SolidWorks/sldworks/c_Edge_Flanges.htm). Fusion: pick edge(s), set flange parameters — [Create sheet metal flanges](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-CREATE-FLANGE) | ✅ | `SheetMetalEdgeFlangeParamsV1` — exact developed cross-section (partial annulus + rectangle) extruded along the bend axis, provenance-tagged via `CylindricalFaceSignature`. Kernel-complete for a single straight bend line per feature. | — |
| **Miter flange** (a series of flanges around one/more edges, corner material auto-trimmed to fit) | Flanges added along a chain of tangent/coplanar edges with the shared-corner overlap automatically mitered — [Miter Flanges](https://help.solidworks.com/2025/english/solidworks/sldworks/c_Miter_Flanges.htm), [Miter Flange PropertyManager](https://help.solidworks.com/2023/english/SolidWorks/sldworks/HIDD_SHEET_METAL_DVE_MITERED_FLANGE.htm) | ❌ | No miter-corner trim geometry exists; `docs/design/sheet-metal.md` §1/§7 explicitly defers it ("two edge flanges meeting at a shared corner with the bend material trimmed to fit"). Needs a corner-intersection trim step layered on the depth-≥2 bend-tree unfold once corner relief (below) lands, since a miter is fundamentally a corner-relief variant with a 0-gap trim instead of a cutout. | M — sequenced after corner relief |
| **Swept flange** (a profile swept along a picked path/edge chain — compound/curved bends) | Swept-Flange tool: an open profile sketch + a path (sketch or existing sheet-metal edges) — behaves like the general Sweep tool but sheet-metal-aware — [Swept Flange](https://help.solidworks.com/2020/english/SolidWorks/sldworks/t_Swept_Flanges.htm) | ❌ | No path-driven flange exists; today's edge flange is strictly a straight bend line. `sweep.py`'s profile-along-path primitives are already load-bearing elsewhere (per `sheet-metal.md` §4.2) so this reuses shipped machinery, but the compound-bend geometry (a curved developable path) is new unfold risk, closer to lofted-bend risk than edge-flange risk. | L |
| **Lofted flange/bend** (two open-profile sketches connected by a loft — cones, reducers) | Lofted Bends: two open profiles, no base-flange dependency, loft between them — [Lofted Bends](https://help.solidworks.com/2021/english/SolidWorks/sldworks/c_lofted_bends.htm). Onshape also supports lofted sheet metal for cones/reducers, fully editable — [Onshape sheet metal](https://www.onshape.com/en/features/sheet-metal) | ❌ | Genuinely new kernel risk — a lofted bend's flat pattern requires a **developable-surface** argument (can this loft actually be flattened without distortion at all?) that neither Loft's kernel nor `sheet-metal.md` has made. Named explicitly as future risk in `sheet-metal.md` §10 ("needs a developable-surface argument this doc does not make"). | L — real risk, not just authoring work |
| **Contour / sketched flange** (a sketch profile becomes a wall matching an existing edge's contour, not just a straight/swept flange) | Not independently confirmed as a distinct SolidWorks/Fusion tool name this pass — likely covered by base-flange-on-a-face + edge-flange combinations rather than a dedicated tool. Flagged, not asserted. | — | Not clearly a distinct incumbent primitive; low priority to chase as a separate feature until re-verified. | — (needs re-verification) |
| **Sketched bend / "insert bend from a line"** (add a bend line to a flat face, not off an edge) | Sketched Bend: draw a line on a flat sheet-metal face, the tool bends the face along it — commonly paired with a tab to fold a small protrusion — [Sketched Bends](https://help.solidworks.com/2024/english/solidworks/sldworks/c_Sketched_Bends.htm). Fusion's **Fold** does the same: sketch a straight line on a flange face, Sheet Metal ▸ Create ▸ Fold — [Fold sheet metal bodies](https://help.autodesk.com/view/fusion360/ENU/index.html?guid=GUID-D11BA900-A40A-4EC2-85E1-01CBF6BF642C) | ❌ | Every Loft bend today originates from a **picked model edge** (`edge_flange`'s `edge` selector); there is no path to bend an *interior* sketched line on an existing flat face. This is the mechanism tabs (below) and many real-world offset bends need. | M |

## 2. Bends

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Bend off a straight edge** | Core of Edge-Flange (§1) | ✅ | Shipped, single straight bend line per feature. | — |
| **Depth-1 bend star** (N edge flanges off one shared base — L-bracket, U-channel, 4-sided pan) | Implicit in both incumbents (no depth restriction at all) | ✅ | `unfold_sheet_metal` — parallel AND non-parallel depth-1 stars, goldened at N=1/2/4 (`corner-tray-perp-unfold`, `pan-four-flange-perp-unfold`). | — |
| **Bend chains / bend trees (depth ≥2 — a flange off a flange: box corners, returns, Z-chains)** | No depth restriction — a box or hat-channel is ordinary sheet-metal modeling in both tools. | ✅ (narrower than incumbents) | `_unfold_bend_tree` (spike `5d3ac32` → shipped `66aee0a`) handles axis-aligned, non-self-overlapping trees (box corner, return, parallel Z) via recursive-compositional frame placement — real, goldened, byte-deterministic. **Still short of incumbent parity**: non-axis-aligned intermediate flanges are a typed reject (`UnfoldStarError`), a self-overlapping tree (the case that genuinely needs corner relief, e.g. a closed box) is a typed reject (`UnfoldOverlapError`) rather than a resolved geometry, and there is no declarative multi-bend authoring path (goldens author via chained `build_edge_flange` calls, not a single request). | S–M — the axis-aligned + no-overlap ceiling is the main remaining gap, and corner relief (below) is the direct unlock for the self-overlap case |
| **Unfold (temporary, in-session flatten for editing)** | Fusion: Sheet Metal ▸ Modify ▸ Unfold — flattens specific bends temporarily to sketch/cut across a bend region, then Fold restores — [Unfold](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-UNFOLD-IN-SM). SolidWorks: Unfold/Fold PropertyManager, same purpose. | ❌ | Loft's `unfold_sheet_metal` computes a **read-only flat-pattern query** (§6 of `sheet-metal.md`) for the drawing view — it is not an *editable, re-foldable* state a user can sketch/cut into and fold back. This is a distinct authoring workflow (temporarily flatten → add a cutout across the bend region → re-fold), not just a rename of what's shipped. | M |
| **Fold** (fold a bent-line sketch on a flat face into a 3D bend — the authoring counterpart to Sketched Bend, §1) | Fusion ▸ Sheet Metal ▸ Create ▸ Fold — same doc as above | ❌ | Depends on Sketched Bend (§1) shipping first. | M (bundled with sketched bend) |
| **Cross-breaks** (a cosmetic stiffening crease across a flat face — HVAC/duct convention; a graphical annotation, NOT a geometric bend) | Cross Break command inserts a graphical crease indicator; explicitly **does not alter part geometry** — [Cross Breaks](https://help.solidworks.com/2025/english/Solidworks/sldworks/c_cross_break.htm) | ❌ | No equivalent. Genuinely low-risk (it's cosmetic, not geometric — no unfold interaction) but also low-value outside HVAC/duct work; **candidate for explicit deprioritization**, see §Verdict. | S, low priority |
| **Jog** (two bends with no length between — a stepped offset of a flat face) | Jog tool: sketch a single line, the tool inserts two bends (a "Z-step") to offset the face by a set distance while keeping it parallel — [Jogs](https://help.solidworks.com/2020/english/SolidWorks/sldworks/c_jogs.htm) | ❌ | Geometrically a **degenerate two-bend depth-1 chain with zero flange length between the bends** — since depth-≥2 bend-tree unfold now ships, a jog is much closer to reachable than it looked when `sheet-metal.md` was written (it predates depth-2). Needs: (a) a dedicated feature type (two coupled bend params, not two independent edge-flange authorings) or (b) confirmation the existing chain machinery composes correctly at zero intermediate length (an edge case worth a golden, not an assumption). | S–M — reassess priority now that depth-2 unfold exists |
| **Hem** — open, closed, teardrop, rolled | Four hem types: **Closed** (bent 180° flat against the parent, zero inside radius, cheapest/most common), **Open** (curved outer edge, air gap — safe-to-touch edges/handles), **Teardrop** (rounded tear-shaped profile — brittle materials like aluminum), **Rolled** (full circular edge — eliminates raw edges, doors/furniture) — [SolidWorks hem tutorial summary](https://solidworkstutorialsforbeginners.com/solidworks-sheetmetal-hem/), [Approved Sheet Metal — hem types](https://www.approvedsheetmetal.com/blog/what-type-of-hem-does-your-custom-sheet-metal-part-need). Fusion's Hem tool: pick edge(s), flip fold direction, **Miter Corners** option, **Override Rules** per-feature — [Create hem](https://help.autodesk.com/view/fusion360/ENU/?contextId=SM-CREATE-HEM-FLANGE) | 🟡 **closed shipped** (2026-07-19, kernel-architect) | **CLOSED hem SHIPPED** as a first-class feature `SheetMetalHemParamsV1` (`type="sheet_metal_hem"`, edge ref + `length_mm` + optional `bend_radius_mm`/`k_factor`, `hem_type="closed"`) — kernel finding: the closed hem is even freer than predicted. `build_edge_flange` at `bend_angle_deg=180` with a small radius produces **ONE clean valid solid** (BRepCheck-valid, one shell) and `unfold_sheet_metal` develops it correctly (BA = π·(r+K·t)); the near-flat fold **cannot self-intersect** — the return sits ~2·radius above the base with an air gap, verified valid down to r=1e-6 — so no guard or rescope was needed, the hem reuses the edge-flange bend + unfold machinery verbatim (a fixed 180° fold, DRY-shared `_fold_flange_off_edge`). Golden `closed-hem-plate` (valid solid + analytic unfold + area conservation + byte-determinism). Honest degradation (parity §3): a zero-radius/zero-gap hem is a typed schema rejection; a kernel fold failure is a typed `edge_flange_failed`. **Closed-hem authoring UI SHIPPED** (2026-07-19, frontend-builder): a `HemEditor` in the SHEET METAL toolbar group next to Base/Edge flange — single-select edge pick (reuses the edge-flange overlay), brass `length_mm` handle, a fixed "180° (closed)" fold readout (no angle field), inherited radius/K overrides; e2e models a plate with a closed hem by clicking, body + flat pattern render (`sheet-metal-hem-*.png`). **Deferred:** open / teardrop / rolled — each a genuinely different **curved cross-section profile** at the fold tip the exact-cross-section extrude does not build. | S ✅ (closed geom + UI) / M (open/teardrop/rolled — curved cross-section) |

## 3. Corners

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Corner relief** (rectangular / round / tear / obround cutout at a bend intersection so the sheet doesn't tear/interfere when folded) | SolidWorks Corner Relief PropertyManager: choose relief type **Rectangular, Tear, or Obround** (a "Round" relief is documented under the closely-related Auto Relief options, sourced separately below); Tear reliefs are minimum-size, Rectangular/Obround take a **Relief Ratio** — [Corner Relief PropertyManager](https://help.solidworks.com/2022/english/SolidWorks/sldworks/hidd_sheet_metal_corner_relief.htm), [Adding a Corner Relief](https://help.solidworks.com/2024/English/SolidWorks/sldworks/t_adding_corner_relief.htm), [Corner Reliefs and Bend Transitions](https://help.solidworks.com/2025/english/Solidworks/sldworks/c_corner_reliefs_bend_transitions.htm). Fusion: corner relief is driven by the sheet-metal **rule** (thickness/bend-radius/corner-relief together), auto-applied where needed, overridable per-operation — [Sheet metal rule reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF) | 🟡 **RECTANGULAR shipped + WIRED** (2026-07-19, kernel-architect) | Both halves ship AND are authorable end-to-end: the 3D notch (`apply_corner_relief`) + the relieved flat-pattern unfold (`unfold_sheet_metal(reliefs=...)`), driven by an EXPLICIT `sheet_metal_corner_relief` feature (`bend_a`/`bend_b` FeatureRefs + `relief_ratio`/`size_mm`, §4.4.2). A user models a tray with a relieved corner → the evaluated body has the 3D notch AND the flat pattern has the matching notch (fold-back invariant proven at the pipeline level, golden `corner-tray-relieved-feature`). **Corner-relief authoring UI SHIPPED** (2026-07-19, frontend-builder): a `CornerReliefEditor` in the SHEET METAL toolbar group — NOT an edge pick, it references the two edge-flange FEATURES via two ruled selects (Bend A / Bend B, seeded with the part's edge flanges), with a `relief_ratio` field (gauge-sized notch previewed) + an absolute `size_mm` override; enabled only with ≥2 edge flanges; the typed `corner_relief_failed`/`reference_unresolved` surface in the editor. A direct viewport bend-face pick is a noted follow-up. e2e models a relieved tray by clicking, body + relieved flat pattern render (`sheet-metal-corner-relief-*.png`). **Still narrower than incumbents:** RECTANGULAR only (obround / round / tear deferred, §4.4.1); the fully-welded depth-2 box corner stays a typed reject (needs miter/closed-corner geometry). | S–M — obround/tear variants + welded-corner geometry remain |
| **Auto relief** (default relief applied automatically wherever a bend needs it, without per-bend authoring) | Auto Reliefs: a document-level default so most bends don't need per-feature relief authoring — [Auto Reliefs](https://help.solidworks.com/2023/English/SolidWorks/sldworks/c_Auto_Reliefs.htm) | ❌ (UNBLOCKED — explicit relief now shipped) | The explicit per-corner primitive landed (above), so "auto" is now a pure POLICY layer over it: walk the bend graph, find every corner whose flanges collide/tear on unfold, synthesise an explicit `CornerRelief` per corner from a part-level default size. No new geometry risk — a clean fast-follow, the next corner-relief slice. | S, next |
| **Closed corners** (bend-adjacent faces trimmed/extended to meet flush with no gap, vs. an open/gapped corner) | A documented corner-treatment option distinct from relief — controls whether adjoining bend faces are extended to close the gap — [Corner Reliefs and Bend Transitions](https://help.solidworks.com/2025/english/Solidworks/sldworks/c_corner_reliefs_bend_transitions.htm) | ❌ | Not started; likely rides the same corner-geometry work as corner relief/miter (all three are "what happens where two bend-adjacent faces meet" variants). | S–M, bundle with corner relief |
| **Corner trim** (manual sketch-driven material removal at a corner, distinct from the automatic relief options) | Named alongside relief/closed-corner options in the same incumbent corner-treatment family — not independently deep-dived this pass. | ❌ | Same family as above. | S, bundle |
| **Weld/gap corners** | Named in the incumbent corner-treatment family (gap size between mating flanges) — not independently deep-dived this pass, flagged for re-verification. | ❌ | Lower priority than relief/closed — mostly a cosmetic/manufacturing-note concern once real geometry closes. | S, low priority |
| **Bend relief** (the relief cut at the END of a single bend line, distinct from corner relief which is at a bend INTERSECTION) | Standard part of every edge-flange bend in both incumbents — prevents tearing where the bend line meets the sheet edge. | 🟡 | Loft's exact-cross-section bend construction (`sheet-metal.md` §4.2 implementation note) sidesteps the general wire-reconstruction robustness risk specifically *because* it never needs bend-end relief in the depth-1/depth-≥2-no-overlap cases goldened so far — the geometry is exact by construction, not because relief was explicitly modeled. **Verified 2026-07-22 (founder dogfooding, PB-1 bracket):** a partial-width flange (70 mm fold on a notch-split edge of a 200 mm base) builds a PERFECT 3D body — evaluate green, kernel volume matches closed-form exactly — but the flat pattern is a typed reject: "The developed outline is not a single closed loop — a flange does not span its full base edge" (`_emit_plus_pattern`'s guard, exactly as this row predicted). So partial-width folds are 3D-complete, unfold-blocked; developing them needs the multi-segment outline (and is where bend relief becomes load-bearing). | S–M — now a confirmed, repro'd gap (BACKLOG P2) |

## 4. The bend-allowance model

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **K-factor** (neutral-axis offset fraction of thickness from the inner bend face) | Fusion sheet-metal rules configure K-factor as exactly this — [Sheet metal rule reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF). SolidWorks: bend-allowance TYPE setting on the Edge-Flange PropertyManager, K-factor one of three types — [Edge-Flange PropertyManager](https://help.solidworks.com/2024/english/Solidworks/sldworks/HIDD_FEAT_SM_EDGE_FLANGE.htm) | ✅ (single global/per-feature value, not a table — see below) | `k_factor` on `SheetMetalBaseFlangeParamsV1`, overridable per edge-flange; default `0.44`; BA formula verified across 45/60/90/120° with Δ≤2.6e-14 (`docs/GEOMETRY-QA.md` 2026-07-19). The *math* is at parity; the *lookup model* (below) is not. | — |
| **Bend allowance** (closed-form: flat length added by a bend) | Same closed-form both incumbents use; SolidWorks additionally lets you set bend-allowance-type to **Bend Allowance** directly (bypass K-factor derivation) — [Edge-Flange PropertyManager](https://help.solidworks.com/2024/english/Solidworks/sldworks/HIDD_FEAT_SM_EDGE_FLANGE.htm) | ✅ (via K-factor only) | Loft always derives BA from K-factor; there's no path to type in a bend allowance (or deduction) value directly, bypassing K. | S |
| **Bend deduction** (an alternate convention: how much SHORTER the total flat length is vs. the sum of the two outside leg lengths) | A named alternate bend-allowance TYPE in both incumbents' bend-table/rule systems, common in shops that measure from OUTSIDE mold lines — [Bend Table](https://help.solidworks.com/2019/English/SolidWorks/sldworks/c_Bend_Table_Overview.htm) | ❌ | Not modeled at all — Loft's unfold math has one convention (K-factor→BA); a shop that specs bend deduction has no way to drive Loft's flat pattern from their own numbers. | S–M |
| **Gauge/material bend TABLES** (thickness × radius × angle → allowance/deduction/K, looked up per material, overridable per bend, interpolated between table rows) | This is the incumbent-standard workflow, not an edge case: SolidWorks bend/gauge tables are stored per-material text files supporting all three allowance TYPES, with interpolation between thickness/angle rows — [Sheet Metal Gauge/Bend Table](https://help.solidworks.com/2021/english/solidworks/sldworks/c_sheet_metal_gauge_bend_table.htm), [Sheet Metal Gauge Tables](https://help.solidworks.com/2021/english/solidworks/sldworks/c_sheet_metal_gauge_tables.htm). Fusion's sheet-metal **rules** bundle thickness+K-factor+bend-radius+relief as one named, reusable, per-material preset — [Sheet metal rules](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-FA8B0BDF-BCF7-4A61-B3F0-0F25223E7EAE) | ❌ | **This is the single largest, most explicitly-named gap in the whole pillar** — `sheet-metal.md` calls it out at every mention (§1, §7, §9, §10) as an intentional v1 deferral, not an oversight. A real shop workflow is "pick 16-gauge cold-rolled steel from our shop's table," not "type 0.44." Needs: a persisted gauge-table document/schema (material × thickness × radius × angle → allowance), a per-part/per-feature lookup override chain (mirrors the incumbents' rule/table layering), and interpolation between rows. This is squarely a documents-service data-modeling problem (a new small reference table + CRUD), NOT new kernel risk — the unfold math already consumes a resolved `k_factor`/BA value regardless of where it came from. | M — data modeling + UI, not kernel; high founder-value because it's named explicitly as the standing gap |

## 5. Manufacturing features

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Forming tools** (library parts that act as dies — louvers, lances, ribs, embosses — dropped onto a face and stamped) | Forming Tools: library parts stored under a design-library folder, applied to bend/stretch/form sheet metal; example: creating a louver — [Using Forming Tools with Sheet Metal](https://help.solidworks.com/2025/english/solidworks/sldworks/c_Forming_Tools.htm), [Example of Creating a Louver](https://help.solidworks.com/2025/english/solidworks/sldworks/t_Example_of_Creating_a_Louver.xls.htm) | ❌ | No equivalent concept at all — no forming-tool library, no "stamp this shape into that face" feature. This is a genuinely separate authoring paradigm (a reusable tool PART applied parametrically to a target face) layered on top of ordinary solid-modeling primitives Loft already has (a scaled/positioned cut+draft, roughly) — real but not urgent; low representation in "does a working engineer's FIRST sheet-metal parts need this" per the operating question. | L, low near-term priority |
| **Louvers / lances / dimples / countersinks-in-sheet** (specific forming-tool shapes) | Named forming-tool examples in the same family above; Onshape ships countersink/counterbore directly on sheet-metal bodies with hole details carried into the flat pattern for DXF — [Onshape feature highlights](https://www.onshape.com/en/blog/feature-highlights-march-2024) | ❌ | Countersinks/counterbores are the highest-value subset (they're just holes with a recess, not a new die-stamp paradigm) and could ship WITHOUT the general forming-tool-library machinery, closer to a hole-feature variant than a sheet-metal-specific risk. Dimples/louvers/lances genuinely need the forming-tool paradigm. | S (countersink/counterbore) / L (general forming tools) |
| **Gussets** (a stiffening indent pressed across a bend, between two flanges) | Sheet Metal Gusset: pick two faces meeting at a bend, set depth/width/radius — [Adding Sheet Metal Gussets](https://help.solidworks.com/2021/english/SolidWorks/sldworks/t_adding_sheet_metal_gussets.htm), [Sheet Metal Gusset PropertyManager](https://help.solidworks.com/2024/english/SolidWorks/sldworks/r_sheet_metal_gusset_pm.htm) | ❌ | Not started. Geometrically closer to a shaped rib/emboss cut than a new unfold-risk category (a gusset doesn't change the flat pattern's outline, just adds a local stiffening feature to the formed body) — plausible mid-size add once corner relief's bend-intersection geometry exists (a gusset sits exactly where two flanges meet). | M |
| **Mounting boss** | Not a sheet-metal-specific concept in the incumbent docs surfaced this pass — bosses are a general solid-modeling feature (extruded cylinder), not sheet-metal-specific. Flagged for re-verification, likely a mis-scoped ask in the original task framing. | — | If "mounting boss" means a formed/drawn boss stamped into sheet (a forming-tool shape), it's covered by §Forming tools above; if it means an ordinary extruded boss on a sheet-metal part, Loft's existing `extrude` feature already covers it once sketch-on-flange-face is exercised (already reuse per `sheet-metal.md` §7). | — (needs re-scoping, not a real standalone gap) |

## 6. Flat pattern

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Flat-pattern generation** | "Create a flat pattern" flattens the formed body, factoring bend allowance — [Sheet metal flat patterns](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-121F6E58-0459-4552-85EF-319F44324AE6). SolidWorks Flatten/Flat-Pattern feature — [Flattening Sheet Metal Bends](https://help.solidworks.com/2022/English/SolidWorks/sldworks/t_Flattening_Sheet_Metal_Bends.htm) | ✅ (depth-1 + non-self-overlapping depth-≥2 trees) | `unfold_sheet_metal` — see §2 Bends for the exact scope ceiling. Genuinely good coverage of the common cases (L-bracket, U-channel, 4-flange pan, box corner, Z-chain), narrower than "any formed body" only at self-overlapping/non-axis-aligned geometry. | — |
| **Bend lines + bend table + notes on the flat pattern** | Bend-line notes auto-update with angle/direction/radius changes, mergeable when collinear — [Sheet Metal Bend Line Notes](https://help.solidworks.com/2026/english/solidworks/sldworks/c_Sheet_Metal_Bend_Line_Notes.htm) | ✅ | `FlatPattern`'s `edge_role: "bend"` edges render as a dashed-blue stroke (shared token, server-compose ↔ on-screen SVG); `BendTableRow` (bend_id/angle/radius/direction/allowance) surfaces as a columnar table, rendered + a text-accessible twin panel for a11y (`2ba4df4`). At functional parity with SolidWorks' bend-line-notes deliverable for the depth-1/goldened depth-≥2 cases; no note-merging for collinear bends (a polish item, not a gap that blocks shop use). | S (collinear-merge polish only) |
| **Flat-pattern EXPORT (DXF/DWG for the shop)** | `*.dxf`/`*.dwg` direct from the sheet-metal part, bend lines optionally included/excluded, bend-direction-to-layer mapping — [Exporting Sheet Metal Parts to DXF or DWG Files](https://help.solidworks.com/2024/English/SolidWorks/sldworks/c_Exporting_to_DXF_or_DWG_Files.htm), [Saving Sheet Metal Flat Patterns as DXF Files](https://help.solidworks.com/2024/English/SWConnected/swdotworks/t_Saving_Sheet_Metal_Flat_Patterns_DXF_Files.htm) | ✅ | The flat pattern is a first-class drawing view (`projection: "flat_pattern"`) riding the SAME server-composed SVG/PDF/DXF pipeline every other drawing view uses (`ezdxf`-backed, byte-pinned goldens, unified bend-table cell formatting across all three serializers as of `24b1c53`). **This is a place Loft is at genuine parity today** — a deterministic, three-format, server-composed export loop, which is at least as good as SolidWorks' DXF/DWG export for the shapes Loft can already unfold. No bend-line-to-layer mapping control yet (a minor export-options gap, not a missing capability). | S (layer-mapping option only) |
| **Nesting** (multi-part layout optimization on a stock sheet) | **Not native to either core tool** — SolidWorks nesting is a separate paid add-in (NESTINGWorks, third-party/GoEngineer) layered on top of DXF export; Fusion has no native nesting in the Sheet Metal workspace either (nesting is typically CAM-side). | ❌ | This is NOT a Loft-vs-incumbent-core gap — neither SolidWorks nor Fusion ship it as a core sheet-metal capability. **Correctly out of scope for near-term parity work**; flag only if the founder wants to leapfrog into CAM-adjacent territory later. | — (deliberately deprioritize) |
| **Grain direction** (align the flat pattern's bounding box to a specified sheet-stock rolling direction) | A `Grain Direction` option on SolidWorks' Flat-Pattern feature — pick an edge to define grain, or let the software choose the minimal bounding box — [SOLIDWORKS Sheet Metal and Flat Pattern View Direction](https://www.cati.com/blog/solidworks-sheet-metal-and-flat-pattern-view-direction/) (secondary source — a direct `help.solidworks.com` citation was not retrieved this pass, flag for re-verification) | ❌ | Not modeled. Real but narrow — a metadata/orientation concern on the already-correct flat outline, not a new unfold-geometry risk. | S, low priority until DXF nesting workflows are a stated founder need |
| **Bend-order / bend sequence** (author which bend folds first — matters for manufacturability, tooling clearance) | Reorder Bends dialog: move bends up/down in fold sequence, independent of feature-creation order — [Reordering Bends](https://help.solidworks.com/2022/english/SolidWorks/sldworks/HIDD_BEND_REORDER.htm) | ❌ | Loft's depth-≥2 unfold currently folds/develops purely by the bend TREE's parent-child structure (deterministic, but not independently user-orderable) — there is no concept of "fold bend 3 before bend 1" as a manufacturing-sequence override distinct from authoring order. Real gap for complex multi-bend parts where fold sequence affects tooling clearance, but the tree-walk math would need it as an explicit new input, not a rename. | S–M, defer until bend-tree parts are common in practice |
| **K-factor display on the flat pattern / bend table** | Bend tables can show K-factor per row alongside angle/radius — configurable precision in Tools ▸ Options — [Sheet Metal Gauge/Bend Table](https://help.solidworks.com/2021/english/solidworks/sldworks/c_sheet_metal_gauge_bend_table.htm) | 🟡 | `BendTableRow` carries `bend_allowance_mm` (the derived quantity) but not the `k_factor` input itself as a displayed column — the value IS used and correct, just not surfaced per-row. Trivial addition once wanted. | S |

## 7. Convert / recognize

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Convert a solid to sheet metal** (pick a fixed face, set thickness/default bend radius, pick edges to become bends, set auto-relief) | Convert to Sheet Metal tool: select fixed face, set thickness + default bend radius, select bend edges, configure rip options, choose auto-relief type (Rectangular/Tear/Obround + Relief Ratio) — [Converting a Solid Part to a Sheet Metal Part](https://help.solidworks.com/2026/english/SolidWorks/Sldworks/t_solid_to_sheet_metal.htm) | ❌ | `sheet-metal.md` §2.2/§10 explicitly and correctly separates this as **the harder recognition problem** ("any cylindrical face of the right radius could be a bend OR an unrelated fillet/hole") from v1's provenance-tracked approach — not attempted, not claimed. Genuinely independent effort from everything else in this doc; needs its own design pass (a classification/recognition algorithm, not a reuse of `unfold_sheet_metal`'s provenance-driven resolve). | L — independent design doc needed before sizing further |
| **Rip / insert bends** (split a solid at a seam so it can be converted, or add bend geometry to an already-converted body) | Bundled into the Convert-to-Sheet-Metal workflow above — [Converting a Solid Part to a Sheet Metal Part](https://help.solidworks.com/2026/english/SolidWorks/Sldworks/t_solid_to_sheet_metal.htm) | ❌ | Same dependency as above. | L, bundled |
| **Sheet-metal-from-imported-STEP recognition** | Not a distinct tool name — same Convert-to-Sheet-Metal path applies to imported geometry once it's a solid body in the session. | ❌ | Loft's STEP import (multi-solid, MB-4b) already produces a plain solid body that COULD feed a future convert-to-sheet-metal tool — the import side is not the blocker, the recognition algorithm is (same item as above). | L, bundled |

## 8. Drawings

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Flat-pattern view on a drawing sheet** | A dedicated drawing view type showing the flattened part — [Drawings of Sheet Metal Parts](https://help.solidworks.com/2017/english/solidworks/sldworks/c_drawings_of_sheet_metal_parts.htm) | ✅ | `projection: "flat_pattern"` — a first-class view kind in the shipped drawing pipeline (§6 above), auto-composed onto a sheet, rendered with fold-line + bend-table annotation. One honest scope note: the shipped **multi-view auto-layout composer** does NOT place a `flat_pattern` view alongside the standard 4 orthographic views on the same sheet (`sheet-metal.md` §7 implementation note) — a flat-pattern sheet is its own single-view sheet today, not mixed with a folded-part orthographic sheet. | S — mixed-view sheet composition |
| **Bend table / bend notes on the drawing** | Covered in §6 above | ✅ | Same as §6. | — |
| **Ordinate / tab dimensioning** | Standard SolidWorks/Fusion drawing dimension styles alongside linear/angular/radial. | ❌ | Grep of `packages/py-kit/src/py_kit/schemas/drawings.py` confirms Loft's shipped dimension kinds are linear/diameter/radius/angular/point-to-point (`981c42f`) — no ordinate (baseline, running) dimension style, which shops commonly use for hole patterns on a flat blank. This is a **general Drawings-pillar gap, not sheet-metal-specific** — noting it here because a flat-pattern hole layout is exactly where ordinate dimensioning is most used, but the fix belongs to the Drawings pillar's own parity work, not a sheet-metal-only slice. | M — cross-pillar, sequence with Drawings, not Sheet metal |

---

## Parity roadmap

Ordered sequence to close the gaps above, reconciled with the founder's
stated campaign (authoring UI → corner relief → hems → jogs → miters → tabs
→ gauge/material bend tables → flat-pattern DXF/nesting → convert-to-sheet-
metal → forming tools). Two corrections to that campaign surfaced by this
research, called out inline.

1. **Feature-authoring UI** (✅ base + edge flange `47c88f4`; closed hem +
   corner relief 2026-07-19). Table-stakes prerequisite for everything below —
   all four shipped sheet-metal features are now authorable in-app from the
   SHEET METAL toolbar group (BaseFlange/EdgeFlange/Hem/CornerRelief editors +
   the flat-pattern action), not only via the documents/geometry API.
2. **Corner relief** (🟡 rectangular SHIPPED + WIRED + FULL-PAN 2026-07-19). The
   explicit `sheet_metal_corner_relief` feature is authorable end-to-end (3D notch +
   relieved flat pattern, fold-back-proven at the pipeline level), and the canonical
   case — a pan/box with ALL FOUR corners relieved (adjacent pairs share a flange) —
   now relieves cleanly (golden `pan-four-corner-relieved`): each relief resolves its
   bends against the clean un-notched reference, not the live notched body, so a
   shared flange no longer fails `subshape_unresolved`, and a flange authored AFTER a
   relief still develops a correct flat pattern. **Authoring UI SHIPPED 2026-07-19**
   (a `CornerReliefEditor` — two-feature Bend A/Bend B selects, ratio + size override).
   Remaining: obround/tear relief variants, the welded-depth-2 corner
   (miter/closed-corner geometry), the now-unblocked **auto-relief policy layer**, and
   a direct viewport bend-face pick (the editor references bends by feature today).
3. **Hems** (🟡, §2). Research correction CONFIRMED and **closed hem SHIPPED**
   (2026-07-19): the closed hem is exactly the near-trivial specialization of
   the shipped edge-flange it was predicted to be — a fixed 180° fold at a small
   radius through `build_edge_flange` + the shipped unfold, no new kernel
   geometry, no guard needed (the fold-back cannot self-intersect). **Hem authoring
   UI SHIPPED 2026-07-19** (a `HemEditor` — single-select edge pick, brass length
   handle, fixed 180° fold readout, inherited radius/K overrides). Remaining:
   **open / teardrop / rolled** (each a new curved cross-section profile — a
   genuinely different geometry), sequenced as the predicted fast-follows.
4. **Jogs** (❌, §2). Research correction: **jogs got easier, not harder,
   since `sheet-metal.md` was written** — it predates the now-shipped
   depth-≥2 bend-tree unfold, and a jog is exactly a degenerate two-bend
   depth-1-off-depth-1 chain with zero length between bends. Verify the
   existing chain machinery handles the zero-length-strip edge case before
   assuming new kernel work is needed; likely a smaller item than the
   original campaign assumed.
5. **Miter flanges** (❌, §1). Correctly sequenced after corner relief — a
   miter is a corner-relief variant (zero-gap trim instead of a cutout) at
   a **straight, non-bent** corner (two coplanar-ish edge flanges meeting),
   so it shares machinery with corner relief's bend-intersection geometry.
6. **Tabs** (not independently gapped above — a tab is a **base-flange-
   shaped protrusion off an edge**, i.e. mechanically an edge flange with
   `bend_angle_deg = 0`, per SolidWorks' own framing pairing Tab with
   Sketched Bend). Likely near-free once sketched-bend/fold (§1, §2) ships,
   since a tab is "extrude a small flange, no fold" — flag for re-scoping
   as a fast-follow of sketched-bend rather than its own multi-week item.
7. **Gauge/material bend TABLES** (❌, §4 — the single most-repeated gap in
   `sheet-metal.md` itself). Correction on framing, not sequencing: this is
   **documents-service data modeling** (a new small reference-table schema
   + CRUD + lookup-override chain), not kernel risk — the unfold algorithm
   already consumes a resolved K-factor regardless of source. Could in
   principle be pulled EARLIER in the campaign (it's independent of corner
   relief/hems/jogs/miters, all of which are kernel/geometry work); flagged
   as a parallelizable track, not strictly serial after miters.
8. **Flat-pattern DXF / nesting.** Correction: **DXF export is already
   shipped and at genuine parity** (§6 — server-composed, three formats,
   byte-pinned goldens); **nesting is correctly out of scope** — neither
   SolidWorks nor Fusion ship native nesting either (third-party add-in
   territory). Rename this campaign item to what's actually missing:
   bend-line-to-layer export options + grain direction, both small polish
   items, not a DXF gap.
9. **Convert-to-sheet-metal** (❌, §7). Correctly last among the "real
   work" items — `sheet-metal.md` §2.2 already separates it as a genuinely
   harder, independent recognition problem deserving its own design pass
   before sizing.
10. **Forming tools** (❌, §5). Correction on ordering: split into
    **countersink/counterbore-in-sheet** (small — a hole-feature variant,
    could realistically land alongside gauge tables, well before general
    forming tools) vs. **general forming-tool library** (louvers/lances/
    dimples/gussets — large, a new reusable-tool-part authoring paradigm,
    correctly last).

**Not in the founder's stated campaign, surfaced by this research —
recommend explicit deprioritization, not silent omission:**
- **Cross-breaks** (§2) — cosmetic-only (no geometry change) HVAC/duct
  convention; low value outside that niche.
- **Nesting** (§6) — neither incumbent ships it natively; would be
  leapfrogging into CAM territory, not closing a parity gap.
- **Lofted flanges/bends** (§1) and **swept flanges** (§1) — both real
  incumbent features, but the loft variant specifically carries new
  *kernel* risk (a developable-surface argument, unlike everything else
  in this roadmap which reuses shipped unfold machinery) — recommend
  slotting these late, after the gauge-table/forming-tool items, and
  treating the loft case as needing its own spike before commitment,
  the same posture `sheet-metal.md` took for the original unfold.

---

## Verdict — how far from ✅

**Current distance: meaningfully closer than a stub, still short of a
working sheet-metal engineer's daily-driver bar — the VISION.md ➖ judgment
is correct and this research doesn't move it to ✅.** Loft can already take
an engineer from a rectangular-tray/L-bracket/U-channel/simple-box-corner
concept to a dimensionally-correct, shop-ready flat blank with a bend table,
exported to SVG/PDF/DXF, with independently-verified geometric correctness
(STEP round-trip, area conservation, byte-determinism) — that is real,
audited work, not a demo. But a working sheet-metal engineer's actual daily
queue — enclosures with hemmed edges for safety, tabs for assembly location,
miters for a clean corner, and a gauge table driven by the shop's own
material stock — hits a wall on features that don't exist yet, every single
day, not in an edge case.

**The 3-5 features that most move the needle, in order:**

1. **Feature-authoring UI** (✅ base + edge flange, closed hem, corner relief) —
   the gate on every other row's real-world value; all four shipped sheet-metal
   features are now click-drivable in-app.
2. **Corner relief** (🟡 rectangular SHIPPED + WIRED + UI 2026-07-19) — the direct
   unlock for tray/enclosure corners, now authorable as a feature end-to-end AND
   from a `CornerReliefEditor`; obround/tear variants, welded corners, auto-relief,
   and a viewport bend-face pick remain the fast-follows.
3. **Closed hem** (✅ geom + UI SHIPPED 2026-07-19) — hems appear on a large fraction
   of real sheet-metal parts (safety edges, stiffening) and this shape proved
   nearly free given the shipped edge-flange machinery — a disproportionate
   parity gain, now landed with its authoring UI (open/teardrop/rolled remain).
4. **Gauge/material bend tables** (❌) — not kernel risk, pure data
   modeling, and it's the gap `sheet-metal.md` calls out most consistently
   as the honest ceiling on "is this a real material" vs. "is this a demo
   K-factor" — closing it changes the pillar's credibility with an actual
   shop, independent of which flange/bend features exist.
5. **Miters + tabs** (❌, sequenced together as fast-follows of corner
   relief and sketched-bend/fold respectively) — round out the "bracket/
   enclosure" case that covers most of a working engineer's first hundred
   sheet-metal parts.

**Where Loft is already at or ahead of parity** (worth stating plainly, per
this doc's brief — overclaiming is the failure mode, but so is
under-crediting real work):
- **Flat-pattern DXF/PDF/SVG export** (§6) — a deterministic,
  byte-pinned, three-format, server-composed pipeline is at least as
  reliable as SolidWorks' DXF/DWG export for every shape Loft can already
  unfold, and the cross-format bend-table consistency fix (`24b1c53`)
  closes a WYSIWYG gap SolidWorks itself doesn't have to worry about
  (single source of truth, not three independently-drawn outputs).
- **Depth-≥2 bend-tree unfold's determinism and correctness bar** — the
  goldened area-conservation/volume/byte-determinism proof (§9 of
  `sheet-metal.md`, `docs/GEOMETRY-QA.md` 2026-07-19 entries) is a stronger
  correctness guarantee than either incumbent publicly documents about
  their own (closed-source) unfold algorithms; Loft's *scope* is narrower,
  but what's in scope is provably right, not just visually plausible.
- **Nesting** is a non-gap — neither core incumbent ships it; Loft is
  already at parity (both "don't have it natively") without any work.
