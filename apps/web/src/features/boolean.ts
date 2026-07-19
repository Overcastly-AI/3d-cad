/**
 * Combine-feature (boolean) view logic — the pure functions the CombineEditor
 * and PartPage share (multi-body §MB). A boolean names two BODIES by their base
 * features: a TARGET (the surviving body) and a TOOL (the consumed body), plus
 * an OPERATION. MB-2 wires all three ops: `union` (fuse), `subtract` (target −
 * tool) and `intersect` (common volume). Union/intersect are order-independent;
 * subtract is NOT — the target keeps, the tool is removed FROM it. Param shapes
 * come from the generated client (CLAUDE.md DRY rule); the create builder lives
 * in `../api/parts`.
 */
import type { BooleanOperation, BooleanParams } from "../api/parts";
import type { BodyInfo } from "./bodies";

export { computeBodies } from "./bodies";
export type { BodyInfo } from "./bodies";
export type { BooleanOperation } from "../api/parts";

/** The editable combine form: the operation + which body survives / is consumed. */
export interface CombineForm {
  operation: BooleanOperation;
  targetFeatureId: string;
  toolFeatureId: string;
  /** Opt in to a multi-lump result (MB-4c): when true, a boolean whose lumps
   * don't form one connected solid is kept as ONE multi-lump body instead of
   * failing `boolean_disjoint`. Off by default (a disjoint result is usually a
   * positioning bug — the "operands must touch" safety). */
  allowDisjoint: boolean;
}

/** True when the operation's operand order matters (subtract: Target − Tool). */
export function isOrderedOperation(operation: BooleanOperation): boolean {
  return operation === "subtract";
}

/** Per-operation editor copy: the arithmetic glyph, the two role labels, and a
 * one-line note. Only `subtract` is order-dependent, so its labels/note make the
 * Target − Tool asymmetry explicit; union/intersect read symmetrically. */
export interface OperationCopy {
  /** The arithmetic glyph shown in the segment: `+` / `−` / `∩`. */
  glyph: string;
  /** Label for the surviving (target) body select. */
  targetLabel: string;
  /** Label for the consumed (tool) body select. */
  toolLabel: string;
  /** One-line explanation of what the operation does and its limit. */
  note: string;
  /** Copy for the "keep as one body" opt-in (MB-4c) — names, per operation,
   * WHEN the result would split into disconnected lumps, so the multi-lump
   * choice reads specifically rather than generically. */
  disjointNote: string;
}

/** The shared label for the multi-lump opt-in (all three operations). */
export const KEEP_AS_ONE_BODY_LABEL = "Keep as one body";

export function operationCopy(operation: BooleanOperation): OperationCopy {
  switch (operation) {
    case "subtract":
      return {
        glyph: "−",
        targetLabel: "Target (kept)",
        toolLabel: "Tool (subtracted)",
        note: "Subtract removes the Tool from the Target — order matters: Target − Tool. If the Tool covers the whole Target, nothing remains.",
        disjointNote:
          "If the cut severs the Target into disconnected pieces, keep them as one multi-lump body.",
      };
    case "intersect":
      return {
        glyph: "∩",
        targetLabel: "Body A (kept)",
        toolLabel: "Body B",
        note: "Intersect keeps only the volume the two bodies share. They must overlap — no overlap leaves nothing.",
        disjointNote:
          "If the bodies meet in two separate regions, keep both as one multi-lump body.",
      };
    case "union":
    default:
      return {
        glyph: "+",
        targetLabel: "Target (keeps)",
        toolLabel: "Tool (consumed)",
        note: "Union fuses the two bodies into one — normally they must touch.",
        disjointNote:
          "If the bodies don't touch, keep them as one multi-lump body instead of failing.",
      };
  }
}

/** The default form: fuse (union) the first two bodies in tree order, with the
 * multi-lump opt-in OFF (the "operands must touch" safety default). */
export function defaultCombineForm(bodies: readonly BodyInfo[]): CombineForm {
  return {
    operation: "union",
    targetFeatureId: bodies[0]?.baseFeatureId ?? "",
    toolFeatureId: bodies[1]?.baseFeatureId ?? "",
    allowDisjoint: false,
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

/** Build the persisted boolean params from valid form state, or null.
 *
 * `allow_disjoint` is threaded from the form's opt-in (MB-4c): off keeps today's
 * "operands must touch" contract — a boolean whose result would be more than one
 * disconnected lump fails as `boolean_disjoint`; on accepts that result as ONE
 * multi-lump body (a `Compound`). Meaningful for all three operations — a
 * non-touching union, a severing subtract, and a two-region intersect each
 * produce >1 lump (docs/design/multi-body.md §MB-4). */
export function buildCombineParams(form: CombineForm): BooleanParams | null {
  if (!canSubmitCombine(form)) return null;
  return {
    operation: form.operation,
    target: { kind: "feature", feature_id: form.targetFeatureId },
    tool: { kind: "feature", feature_id: form.toolFeatureId },
    allow_disjoint: form.allowDisjoint,
  };
}
