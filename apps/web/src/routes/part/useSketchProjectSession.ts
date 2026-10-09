/**
 * The sketcher's PROJECT tool session (SKETCH-PROJECT-EDGES).
 *
 * Arming Project (P with nothing selected, or the strip's button) opens an
 * edge-pick session on the shared `edgePickStore` with `purpose: "project"`,
 * so the SAME overlay a fillet picks from offers the body's edges inside the
 * sketch. A click projects that edge at once (Onshape's Use, Fusion's
 * Project): the sketch store appends the linked entity, and this hook mirrors
 * the sketch's projected set back into the store's `picked`, so an edge you
 * have brought in reads as taken. Any other tool, or leaving the sketch,
 * closes the session.
 *
 * No body to project from: the tool refuses to arm and says why, rather than
 * waiting on an overlay that cannot come.
 */
import { useEffect, useRef } from "react";

import { useEdgePickStore } from "../../features/edgePickStore";
import { projectedSignatures } from "../../sketch/project";
import { type SketchMode, useSketchStore } from "../../sketch/store";

/** The refusal a Project press meets on a part with no body yet. */
export const PROJECT_NO_BODY_HINT =
  "Add a feature that creates a body before projecting its edges.";

export function useSketchProjectSession({
  mode,
  anchorFeatureId,
}: {
  mode: SketchMode;
  /** The body-affecting feature before the sketch, or null (no body). */
  anchorFeatureId: string | null;
}): void {
  const tool = useSketchStore((s) => s.tool);
  const entities = useSketchStore((s) => s.entities);
  const armed = mode === "draw" && tool === "project";
  // Read at click time, so a save that binds the sketch mid-session (and so
  // moves the anchor computation onto its own row) never reopens the session.
  const anchor = useRef(anchorFeatureId);
  anchor.current = anchorFeatureId;
  const hasBody = anchorFeatureId !== null;

  useEffect(() => {
    const picks = useEdgePickStore.getState();
    if (!armed) {
      if (picks.purpose === "project") picks.close();
      return;
    }
    if (!hasBody) {
      useSketchStore.getState().setTool("select");
      useSketchStore.setState({ hint: PROJECT_NO_BODY_HINT });
      return;
    }
    picks.open(projectedSignatures(useSketchStore.getState().entities), true, {
      purpose: "project",
      onProject: (edge) => {
        const at = anchor.current;
        if (at !== null) useSketchStore.getState().projectEdge(edge, at);
      },
    });
  }, [armed, hasBody]);

  useEffect(() => {
    if (!armed) return;
    useEdgePickStore.getState().setPicked(projectedSignatures(entities));
  }, [armed, entities]);

  // Leaving the workspace mid-Project tears the session down with it.
  useEffect(
    () => () => {
      const picks = useEdgePickStore.getState();
      if (picks.purpose === "project") picks.close();
    },
    [],
  );
}
