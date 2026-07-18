/**
 * Drawing-dimension client helpers — the sliver left after the DE-1c placement
 * cutover. Dimension PLACEMENT (extension/witness lines, arrowheads, angular arc
 * sweep, text position/angle, the sibling-collision flip) moved server-side into
 * the composed sheet (`geometry.drawings.compose`), which stamps the final value
 * string too (`ComposedDimText.value`). What remains is what the CLIENT still
 * needs, neither of it placement:
 *
 *  - `edgeSignatureKey`: a rounding-stable key for a model edge, used to build
 *    the sheet's per-edge / per-vertex React + selection keys, and
 *  - `formatDimensionLabel`: the value formatter the Dimensions side-PANEL uses
 *    to echo a measured dimension in its list (the SHEET reads the server-stamped
 *    `ComposedDimText.value`; the panel measures off the evaluate result).
 */
import type { DimensionParams, EdgeSignature } from "../api/drawings";

// --- signature key (a model edge → a stable, rounding-independent key) ----
/** Round a coordinate so the stored signature matches the re-projected one. */
const r3 = (n: number): string => n.toFixed(3);

/** A rounded, orientation-independent key for a model-edge signature. */
export function edgeSignatureKey(sig: EdgeSignature): string {
  const pt = (p: { x: number; y: number; z: number }): string =>
    `${r3(p.x)},${r3(p.y)},${r3(p.z)}`;
  return `${sig.curve}|${pt(sig.end_a)}|${pt(sig.end_b)}|${pt(sig.midpoint)}`;
}

// --- value formatting (the Dimensions side-panel) ------------------------
/** Format a measured value at a sensible precision (mm to 3dp, angles to 1dp). */
function numberText(value: number, unit: string | null | undefined): string {
  return value.toFixed(unit === "deg" ? 1 : 3);
}

/**
 * The stamped label with its drafting prefix/suffix: `Ø10.000` (diameter),
 * `R5.000` (radius), `90.0°` (angular), `40.000` (linear). Mirrors the server's
 * `format_dimension_label` so the panel and the composed sheet read the same.
 */
export function formatDimensionLabel(
  type: DimensionParams["type"],
  value: number,
  unit: string | null | undefined,
): string {
  const n = numberText(value, unit);
  switch (type) {
    case "diameter":
      return `Ø${n}`;
    case "radius":
      return `R${n}`;
    case "angular":
      return `${n}°`;
    default:
      return n;
  }
}
