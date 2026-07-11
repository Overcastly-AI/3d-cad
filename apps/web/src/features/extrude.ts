/**
 * Extrude-feature view logic — pure functions the ExtrudeEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM. Param shapes come from the generated client (CLAUDE.md DRY rule); the
 * builders live in `../api/parts` alongside the sketch builders.
 */
import type { ExtrudeParams, FeatureResponse } from "../api/parts";

export type ExtrudeOperation = ExtrudeParams["operation"];
export type ExtrudeDirection = ExtrudeParams["direction"];

/** The editable extrude form state (distance kept as raw text — unit input). */
export interface ExtrudeForm {
  profileFeatureId: string;
  distanceInput: string;
  operation: ExtrudeOperation;
  direction: ExtrudeDirection;
}

/** A sketch the extrude may consume, as offered in the profile picker. */
export interface ProfileOption {
  id: string;
  name: string;
}

/** The default new-extrude form: 10 mm, add, normal — the common first cut. */
export function defaultExtrudeForm(profileFeatureId: string): ExtrudeForm {
  return {
    profileFeatureId,
    distanceInput: "10",
    operation: "add",
    direction: "normal",
  };
}

/** Seed the form from an existing extrude feature for editing. */
export function formFromParams(params: ExtrudeParams): ExtrudeForm {
  return {
    profileFeatureId: params.profile.feature_id,
    distanceInput: formatDistanceInput(params.distance_mm),
    operation: params.operation,
    direction: params.direction,
  };
}

/** Trim trailing zeros so 10 shows as "10", not "10.000". */
export function formatDistanceInput(distanceMm: number): string {
  return String(distanceMm);
}

/**
 * Parse the distance field to a positive millimetre value, or null when it is
 * empty, non-numeric, or non-positive (an extrude of zero depth is no solid).
 */
export function parseDistanceMm(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

/** Field-level validation message for the distance, or null when it is valid. */
export function distanceError(input: string): string | null {
  if (input.trim() === "") return null; // empty is pending, not yet wrong
  return parseDistanceMm(input) === null
    ? "Distance must be a positive number of millimetres."
    : null;
}

/** True when the form can be submitted (a profile and a valid distance). */
export function canSubmitExtrude(form: ExtrudeForm): boolean {
  return (
    form.profileFeatureId !== "" && parseDistanceMm(form.distanceInput) !== null
  );
}

/** The sketch features a new extrude may consume, in build order. */
export function profileOptions(
  features: readonly FeatureResponse[],
): ProfileOption[] {
  return features
    .filter((f) => f.feature.type === "sketch")
    .map((f) => ({ id: f.id, name: f.name }));
}

/** Default profile for a NEW extrude: the last sketch in the tree, or "". */
export function defaultProfileId(features: readonly FeatureResponse[]): string {
  const sketches = profileOptions(features);
  return sketches.length > 0 ? (sketches[sketches.length - 1]?.id ?? "") : "";
}
