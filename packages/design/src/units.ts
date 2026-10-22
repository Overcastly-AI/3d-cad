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
 * One magnitude, as a framer types it: a mixed number (`11 15/32`, or the
 * hyphenated `11-15/32` with NO spaces round the hyphen), a simple fraction
 * (`15/32`) or a plain decimal (`11.5`; no scientific notation, CAD dimensions
 * aren't typed as `5e3`).
 */
const MAGNITUDE = String.raw`(?:\d+(?:[ \t]+|-)\d+\/\d+|\d+\/\d+|\d+\.?\d*|\.\d+)`;

/** The foot mark and the inch mark, ASCII and typographic (prime, double prime). */
const FOOT_MARK = String.raw`['′]`;
const INCH_MARK = String.raw`(?:"|″|'')`;

/**
 * A whole length entry (RESEARCH §29, carpenter notation): an optional sign,
 * an optional feet part (`5'`, then the inches straight on, after a space, or
 * after a hyphen with no spaces: `5'6"`, `5' 6"`, `5'-6"`), then a magnitude
 * with an optional inch mark or unit suffix. The suffix, when present,
 * OVERRIDES the document unit. After a feet part the inches are inches
 * whatever the document unit, as in SketchUp and Chief Architect.
 */
const LENGTH_RE = new RegExp(
  String.raw`^([+-]?)(?:(${MAGNITUDE})[ \t]*${FOOT_MARK}(?:-|[ \t]*))?` +
    String.raw`(?:(${MAGNITUDE})[ \t]*(${INCH_MARK}|[a-zA-Z]*))?$`,
);

const MIXED_RE = /^(\d+)(?:[ \t]+|-)(\d+)\/(\d+)$/;
const FRACTION_RE = /^(\d+)\/(\d+)$/;
const HYPHEN_MIXED_RE = /^\d+-\d+\/\d+$/;

/** A magnitude's value, or null for a zero denominator. */
function magnitudeValue(text: string): number | null {
  const mixed = MIXED_RE.exec(text);
  if (mixed !== null) {
    const den = Number(mixed[3]);
    return den === 0 ? null : Number(mixed[1]) + Number(mixed[2]) / den;
  }
  const fraction = FRACTION_RE.exec(text);
  if (fraction !== null) {
    const den = Number(fraction[2]);
    return den === 0 ? null : Number(fraction[1]) / den;
  }
  return Number(text);
}

/** A magnitude as the expression grammar spells it, carrying `unit`. */
function magnitudeExpression(text: string, unit: LengthUnit): string {
  const mixed = MIXED_RE.exec(text);
  if (mixed !== null) {
    return `${mixed[1]} ${unit} + ${mixed[2]} ${unit}/${mixed[3]}`;
  }
  const fraction = FRACTION_RE.exec(text);
  if (fraction !== null) return `${fraction[1]} ${unit}/${fraction[2]}`;
  return `${text} ${unit}`;
}

interface LengthParts {
  negative: boolean;
  /** The feet magnitude's text, when there is a feet part. */
  feet: string | null;
  /** The main magnitude's text, when there is one. */
  value: string | null;
  /** The unit the main magnitude is in. */
  unit: LengthUnit;
}

/** Split an entry into its parts, or null when it is not a length. */
function lengthParts(input: string, unit: LengthUnit): LengthParts | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const match = LENGTH_RE.exec(trimmed);
  if (match === null) return null;
  const feet = match[2] ?? null;
  const value = match[3] ?? null;
  if (feet === null && value === null) return null;
  const mark = match[4] ?? "";
  const suffix = mark.toLowerCase();
  let unitFor: LengthUnit = unit;
  if (mark === '"' || mark === "″" || mark === "''") unitFor = "in";
  else if (suffix !== "") {
    const found = SUFFIX_UNIT.find(([s]) => s === suffix);
    if (found === undefined) return null; // an unknown suffix is not a length
    unitFor = found[1];
  }
  // After feet, only inches may follow (`5' 6"`, `5' 6`, `5' 6 in`).
  if (feet !== null) {
    if (value !== null && suffix !== "" && unitFor !== "in") return null;
    unitFor = "in";
  }
  // The hyphenated mixed number is imperial notation. In a metric reading
  // (`100-10/2` in an mm field) a hyphen is far more likely a minus, so it is
  // not a length here; the field then refuses it as ambiguous (RESEARCH §29).
  if (value !== null && HYPHEN_MIXED_RE.test(value)) {
    if (unitFor !== "in" && unitFor !== "ft") return null;
  }
  return { negative: match[1] === "-", feet, value, unit: unitFor };
}

/**
 * Parse a length the user typed → canonical millimetres, or `null` when it is
 * empty / unparseable / NaN. A bare number is read in the document `unit`
 * (`50` → the doc unit); an explicit suffix overrides it (`2in`, `2 in`,
 * `50mm`, `3.5 cm`). Signed values are valid — a gap/offset can be negative.
 *
 * Carpenter notation is a length too (RESEARCH §29): `11 15/32` is eleven
 * and fifteen thirty-seconds in the document unit, `11 15/32"` the same in
 * inches, `5' 6-1/2"` is 66.5 in and `-3/4` is minus three quarters. The
 * hyphenated `11-15/32` (no spaces round the hyphen) is a mixed number only
 * when it reads in inches or feet (the unit, a `"`/`in`/`ft` suffix, or a
 * feet part): in a metric reading it is not a length, and the field refuses
 * it as ambiguous. `11 - 15/32` is never a length, so it reaches the
 * expression language as the subtraction it reads as.
 *
 * This deliberately does NOT evaluate expressions (`width/2`): an ExpressionField
 * resolves its expression to a number FIRST, then the resolved value is
 * converted via {@link toMm}. `parseLength` is the number→mm boundary only.
 */
export function parseLength(input: string, unit: LengthUnit): number | null {
  const parts = lengthParts(input, unit);
  if (parts === null) return null;
  const feet = parts.feet === null ? 0 : magnitudeValue(parts.feet);
  const value = parts.value === null ? 0 : magnitudeValue(parts.value);
  if (feet === null || value === null) return null;
  // Feet and inches sum in inches first: 5' 6-1/2" is exactly 66.5 in.
  const magnitude =
    parts.feet === null
      ? toMm(value, parts.unit)
      : toMm(feet * 12 + value, "in");
  if (!Number.isFinite(magnitude)) return null;
  return parts.negative ? -magnitude : magnitude;
}

/**
 * True when `input` is a length written with a fraction or a foot/inch mark
 * (`11 15/32`, `3/4`, `5' 6"`) rather than a plain decimal: the entries a
 * field echoes back (`= 11.46875 in`) so a typo shows before it is committed.
 */
export function isCarpenterLength(input: string, unit: LengthUnit): boolean {
  return /[/'"′″]/.test(input) && parseLength(input, unit) !== null;
}

/**
 * The entry text an expression {@link lengthExpression} wrote reads back as
 * (`11 in + 15 in/32` → `11 15/32"`, `11 mm + 15 mm/32` → `11 15/32 mm`), so a
 * stored spelled-out length reopens looking like what was typed; null when
 * `expression` is not one (a formula, or anything else).
 */
export function lengthEntryText(expression: string): string | null {
  let body = expression.trim();
  let sign = "";
  const wrapped = /^-\((.*)\)$/.exec(body);
  if (wrapped !== null) {
    sign = "-";
    body = wrapped[1] as string;
  } else if (body.startsWith("-")) {
    sign = "-";
    body = body.slice(1);
  }
  const terms = body.split(" + ");
  const parts: string[] = [];
  let unit: string | null = null;
  for (let i = 0; i < terms.length; i += 1) {
    const whole = /^(\d+(?:\.\d*)?|\.\d+) ([a-z]+)$/.exec(terms[i] as string);
    const frac = /^(\d+) ([a-z]+)\/(\d+)$/.exec(terms[i] as string);
    const next = /^(\d+) ([a-z]+)\/(\d+)$/.exec(terms[i + 1] ?? "");
    let magnitude: string;
    if (whole !== null && next !== null && next[2] === whole[2]) {
      magnitude = `${whole[1]} ${next[1]}/${next[3]}`;
      unit = whole[2] as string;
      i += 1;
    } else if (whole !== null) {
      magnitude = whole[1] as string;
      unit = whole[2] as string;
    } else if (frac !== null) {
      magnitude = `${frac[1]}/${frac[3]}`;
      unit = frac[2] as string;
    } else {
      return null;
    }
    parts.push(
      unit === "ft" && parts.length === 0 ? `${magnitude}'` : magnitude,
    );
  }
  if (parts.length === 0 || unit === null) return null;
  const last = parts.length - 1;
  if (unit !== "ft") {
    parts[last] = unit === "in" ? `${parts[last]}"` : `${parts[last]} ${unit}`;
  }
  const text = `${sign}${parts.join(" ")}`;
  // Only a faithful round trip is shown; anything else stays as stored.
  return lengthExpression(text, "mm") === expression.trim() ? text : null;
}

/**
 * A length entry as the expression language spells it, every unit explicit,
 * so the server (which knows no marks and no mixed numbers) reads exactly the
 * value {@link parseLength} does: `11-15/32` in an inch document is
 * `11 in + 15 in/32`, `5' 6"` is `5 ft + 6 in`. Null when `input` is not a
 * length.
 */
export function lengthExpression(
  input: string,
  unit: LengthUnit,
): string | null {
  const parts = lengthParts(input, unit);
  if (parts === null || parseLength(input, unit) === null) return null;
  const terms: string[] = [];
  if (parts.feet !== null) terms.push(magnitudeExpression(parts.feet, "ft"));
  if (parts.value !== null) {
    terms.push(magnitudeExpression(parts.value, parts.unit));
  }
  const body = terms.join(" + ");
  if (!parts.negative) return body;
  return body.includes(" + ") ? `-(${body})` : `-${body}`;
}

/**
 * True when `input` is not a length YET, but typing more could make it one —
 * the transient states every unit field passes through under the keyboard: the
 * empty cell, a lone sign (`-`), a bare decimal point (`.`, `-.`), and a number
 * trailing the first letters of a suffix (`12 i` on the way to `12 in`), and
 * a mixed number or feet-and-inches on its way (`11 1`, `11-15/`, `5' 6-`).
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
  // A mixed number or feet-and-inches on its way (`11 1`, `11-15/`, `5' 6-`):
  // some ending completes it, and it is not already a whole formula (`20-5`
  // still reads as the subtraction it is until a `/` makes it a mixed number).
  const unfinished =
    /[/'′-]$/.test(trimmed) ||
    /['′]/.test(trimmed) ||
    /\d[ \t]+\d+$/.test(trimmed);
  if (
    unfinished &&
    // Shape only: read as inches, where every carpenter form is a length.
    ["1", "/1", "1/1"].some((end) => parseLength(trimmed + end, "in") !== null)
  ) {
    return true;
  }
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

/** Options for {@link formatAngle}. */
export interface FormatAngleOptions {
  /** Max digits after the decimal point before trailing zeros are trimmed. */
  maxFractionDigits?: number;
  /** Append the degree sign (`"45°"`); false yields the bare number (`"45"`). */
  unitSuffix?: boolean;
}

/**
 * Degrees → a display string, trailing-zero trimmed, with the degree sign by
 * default (`formatAngle(45) === "45°"`).
 *
 * IT LIVES HERE BECAUSE THERE WERE ALREADY THREE OF IT AND NONE OF THEM HERE
 * (W3 direction §1.9): `measure/geometry.ts: formatAngleDeg` (`toFixed(1)` + the
 * sign, `"—"` for null), `features/revolve.ts: formatAngleInput`
 * (`String(angleDeg)`), `features/hole.ts: formatAngle` (integer, else
 * `toFixed(2)`, no suffix). An angular gauge written against any of them makes
 * a FOURTH, in the one place — a manipulator the user drags — where the number
 * under the pointer and the number in the rail disagreeing is most visible.
 * `formatLength` is the shape this follows exactly, down to the `unitSuffix`
 * option, so the tag cell that prints a length bare and the one that prints an
 * angle bare are one habit rather than two.
 *
 * THE THREE EXISTING CALL SITES ARE DELIBERATELY NOT MIGRATED HERE. Each has
 * its own rounding and its own null handling, so folding them in is a
 * behaviour change in three features at once; that is a DRY item of its own,
 * and doing it inside the wave's foundation commit would put three unrelated
 * regressions behind one pixel-match gate.
 *
 * A DEGREE IS NOT A `LengthUnit`, and that is why there is no unit argument:
 * angles have exactly one display unit in this product. The kernel, the wire
 * and the forms are all degrees, so there is nothing to convert and nothing to
 * remember — unlike a length, where the canonical mm and the document's own
 * unit genuinely differ.
 */
export function formatAngle(
  deg: number,
  opts: FormatAngleOptions = {},
): string {
  const { maxFractionDigits = 4, unitSuffix = true } = opts;
  const text = trimDecimal(deg, maxFractionDigits);
  return unitSuffix ? `${text}°` : text;
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
