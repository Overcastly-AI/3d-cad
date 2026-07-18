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
import { formatLength, type LengthUnit, parseLength, toMm } from "@loft/design";

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
