/**
 * Fillet + chamfer view logic — the pure functions the FilletEditor,
 * ChamferEditor, and PartPage share, kept out of the components so they can be
 * unit-tested without a DOM (the extrude/revolve/pattern twins). Param shapes
 * come from the generated client (CLAUDE.md DRY rule); the builders live in
 * `../api/parts`.
 *
 * Both features round/bevel edges chosen by the SAME geometric `EdgeSelector`
 * predicate — NOT a click-picked edge id (design §2.4; topological naming is
 * Phase 2). v1 offers the whole predicate set as one ruled SelectField:
 * "All edges" (the AllEdgesSelector) and one entry per world axis (the
 * AxisParallelEdgesSelector, which matches only straight edges parallel to that
 * axis). The copy stays honest — it names a predicate, never "pick this edge".
 */
import type { ChamferParams, EdgeSelector, FilletParams } from "../api/parts";

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

/** Seed the ruled-cell id from an existing selector (edit path). */
export function edgeSelectorId(selector: EdgeSelector): EdgeSelectorId {
  if (selector.kind === "all_edges") return "all_edges";
  return selector.axis === "X"
    ? "axis_x"
    : selector.axis === "Y"
      ? "axis_y"
      : "axis_z";
}

/** Trim trailing zeros so 5 shows as "5", not "5.000"; -0 renders as "0". */
function formatMm(mm: number): string {
  return String(Object.is(mm, -0) ? 0 : mm);
}

/**
 * Parse a positive-millimetre size field (fillet radius / chamfer distance), or
 * null when empty, non-numeric, or non-positive (a zero radius is no round).
 */
export function parseSizeMm(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

// ---------------------------------------------------------------------------
// Fillet
// ---------------------------------------------------------------------------
/** The editable fillet form (radius kept as raw text — a unit input). */
export interface FilletForm {
  radiusInput: string;
  edges: EdgeSelectorId;
}

/** The default new-fillet form: a 2 mm round of every edge — the common break. */
export function defaultFilletForm(): FilletForm {
  return { radiusInput: "2", edges: "all_edges" };
}

/** Seed the form from an existing fillet feature for editing. */
export function formFromFilletParams(params: FilletParams): FilletForm {
  return {
    radiusInput: formatMm(params.radius_mm),
    edges: edgeSelectorId(params.edges),
  };
}

/** Field-level radius message, or null when valid (empty is pending). */
export function radiusError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseSizeMm(input) === null
    ? "Radius must be a positive number of millimetres."
    : null;
}

/** Build the `FilletParamsV1` from the form, or null when the radius is invalid. */
export function buildFilletParams(form: FilletForm): FilletParams | null {
  const radius = parseSizeMm(form.radiusInput);
  if (radius === null) return null;
  return { radius_mm: radius, edges: edgeSelector(form.edges) };
}

/** True when the fillet form can be submitted (a valid radius). */
export function canSubmitFillet(form: FilletForm): boolean {
  return buildFilletParams(form) !== null;
}

// ---------------------------------------------------------------------------
// Chamfer
// ---------------------------------------------------------------------------
/** The editable chamfer form (distance kept as raw text — a unit input). */
export interface ChamferForm {
  distanceInput: string;
  edges: EdgeSelectorId;
}

/** The default new-chamfer form: a 1 mm bevel of every edge. */
export function defaultChamferForm(): ChamferForm {
  return { distanceInput: "1", edges: "all_edges" };
}

/** Seed the form from an existing chamfer feature for editing. */
export function formFromChamferParams(params: ChamferParams): ChamferForm {
  return {
    distanceInput: formatMm(params.distance_mm),
    edges: edgeSelectorId(params.edges),
  };
}

/** Field-level distance message, or null when valid (empty is pending). */
export function distanceError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseSizeMm(input) === null
    ? "Distance must be a positive number of millimetres."
    : null;
}

/** Build the `ChamferParamsV1` from the form, or null when distance is invalid. */
export function buildChamferParams(form: ChamferForm): ChamferParams | null {
  const distance = parseSizeMm(form.distanceInput);
  if (distance === null) return null;
  return { distance_mm: distance, edges: edgeSelector(form.edges) };
}

/** True when the chamfer form can be submitted (a valid distance). */
export function canSubmitChamfer(form: ChamferForm): boolean {
  return buildChamferParams(form) !== null;
}
