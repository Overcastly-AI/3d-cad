/**
 * WHERE AN OPENING'S DISTANCE RUNS FROM (OPENING-MEASURE-SWITCH).
 *
 * `loft.window` / `loft.door` 1.2.0 store a distance along the host wall and
 * the point it runs from (`measure_from`: the wall's start, its end, its
 * centre, or "nearer the origin", which documents stores as the end it is).
 * Changing the reference in the dialog must not move the opening, as in
 * Revit and Chief Architect, where a temporary dimension re-anchored to the
 * other end reads the other distance: the distance is CONVERTED, from the
 * host wall's length.
 *
 * The length and the ends come from what the editor already holds: the host
 * wall's stored members. Every `loft.wall` release emits each top plate
 * along the full wall, its section's first line running from the wall's
 * start to its end in plan (world mm; `loft_plugins.builtin.wall._emit`), and
 * an outline wall names each wall's members under its sketch line
 * (`e1/...`). So this works for a typed wall, a formula-driven one and every
 * wall of an outline alike, with no kernel and no request.
 *
 * Pure: unit-tested without a DOM.
 */
import { type LengthUnit, parseLength } from "@loft/design";

import type { FeatureResponse } from "../api/parts";
import type { CustomInputValue, ExpandedMember } from "../api/plugins";
import type { XY } from "./outline";
import { storedLengthInput, storedLengthMm } from "./storedNumber";

/** A stored or picked reference (`measure_from`'s options). */
export type MeasureFrom = "nearer" | "start" | "end" | "centre";
/** What `nearer` resolves to. */
export type WallEnd = "start" | "end";

export const MEASURE_FROM = "measure_from";
export const DISTANCE = "offset_mm";

/** The host wall as an opening's distance reads it (mm, plan). */
export interface HostWallLine {
  readonly start: XY;
  readonly end: XY;
  readonly lengthMm: number;
}

/** `loft_plugins.builtin.wall._EPS` (1e-9 in), in mm: the nearer-end tie. */
const TIE_MM = 1e-9 * 25.4;

export function isMeasureFrom(value: string): value is MeasureFrom {
  return (
    value === "nearer" ||
    value === "start" ||
    value === "end" ||
    value === "centre"
  );
}

/** Whether a manifest's form carries a reference and its distance. */
export function hasMeasureFrom(
  inputs: readonly { readonly name: string; readonly kind: string }[],
): boolean {
  return (
    inputs.some((i) => i.name === MEASURE_FROM && i.kind === "choice") &&
    inputs.some((i) => i.name === DISTANCE && i.kind === "length")
  );
}

function firstLine(member: ExpandedMember | undefined): HostWallLine | null {
  if (member?.role !== "section" || member.feature.type !== "sketch") {
    return null;
  }
  const line = member.feature.params.entities[0];
  if (line?.kind !== "line") return null;
  const lengthMm = Math.hypot(
    line.end.x - line.start.x,
    line.end.y - line.start.y,
  );
  if (!(lengthMm > 0)) return null;
  return { start: line.start, end: line.end, lengthMm };
}

/**
 * The host wall an opening's form names, read from the wall's stored top
 * plate: `hostWall` is the wall feature's id, `segment` the outline line it
 * sits in ("" for a single wall). Null while either is unpicked, or the wall
 * has no members yet.
 */
export function hostWallLine(
  features: readonly FeatureResponse[],
  hostWall: string,
  segment: string,
): HostWallLine | null {
  const row = features.find((f) => f.id === hostWall);
  if (row?.feature.type !== "custom") return null;
  const params = row.feature.params;
  if (params.plugin_id !== "loft.wall") return null;
  const outline = params.inputs.outline;
  const onOutline =
    outline !== undefined &&
    outline !== null &&
    typeof outline === "object" &&
    !Array.isArray(outline);
  if (onOutline !== (segment !== "")) return null;
  const prefix = segment === "" ? null : `${segment}/`;
  const members = params.expansion ?? [];
  // A member's section is emitted just before it (levels come first).
  const at = members.findIndex(
    (m) =>
      m.role === "top_plate" &&
      (prefix === null || (m.name ?? "").startsWith(prefix)),
  );
  return at > 0 ? firstLine(members[at - 1]) : null;
}

/** The wall end nearer the part origin; the start on a tie (`nearer_end`). */
export function nearerEnd(wall: HostWallLine): WallEnd {
  const start = Math.hypot(wall.start.x, wall.start.y);
  const end = Math.hypot(wall.end.x, wall.end.y);
  return end < start - TIE_MM ? "end" : "start";
}

function resolved(
  from: MeasureFrom,
  wall: HostWallLine,
): Exclude<MeasureFrom, "nearer"> {
  return from === "nearer" ? nearerEnd(wall) : from;
}

/** The opening's centre from the wall's start (mm), from its distance. */
export function centreFromStart(
  distanceMm: number,
  from: MeasureFrom,
  wall: HostWallLine,
): number {
  switch (resolved(from, wall)) {
    case "start":
      return distanceMm;
    case "end":
      return wall.lengthMm - distanceMm;
    case "centre":
      return wall.lengthMm / 2 + distanceMm;
  }
}

/** The distance from *from* to a centre *alongMm* from the wall's start;
 * from the centre it is signed, positive towards the wall's end. */
export function distanceFrom(
  alongMm: number,
  from: MeasureFrom,
  wall: HostWallLine,
): number {
  switch (resolved(from, wall)) {
    case "start":
      return alongMm;
    case "end":
      return wall.lengthMm - alongMm;
    case "centre":
      return alongMm - wall.lengthMm / 2;
  }
}

/** *distanceMm* from *from* re-read from *to*: the same place on the wall. */
export function convertDistance(
  distanceMm: number,
  from: MeasureFrom,
  to: MeasureFrom,
  wall: HostWallLine,
): number {
  return distanceFrom(centreFromStart(distanceMm, from, wall), to, wall);
}

/** The opening's centre from each end of its wall (mm), or null when the
 * distance or the wall is not known. */
export function endDistances(
  distanceMm: number | null,
  from: string,
  wall: HostWallLine | null,
): { start: number; end: number } | null {
  if (distanceMm === null || wall === null || !isMeasureFrom(from)) return null;
  const along = centreFromStart(distanceMm, from, wall);
  return { start: along, end: wall.lengthMm - along };
}

/** The mm the distance field means now (its text, else the stored value
 * while untouched), or null for an empty or unreadable field. */
export function distanceMm(
  text: string,
  unit: LengthUnit,
  stored: CustomInputValue | undefined,
): number | null {
  return storedLengthMm(
    text,
    unit,
    typeof stored === "number" ? stored : null,
    (t, u) => parseLength(t, u),
  );
}

/**
 * The form's values with the reference set to *to* and the distance
 * converted so the opening stays put (one state change, so one undo).
 * The distance is kept as typed when it cannot be read or the wall is not
 * known: there is nothing to convert from.
 */
export function withReference(
  values: Readonly<Record<string, string>>,
  to: string,
  wall: HostWallLine | null,
  unit: LengthUnit,
  stored: CustomInputValue | undefined,
): Record<string, string> {
  const next: Record<string, string> = { ...values, [MEASURE_FROM]: to };
  const from = values[MEASURE_FROM] ?? "";
  if (wall === null || !isMeasureFrom(from) || !isMeasureFrom(to)) return next;
  const mm = distanceMm(values[DISTANCE] ?? "", unit, stored);
  if (mm === null) return next;
  if (resolved(from, wall) === resolved(to, wall)) return next;
  next[DISTANCE] = storedLengthInput(convertDistance(mm, from, to, wall), unit);
  return next;
}
