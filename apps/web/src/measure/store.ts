/**
 * Measurement-mode state (zustand) — the inspect tool's overlay, the two
 * picks, hover feedback, and the result. Shared by the in-canvas overlay layer
 * and the DOM readout so both draw from one source. PartPage owns the network
 * effects (fetch the overlay, call /measure on the second pick) and pushes
 * their results here; this store only holds state and the pick transitions.
 */
import { create } from "zustand";

import type { MeasureResult, OverlayResult, Vec3 } from "../api/measure";
import type { MeasurePick } from "./geometry";

/** True when two picks name the same target (a repeat click toggles it off). */
function samePick(a: MeasurePick, b: MeasurePick): boolean {
  if (a.kind !== b.kind) return false;
  return a.index === b.index;
}

export interface MeasureState {
  /** The Measure tool is armed. */
  active: boolean;
  /** Pickable geometry of the current body, or null until it loads. */
  overlay: OverlayResult | null;
  /** Overlay-fetch failure message (422 envelope), or null. */
  overlayError: string | null;
  /** The ordered picks: [] → pick A → [A] → pick B → [A, B]. */
  picks: MeasurePick[];
  /** Vertex index under the pointer / focus, or null. */
  hoverVertex: number | null;
  /** Edge index under the pointer / focus, or null. */
  hoverEdge: number | null;
  /** The measured result once both picks resolve, or null. */
  result: MeasureResult | null;
  /** Measurement failure message (422 envelope), or null. */
  measureError: string | null;

  /** Arm the tool (clears any prior session). */
  activate: () => void;
  /** Disarm the tool and drop the overlay + picks. */
  deactivate: () => void;
  setOverlay: (overlay: OverlayResult | null) => void;
  setOverlayError: (message: string | null) => void;
  setHoverVertex: (index: number | null) => void;
  setHoverEdge: (index: number | null) => void;
  /** Pick a vertex (echoes its exact coordinates for an exact measurement). */
  pickVertex: (index: number, position: Vec3) => void;
  /** Pick an edge by its overlay list index. */
  pickEdge: (index: number) => void;
  setResult: (result: MeasureResult) => void;
  setMeasureError: (message: string | null) => void;
  /** Clear the picks + result, keeping the tool armed (Esc / Clear). */
  reset: () => void;
}

const EMPTY = {
  overlay: null,
  overlayError: null,
  picks: [] as MeasurePick[],
  hoverVertex: null,
  hoverEdge: null,
  result: null,
  measureError: null,
} as const;

/** Append a pick, toggling it off if it is the sole current pick, and
 *  starting over once a full pair is already measured. */
function nextPicks(picks: MeasurePick[], pick: MeasurePick): MeasurePick[] {
  if (picks.length === 1 && samePick(picks[0] as MeasurePick, pick)) return [];
  if (picks.length >= 2) return [pick];
  return [...picks, pick];
}

export const useMeasureStore = create<MeasureState>((set) => ({
  active: false,
  ...EMPTY,

  activate: () => set({ active: true, ...EMPTY }),
  deactivate: () => set({ active: false, ...EMPTY }),
  setOverlay: (overlay) => set({ overlay, overlayError: null }),
  setOverlayError: (overlayError) => set({ overlayError }),
  setHoverVertex: (hoverVertex) => set({ hoverVertex }),
  setHoverEdge: (hoverEdge) => set({ hoverEdge }),
  pickVertex: (index, position) =>
    set((state) => ({
      picks: nextPicks(state.picks, { kind: "vertex", index, position }),
      result: null,
      measureError: null,
    })),
  pickEdge: (index) =>
    set((state) => ({
      picks: nextPicks(state.picks, { kind: "edge", index }),
      result: null,
      measureError: null,
    })),
  setResult: (result) => set({ result, measureError: null }),
  setMeasureError: (measureError) => set({ measureError }),
  reset: () => set({ picks: [], result: null, measureError: null }),
}));
