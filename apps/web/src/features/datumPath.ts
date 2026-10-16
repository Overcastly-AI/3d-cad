/**
 * The Plane Along Path datum's form logic (PIPE-ALONG-PATH) — Fusion 360's
 * Plane Along Path: a plane normal to a sketch curve at a fraction of its
 * length or a distance along it from its start. Kept beside `./datum` (which
 * folds it into the datum editor's discriminated form) so the field rules are
 * unit-testable on their own. The curve is one of the pipe picker's curves
 * (`./pipe`), keyed `<sketch id>:<entity id>`.
 */
import type { LengthUnit } from "@loft/design";

import type { DatumAlongPathParams } from "../api/parts";
import { parseSignedLengthMm } from "../units/length";
import { curveKey } from "./pipe";
import { storedLengthInput } from "./storedNumber";

export type PathMeasure = "ratio" | "distance";

/** The along-path slice of the datum form. */
export interface AlongPathForm {
  /** The curve's key (`""` = unchosen). */
  curve: string;
  measure: PathMeasure;
  /** A ratio 0..1, or a length in the document unit, as typed. */
  positionInput: string;
  flip: boolean;
}

export function defaultAlongPathForm(flip = false): AlongPathForm {
  return { curve: "", measure: "ratio", positionInput: "0.5", flip };
}

/** A ratio in [0, 1], or null. */
export function parsePathRatio(input: string): number | null {
  const value = Number(input.trim());
  if (input.trim() === "" || !Number.isFinite(value)) return null;
  return value >= 0 && value <= 1 ? value : null;
}

/** A non-negative distance in mm, or null. */
export function parsePathDistanceMm(
  input: string,
  unit: LengthUnit,
): number | null {
  const mm = parseSignedLengthMm(input, unit);
  return mm === null || mm < 0 ? null : mm;
}

/** Field message for the position, or null when valid (empty is pending). */
export function pathPositionError(
  form: AlongPathForm,
  unit: LengthUnit,
): string | null {
  if (form.positionInput.trim() === "") return null;
  if (form.measure === "ratio") {
    return parsePathRatio(form.positionInput) === null
      ? "A ratio from 0 (start) to 1 (end)."
      : null;
  }
  return parsePathDistanceMm(form.positionInput, unit) === null
    ? "A distance of 0 or more."
    : null;
}

/** The wire params, or null while a field is missing or invalid. */
export function buildAlongPathParams(
  form: AlongPathForm,
  unit: LengthUnit,
): DatumAlongPathParams | null {
  const cut = form.curve.indexOf(":");
  if (cut <= 0) return null;
  const path = {
    kind: "sketch_curve" as const,
    sketch: { kind: "feature" as const, feature_id: form.curve.slice(0, cut) },
    entity: form.curve.slice(cut + 1),
  };
  if (form.measure === "ratio") {
    const ratio = parsePathRatio(form.positionInput);
    if (ratio === null) return null;
    return {
      kind: "along_path",
      path,
      measure: "ratio",
      ratio,
      distance_mm: 0,
      flip: form.flip,
    };
  }
  const distance = parsePathDistanceMm(form.positionInput, unit);
  if (distance === null) return null;
  return {
    kind: "along_path",
    path,
    measure: "distance",
    ratio: 0,
    distance_mm: distance,
    flip: form.flip,
  };
}

/** Seed the form from a stored along-path datum (a model-edge path seeds
 * unchosen: the picker lists sketch curves). */
export function alongPathForm(
  params: DatumAlongPathParams,
  unit: LengthUnit,
): AlongPathForm {
  const path = params.path;
  return {
    curve:
      path.kind === "sketch_curve"
        ? curveKey(path.sketch.feature_id, path.entity)
        : "",
    measure: params.measure ?? "ratio",
    positionInput:
      params.measure === "distance"
        ? storedLengthInput(params.distance_mm ?? 0, unit)
        : String(params.ratio ?? 0),
    flip: params.flip ?? false,
  };
}
