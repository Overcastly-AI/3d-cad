/**
 * Datum-plane view logic — the pure functions the datum authoring surfaces
 * (the standalone DatumEditor and the inline "+ Offset plane" affordance in
 * the plane picker) share, kept out of the components so they can be
 * unit-tested without a DOM. Param shapes come from the generated client
 * (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * A datum plane is authored in one of several kinds (docs/design/datum-planes.md
 * §3/§7): `offset` (an origin datum slid a signed distance along its normal),
 * `offset_from` (that slide off ANOTHER earlier datum — offset chaining), or
 * `midplane` (a plane midway between two references — an origin datum or an
 * earlier datum). The `on_face` kind (a picked planar face) and midplane
 * FACE-sides are authored through the sketch-on-face picker, not this editor yet
 * (see docs/BACKLOG.md). Any FINITE offset is a valid plane and a midplane over
 * two resolved sides is total, so the only invalid input is a missing reference
 * or a non-numeric field.
 */
import type { LengthUnit } from "@loft/design";

import type {
  DatumMidplaneParams,
  DatumOffsetFromParams,
  DatumOffsetParams,
  DatumParams,
  MidplaneSide,
} from "../api/parts";
import { lengthInputValue, parseSignedLengthMm } from "../units/length";
import type { DatumPlaneName } from "../sketch/plane";

/** The three origin datums a plane can parallel, in a stable order. */
export const DATUM_BASES: readonly { id: DatumPlaneName; label: string }[] = [
  { id: "XY", label: "XY" },
  { id: "XZ", label: "XZ" },
  { id: "YZ", label: "YZ" },
];

/** A datum feature already in the tree, offered as a reference. */
export interface DatumRef {
  id: string;
  name: string;
}

// --- Offset-from-origin form (the inline picker panel + the editor's default) --

/**
 * The offset datum form — base origin datum, signed offset (raw text, a unit
 * input), and an optional normal flip. Shared by the inline "sketch at a height"
 * panel and the standalone editor's `offset` kind.
 */
export interface OffsetForm {
  base: DatumPlaneName;
  /** Signed offset along the base normal (mm), as typed. */
  offsetInput: string;
  /** Reverse the plane normal (negate z_dir; +u unchanged, +v flips). */
  flip: boolean;
}

/** The default offset form: 30 mm above XY (the everyday "sketch up" case). */
export function defaultOffsetForm(): OffsetForm {
  return { base: "XY", offsetInput: "30", flip: false };
}

/**
 * Parse the offset field → canonical mm in the document `unit`. Any FINITE
 * value is valid (0 coincides with the base plane; negatives select the other
 * side) — only an empty or non-numeric field is not-yet-valid. A bare number
 * reads in `unit`; a suffix overrides it.
 */
export function parseOffsetMm(input: string, unit: LengthUnit): number | null {
  return parseSignedLengthMm(input, unit);
}

/** Field-level offset message, or null when valid (empty is pending). */
export function offsetError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parseOffsetMm(input, unit) === null
    ? "Enter a distance (0, negative, or positive)."
    : null;
}

/** Build the offset params from the offset form, or null when the offset is
 * missing/invalid (the inline picker's submit gate). */
export function buildOffsetParams(
  form: OffsetForm,
  unit: LengthUnit,
): DatumOffsetParams | null {
  const offset = parseOffsetMm(form.offsetInput, unit);
  if (offset === null) return null;
  return {
    kind: "offset",
    base: form.base,
    offset_mm: offset,
    flip: form.flip,
  };
}

/** True when the offset form can be submitted (offset present + finite). */
export function canSubmitOffset(form: OffsetForm, unit: LengthUnit): boolean {
  return buildOffsetParams(form, unit) !== null;
}

// --- Midplane side encoding (a select's string value ⇄ a wire MidplaneSide) ---

/**
 * Encode a midplane side as a single `<select>` value: `origin:XY` for an origin
 * datum, `feature:<id>` for an earlier datum feature. The empty string is the
 * unchosen placeholder (blocks submit). Face sides are deferred (BACKLOG).
 */
export function encodeOriginSide(base: DatumPlaneName): string {
  return `origin:${base}`;
}

/** Encode an earlier datum feature reference as a side value. */
export function encodeFeatureSide(featureId: string): string {
  return `feature:${featureId}`;
}

/** Decode a side value to a wire `MidplaneSide`, or null when unchosen/unknown. */
export function decodeMidplaneSide(value: string): MidplaneSide | null {
  if (value.startsWith("origin:")) {
    const plane = value.slice("origin:".length);
    if (plane === "XY" || plane === "XZ" || plane === "YZ") {
      return { kind: "datum_plane", plane };
    }
    return null;
  }
  if (value.startsWith("feature:")) {
    const featureId = value.slice("feature:".length);
    return featureId === "" ? null : { kind: "feature", feature_id: featureId };
  }
  return null;
}

/** Re-encode a persisted `MidplaneSide` to its select value (form seeding). */
export function encodeMidplaneSide(side: MidplaneSide): string {
  if (side.kind === "datum_plane") return encodeOriginSide(side.plane);
  if (side.kind === "feature") return encodeFeatureSide(side.feature_id);
  // A face side has no dropdown value yet — seed it blank (BACKLOG).
  return "";
}

/** Select options for a midplane side: origin datums, then earlier datums. */
export function midplaneSideOptions(
  datumRefs: readonly DatumRef[],
): { value: string; label: string }[] {
  return [
    { value: "", label: "Choose a reference…" },
    ...DATUM_BASES.map((b) => ({
      value: encodeOriginSide(b.id),
      label: `${b.label} datum`,
    })),
    ...datumRefs.map((d) => ({
      value: encodeFeatureSide(d.id),
      label: d.name,
    })),
  ];
}

/** Select options for an offset-from base: earlier datums only (a FeatureRef). */
export function datumRefOptions(
  datumRefs: readonly DatumRef[],
): { value: string; label: string }[] {
  return [
    { value: "", label: "Choose a datum plane…" },
    ...datumRefs.map((d) => ({ value: d.id, label: d.name })),
  ];
}

// --- The editor's discriminated form over the authorable datum kinds ----------

/** The datum kinds the editor authors today (`on_face` is deferred). */
export type DatumKind = "offset" | "offset_from" | "midplane";

/** The editable datum form — a discriminated union over {@link DatumKind}. */
export type DatumForm =
  | ({ kind: "offset" } & OffsetForm)
  | {
      kind: "offset_from";
      /** The earlier datum feature to offset from (`""` = unchosen). */
      baseFeatureId: string;
      offsetInput: string;
      flip: boolean;
    }
  | {
      kind: "midplane";
      /** First side, as a {@link midplaneSideOptions} value (`""` = unchosen). */
      a: string;
      /** Second side (same encoding). */
      b: string;
      flip: boolean;
    };

/** The default new-datum form: 30 mm above XY (the everyday "sketch up" case). */
export function defaultDatumForm(): DatumForm {
  return { kind: "offset", ...defaultOffsetForm() };
}

/** A fresh form for a chosen kind, carrying the flip across the switch. */
export function defaultFormForKind(kind: DatumKind, flip: boolean): DatumForm {
  switch (kind) {
    case "offset":
      return { kind: "offset", base: "XY", offsetInput: "30", flip };
    case "offset_from":
      return {
        kind: "offset_from",
        baseFeatureId: "",
        offsetInput: "30",
        flip,
      };
    case "midplane":
      return { kind: "midplane", a: "", b: "", flip };
  }
}

/** Seed the form from an existing datum feature for editing (offset in `unit`). */
export function formFromDatumParams(
  params: DatumParams,
  unit: LengthUnit,
): DatumForm {
  switch (params.kind) {
    case "offset":
      return {
        kind: "offset",
        base: params.base,
        offsetInput: lengthInputValue(params.offset_mm, unit),
        flip: params.flip,
      };
    case "offset_from":
      return {
        kind: "offset_from",
        baseFeatureId: params.base.feature_id,
        offsetInput: lengthInputValue(params.offset_mm, unit),
        flip: params.flip,
      };
    case "midplane":
      return {
        kind: "midplane",
        a: encodeMidplaneSide(params.a),
        b: encodeMidplaneSide(params.b),
        flip: params.flip,
      };
    case "on_face":
      // Not editable in this surface yet — fall back to a fresh offset form.
      return defaultDatumForm();
  }
}

/**
 * Build the datum params from the form, or null when a required field is
 * missing/invalid (the submit gate). Server-side rebuild is total for finite
 * offsets and any two resolved midplane sides — this only guards the shape.
 */
export function buildDatumParams(
  form: DatumForm,
  unit: LengthUnit,
): DatumParams | null {
  switch (form.kind) {
    case "offset": {
      const offset = parseOffsetMm(form.offsetInput, unit);
      if (offset === null) return null;
      return {
        kind: "offset",
        base: form.base,
        offset_mm: offset,
        flip: form.flip,
      };
    }
    case "offset_from": {
      if (form.baseFeatureId === "") return null;
      const offset = parseOffsetMm(form.offsetInput, unit);
      if (offset === null) return null;
      const params: DatumOffsetFromParams = {
        kind: "offset_from",
        base: { kind: "feature", feature_id: form.baseFeatureId },
        offset_mm: offset,
        flip: form.flip,
      };
      return params;
    }
    case "midplane": {
      const a = decodeMidplaneSide(form.a);
      const b = decodeMidplaneSide(form.b);
      if (a === null || b === null) return null;
      const params: DatumMidplaneParams = {
        kind: "midplane",
        a,
        b,
        flip: form.flip,
      };
      return params;
    }
  }
}

/** True when the form can be submitted (all required fields present + valid). */
export function canSubmitDatum(form: DatumForm, unit: LengthUnit): boolean {
  return buildDatumParams(form, unit) !== null;
}
