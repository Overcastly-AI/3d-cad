/**
 * WHAT THE PART CAMERA FRAMES, sketches included (split out of `Viewport`).
 *
 * - `fitBounds`: the bodies' bounds joined by every DRAWN saved sketch, so
 *   Fit frames a sketch as Fusion's Fit frames every visible object, and a
 *   part that holds only a sketch (a house's outline before its walls) opens
 *   framed on it rather than on an empty origin. The bench, the pool and the
 *   origin geometry stay sized from the bodies alone: a flat sketch casts no
 *   shadow.
 * - `framesSketches`: sketches are the whole subject (no body), the refit
 *   key's part of it.
 * - `readSketchSubject`: what Fit frames WHILE DRAWING, the open sketch's
 *   entities, read from the store at the instant of the Fit and never
 *   subscribed (a sketch that changes on every pointer move must not
 *   re-render the scene).
 */
import { useCallback, useMemo, useRef } from "react";
import { Box3 } from "three";

import { resolveSpecBasis } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";
import { sketchIsDrawn, usePartViewStore } from "./partView";
import {
  type SketchFitLayer,
  sketchLayersBox,
  sketchWorldBox,
} from "./sketchFit";

/** A saved sketch the viewport may frame: its layer and its feature id. */
export type FramedSketch = SketchFitLayer & { readonly featureId: string };

export function useSketchFraming(
  bounds: Box3 | null,
  worldBounds: Box3 | null | undefined,
  sketchLayers: readonly FramedSketch[] | undefined,
) {
  const view = usePartViewStore((state) => state.view);
  const bodyPresent = usePartViewStore((state) => state.bodyPresent);
  const sketchBounds = useMemo(
    () =>
      sketchLayers === undefined
        ? null
        : sketchLayersBox(
            sketchLayers.filter((layer) =>
              sketchIsDrawn(view, layer.featureId, bodyPresent),
            ),
          ),
    [sketchLayers, view, bodyPresent],
  );
  const fitBounds = useMemo<Box3 | null>(() => {
    if (worldBounds !== undefined || sketchBounds === null) return bounds;
    if (bounds === null || bounds.isEmpty()) return sketchBounds;
    return bounds.clone().union(sketchBounds);
  }, [worldBounds, bounds, sketchBounds]);

  const sketchFitBox = useRef(new Box3());
  const readSketchSubject = useCallback((): Box3 | null => {
    const { mode, plane, entities } = useSketchStore.getState();
    if (mode !== "draw" || plane === null) return null;
    return sketchWorldBox(
      entities,
      resolveSpecBasis(plane),
      sketchFitBox.current,
    );
  }, []);

  return {
    fitBounds,
    framesSketches: sketchBounds !== null,
    readSketchSubject,
  };
}
