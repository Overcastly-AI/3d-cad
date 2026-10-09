/**
 * The origin sheets YIELD TO THE BODY in the sketch plane-pick step
 * (SKETCH-PLANE-PICK, from SKETCH-ON-FACE-CLICK).
 *
 * Fusion's Create Sketch takes a click on an origin plane or on a planar face,
 * and a face you can see is the face you get. Here the three sheets are big,
 * translucent and drawn through the part, so a body sitting in the positive
 * octant is BEHIND the XZ sheet from the default view, and a click on its top
 * face struck the sheet first: the bracket's boss sketch landed on XY at z = 0.
 * Depth order is the wrong test, because the sheet does not hide the body; the
 * modeller sees the face through it and aims at the face.
 *
 * So wherever the pointer's ray also strikes the body's pick surface, a sheet
 * neither hovers nor takes the click, whichever is nearer, and the event goes
 * on to the surface (`FacePickOverlay`). Off the body's silhouette the sheets
 * behave exactly as before.
 */
import { useCursor } from "@react-three/drei";
import { useCallback, useState } from "react";

import type { DatumPlaneName } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";

/** `userData.pickId` of the plane-pick step's body surface. */
export const PLANE_PICK_BODY_ID = "plane-pick-body";

/** The slice of an r3f event this reads: every object the ray struck. */
export interface RayHits {
  intersections: readonly { object: { userData: Record<string, unknown> } }[];
}

/** Does this ray also strike the body's pick surface? Then the body has it. */
export function bodyTakesRay(event: RayHits): boolean {
  return event.intersections.some(
    (hit) => hit.object.userData["pickId"] === PLANE_PICK_BODY_ID,
  );
}

/**
 * A sheet's hover, driven by pointer MOVES rather than `pointerover`: the
 * pointer can slide from bare sheet onto the body without leaving the sheet,
 * and the hover must let go at that moment. Pass the event to claim the hover
 * (it stops there), or null to release it.
 */
export function useSheetHover(
  plane: DatumPlaneName,
): (event: { stopPropagation: () => void } | null) => void {
  const setHoveredPlane = useSketchStore((state) => state.setHoveredPlane);
  const [pointerOver, setPointerOver] = useState(false);
  useCursor(pointerOver);
  return useCallback(
    (event: { stopPropagation: () => void } | null) => {
      if (event !== null) {
        event.stopPropagation();
        setPointerOver(true);
        if (useSketchStore.getState().hoveredPlane !== plane) {
          setHoveredPlane(plane);
        }
        return;
      }
      setPointerOver(false);
      if (useSketchStore.getState().hoveredPlane === plane) {
        setHoveredPlane(null);
      }
    },
    [plane, setHoveredPlane],
  );
}
