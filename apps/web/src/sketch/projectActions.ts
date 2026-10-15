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
import type { InContextLink } from "../assembly/inContext";
import {
  breakLinks,
  inContextLinks,
  isProjected,
  projectedSignatures,
  type SketchProjectionStatus,
  withInContextLink,
} from "./project";
import { projectOverlayEdge } from "./projectEdge";
import type { SketchEntity } from "./tools";

/** A picked edge; with `inContext`, another component's (Edit in Place). */
export type ContextEdge = OverlayEdge & { inContext?: InContextLink };

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
 *
 * An edge carrying `inContext` belongs to another component (Edit in Place,
 * ASM-A3-IN-CONTEXT): it is already carried into this part's frame for the
 * first draw, and the entity stores the in-context link instead of a
 * body-edge reference. (It rides on the edge so the store's `projectEdge`
 * keeps its signature.)
 */
export function projectEdgeTransition(
  state: ProjectableState,
  edge: ContextEdge,
  anchorFeatureId: string,
):
  | { hint: string }
  | Pick<ProjectableState, "entities" | "nextIdIndex" | "revision">
  | null {
  const { plane, entities, nextIdIndex, revision } = state;
  if (plane === null) return null;
  const link = edge.inContext;
  const taken =
    link === undefined
      ? projectedSignatures(entities).some(
          (s) => edgeSignatureKey(s) === edgeSignatureKey(edge.signature),
        )
      : inContextLinks(entities).some(
          (l) =>
            l.occurrence_id === link.occurrence_id &&
            edgeSignatureKey(l.edge) === edgeSignatureKey(link.edge),
        );
  if (taken) {
    return { hint: "That edge is already projected into this sketch." };
  }
  const result = projectOverlayEdge(
    edge,
    resolveSpecBasis(plane),
    anchorFeatureId,
    `e${nextIdIndex}`,
  );
  if (!("entity" in result)) return { hint: result.hint };
  const entity: SketchEntity =
    link === undefined ? result.entity : withInContextLink(result.entity, link);
  return {
    entities: [...entities, entity],
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
