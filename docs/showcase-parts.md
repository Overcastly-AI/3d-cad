# Complex-part showcase + Part-modeling stress test

_QA run 2026-07-13 (qa-tester). Four genuinely multi-feature engineering parts
built end-to-end on the REAL running stack (isolated gateway/documents/geometry
on :8300/:8301/:8302), rendered in the actual r3f viewport. Trees seeded through
the gateway feature API; sketch-on-face / shell / picked-edge signatures were
harvested from the live `/overlay` endpoint — the exact pick→echo flow the UI
uses — so every named reference resolves against the real kernel body. Final
renders + mass properties come from the shipped product, not a mock._

Screenshots: `docs/screenshots/showcase/` (`*-hero.png` = viewport-dominant;
`*-full.png` = premium chrome + the parametric feature tree).

## Verdict

**Part-modeling ✅ HOLDS on real complex parts.** All four parts modelled
cleanly to a single closed shell; every feature interaction the scorecard
implies (sketch-on-a-model-face → boss, multi-loop bolt holes, offset-datum
loft, revolve, shell, draft, click-specific edge fillets) composed without a
topological-naming failure across 6–16-feature trees. The inspector's mass
properties matched the API evaluation byte-for-byte, and the bracket volume
matched a hand-derivation to 0.01%. The friction found is **feature-coverage
gaps, not modelling-engine defects** (see Findings) — no wrong geometry, no P0.

## The four parts

| Part | Features exercised | Build | Volume (mm³) | Faces/Shells |
|------|--------------------|-------|--------------|--------------|
| **Mounting bracket** | multi-loop sketch (4 bolt holes) · extrude · **sketch-on-face** boss · **click-specific edge** fillet (4 outer corners, boss left sharp) | clean (6 feat) | 36,301.8 | 16 / 1 |
| **Enclosure housing** | extrude · **draft** (4 walls, 4° mold taper) · **shell** (open top, 3 mm wall) · **picked-edge fillet** (outer top rim) | clean (5 feat) | 55,927.4 | 15 / 1 |
| **Flanged transition duct** | circle sketch · **offset datum** · square sketch · **loft** (round→square) · **sketch-on-face** ×2 (both ends) · multi-loop bolt-hole flanges | clean (10 feat) | 153,518.4 | 26 / 1 |
| **Pulley / hub** | **revolve** (hub+web+rim profile, 360°) · **sketch-on-face** on the web · 6 lightening-hole cuts · **picked-edge fillet** (rim) | clean (16 feat) | 106,439.4 | 20 / 1 |

### Sanity checks
- **Bracket** — 80×50×8 plate (−4 bolt holes) + Ø28×10 boss − 4×r6 corner
  fillets ≈ **36,302** analytic vs **36,301.8** measured (< 0.01%). Boss stays
  sharp while the four outer corners round — the thing edge predicates
  structurally can't express.
- **Duct** — bbox `[-32,-32,-8]..[32,32,78]`: the two on-face flanges extruded
  in the correct **outward** normal direction (−Z below, +Z above the loft),
  confirming the deterministic on-face basis. Single shell through a
  round→square loft + two fused flanges.
- **Pulley** — centroid on-axis `(0, 15, 0)`, symmetric; 6 lightening holes +
  bore + rim fillet, one connected solid.
- **Enclosure** — 3 mm uniform wall, drafted walls visibly tapered, rounded
  outer top rim; inspector volume == API volume == 55,927.42.

## Findings (the honest half)

**F1 — Pattern is union-only, so the two most common patterns (hole arrays)
can't use it.** `PatternParamsV1` replicates the whole current body and
*unions* (`operation` is add-only; a disjoint result is `pattern_disjoint`).
Bolt-hole circles and lightening-hole rings are *cuts*, which the pattern
feature cannot express. Both natural uses in this batch (bracket bolt pattern,
pulley lightening ring) had to be modelled another way. Severity: **P2 feature
gap** (documented v1 scope, not a defect) — but it's the #1 thing an engineer
reaches "circular pattern" for, so it reads as missing capability.

**F2 — A ring of holes is not authorable as one sketch.** A sketch of N
disjoint circles with no enclosing outer boundary is rejected
`profile_unsupported` ("6 closed loops not all enclosed by a single outer
boundary") on extrude-cut. Combined with F1, a circular pattern of lightening
holes must be authored as **N individual cut features** (6 sketch+extrude pairs
here → the pulley's 16-feature tree). Correct behaviour, but the ergonomic path
(pattern a cut, or one multi-circle cut sketch) is absent. Severity: **P2**.

**F3 — Filleting a thin shelled rim is radius-fragile.** Rounding *all* 8 top
rim edges (inner+outer) of the 3 mm-wall enclosure at r1.5 failed
`fillet_failed` — the inner and outer round-overs collide at the half-wall
(1.5+1.5 = 3). Filleting only the 4 outer edges at r1.2 succeeds. This is
geometrically correct (OCCT refuses an impossible blend) and the error is
legible, but there's no UI affordance warning that a rim radius ≥ half the wall
is impossible. Severity: **P3 UX** (correct error, discoverability only).

**F4 — Sketch-on-face + offset-datum + loft + draft + shell all composed with
zero topological-naming failures.** The stage-1 face/edge signatures resolved
deterministically across every rebuild in this batch (re-evaluated on reload;
inspector == API each time). No `subshape_unresolved` / `subshape_ambiguous`
surprises on these parts. This is the load-bearing positive result: the
Part-modeling ✅ re-score is earned on real geometry, not just goldens.

## Not attempted (scope-honest)
- A **flange lip on the housing** (brief-listed) was omitted: shell hollows the
  *whole* current body, so a flange added before shelling becomes a thin tray
  and one added after needs sketch-on-a-thin-rim — both awkward in v1. The
  flange + bolt-pattern capability is instead shown on the duct, where it's
  natural. Worth a backlog note: "shell a selected feature/region," not the
  whole body.
- The **pattern feature itself** (linear/circular) was not showcased because its
  union-only semantics don't fit any of these four parts' real needs (see F1).
