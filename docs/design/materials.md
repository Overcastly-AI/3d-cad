# Design — Materials, density, and mass (v1)

Status: **accepted** (2026-07-30). Scope: a panel titled MASS PROPERTIES that
reports Volume, Area and Centroid and **no mass** is an overstated surface —
the defect class this codebase keeps producing (the false CLASH badge, the
Tapped checkbox's phantom drawing note, "Up to date" derived from
`isFetching`). This slice gives bodies a **material with a density**, derives
mass from it in the kernel, rolls it up honestly through multi-body parts and
assemblies, and — where nothing has been assigned — reports **no mass at all**.

Founder-raised 2026-07-30: "units and mass should be controlled from a settings
page."

## 1. The load-bearing rules

1. **Mass is DERIVED, never stored.** `mass = volume x density`, computed in
   `geometry.kernel.properties.measure_shape` from the very volume that
   function just measured, so a reported mass can never drift from the volume
   it belongs to. Nothing persists a mass; nothing else multiplies a density.
   One helper (`py_kit.schemas.materials.mass_g`) is the single conversion.

2. **No material means NO mass — absent, not zero.** Every mass field on the
   wire is `float | None`, and `None` means "nobody has said what this is made
   of". `0 g` would be a claim about a real, massless body; a defaulted steel
   would be a different lie ("what do you mean my ABS bracket weighs 2 kg?").
   A consumer must render absence as absence, and must not title a surface
   "mass" on the strength of a null (§6).

3. **Density is the only property v1 models.** Thermal/elastic/appearance
   properties would be unbacked promises until something computes with them.
   The library carries `key`, display `name`, `density_kg_m3` — nothing else.

4. **Canonical units mirror the length convention** (docs/design/units.md).
   Storage and the kernel are canonical millimetres, so the canonical mass unit
   is what falls out of `mm^3 x kg/m^3`: **grams**. `mass_g` is grams
   everywhere on the wire, forever. Display units (g / kg / lb) are a
   presentation concern (§5).

## 2. The assignment: one document default + per-body overrides

A single document-level material would be wrong for exactly the parts mass
matters most on — a multi-body part legitimately mixes materials (a steel pin
pressed into an aluminium housing). So:

```
MaterialAssignment
  default_material: MaterialKey | None     # the document's material
  bodies: [ { base_feature_id, material } ]  # per-BODY overrides
```

- `base_feature_id` is the body's §MB-0 identity — the id of the feature that
  CREATED it, the same key `EvaluationState.bodies` and `BodyLumpInfo` use — so
  an override survives edits the way any body reference does. An override
  naming a body the current tree does not produce is inert, not an error (a
  rolled-back tree legitimately hides a body for a while).
- Resolution is ONE function, `resolve_body_material`: the body's own override,
  else the document default, else nothing. No consumer re-derives it.
- **Duplicate overrides for one body are rejected at the boundary.** "Last
  wins" would make a body's mass depend on array order, which is the
  nondeterminism RESEARCH §9 forbids.
- Storage: `parts.materials`, one nullable JSON/JSONB column (migration 0013)
  holding the serialized assignment. NULL is the honest "never assigned", which
  every pre-existing row backfills to for free. Read and written as ONE object;
  a normalized child table would buy nothing over the validated pydantic model
  (`features.params` sets the precedent).
- Writing it is `PATCH /api/v1/parts/{id}` with `materials` — a **wholesale
  replacement**, so the request states the full intended state and two
  concurrent edits cannot interleave into an assignment neither of them sent.
  An assignment naming nothing clears back to NULL.
- **A material change bumps `tree_version` AND leaves the last-evaluate record
  behind as stale.** This is the one difference from `length_unit`: units are
  presentation metadata the kernel never sees, so a unit change carries the
  recorded verdict forward (feature-tree.md §4.4a); a material change really
  does invalidate the previous answer, because mass was derived from it.

Material is therefore the **one thing on the evaluation request that is not
pure geometry intent** — documents hands it to geometry alongside the feature
prefix, and the gateway forwards it verbatim like the rest of the request.

## 3. Roll-ups: mass composes analytically, and the centroid stops lying

Both existing analytic roll-ups — the multi-body part
(`kernel.properties.combine_properties`) and the assembly
(`assembly.evaluate._combine_properties`) — gain mass the same way they already
compose volume: no re-mesh, no boolean, a fixed-order float64 reduction.

- Total `mass_g` = Σ per-body / per-instance masses.
- `center_of_mass` is weighted by **MASS**.
- `centroid` remains the VOLUME-weighted geometric centre, and is always
  reported (it needs no material).

The distinction is not academic, and the old code got it wrong in words: the
assembly roll-up already **called** its centroid "mass-weighted" while
computing a volume weighting. Those agree only when every body shares one
density. The `multibody-two-disjoint-boxes` golden is the case where they do
not: two cubes of equal volume, one aluminium and one steel, whose volume
centroid sits at x=25 mm while their true centre of mass sits at
x = 34180/1057 = 32.3368… mm — 7.34 mm toward the steel.

**A roll-up is null unless EVERY contributor has a material.** A partial sum
would under-report the part while looking like a complete answer — the same
class of confidently-wrong output this slice exists to remove. Per-body masses
are still reported individually (`BodyLumpInfo.material` / `.mass_g`), so a
consumer can say WHICH body is missing one instead of just going quiet.

STEP export/import does not carry material in v1: a re-imported body has no
material and therefore no mass, which is honest — the file did not tell us.

## 4. The wire

| Field | Meaning |
|---|---|
| `ShapeProperties.mass_g` | Mass (g), or **null** = no material anywhere in the shape |
| `ShapeProperties.center_of_mass` | Mass-weighted centre (mm), or **null**, same condition |
| `ShapeProperties.centroid` | VOLUME centroid (mm) — always present; equals the centre of mass only for a single-material shape |
| `BodyLumpInfo.material` / `.mass_g` | The resolved material and mass of ONE body; null = none assigned |
| `EvaluateTreeRequest.materials` | The part's assignment (null = none) |
| `EvaluatedInstance.materials` | The instanced part's assignment; an instance evaluates to the same mass as opening the part |
| `PartResponse.materials` | Always an assignment object; a stored NULL reads back as the EMPTY assignment, so a consumer never has to tell null from empty |
| `GET /api/v1/materials` | The built-in library (key, name, density) — served, never hardcoded client-side |

## 5. Units (display) — the same seam the lengths use

`packages/design/src/units.ts` is the one conversion/format core for both
renderers (units.md §2), and mass joins it there — **not a second path**:

- `MASS_G_PER_UNIT = { g: 1, kg: 1000, lb: 453.59237 }` (the pound is exact by
  definition, like the inch).
- The document's mass unit is DERIVED from its `length_unit`, so there is no
  second setting to keep in sync: `in`/`ft` → `lb`, everything else → metric,
  promoting g → kg above 1000 g.
- `formatMass(g, lengthUnit)` returns the display string; the wire stays grams.

py-kit deliberately declares **no** mass-unit enum: the wire carries only
canonical grams, so a `MassUnit` literal on the contract would be a second
declaration of a rule that has exactly one consumer (the display boundary).
This mirrors units.md, where py-kit owns the length-unit *vocabulary* (because
documents persist it) and `packages/design` owns the *factors*.

## 6. Honesty in the UI (what the frontend must do)

1. **Do not promise mass until there is a material.** While
   `properties.mass_g` is null the panel is what it always was —
   Volume / Area / Centroid — and must NOT be titled "MASS PROPERTIES". Title
   it for what it shows (e.g. "PROPERTIES"), and offer the assign-material
   affordance; once mass exists, a mass row appears and the mass title is
   earned.
2. **Never render `0 g` for absent.** Absence is a different glyph (an em dash,
   "no material") plus the way to fix it.
3. **A mixed-material part shows the centre of MASS**, labelled distinctly from
   the centroid, because they differ.
4. **Show which body is unassigned** when the whole-part mass is null — the
   per-body `material`/`mass_g` fields exist for exactly that.

## 7. What v1 does NOT do (deliberately)

- **No user-defined materials.** `MaterialKey` is a closed literal so an
  unrecognised material is a parse error at the boundary instead of a silent
  "no mass" three services later. Custom materials extend the type additively
  (a `{kind: "custom", density_kg_m3}` branch), never by loosening it to `str`.
- **No material on assemblies.** An assembly has no material of its own; its
  mass is the sum of what its parts are made of.
- **No appearance coupling.** Material does not drive viewport shading in v1;
  making "steel" look like steel is a separate (welcome) piece of work.
- **No cost/BOM roll-up**, no centre-of-gravity display in drawings, no
  moments of inertia. Inertia tensors are the obvious next physical property
  and compose the same analytic way — filed, not built.

## 8. Gates

- Golden `sketch-extrude-40x25x10` assigns aluminium 6061 → mass 27.0 g exactly
  (10000 mm^3 x 2.70 g/cm^3), centre of mass = the volume centroid.
- Golden `multibody-two-disjoint-boxes` mixes aluminium 6061 with a per-body
  steel 1018 override → 84.56 g, centre of mass x = 34180/1057 mm ≠ the volume
  centroid 25 mm.
- **Every other golden asserts the absence half**: no material in its model ⇒
  the runner requires `mass_g is None` and `center_of_mass is None`. A future
  "helpful" default would fail 45 goldens at once.
- Mass rides each model's existing documented tolerance rather than a new bound
  of its own: mass = volume x density and every library density is < 1 expressed
  in g/mm^3 (steel, the densest, is 7.87e-3), so the propagated mass error is
  strictly SMALLER than the volume error already bounded. A test asserts that
  premise (`test_every_library_density_is_under_one_gram_per_cubic_mm`) so
  adding a denser material fails loudly instead of silently widening the claim.
  Measured deviations: docs/GEOMETRY-QA.md 2026-07-30.

## 9. The library (v1)

Handbook NOMINAL densities at room temperature, rounded to the three
significant figures every MCAD system ships as its default (ASM Metals
Reference Book / MatWeb typical values for the metals; resin and filament
datasheet typicals for the polymers). They are defaults, not measurements — a
production part uses its supplier's certificate, and a printed part is lighter
than solid PLA because it is not solid.

| key | name | kg/m^3 |
|---|---|---|
| `steel_1018` | Steel (AISI 1018) | 7870 |
| `stainless_304` | Stainless steel (AISI 304) | 8000 |
| `aluminium_6061` | Aluminium 6061 | 2700 |
| `brass_c360` | Brass (C360) | 8500 |
| `abs` | ABS | 1040 |
| `pla` | PLA | 1240 |
| `nylon_6` | Nylon (PA6) | 1140 |
