/** Readout formatting for the title block — unit-aware, tabular-friendly. */
import {
  fromMm,
  fromMmArea,
  fromMmVolume,
  type LengthUnit,
} from "@loft/design";

import type { Vec3 } from "../api/tessellate";

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatCount(value: number): string {
  return integer.format(value);
}

/** 6000 → "6,000" — a raw grouped quantity (unit rendered separately by the
 * cell). Used where the value is already in its display unit (assembly readouts,
 * still mm-only). */
export function formatQuantity(value: number): string {
  return number.format(value);
}

/**
 * Part mass-props/bbox readouts honor the document unit (FINDINGS #17): the
 * stored value is always canonical mm/mm²/mm³, so these convert at the display
 * boundary through the one units core (`@loft/design`) — the SAME seam the input
 * cells use. The cell renders the matching `{unit}³ / {unit}² / {unit}` label
 * beside the value (via the caller's `PanelRow unit=…`). The `unit` defaults to
 * `"mm"` (the identity conversion), so an mm document — and every existing mm
 * caller — reads exactly as before.
 */

/** A canonical-mm³ volume → the document unit³, thousands-grouped. */
export function formatVolume(mm3: number, unit: LengthUnit): string {
  return number.format(fromMmVolume(mm3, unit));
}

/** A canonical-mm² area → the document unit², thousands-grouped. */
export function formatArea(mm2: number, unit: LengthUnit): string {
  return number.format(fromMmArea(mm2, unit));
}

/** "10, 20, 30" — compact vector readout, each component in the document unit. */
export function formatVec3(v: Vec3, unit: LengthUnit = "mm"): string {
  return [v.x, v.y, v.z].map((c) => number.format(fromMm(c, unit))).join(", ");
}

/** "10 × 20 × 30" — extents readout, each span in the document unit. */
export function formatExtents(
  min: Vec3,
  max: Vec3,
  unit: LengthUnit = "mm",
): string {
  return [max.x - min.x, max.y - min.y, max.z - min.z]
    .map((d) => number.format(fromMm(d, unit)))
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

/**
 * ISO date-time → "2026-07-11" for the parts register. ISO-8601 calendar
 * form (YYYY-MM-DD) reads as a drawing-register date and stays stable across
 * locales/timezones; a malformed value passes through as "—" rather than
 * throwing.
 */
export function formatDate(iso: string): string {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return "—";
  return new Date(time).toISOString().slice(0, 10);
}

/** 12994 → "12.7 KiB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${integer.format(bytes)} B`;
  return `${(bytes / 1024).toFixed(1)} KiB`;
}
