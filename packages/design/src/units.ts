/**
 * Length units — the one conversion + parse + format core (docs/design/units.md
 * §2). BOTH renderers consume this module: the DOM input cells and any
 * viewport/HUD readout. There is no second copy of a factor anywhere.
 *
 * The load-bearing rule: storage and the kernel are canonical millimetres,
 * forever. A document's `length_unit` is presentation metadata — it says how to
 * PARSE what a human types and how to FORMAT a stored mm value, nothing more.
 * Every `*_mm` value on the wire stays mm; conversion happens only here, at the
 * input/display boundary.
 *
 * `LengthUnit` has exactly one home — the generated ts-client type (pydantic →
 * OpenAPI → ts-client). We import it, never re-declare the union; only the
 * mathematical FACTORS (exact mm-per-unit constants) live in this package.
 */
import type { components } from "@loft/ts-client/gateway";

/** The document display unit — single source: the generated contract. */
export type LengthUnit = components["schemas"]["PartResponse"]["length_unit"];

/**
 * Exact millimetres per unit. Imperial factors are exact by definition
 * (1 in ≡ 25.4 mm, 1 ft ≡ 304.8 mm) — never rounded, so a round-trip through a
 * unit never drifts a stored mm value.
 */
export const MM_PER_UNIT: Readonly<Record<LengthUnit, number>> = {
  mm: 1,
  cm: 10,
  m: 1000,
  in: 25.4,
  ft: 304.8,
};

/** The units, in display order (metric ascending, then imperial). */
export const LENGTH_UNITS: readonly LengthUnit[] = [
  "mm",
  "cm",
  "m",
  "in",
  "ft",
];

/** A short human label for a unit (identical to its code — SI/US convention). */
export function lengthUnitLabel(unit: LengthUnit): string {
  return unit;
}

/** A display value in `unit` → canonical millimetres. */
export function toMm(value: number, unit: LengthUnit): number {
  return value * MM_PER_UNIT[unit];
}

/** Canonical millimetres → a display value in `unit`. */
export function fromMm(mm: number, unit: LengthUnit): number {
  return mm / MM_PER_UNIT[unit];
}

/**
 * Canonical square-millimetres → a display value in `unit²` (area scales with
 * the square of the length factor, so mm²→in² divides by 25.4²). Storage/kernel
 * are always mm²; this is the display boundary for an AREA readout.
 */
export function fromMmArea(mm2: number, unit: LengthUnit): number {
  const factor = MM_PER_UNIT[unit];
  return mm2 / (factor * factor);
}

/**
 * Canonical cubic-millimetres → a display value in `unit³` (volume scales with
 * the cube of the length factor, so mm³→in³ divides by 25.4³). Storage/kernel
 * are always mm³; this is the display boundary for a VOLUME readout.
 */
export function fromMmVolume(mm3: number, unit: LengthUnit): number {
  const factor = MM_PER_UNIT[unit];
  return mm3 / (factor * factor * factor);
}

/** The area-unit label for a readout cell (`"mm²"`, `"in²"`). */
export function areaUnitLabel(unit: LengthUnit): string {
  return `${unit}²`;
}

/** The volume-unit label for a readout cell (`"mm³"`, `"in³"`). */
export function volumeUnitLabel(unit: LengthUnit): string {
  return `${unit}³`;
}

/** Suffix → unit, longest-first so `mm` wins over `m` and `cm` over `m`. */
const SUFFIX_UNIT: ReadonlyArray<readonly [string, LengthUnit]> = [
  ["mm", "mm"],
  ["cm", "cm"],
  ["ft", "ft"],
  ["in", "in"],
  ["m", "m"],
];

/**
 * A number, optionally followed by a unit suffix. The number is a plain decimal
 * (signed, no scientific notation — CAD dimensions aren't typed as `5e3`). The
 * suffix, when present, OVERRIDES the document unit.
 */
const LENGTH_RE = /^([+-]?(?:\d+\.?\d*|\.\d+))\s*([a-zA-Z]*)$/;

/**
 * Parse a length the user typed → canonical millimetres, or `null` when it is
 * empty / unparseable / NaN. A bare number is read in the document `unit`
 * (`50` → the doc unit); an explicit suffix overrides it (`2in`, `2 in`,
 * `50mm`, `3.5 cm`). Signed values are valid — a gap/offset can be negative.
 *
 * This deliberately does NOT evaluate expressions (`width/2`): an ExpressionField
 * resolves its expression to a number FIRST, then the resolved value is
 * converted via {@link toMm}. `parseLength` is the number→mm boundary only.
 */
export function parseLength(input: string, unit: LengthUnit): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const match = LENGTH_RE.exec(trimmed);
  if (match === null) return null;
  const value = Number(match[1]);
  if (!Number.isFinite(value)) return null;
  const suffix = match[2]?.toLowerCase() ?? "";
  let unitFor: LengthUnit = unit;
  if (suffix !== "") {
    const found = SUFFIX_UNIT.find(([s]) => s === suffix);
    if (found === undefined) return null; // an unknown suffix is not a length
    unitFor = found[1];
  }
  return toMm(value, unitFor);
}

/**
 * True when `input` is not a length YET, but typing more could make it one —
 * the transient states every unit field passes through under the keyboard: the
 * empty cell, a lone sign (`-`), a bare decimal point (`.`, `-.`), and a number
 * trailing the first letters of a suffix (`12 i` on the way to `12 in`).
 *
 * It lives beside {@link parseLength} because only this module knows the
 * accepted grammar, suffix table included. Callers ask it only when
 * `parseLength` has already returned `null`, and the distinction is the whole
 * point: a field that reported "not a number" the instant you typed `-` would
 * be lying about a keystroke in progress, and a field that stayed silent for
 * `12 x` would be hiding a real mistake. Incomplete reads as PENDING; anything
 * else reads as INVALID.
 */
export function isPartialLength(input: string): boolean {
  const trimmed = input.trim();
  if (trimmed === "") return true;
  // Already a length — nothing pending about it.
  if (parseLength(trimmed, "mm") !== null) return false;
  // A signed/decimal fragment: "-", "+", ".", "-.", "+."
  if (/^[+-]?\.?$/.test(trimmed)) return true;
  // A number trailing a suffix fragment: "12 i" (→ "in"), "3c" (→ "cm").
  const match = /^[+-]?(?:\d+\.?\d*|\.\d+)\s*([a-zA-Z]+)$/.exec(trimmed);
  if (match === null) return false;
  const fragment = (match[1] as string).toLowerCase();
  return SUFFIX_UNIT.some(([suffix]) => suffix.startsWith(fragment));
}

/** Options for {@link formatLength}. */
export interface FormatLengthOptions {
  /** Max digits after the decimal point before trailing zeros are trimmed. */
  maxFractionDigits?: number;
  /** Append the unit suffix (`"2 in"`); false yields the bare number (`"2"`). */
  unitSuffix?: boolean;
}

/** Trailing-zero-trimmed decimal string; normalises `-0` to `0`. */
function trimDecimal(value: number, maxFractionDigits: number): string {
  const rounded = Number(value.toFixed(maxFractionDigits));
  const normalised = Object.is(rounded, -0) ? 0 : rounded;
  return String(normalised);
}

/**
 * Canonical millimetres → a display string in `unit`, trailing-zero trimmed,
 * with the unit suffix by default (`formatLength(50.8, "in") === "2 in"`).
 */
export function formatLength(
  mm: number,
  unit: LengthUnit,
  opts: FormatLengthOptions = {},
): string {
  const { maxFractionDigits = 4, unitSuffix = true } = opts;
  const text = trimDecimal(fromMm(mm, unit), maxFractionDigits);
  return unitSuffix ? `${text} ${unit}` : text;
}

/**
 * The mass units a readout may use (docs/design/materials.md §5).
 *
 * This vocabulary lives HERE and nowhere else, deliberately: the wire carries
 * canonical grams forever, so py-kit declares no mass-unit enum — a literal on
 * the contract would be a second declaration of a rule with exactly one
 * consumer, the display boundary. Length is the mirror image: py-kit owns the
 * `LengthUnit` vocabulary (documents PERSIST it) and this package owns the
 * factors; nothing persists a mass unit, so this package owns both.
 */
export type MassUnit = "g" | "kg" | "lb";

/**
 * Exact grams per mass unit. The pound is exact by definition
 * (1 lb ≡ 453.59237 g), like the inch — never rounded, so a mass never drifts
 * through a display conversion.
 */
export const MASS_G_PER_UNIT: Readonly<Record<MassUnit, number>> = {
  g: 1,
  kg: 1000,
  lb: 453.59237,
};

/**
 * The mass unit a document reads in — DERIVED from its length unit, so there is
 * no second setting to keep in sync (materials.md §5): an imperial document
 * (`in`/`ft`) reads pounds; every metric one reads grams, promoting to
 * kilogrammes above 1000 g so a 12 kg weldment never reads as `12000 g`.
 */
export function massUnitFor(lengthUnit: LengthUnit, grams: number): MassUnit {
  if (lengthUnit === "in" || lengthUnit === "ft") return "lb";
  return Math.abs(grams) >= MASS_G_PER_UNIT.kg ? "kg" : "g";
}

/** Canonical grams → a display value in `unit`. */
export function fromGrams(grams: number, unit: MassUnit): number {
  return grams / MASS_G_PER_UNIT[unit];
}

/** Options for {@link formatMass}. */
export interface FormatMassOptions {
  /** Max digits after the decimal point before trailing zeros are trimmed. */
  maxFractionDigits?: number;
  /** Append the unit suffix (`"27 g"`); false yields the bare number (`"27"`). */
  unitSuffix?: boolean;
}

/**
 * Canonical GRAMS → a display string in the document's derived mass unit
 * (`formatMass(27, "mm") === "27 g"`, `formatMass(27, "in") === "0.0595 lb"`).
 * The wire stays grams; this is the only place a mass is ever converted.
 *
 * There is deliberately no null overload: `mass_g: null` means "nobody has said
 * what this is made of" (materials.md §1.2), and a formatter that answered it
 * with a dash would let a caller render absence without deciding what to say
 * about it. Absence is the CALLER's sentence — and it is never `0 g`.
 */
export function formatMass(
  grams: number,
  lengthUnit: LengthUnit,
  opts: FormatMassOptions = {},
): string {
  const { maxFractionDigits = 4, unitSuffix = true } = opts;
  const unit = massUnitFor(lengthUnit, grams);
  const text = trimDecimal(fromGrams(grams, unit), maxFractionDigits);
  return unitSuffix ? `${text} ${unit}` : text;
}
