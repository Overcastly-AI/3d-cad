/**
 * Fillet + chamfer view logic — the pure functions the FilletEditor,
 * ChamferEditor, and PartPage share, kept out of the components so they can be
 * unit-tested without a DOM (the extrude/revolve/pattern twins). Param shapes
 * come from the generated client (CLAUDE.md DRY rule); the builders live in
 * `../api/parts`.
 *
 * Both features round/bevel a set of edges chosen one of two ways (the
 * `SelectionMode`): "By rule" — the geometric `EdgeSelector` predicate ("All
 * edges" / one entry per world axis), the fast path for rounding everything;
 * or "Pick edges" — click-specific edges named by stage-1 signature refs
 * (topological naming §10), so an engineer rounds ONE edge and leaves its
 * neighbour sharp. The picked signatures live in the edge-pick store (shared
 * with the viewport overlay); the size stays in the editor's form.
 */
import type { LengthUnit } from "@loft/design";

import type {
  ChamferParams,
  EdgeSelector,
  EdgeSignature,
  FilletParams,
} from "../api/parts";
import { lengthInputValue, parsePositiveLengthMm } from "../units/length";
import { pickedEdgesSelector } from "./edge";

/** How the fillet/chamfer chooses its edges: a predicate, or clicked edges. */
export type SelectionMode = "rule" | "pick";

/** The flat id for the ruled edge-selector cell (predicate + axis in one list). */
export type EdgeSelectorId = "all_edges" | "axis_x" | "axis_y" | "axis_z";

export interface EdgeSelectorOption {
  id: EdgeSelectorId;
  label: string;
}

/** The predicate choices, in a stable order (whole body first, then per axis). */
export const EDGE_SELECTORS: readonly EdgeSelectorOption[] = [
  { id: "all_edges", label: "All edges" },
  { id: "axis_x", label: "Edges parallel to X" },
  { id: "axis_y", label: "Edges parallel to Y" },
  { id: "axis_z", label: "Edges parallel to Z" },
];

/** The `EdgeSelector` param for a ruled-cell id. */
export function edgeSelector(id: EdgeSelectorId): EdgeSelector {
  switch (id) {
    case "all_edges":
      return { kind: "all_edges" };
    case "axis_x":
      return { kind: "axis_parallel", axis: "X" };
    case "axis_y":
      return { kind: "axis_parallel", axis: "Y" };
    case "axis_z":
      return { kind: "axis_parallel", axis: "Z" };
  }
}

/**
 * Seed the ruled-cell id from an existing selector (edit path).
 *
 * The backend added a `{ kind: "edges" }` picked-edge selector (topological
 * naming — click-specific fillet/chamfer). The in-viewport picker that AUTHORS
 * it is a follow-up UI slice; until it lands, a persisted picked selector has no
 * predicate-cell equivalent, so this predicate chooser falls back to `all_edges`
 * (forward-compat, not a data change — the stored selector is untouched).
 */
export function edgeSelectorId(selector: EdgeSelector): EdgeSelectorId {
  if (selector.kind === "axis_parallel") {
    return selector.axis === "X"
      ? "axis_x"
      : selector.axis === "Y"
        ? "axis_y"
        : "axis_z";
  }
  return "all_edges";
}

/**
 * Parse a positive size field (fillet radius / chamfer distance) → canonical mm
 * in the document `unit`, or null when empty, non-numeric, or non-positive (a
 * zero radius is no round). A bare number reads in `unit`; a suffix overrides it.
 */
export function parseSizeMm(input: string, unit: LengthUnit): number | null {
  return parsePositiveLengthMm(input, unit);
}

/**
 * The edge selector from an editor's mode + predicate + picked signatures, or
 * null when it cannot be built (pick mode with no body anchor or no picks). The
 * shared fillet/chamfer bridge between the form (mode + predicate) and the
 * edge-pick store (signatures).
 */
export function buildEdgeSelector(
  mode: SelectionMode,
  predicate: EdgeSelectorId,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
): EdgeSelector | null {
  return mode === "pick"
    ? pickedEdgesSelector(bodyFeatureId, picked)
    : edgeSelector(predicate);
}

// ---------------------------------------------------------------------------
// Fillet
// ---------------------------------------------------------------------------
/**
 * The editable fillet form (radius kept as raw text — a unit input). `mode`
 * chooses the predicate cell vs. the click-pick flow; `edges` is the predicate
 * used in "rule" mode. The picked signatures live in the edge-pick store, not
 * here (the viewport overlay writes them), so the form stays serialisable.
 */
export interface FilletForm {
  radiusInput: string;
  mode: SelectionMode;
  edges: EdgeSelectorId;
}

/** The default new-fillet form: a 2 mm round of every edge — the common break. */
export function defaultFilletForm(): FilletForm {
  return { radiusInput: "2", mode: "rule", edges: "all_edges" };
}

/** Seed the form from an existing fillet feature for editing (in `unit`). */
export function formFromFilletParams(
  params: FilletParams,
  unit: LengthUnit,
): FilletForm {
  return {
    radiusInput: lengthInputValue(params.radius_mm, unit),
    mode: params.edges.kind === "edges" ? "pick" : "rule",
    edges: edgeSelectorId(params.edges),
  };
}

/** The picked-edge signatures of a persisted fillet (empty for a predicate). */
export function pickedFromFilletParams(params: FilletParams): EdgeSignature[] {
  return params.edges.kind === "edges"
    ? params.edges.refs.map((ref) => ref.selector.signature)
    : [];
}

/** Field-level radius message, or null when valid (empty is pending). */
export function radiusError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parseSizeMm(input, unit) === null
    ? "Radius must be a positive length."
    : null;
}

/**
 * Build the `FilletParamsV1` from the form + the picked signatures, or null
 * when the radius is invalid OR pick mode has no resolvable edge selector (no
 * body anchor / no picks).
 */
export function buildFilletParams(
  form: FilletForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): FilletParams | null {
  const radius = parseSizeMm(form.radiusInput, unit);
  if (radius === null) return null;
  const edges = buildEdgeSelector(form.mode, form.edges, picked, bodyFeatureId);
  if (edges === null) return null;
  return { radius_mm: radius, edges };
}

/** True when the fillet form can be submitted (valid radius + edge selector). */
export function canSubmitFillet(
  form: FilletForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return buildFilletParams(form, picked, bodyFeatureId, unit) !== null;
}

// ---------------------------------------------------------------------------
// Chamfer
// ---------------------------------------------------------------------------
/** The editable chamfer form — the fillet twin (distance in place of radius). */
export interface ChamferForm {
  distanceInput: string;
  mode: SelectionMode;
  edges: EdgeSelectorId;
}

/** The default new-chamfer form: a 1 mm bevel of every edge. */
export function defaultChamferForm(): ChamferForm {
  return { distanceInput: "1", mode: "rule", edges: "all_edges" };
}

/** Seed the form from an existing chamfer feature for editing (in `unit`). */
export function formFromChamferParams(
  params: ChamferParams,
  unit: LengthUnit,
): ChamferForm {
  return {
    distanceInput: lengthInputValue(params.distance_mm, unit),
    mode: params.edges.kind === "edges" ? "pick" : "rule",
    edges: edgeSelectorId(params.edges),
  };
}

/** The picked-edge signatures of a persisted chamfer (empty for a predicate). */
export function pickedFromChamferParams(
  params: ChamferParams,
): EdgeSignature[] {
  return params.edges.kind === "edges"
    ? params.edges.refs.map((ref) => ref.selector.signature)
    : [];
}

/** Field-level distance message, or null when valid (empty is pending). */
export function distanceError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parseSizeMm(input, unit) === null
    ? "Distance must be a positive length."
    : null;
}

/**
 * Build the `ChamferParamsV1` from the form + the picked signatures, or null
 * when the distance is invalid OR pick mode has no resolvable edge selector.
 */
export function buildChamferParams(
  form: ChamferForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): ChamferParams | null {
  const distance = parseSizeMm(form.distanceInput, unit);
  if (distance === null) return null;
  const edges = buildEdgeSelector(form.mode, form.edges, picked, bodyFeatureId);
  if (edges === null) return null;
  return { distance_mm: distance, edges };
}

/** True when the chamfer form can be submitted (valid distance + selector). */
export function canSubmitChamfer(
  form: ChamferForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return buildChamferParams(form, picked, bodyFeatureId, unit) !== null;
}
