/** Readout formatting for the title block — unit-aware, tabular-friendly. */
import type { Vec3 } from "../api/tessellate";

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** 6000 → "6,000" (unit rendered separately by the cell). */
export function formatQuantity(value: number): string {
  return number.format(value);
}

export function formatCount(value: number): string {
  return integer.format(value);
}

/** "10, 20, 30" — compact vector readout (mm). */
export function formatVec3(v: Vec3): string {
  return `${number.format(v.x)}, ${number.format(v.y)}, ${number.format(v.z)}`;
}

/** "10 × 20 × 30" — extents readout (mm). */
export function formatExtents(min: Vec3, max: Vec3): string {
  return [max.x - min.x, max.y - min.y, max.z - min.z]
    .map((d) => number.format(d))
    .join(" × ");
}

/**
 * DRO cell readout: explicit sign + fixed decimals, like a machine readout.
 * `12.5 → "+12.50"`, `-3 → "-3.00"`, null (pointer off-plane) → "—".
 */
export function formatDroMm(value: number | null): string {
  if (value === null) return "—";
  const sign = value < 0 ? "-" : "+";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

/** 12994 → "12.7 KiB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${integer.format(bytes)} B`;
  return `${(bytes / 1024).toFixed(1)} KiB`;
}
