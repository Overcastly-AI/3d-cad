# Design — Document units (length) v1

Status: **accepted** (2026-07-17). Scope: let a working engineer set a
document's length unit and type/read dimensions in it (`2 in`, `50 mm`),
while the kernel and every stored value stay canonical. Angles are always
degrees in v1 (no rad/gon).

## The one load-bearing rule

**Storage and the kernel are canonical millimetres, forever. Units are a
presentation + input concern that lives entirely at the UI boundary.** No
`*_mm` field changes meaning; the geometry service never learns what unit a
document is displayed in. A document's unit is metadata *about how to render
and parse* its canonical mm values — nothing downstream of the input cell
converts.

This keeps determinism, goldens, tolerances (linear 1e-7), and every existing
`distance_mm`/`x_mm`/`offset_mm` contract byte-identical. Changing the display
unit of a document re-labels and re-formats; it never re-solves or migrates a
single stored number.

## Where each piece lives (single source of truth)

1. **The unit enum + the document's setting → the contract** (pydantic →
   OpenAPI → ts-client). `LengthUnit = Literal["mm","cm","m","in","ft"]`, added
   to `py-kit` schemas and persisted as `length_unit` on the `parts` and
   `assemblies` documents (column, default `"mm"`; drawings follow their
   referenced part in a later slice — out of v1). Backward compatible: existing
   rows default to `mm`, so nothing observable changes until a user picks
   another unit.

2. **The conversion + parse + format core → `packages/design`** (one module,
   both renderers consume it: DOM input cells AND any viewport/HUD readout — no
   second copy of a factor). Pure, exhaustively unit-tested. Exact factors only:

   | unit | mm per unit (exact) |
   |------|--------------------|
   | mm   | 1                  |
   | cm   | 10                 |
   | m    | 1000               |
   | in   | 25.4               |
   | ft   | 304.8              |

   API (canonical mm is always the wire/storage value):
   - `toMm(value: number, unit: LengthUnit): number`
   - `fromMm(mm: number, unit: LengthUnit): number`
   - `parseLength(input: string, unit: LengthUnit): number | null` — accepts a
     bare number in the document unit (`50` → doc unit) OR an explicit
     unit-suffixed literal (`2in`, `2 in`, `50mm`, `3.5 cm`) which overrides the
     document unit; returns canonical mm, or `null` on unparseable/`NaN`.
   - `formatLength(mm: number, unit: LengthUnit, opts?): string` — canonical mm →
     display string in the document unit, sensible precision (trailing-zero
     trimmed), unit suffix.

   `LengthUnit` is imported from the generated ts-client type (never re-declared)
   so the enum has exactly one home; only the *factors* (mathematical constants)
   live in `packages/design`.

3. **The input cells stay the design primitives.** `NumberField` /
   `ExpressionField` already carry a `unit` suffix prop and expression parsing;
   the wiring passes the document unit as that suffix and routes the raw string
   through `parseLength` (so `width/2` in `ExpressionField` still resolves, then
   converts). App code never restyles a raw `<input>` and never inlines a factor.

## Slice sequence

- **U1 (backend + contract):** `length_unit: LengthUnit` on the part and
  assembly document models + Create/Response schemas; alembic migration (default
  `mm`, backfill existing rows); documents CRUD accepts/returns it; gateway
  passes it through; `just gen` regen (ts-client gains `LengthUnit` + the field).
  Golden: an existing part with no unit reads back `mm`; setting `in` round-trips.
- **U2 (frontend core + wiring):** the `packages/design` units module (+ full
  vitest); a document-unit selector in the editor chrome (persists via the
  document update API); every dimension input (extrude/revolve/… feature params,
  the assembly distance/angle mate value) parses via `parseLength` and displays
  via `formatLength` in the document unit; readouts (measured dimensions, mate
  gap echo) format the same way. e2e: set a part to inches, type `2`, confirm the
  body is 50.8 mm (canonical) and the field reads `2 in`; type `25.4 mm` into an
  inch document and confirm it stores 25.4 mm / shows `1 in`.

## Explicitly out of v1 (later slices, note in BACKLOG)

Per-document *angle* unit (always degrees now); mass/volume/area unit display
(the roll-up readouts — follow once length lands); drawing-sheet display units
(follow the referenced part); dual-dimension display; imperial fractional input
(`1 1/2"`); unit-aware STEP/STL export headers.
