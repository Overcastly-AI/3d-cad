/**
 * Extrude-feature view logic — pure functions the ExtrudeEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM. Param shapes come from the generated client (CLAUDE.md DRY rule); the
 * builders live in `../api/parts` alongside the sketch builders.
 */
import type { LengthUnit } from "@loft/design";

import type { ExtrudeParams, FeatureResponse } from "../api/parts";
import { lengthInputValue, parsePositiveLengthMm } from "../units/length";

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

/** Seed the form from an existing extrude feature for editing (in `unit`). */
export function formFromParams(
  params: ExtrudeParams,
  unit: LengthUnit,
): ExtrudeForm {
  return {
    profileFeatureId: params.profile.feature_id,
    distanceInput: lengthInputValue(params.distance_mm, unit),
    operation: params.operation,
    direction: params.direction,
  };
}

/**
 * Parse the distance field to a positive CANONICAL millimetre value in the
 * document `unit`, or null when empty, non-numeric, or non-positive (an extrude
 * of zero depth is no solid). A bare number reads in `unit`; a suffix (`2in`)
 * overrides it — the storage value is always mm.
 */
export function parseDistanceMm(
  input: string,
  unit: LengthUnit,
): number | null {
  return parsePositiveLengthMm(input, unit);
}

/** Field-level validation message for the distance, or null when it is valid. */
export function distanceError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null; // empty is pending, not yet wrong
  return parseDistanceMm(input, unit) === null
    ? "Distance must be a positive length."
    : null;
}

/** True when the form can be submitted (a profile and a valid distance). */
export function canSubmitExtrude(form: ExtrudeForm, unit: LengthUnit): boolean {
  return (
    form.profileFeatureId !== "" &&
    parseDistanceMm(form.distanceInput, unit) !== null
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
