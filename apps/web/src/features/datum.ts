/**
 * Datum-plane view logic — the pure functions the datum authoring surfaces
 * (the standalone DatumEditor and the inline "+ Offset plane" affordance in
 * the plane picker) share, kept out of the components so they can be
 * unit-tested without a DOM. Param shapes come from the generated client
 * (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * A datum plane is authored in one of several kinds (docs/design/datum-planes.md
 * §3/§7): `offset` (an origin datum slid a signed distance along its normal),
 * `offset_from` (that slide off ANOTHER earlier datum — offset chaining),
 * `midplane` (a plane midway between two references — an origin datum, an
 * earlier datum, OR a picked planar model face), or `on_face` (a datum adopted
 * from a picked planar face, optionally offset along its normal). The face
 * references are authored by clicking the highlighted face in the viewport
 * (`FacePickOverlay`), reusing the SAME stage-1 signature the sketch-on-face
 * picker echoes — one enumeration, pick side and resolve side. Any FINITE
 * offset is a valid plane and a midplane over two resolved sides is total, so
 * the only invalid input is a missing reference/face or a non-numeric field.
 */
import type { LengthUnit } from "@loft/design";

import type {
  DatumMidplaneParams,
  DatumOffsetFromParams,
  DatumOffsetParams,
  DatumOnFaceParams,
  DatumParams,
  MidplaneSide,
  PlanarFaceSignature,
} from "../api/parts";
import { faceSubshapeRef, onFaceDatumParams } from "./face";
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

/**
 * A picked planar model face, as the datum editor carries it: the full-precision
 * stage-1 `signature` (the resolve identity — never quantized) plus the id of
 * the body-affecting feature whose body owns the face (the `SubshapeRef` anchor,
 * the strict-backward dependency the write records). The single value both a
 * midplane FACE-side and an `on_face` base reduce a click to.
 */
export interface DatumFace {
  signature: PlanarFaceSignature;
  anchorId: string;
}

/**
 * Which slot in the datum form a face pick lands in: the standalone `on_face`
 * base, or either midplane side. The DatumEditor arms a pick for one slot; the
 * clicked face is folded into that slot.
 */
export type DatumFaceSlot = "on_face" | "midplane-a" | "midplane-b";

/**
 * A face delivered from the viewport pick into the editor, tagged with its
 * target slot and a monotonic `nonce` so the editor folds each pick EXACTLY
 * once (the same nonce-guard the sketch edit/offset/mirror effects use).
 */
export interface DatumFacePick {
  nonce: number;
  slot: DatumFaceSlot;
  face: DatumFace;
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
 * A single midplane side, as authored: either a datum REFERENCE chosen from the
 * dropdown (an origin datum or an earlier datum, encoded as a `<select>` value —
 * `origin:XY` / `feature:<id>` / `""` for unchosen), or a picked planar model
 * FACE. Both reduce to a wire {@link MidplaneSide} by {@link buildMidplaneSide}.
 */
export type MidplaneSideForm =
  { source: "ref"; value: string } | { source: "face"; face: DatumFace };

/** The unchosen side — a reference dropdown at its placeholder. */
export const EMPTY_MIDPLANE_SIDE: MidplaneSideForm = {
  source: "ref",
  value: "",
};

/** A midplane side from a chosen reference dropdown value. */
export function refMidplaneSide(value: string): MidplaneSideForm {
  return { source: "ref", value };
}

/** A midplane side from a picked planar model face. */
export function faceMidplaneSide(face: DatumFace): MidplaneSideForm {
  return { source: "face", face };
}

/**
 * Encode a midplane side as a single `<select>` value: `origin:XY` for an origin
 * datum, `feature:<id>` for an earlier datum feature. The empty string is the
 * unchosen placeholder (blocks submit).
 */
export function encodeOriginSide(base: DatumPlaneName): string {
  return `origin:${base}`;
}

/** Encode an earlier datum feature reference as a side value. */
export function encodeFeatureSide(featureId: string): string {
  return `feature:${featureId}`;
}

/** Decode a REFERENCE side value to a wire `MidplaneSide`, or null when
 * unchosen/unknown (a picked face is carried separately — {@link faceMidplaneSide}). */
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

/** Re-encode a persisted REFERENCE `MidplaneSide` to its select value (form
 * seeding). A face side has no dropdown value — it seeds as a face form via
 * {@link midplaneSideForm}. */
export function encodeMidplaneSide(side: MidplaneSide): string {
  if (side.kind === "datum_plane") return encodeOriginSide(side.plane);
  if (side.kind === "feature") return encodeFeatureSide(side.feature_id);
  return "";
}

/** Seed a midplane side FORM from a persisted wire side (reference or face). */
export function midplaneSideForm(side: MidplaneSide): MidplaneSideForm {
  if (side.kind === "subshape") {
    return faceMidplaneSide({
      signature: side.selector.signature,
      anchorId: side.feature_id,
    });
  }
  return refMidplaneSide(encodeMidplaneSide(side));
}

/** Build the wire {@link MidplaneSide} from a side form, or null when unchosen. */
export function buildMidplaneSide(side: MidplaneSideForm): MidplaneSide | null {
  if (side.source === "face") {
    return faceSubshapeRef(side.face.anchorId, side.face.signature);
  }
  return decodeMidplaneSide(side.value);
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

/**
 * A short readout for a picked face — its area centroid, rounded, in the same
 * grammar as `faceLabel`. Names what the engineer picked (a face at a place),
 * never how it's stored.
 */
export function faceReadout(face: DatumFace): string {
  const round = (n: number) => Math.round(n * 10) / 10;
  const { x, y, z } = face.signature.centroid;
  return `Face at ${round(x)}, ${round(y)}, ${round(z)} mm`;
}

// --- The editor's discriminated form over the authorable datum kinds ----------

/** The datum kinds the editor authors. */
export type DatumKind = "offset" | "offset_from" | "midplane" | "on_face";

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
      /** First side: a reference dropdown value or a picked face. */
      a: MidplaneSideForm;
      /** Second side (same forms). */
      b: MidplaneSideForm;
      flip: boolean;
    }
  | {
      kind: "on_face";
      /** The picked planar model face this datum adopts (`null` = unchosen). */
      face: DatumFace | null;
      /** Signed offset along the face normal (mm), as typed. 0 sits on it. */
      offsetInput: string;
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
      return {
        kind: "midplane",
        a: EMPTY_MIDPLANE_SIDE,
        b: EMPTY_MIDPLANE_SIDE,
        flip,
      };
    case "on_face":
      return { kind: "on_face", face: null, offsetInput: "0" };
  }
}

/**
 * Fold a picked face into a form slot: the `on_face` base, or either midplane
 * side. A pick that doesn't match the current kind is ignored (the armed slot
 * always matches the visible kind, but this keeps the fold total).
 */
export function applyFacePick(
  form: DatumForm,
  slot: DatumFaceSlot,
  face: DatumFace,
): DatumForm {
  if (slot === "on_face" && form.kind === "on_face") {
    return { ...form, face };
  }
  if (slot === "midplane-a" && form.kind === "midplane") {
    return { ...form, a: faceMidplaneSide(face) };
  }
  if (slot === "midplane-b" && form.kind === "midplane") {
    return { ...form, b: faceMidplaneSide(face) };
  }
  return form;
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
        a: midplaneSideForm(params.a),
        b: midplaneSideForm(params.b),
        flip: params.flip,
      };
    case "on_face":
      return {
        kind: "on_face",
        face: {
          signature: params.face.selector.signature,
          anchorId: params.face.feature_id,
        },
        offsetInput: lengthInputValue(params.offset_mm, unit),
      };
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
      const a = buildMidplaneSide(form.a);
      const b = buildMidplaneSide(form.b);
      if (a === null || b === null) return null;
      const params: DatumMidplaneParams = {
        kind: "midplane",
        a,
        b,
        flip: form.flip,
      };
      return params;
    }
    case "on_face": {
      if (form.face === null) return null;
      const offset = parseOffsetMm(form.offsetInput, unit);
      if (offset === null) return null;
      const params: DatumOnFaceParams = onFaceDatumParams(
        form.face.anchorId,
        form.face.signature,
        offset,
      );
      return params;
    }
  }
}

/** True when the form can be submitted (all required fields present + valid). */
export function canSubmitDatum(form: DatumForm, unit: LengthUnit): boolean {
  return buildDatumParams(form, unit) !== null;
}
