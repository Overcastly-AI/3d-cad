/**
 * Shared length-input helpers — the thin app-side adapters over the design
 * system's units core (docs/design/units.md §2). Every feature-param length
 * field routes its raw string through one of these so a factor is never inlined
 * and the canonical-mm boundary lives in exactly one place.
 *
 * `parseLength`/`formatLength`/`toMm`/`fromMm` are the pure core (packages/design);
 * these add only the two validation flavours the feature forms need — a strictly
 * positive length (a distance/thickness/radius) and a signed length (an offset /
 * a coordinate) — plus the seed string an edit form shows.
 */
import {
  formatAngle,
  formatLength,
  fromMm,
  isCarpenterLength,
  isPartialLength,
  type LengthUnit,
  parseLength,
  toMm,
} from "@loft/design";

import {
  type BareLengths,
  bareLengths,
  coerceToField,
  evaluateExpression,
  type ExprKind,
  ExprError,
  type FieldKind,
  mixedNumberAmbiguity,
  type Quantity,
} from "../features/expr";

export type { FieldKind } from "../features/expr";

/**
 * Parse a strictly-positive length field → canonical mm, or null when empty,
 * unparseable, or ≤ 0 (a zero-depth extrude / zero-radius fillet is no feature).
 * A bare number is read in `unit`; an explicit suffix (`2in`) overrides it.
 */
export function parsePositiveLengthMm(
  input: string,
  unit: LengthUnit,
): number | null {
  const mm = parseLength(input, unit);
  return mm !== null && mm > 0 ? mm : null;
}

/**
 * Parse a signed length field → canonical mm, or null when empty/unparseable.
 * Any finite value is valid (0 coincides; negatives select the other side) — a
 * datum offset or an axis-point coordinate.
 */
export function parseSignedLengthMm(
  input: string,
  unit: LengthUnit,
): number | null {
  return parseLength(input, unit);
}

/**
 * The display string an edit form seeds into a length cell: a stored mm value
 * rendered in `unit`, trailing-zero trimmed, WITHOUT a suffix (the cell shows
 * the unit as its own affordance).
 *
 * Seed precision is unit-aware. The default 4-fraction-digit *display*
 * precision would quantise an imperial seed by up to ~2.5e-3 mm (0.0001 in) —
 * ABOVE the 1e-4 mm kernel linear tolerance — so re-submitting an unchanged
 * feature in an inch/foot document would silently shift its geometry. We seed
 * with enough digits that the shown value round-trips to within ≤1e-5 mm of the
 * stored value (an order below tolerance): `digits = ceil(log10(mm-per-unit) + 5)`.
 * Clean values still trim short (25.4 mm → "1" in inches); only genuinely
 * non-round foreign-unit values grow a faithful long decimal, as they must.
 */
export function lengthInputValue(mm: number, unit: LengthUnit): string {
  const mmPerUnit = toMm(1, unit);
  const digits = Math.max(4, Math.ceil(Math.log10(mmPerUnit) + 5));
  return formatLength(mm, unit, {
    unitSuffix: false,
    maxFractionDigits: digits,
  });
}

// --- formulas in a numeric field (PART-PARAMETERS step 8, RESEARCH §20) -------

/**
 * What one numeric field's text is: nothing yet, a NUMBER the editor reads as
 * it always has (a bare number in the document unit, or with its own suffix),
 * or a FORMULA (`H/2`, `W - 2 mm`, `20*tan(15)`) the server resolves.
 *
 * The document-unit rule is the Parameters panel's: a bare number typed in an
 * inch document means inches. A number never becomes a formula, so it never
 * reaches the server as text that would read it as mm; inside a formula the
 * grammar's own rule holds (a bare number joins the other side's kind).
 */
export type FieldEntry =
  | { kind: "empty" }
  | { kind: "number" }
  | { kind: "formula"; expression: string };

const PLAIN_NUMBER_RE = /^[+-]?(?:\d+\.?\d*|\.\d+)$/;
/** Half a number on its way: `-`, `.`, `-.`. Still a number, not a formula. */
const PARTIAL_NUMBER_RE = /^[+-]?\.?$/;

export function parseFieldEntry(
  text: string,
  field: FieldKind,
  unit: LengthUnit,
): FieldEntry {
  const trimmed = text.trim();
  if (trimmed === "") return { kind: "empty" };
  if (PARTIAL_NUMBER_RE.test(trimmed)) return { kind: "number" };
  if (field === "length") {
    if (parseLength(trimmed, unit) !== null || isPartialLength(trimmed)) {
      return { kind: "number" };
    }
  } else if (PLAIN_NUMBER_RE.test(trimmed)) {
    // Angles, ratios and counts: the editors read a plain number; `30 deg`
    // is a formula, which resolves to the same 30.
    return { kind: "number" };
  }
  return { kind: "formula", expression: trimmed };
}

/**
 * A resolved field value as the text the editor's form takes: a length in the
 * document unit, an angle in degrees, a count as an integer. Full precision:
 * the field SHOWS the formula, and this text only feeds the editor's own
 * parse, validation and live preview (the server resolves the formula again).
 */
export function formatFieldValue(
  value: number,
  field: FieldKind,
  unit: LengthUnit,
): string {
  if (field === "length") return String(fromMm(value, unit));
  if (field === "int") return String(Math.round(value));
  return String(value);
}

/** The resolved value as the field's hint shows it: `= 10 mm`, `= 30°`. */
export function formatFieldHint(
  value: number,
  field: FieldKind,
  unit: LengthUnit,
): string {
  if (field === "length") return `= ${formatLength(value, unit)}`;
  if (field === "angle") return `= ${formatAngle(value)}`;
  return `= ${formatAngle(value, { unitSuffix: false })}`;
}

/**
 * The echo a length NUMBER written in carpenter notation gets (`11-15/32` →
 * `= 11.46875 in`), as Fusion echoes a formula, so a mis-typed fraction shows
 * before it is committed; null for a plain decimal, which echoes itself.
 * Six fraction digits carry every 1/64 exactly.
 */
export function carpenterHint(text: string, unit: LengthUnit): string | null {
  if (!isCarpenterLength(text, unit)) return null;
  const mm = parseLength(text, unit);
  if (mm === null) return null;
  return `= ${formatLength(mm, unit, { maxFractionDigits: 6 })}`;
}

/**
 * Why a length formula TYPED NOW cannot be taken as written, or null: a
 * hyphenated mixed number inside it (`2*11-15/32`) reads two ways, and the
 * field refuses rather than guess (RESEARCH §29). Stored formulas never come
 * through here, so their meaning is the server's, unchanged.
 */
export function typedFormulaError(
  expression: string,
  field: FieldKind,
  unit: LengthUnit,
): string | null {
  if (field !== "length") return null;
  const why = mixedNumberAmbiguity(expression, unit);
  return why === null ? null : `${why.charAt(0).toUpperCase()}${why.slice(1)}.`;
}

/**
 * The bare terms a part in `unit` reads as mm in `expression`, and the text
 * that reads them in `unit` (FORMULA-BARE-UNIT, `bare_lengths` on the
 * server). Null in an mm part, while the names are unread, or when nothing
 * is bare. A formula a save ENTERS is stored as that text; one already stored
 * keeps its own and is flagged with it as the fix.
 */
export function bareFieldFormula(
  expression: string,
  field: FieldKind,
  names: ReadonlyMap<string, Quantity> | null,
  unit: LengthUnit,
): BareLengths | null {
  if (names === null) return null;
  const kinds = new Map<string, ExprKind>();
  for (const [name, q] of names) kinds.set(name, q.kind);
  return bareLengths(
    expression,
    unit,
    field === "int" ? "unitless" : field,
    kinds,
  );
}

/** A formula's outcome for one field. */
export type FormulaResult =
  { ok: true; value: number } | { ok: false; message: string; code: string };

/**
 * Evaluate a field's formula over the names in scope and coerce it to the
 * field's kind, the way documents will. `null` names = not read yet.
 */
export function resolveFieldFormula(
  expression: string,
  field: FieldKind,
  names: ReadonlyMap<string, Quantity> | null,
): FormulaResult {
  if (names === null) {
    return { ok: false, message: "Reading the parameters…", code: "pending" };
  }
  try {
    const q = evaluateExpression(expression, names);
    return { ok: true, value: coerceToField(q, field) };
  } catch (error) {
    if (!(error instanceof ExprError)) throw error;
    const text = error.message;
    return {
      ok: false,
      message: `${text.charAt(0).toUpperCase()}${text.slice(1)}.`,
      code: error.code,
    };
  }
}
