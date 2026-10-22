/**
 * How the sketcher writes a dimension (split out of `constraints.ts`): the
 * drawing's notation, a length in the PART's unit and an angle in degrees.
 * `constraints.ts` re-exports all three, so every import is unchanged.
 */
// The units core alone: the package root pulls the Tailwind preset, which
// Node (the e2e specs import the shortcut registry) cannot load.
import { formatLength, type LengthUnit } from "@loft/design/units";

import type { DimensionKind } from "./constraints";

/** Dimension text: trailing zeros trimmed, mm implied (drawing convention). */
export function formatDimensionMm(value: number): string {
  const text = value.toFixed(2).replace(/\.?0+$/, "");
  return text === "" || text === "-" ? "0" : text;
}

/**
 * A sketch length (stored in mm) in the PART's unit, bare: the sketcher's
 * labels and cells read as every other length field does, so a 24 ft wall in
 * an inch part reads `288`, not `7315.2`. Millimetres keep the drawing's
 * two-decimal notation; other units take the length fields' precision.
 */
export function formatSketchLength(mm: number, unit: LengthUnit): string {
  if (unit === "mm") return formatDimensionMm(mm);
  return formatLength(mm, unit, { unitSuffix: false, maxFractionDigits: 4 });
}

/**
 * A dimension glyph's label, in the drawing's own notation: a length is bare
 * ("40"), a radius takes the R prefix ("R12.5"), a diameter the ⌀ ring
 * ("⌀25"), an angle the degree ring ("30°"). DRIVEN (reference) dims wear the
 * drafting convention — parentheses, "(40)" — so a measured, informational
 * value is never mistaken for a driving one.
 */
export function formatDimensionLabel(
  kind: DimensionKind,
  value: number,
  driven: boolean,
  unit: LengthUnit = "mm",
): string {
  const text =
    kind === "angle"
      ? formatDimensionMm(value)
      : formatSketchLength(value, unit);
  const core =
    kind === "radius"
      ? `R${text}`
      : kind === "diameter"
        ? `⌀${text}`
        : kind === "angle"
          ? `${text}°`
          : text;
  return driven ? `(${core})` : core;
}
