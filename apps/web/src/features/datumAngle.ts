/**
 * The plane-at-an-angle datum's form logic (DATUM-PLANE-ANGLE) — Fusion 360's
 * Plane at Angle, SolidWorks' Plane "At angle". Kept beside `./datum` (which
 * folds it into the datum editor's discriminated form) so the line encoding and
 * the angle field are unit-testable on their own.
 *
 * The LINE is chosen from a dropdown (an origin axis, or a line of an earlier
 * sketch, encoded `axis:X` / `sketch:<featureId>:<entityId>`) or comes from a
 * straight model EDGE selected before the command (the stage-1 edge signature
 * the fillet pick stores). The REFERENCE takes a midplane side's forms and is
 * folded by `./datum`. The ANGLE is degrees in [-360, 360], as the server
 * validates it.
 */
import type {
  DatumAngleParams,
  EdgeSignature,
  EdgeSubshapeRef,
} from "../api/parts";

type DatumAngleLine = DatumAngleParams["line"];

/** A picked straight model edge, as the form carries it. */
export interface DatumEdge {
  signature: EdgeSignature;
  /** The body-affecting feature whose body owns the edge (the ref anchor). */
  anchorId: string;
}

/** The line slot of the form: a dropdown value, or a picked edge. */
export type AngleLineForm =
  { source: "ref"; value: string } | { source: "edge"; edge: DatumEdge };

/** A line of an earlier sketch, offered in the line dropdown. */
export interface SketchLineOption {
  sketchId: string;
  sketchName: string;
  entityId: string;
  construction: boolean;
}

/** The largest |angle| the server accepts (degrees). */
export const MAX_DATUM_ANGLE_DEG = 360;

/** The default angle a new plane at an angle opens with. */
export const DEFAULT_DATUM_ANGLE = "30";

export const EMPTY_ANGLE_LINE: AngleLineForm = { source: "ref", value: "" };

/** Encode a sketch line as a dropdown value. */
export function encodeSketchLine(sketchId: string, entityId: string): string {
  return `sketch:${sketchId}:${entityId}`;
}

/** Decode a dropdown value to the wire line, or null when unchosen. */
export function decodeAngleLine(value: string): DatumAngleLine | null {
  if (value === "axis:X" || value === "axis:Y" || value === "axis:Z") {
    return { kind: "origin_axis", axis: value.slice(5) as "X" | "Y" | "Z" };
  }
  if (value.startsWith("sketch:")) {
    const rest = value.slice("sketch:".length);
    const cut = rest.indexOf(":");
    if (cut <= 0 || cut === rest.length - 1) return null;
    return {
      kind: "sketch_line",
      sketch: { kind: "feature", feature_id: rest.slice(0, cut) },
      entity: rest.slice(cut + 1),
    };
  }
  return null;
}

/** The wire line from the form's line slot, or null when unchosen. */
export function buildAngleLine(line: AngleLineForm): DatumAngleLine | null {
  if (line.source === "edge") {
    const ref: EdgeSubshapeRef = {
      kind: "subshape",
      feature_id: line.edge.anchorId,
      subshape_type: "edge",
      selector: { selector_version: 1, signature: line.edge.signature },
    };
    return ref;
  }
  return decodeAngleLine(line.value);
}

/** Seed the line slot from a stored wire line. */
export function angleLineForm(line: DatumAngleLine): AngleLineForm {
  switch (line.kind) {
    case "origin_axis":
      return { source: "ref", value: `axis:${line.axis}` };
    case "sketch_line":
      return {
        source: "ref",
        value: encodeSketchLine(line.sketch.feature_id, line.entity),
      };
    case "subshape":
      return {
        source: "edge",
        edge: { signature: line.selector.signature, anchorId: line.feature_id },
      };
  }
}

/** Dropdown options for the line: origin axes, then earlier sketch lines. */
export function angleLineOptions(
  lines: readonly SketchLineOption[],
): { value: string; label: string }[] {
  return [
    { value: "", label: "Choose a line…" },
    { value: "axis:X", label: "X axis" },
    { value: "axis:Y", label: "Y axis" },
    { value: "axis:Z", label: "Z axis" },
    ...lines.map((l) => ({
      value: encodeSketchLine(l.sketchId, l.entityId),
      label: `${l.sketchName} · ${l.construction ? "construction " : ""}line ${l.entityId}`,
    })),
  ];
}

/** A short readout for a picked edge (its midpoint, rounded). */
export function edgeReadout(edge: DatumEdge): string {
  const round = (n: number) => Math.round(n * 10) / 10;
  const { x, y, z } = edge.signature.midpoint;
  return `Edge at ${round(x)}, ${round(y)}, ${round(z)} mm`;
}

/** Parse the angle field (degrees, signed), or null when empty/invalid. */
export function parseDatumAngleDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || Math.abs(value) > MAX_DATUM_ANGLE_DEG) {
    return null;
  }
  return value;
}

/** Field-level angle message, or null when valid (empty is pending). */
export function datumAngleError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseDatumAngleDeg(input) === null
    ? "Enter an angle from -360 to 360 degrees."
    : null;
}

/** A straight preselected edge seeds a plane at an angle; a curve cannot. */
export function isStraightEdge(signature: EdgeSignature): boolean {
  return signature.curve === "line";
}
