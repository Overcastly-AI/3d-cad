/**
 * WHAT THE PART CAMERA FRAMES, sketches included (split out of `Viewport`).
 *
 * - `fitBounds`: the bodies' bounds joined by every DRAWN saved sketch, so
 *   Fit frames a sketch as Fusion's Fit frames every visible object, and a
 *   part that holds only a sketch (a house's outline before its walls) opens
 *   framed on it rather than on an empty origin. The bench, the pool and the
 *   origin geometry stay sized from the bodies alone: a flat sketch casts no
 *   shadow.
 * - `framesSketches`: the part OPENED on sketches only, the refit key's part
 *   of it. Latched when the first evaluation lands: Fusion frames what a
 *   document opens on, but finishing a sketch never zooms the camera, so a
 *   first sketch saved in the session leaves the view where it is (its first
 *   extrude re-frames on the body, FB-20); Fit still frames it.
 * - `readSketchSubject`: what Fit frames WHILE DRAWING, the open sketch's
 *   entities, read from the store at the instant of the Fit and never
 *   subscribed (a sketch that changes on every pointer move must not
 *   re-render the scene).
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { Box3 } from "three";

import { useGlobalKeys } from "../lib/modalGate";
import { resolveSpecBasis } from "../sketch/plane";
import { zeroStartsAValue } from "../sketch/pointEntry";
import { useSketchStore } from "../sketch/store";
import { sketchIsDrawn, usePartViewStore } from "./partView";
import { VIEW_SHORTCUTS } from "./viewCommands";
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

  // `sketchLayers` is undefined until the part's first evaluation lands.
  const [openedOnSketches, setOpenedOnSketches] = useState<boolean | null>(
    null,
  );
  if (openedOnSketches === null && sketchLayers !== undefined) {
    setOpenedOnSketches(sketchBounds !== null);
  }

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
    framesSketches: openedOnSketches === true && sketchBounds !== null,
    readSketchSubject,
  };
}

/**
 * The Fit key, read off the view rail's own table rather than restated, so the
 * sketcher's Fit is the model's Fit key by construction (F-11) and the key
 * card, which also reads `VIEW_SHORTCUTS`, cannot disagree with it.
 */
export const FIT_KEY: string | null =
  Object.entries(VIEW_SHORTCUTS).find(([, kind]) => kind === "fit")?.[0] ??
  null;

/**
 * `0` = Fit while drawing (F-11) — the part rail's key, armed while the rail
 * itself is not (`useViewHotkeys` stands down with `viewNav`, and the named
 * snaps it carries must: they would turn the view off the plane).
 *
 * YIELDS TO A VALUE BEING TYPED. `0` is a digit — "100", "0.5", "0 Tab 25" —
 * so whenever one may start (`zeroStartsAValue`: a draw tool armed, a size,
 * coordinate or dimension cell open or mounting) the key is the value's, read
 * LIVE from the store: FLOW-A1's draft is set inside the pointer handler, a
 * render before anything React could tell this listener.
 */
export function useSketchFitHotkey(onFit: (() => void) | null): void {
  useGlobalKeys(
    "sketch fit",
    onFit !== null && FIT_KEY !== null
      ? (event: KeyboardEvent) => {
          if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey)
            return;
          if (event.key !== FIT_KEY) return;
          // A digit being TYPED (a size, or a coordinate, G2) is not a Fit.
          if (zeroStartsAValue(useSketchStore.getState())) return;
          event.preventDefault();
          onFit();
        }
      : null,
  );
}
