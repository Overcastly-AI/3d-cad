/**
 * Component patterns in the assembly workspace (ASM-A3-PATTERN), pure.
 *
 * The pattern dialog's form, how it becomes a wire pattern (numbers from the
 * typed expressions, read the way the server reads them — the server is the
 * authority and re-evaluates on write), how a stored pattern reads back into
 * the form, and how a pattern is named in the tree. Three kinds, as in Fusion,
 * Onshape and SolidWorks: linear, circular, and on holes (pattern-driven /
 * Replicate), whose count follows the driving part.
 */
import type { EdgeSignature } from "../api/parts";
import type { InstanceResponse } from "../api/assemblies";
import type { ComponentPattern, PatternResponse } from "../api/patterns";
import {
  coerceToField,
  ExprError,
  evaluateExpression,
  type FieldKind,
  lengthEntryExpression,
} from "../features/expr";

export type PatternKind = ComponentPattern["type"];

/** An origin axis, or the edge picked in the viewport. */
export type AxisChoice = "x" | "y" | "z" | "edge";

/** An edge picked for the pattern: a direction / axis edge or a seed hole. */
export interface PickedEdge {
  instanceId: string;
  signature: EdgeSignature;
}

export interface PatternForm {
  kind: PatternKind;
  /** The instances to repeat, in order. */
  seeds: string[];
  axis: AxisChoice;
  edge: PickedEdge | null;
  flip: boolean;
  count: string;
  spacing: string;
  angle: string;
  /** The hole the seed sits at (hole kind). */
  hole: PickedEdge | null;
  /** Further instances of the driving part (hole kind). */
  alsoOn: string[];
}

export const PATTERN_KIND_LABEL: Record<PatternKind, string> = {
  linear: "Linear",
  circular: "Circular",
  hole: "On holes",
};

export function newPatternForm(seeds: string[]): PatternForm {
  return {
    kind: "linear",
    seeds,
    axis: "x",
    edge: null,
    flip: false,
    count: "3",
    spacing: "25 mm",
    angle: "360 deg",
    hole: null,
    alsoOn: [],
  };
}

/** A stored pattern, back in the form (its typed expressions where kept). */
export function formFromPattern(pattern: ComponentPattern): PatternForm {
  const form = newPatternForm([...pattern.seed_instance_ids]);
  form.kind = pattern.type;
  if (pattern.type === "hole") {
    form.hole = {
      instanceId: pattern.seed_hole.instance_id,
      signature: pattern.seed_hole.signature,
    };
    form.alsoOn = [...(pattern.also_on ?? [])];
    return form;
  }
  const axis = pattern.type === "linear" ? pattern.direction : pattern.axis;
  if (axis.kind === "origin_axis") form.axis = axis.axis;
  else {
    form.axis = "edge";
    form.edge = { instanceId: axis.instance_id, signature: axis.signature };
  }
  form.flip = pattern.flip ?? false;
  form.count = pattern.count_expr ?? String(pattern.count);
  if (pattern.type === "linear") {
    form.spacing = pattern.spacing_expr ?? `${pattern.spacing_mm} mm`;
  } else {
    form.angle = pattern.angle_expr ?? `${pattern.angle_deg ?? 360} deg`;
  }
  return form;
}

function value(text: string, kind: FieldKind, field: string): number {
  try {
    return coerceToField(evaluateExpression(text, new Map()), kind);
  } catch (error) {
    const reason = error instanceof ExprError ? error.message : String(error);
    throw new Error(`${field}: ${reason}`);
  }
}

/** The wire pattern for `form`, or the reason it is not one yet. */
export function buildPattern(
  form: PatternForm,
): { pattern: ComponentPattern } | { error: string } {
  if (form.seeds.length === 0) return { error: "Choose a component to repeat" };
  try {
    if (form.kind === "hole") {
      if (form.hole === null)
        return { error: "Pick the hole the seed sits in" };
      return {
        pattern: {
          type: "hole",
          seed_instance_ids: form.seeds,
          seed_hole: {
            instance_id: form.hole.instanceId,
            signature: form.hole.signature,
          },
          also_on: form.alsoOn,
        },
      };
    }
    const count = value(form.count, "int", "Count");
    if (count < 2) return { error: "Count: at least 2 (the seed and a copy)" };
    if (form.axis === "edge" && form.edge === null) {
      return { error: "Pick an edge for the direction" };
    }
    const axis =
      form.axis === "edge" && form.edge !== null
        ? {
            kind: "edge" as const,
            instance_id: form.edge.instanceId,
            signature: form.edge.signature,
          }
        : { kind: "origin_axis" as const, axis: form.axis as "x" | "y" | "z" };
    if (form.kind === "linear") {
      // `11-15/32` is a mixed number here too, sent spelled out (RESEARCH §29).
      let spacingExpr: string;
      try {
        spacingExpr = lengthEntryExpression(form.spacing, "mm");
      } catch (error) {
        const reason =
          error instanceof ExprError ? error.message : String(error);
        throw new Error(`Spacing: ${reason}`);
      }
      const spacing = value(spacingExpr, "length", "Spacing");
      if (spacing <= 0) return { error: "Spacing: more than 0" };
      return {
        pattern: {
          type: "linear",
          seed_instance_ids: form.seeds,
          direction: axis,
          flip: form.flip,
          count,
          spacing_mm: spacing,
          count_expr: form.count,
          spacing_expr: spacingExpr,
        },
      };
    }
    const angle = value(form.angle, "angle", "Angle");
    if (angle <= 0 || angle > 360) {
      return { error: "Angle: more than 0 and at most 360°" };
    }
    return {
      pattern: {
        type: "circular",
        seed_instance_ids: form.seeds,
        axis,
        flip: form.flip,
        count,
        angle_deg: angle,
        count_expr: form.count,
        angle_expr: form.angle,
      },
    };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
}

/** "Linear pattern 2": the kind and its ordinal among patterns of that kind. */
export function patternTitle(
  patterns: readonly PatternResponse[],
  pattern: PatternResponse,
): string {
  const same = patterns.filter((p) => p.pattern.type === pattern.pattern.type);
  const ordinal = same.findIndex((p) => p.id === pattern.id) + 1;
  const noun =
    pattern.pattern.type === "hole"
      ? "Hole pattern"
      : `${PATTERN_KIND_LABEL[pattern.pattern.type]} pattern`;
  return `${noun} ${ordinal}`;
}

/** What a pattern repeats: its seeds' names. */
export function patternSeedNames(
  instances: readonly Pick<InstanceResponse, "id" | "name">[],
  pattern: ComponentPattern,
): string {
  return pattern.seed_instance_ids
    .map((id) => instances.find((i) => i.id === id)?.name ?? "Missing")
    .join(", ");
}

/** The other direct instances of the part `instanceId` instances. */
export function samePartInstances(
  instances: readonly InstanceResponse[],
  instanceId: string,
): InstanceResponse[] {
  const own = instances.find((i) => i.id === instanceId);
  if (own === undefined) return [];
  return instances.filter(
    (i) =>
      i.id !== own.id &&
      i.ref_document_kind === "part" &&
      i.ref_document_id === own.ref_document_id,
  );
}
