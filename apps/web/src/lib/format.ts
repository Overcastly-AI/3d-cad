/** Readout formatting for the title block — unit-aware, tabular-friendly. */
import {
  fromMm,
  fromMmArea,
  fromMmVolume,
  type LengthUnit,
  MM_PER_UNIT,
} from "@loft/design";

import type { Vec3 } from "../api/tessellate";

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/**
 * Readout precision follows the UNIT, not the number (FINDINGS burn-down
 * 2026-07-25). Two fraction digits is right in millimetres and far too coarse
 * in a coarser unit: a 100 mm³ boss reads `0.01 in³` — and a 1 mm feature reads
 * `0` in metres. So a unit that is 10^n times bigger than a millimetre earns n
 * extra digits: mm → 2 (byte-identical to before), cm → 3, in → 4, m/ft → 5.
 * One rule for every readout, so volume, area, and lengths never disagree.
 */
function fractionDigits(unit: LengthUnit): number {
  return 2 + Math.ceil(Math.log10(MM_PER_UNIT[unit]));
}

const numberFormats = new Map<number, Intl.NumberFormat>();

/** A grouped, trailing-zero-trimmed value at the `unit`'s readout precision. */
function formatIn(value: number, unit: LengthUnit): string {
  const digits = fractionDigits(unit);
  let format = numberFormats.get(digits);
  if (format === undefined) {
    format = new Intl.NumberFormat("en-US", { maximumFractionDigits: digits });
    numberFormats.set(digits, format);
  }
  return format.format(value);
}

export function formatCount(value: number): string {
  return integer.format(value);
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
  return formatIn(fromMmVolume(mm3, unit), unit);
}

/**
 * A clash overlap volume → the document unit³ (FINDINGS burn-down 2026-07-25:
 * the clash schedule was the LAST mm-only readout on an inch page — an overlap
 * volume is a volume, and a user who set the document to inches should not have
 * to know one panel is special).
 *
 * A genuine but tiny overlap must never round to a misleading "0" on a pair the
 * panel FLAGS, so a value that would vanish at the unit's readout precision
 * (`< 10^-digits`) falls back to scientific notation instead. That floor follows
 * the unit: 0.005 mm³ reads `5.0e-3`, and the same solid in an inch document
 * (3.05e-7 in³) reads `3.1e-7` rather than `0`.
 */
export function formatOverlapVolume(mm3: number, unit: LengthUnit): string {
  const value = fromMmVolume(mm3, unit);
  const floor = 10 ** -fractionDigits(unit);
  if (value > 0 && value < floor) return value.toExponential(1);
  return formatVolume(mm3, unit);
}

/** A canonical-mm² area → the document unit², thousands-grouped. */
export function formatArea(mm2: number, unit: LengthUnit): string {
  return formatIn(fromMmArea(mm2, unit), unit);
}

/** "10, 20, 30" — compact vector readout, each component in the document unit. */
export function formatVec3(v: Vec3, unit: LengthUnit = "mm"): string {
  return [v.x, v.y, v.z].map((c) => formatIn(fromMm(c, unit), unit)).join(", ");
}

/** "10 × 20 × 30" — extents readout, each span in the document unit. */
export function formatExtents(
  min: Vec3,
  max: Vec3,
  unit: LengthUnit = "mm",
): string {
  return [max.x - min.x, max.y - min.y, max.z - min.z]
    .map((d) => formatIn(fromMm(d, unit), unit))
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
