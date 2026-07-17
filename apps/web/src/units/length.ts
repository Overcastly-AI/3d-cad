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
import { formatLength, type LengthUnit, parseLength } from "@loft/design";

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
 */
export function lengthInputValue(mm: number, unit: LengthUnit): string {
  return formatLength(mm, unit, { unitSuffix: false });
}
