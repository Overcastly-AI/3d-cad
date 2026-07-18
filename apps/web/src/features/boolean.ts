/**
 * Combine-feature (boolean union) view logic — the pure functions the
 * CombineEditor and PartPage share (multi-body §MB-1). A boolean names two
 * BODIES by their base features: a TARGET (the surviving body) and a TOOL (the
 * consumed body). MB-1 wires `union` only; subtract/intersect share the same
 * shape and land in MB-2. Param shapes come from the generated client (CLAUDE.md
 * DRY rule); the create builder lives in `../api/parts`.
 */
import type { BooleanParams } from "../api/parts";
import type { BodyInfo } from "./bodies";

export { computeBodies } from "./bodies";
export type { BodyInfo } from "./bodies";

/** The editable combine form: which body survives, which is consumed. */
export interface CombineForm {
  targetFeatureId: string;
  toolFeatureId: string;
}

/** The default form: fuse the first two bodies in tree order. */
export function defaultCombineForm(bodies: readonly BodyInfo[]): CombineForm {
  return {
    targetFeatureId: bodies[0]?.baseFeatureId ?? "",
    toolFeatureId: bodies[1]?.baseFeatureId ?? "",
  };
}

/** Tool-body choices for a chosen target: every OTHER body (a body can't fuse
 * with itself — `boolean_same_body`). */
export function toolOptionsFor(
  bodies: readonly BodyInfo[],
  targetFeatureId: string,
): BodyInfo[] {
  return bodies.filter((b) => b.baseFeatureId !== targetFeatureId);
}

/** True when the form can be submitted: a target, a tool, and they differ. */
export function canSubmitCombine(form: CombineForm): boolean {
  return (
    form.targetFeatureId !== "" &&
    form.toolFeatureId !== "" &&
    form.targetFeatureId !== form.toolFeatureId
  );
}

/** Build the persisted union params from valid form state, or null. */
export function buildCombineParams(form: CombineForm): BooleanParams | null {
  if (!canSubmitCombine(form)) return null;
  return {
    operation: "union",
    target: { kind: "feature", feature_id: form.targetFeatureId },
    tool: { kind: "feature", feature_id: form.toolFeatureId },
  };
}
