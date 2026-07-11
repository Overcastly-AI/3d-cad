/**
 * Sketch-mode state (zustand) — plane pick, tool sequence, and the local
 * entity buffer that `PartPage` persists on save. All geometry transitions
 * are the pure functions of `tools.ts`; this store only holds state.
 */
import { create } from "zustand";

import type { DatumPlaneName, Point2D } from "./plane";
import { snapPoint } from "./plane";
import {
  escapeAction,
  placePoint,
  type SketchEntity,
  type SketchTool,
} from "./tools";

/** Default grid snap (mm) — toggled with G, not adjustable yet. */
export const SNAP_STEP_MM = 1;

export type SketchMode = "off" | "plane" | "draw";

export interface SketchState {
  mode: SketchMode;
  /** Chosen datum plane (set on entering `draw`). */
  plane: DatumPlaneName | null;
  tool: SketchTool;
  /** Points of the in-progress placement sequence (plane mm, snapped). */
  pending: Point2D[];
  /** Locally buffered entities awaiting save. */
  entities: SketchEntity[];
  /** Next sketch-local id index (`e1`, `e2`, …). */
  nextIdIndex: number;
  snapEnabled: boolean;
  /** Pointer position in plane mm, already snapped; null when off-plane. */
  cursor: Point2D | null;
  /** Plane under the pointer / focused cell during plane pick. */
  hoveredPlane: DatumPlaneName | null;

  /** Enter sketch mode at the plane-pick step. */
  begin: () => void;
  choosePlane: (plane: DatumPlaneName) => void;
  setTool: (tool: SketchTool) => void;
  setHoveredPlane: (plane: DatumPlaneName | null) => void;
  setCursor: (point: Point2D | null) => void;
  toggleSnap: () => void;
  /** Apply the current snap setting to a raw plane-space point. */
  snap: (point: Point2D) => Point2D;
  /** Place the next point of the active tool's sequence. */
  placeAt: (point: Point2D) => void;
  /** Escape cascade: cancel placement → reset tool → exit (discard). */
  escape: () => void;
  /** Leave sketch mode, discarding the local buffer. */
  exit: () => void;
}

const INITIAL = {
  mode: "off" as SketchMode,
  plane: null,
  tool: "select" as SketchTool,
  pending: [],
  entities: [],
  nextIdIndex: 1,
  snapEnabled: true,
  cursor: null,
  hoveredPlane: null,
};

export const useSketchStore = create<SketchState>()((set, get) => ({
  ...INITIAL,

  begin: () => set({ ...INITIAL, mode: "plane" }),
  choosePlane: (plane) =>
    set({ mode: "draw", plane, hoveredPlane: null, cursor: null }),
  setTool: (tool) => set({ tool, pending: [] }),
  setHoveredPlane: (hoveredPlane) => set({ hoveredPlane }),
  setCursor: (cursor) => set({ cursor }),
  toggleSnap: () => set((state) => ({ snapEnabled: !state.snapEnabled })),
  snap: (point) => snapPoint(point, get().snapEnabled ? SNAP_STEP_MM : 0),

  placeAt: (point) => {
    const { tool, pending, nextIdIndex, entities } = get();
    const result = placePoint(tool, pending, point, nextIdIndex);
    set({
      pending: result.pending,
      nextIdIndex: result.nextIdIndex,
      entities:
        result.entities.length > 0
          ? [...entities, ...result.entities]
          : entities,
    });
  },

  escape: () => {
    const { tool, pending } = get();
    switch (escapeAction(tool, pending.length)) {
      case "cancel-placement":
        set({ pending: [] });
        return;
      case "reset-tool":
        set({ tool: "select", pending: [] });
        return;
      case "exit":
        set({ ...INITIAL });
        return;
    }
  },

  exit: () => set({ ...INITIAL }),
}));
