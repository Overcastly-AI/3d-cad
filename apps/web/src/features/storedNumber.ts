/**
 * A NO-OP SAVE ROUND-TRIPS EVERY STORED NUMBER EXACTLY.
 *
 * Every feature editor seeds its fields from the stored params and re-parses
 * them on Save. Seeded through a DISPLAY formatter (4 fraction digits in mm,
 * `toFixed(2)` for some angles) a stored 12.345678901234 mm came back as
 * 12.3457: opening a feature and pressing Enter changed its geometry by a
 * hair and its rebuild cache key outright (the twist's B1, then the same
 * class in every editor). The rule these helpers enforce:
 *
 *  - SEED a field from the stored value with the shortest text that parses
 *    back to it EXACTLY (the readable form when that already does, else the
 *    shortest round-trip, `String`, in the document unit);
 *  - on SAVE, a field whose text is still what it was seeded with means the
 *    STORED value, exactly. Only an edited field is parsed. That second half
 *    is what makes a foreign unit safe: about one stored mm value in ten has
 *    no inch text at all that multiplies back to the same double, so the
 *    seed alone cannot carry it, and the comparison does.
 *
 * One pair for lengths (unit-aware), one for unitless numbers (angles,
 * counts, ratios), so every editor states the rule in one call per field.
 */
import { fromMm, type LengthUnit, parseLength } from "@loft/design";

import { lengthInputValue } from "../units/length";

/**
 * The text a length field seeds with for a STORED `mm`, in `unit`: the
 * readable seed ({@link lengthInputValue}) when it parses back to exactly `mm`,
 * else the shortest round-trip text in `unit` when one exists, else the
 * readable seed (which {@link storedLengthMm} then resolves to `mm` for as
 * long as it is left untouched).
 */
export function storedLengthInput(mm: number, unit: LengthUnit): string {
  const readable = lengthInputValue(mm, unit);
  if (parseLength(readable, unit) === mm) return readable;
  const shortest = String(fromMm(mm, unit));
  if (parseLength(shortest, unit) === mm) return shortest;
  return readable;
}

/**
 * The mm a length field means on Save: the STORED value, exactly, while the
 * field still reads what {@link storedLengthInput} seeded it with; otherwise
 * `parse(input, unit)` (the field's own validation: positive, signed, ...).
 */
export function storedLengthMm(
  input: string,
  unit: LengthUnit,
  storedMm: number | null | undefined,
  parse: (input: string, unit: LengthUnit) => number | null,
): number | null {
  if (
    storedMm !== null &&
    storedMm !== undefined &&
    input.trim() === storedLengthInput(storedMm, unit)
  ) {
    return storedMm;
  }
  return parse(input, unit);
}

/** The text a unitless field (an angle, a count, a ratio) seeds with. */
export function storedNumberInput(value: number): string {
  return String(value);
}

/**
 * The number a unitless field means on Save: the STORED value while the field
 * still reads {@link storedNumberInput}'s seed, otherwise `parse(input)`. A
 * parse that rounds or clamps (a count, an angle in an open interval) can
 * then never move a value nobody touched.
 */
export function storedNumber(
  input: string,
  storedValue: number | null | undefined,
  parse: (input: string) => number | null,
): number | null {
  if (
    storedValue !== null &&
    storedValue !== undefined &&
    input.trim() === storedNumberInput(storedValue)
  ) {
    return storedValue;
  }
  return parse(input);
}
