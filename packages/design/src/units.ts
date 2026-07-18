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
