/**
 * The sketch store's two Project transitions (SKETCH-PROJECT-EDGES), as pure
 * functions of the state they read: the store's `projectEdge` / `breakLink`
 * actions only `set` what these return, through the history recorder, so both
 * are ordinary undoable edits.
 */
import type { OverlayEdge } from "../api/measure";
import { edgeSignatureKey } from "../features/edge";
import type { SketchPick } from "./pick";
import { resolveSpecBasis, type SketchPlaneSpec } from "./plane";
import {
  breakLinks,
  isProjected,
  projectedSignatures,
  type SketchProjectionStatus,
} from "./project";
import { projectOverlayEdge } from "./projectEdge";
import type { SketchEntity } from "./tools";

interface ProjectableState {
  plane: SketchPlaneSpec | null;
  entities: SketchEntity[];
  nextIdIndex: number;
  revision: number;
  selection: SketchPick[];
  projections: SketchProjectionStatus[];
}

/**
 * Append the entity a picked edge projects to, or say why not: the edge is
 * already projected, or it cannot be (a spline, a tilted circle, an end-on
 * line). Null with no plane yet (nothing to project onto).
 */
export function projectEdgeTransition(
  state: ProjectableState,
  edge: OverlayEdge,
  anchorFeatureId: string,
):
  | { hint: string }
  | Pick<ProjectableState, "entities" | "nextIdIndex" | "revision">
  | null {
  const { plane, entities, nextIdIndex, revision } = state;
  if (plane === null) return null;
  const key = edgeSignatureKey(edge.signature);
  if (projectedSignatures(entities).some((s) => edgeSignatureKey(s) === key)) {
    return { hint: "That edge is already projected into this sketch." };
  }
  const result = projectOverlayEdge(
    edge,
    resolveSpecBasis(plane),
    anchorFeatureId,
    `e${nextIdIndex}`,
  );
  if (!("entity" in result)) return { hint: result.hint };
  return {
    entities: [...entities, result.entity],
    nextIdIndex: nextIdIndex + 1,
    revision: revision + 1,
  };
}

/** Break link on the selection: geometry kept, link gone, statuses pruned. */
export function breakLinkTransition(state: ProjectableState):
  | { hint: string }
  | {
      entities: SketchEntity[];
      revision: number;
      projections: SketchProjectionStatus[];
      selection: SketchPick[];
      editNote: string;
    } {
  const result = breakLinks(state.selection, state.entities);
  if (result === null) {
    return { hint: "Select projected geometry to break its link." };
  }
  const what = `${result.broken} ${result.broken === 1 ? "entity" : "entities"}`;
  return {
    entities: result.entities,
    revision: state.revision + 1,
    // The broken entities are no longer the solver's to report on.
    projections: state.projections.filter((status) =>
      isProjected(result.entities.find((e) => e.id === status.entity)),
    ),
    selection: [],
    editNote: `Link broken on ${what}. It no longer follows the body.`,
  };
}
