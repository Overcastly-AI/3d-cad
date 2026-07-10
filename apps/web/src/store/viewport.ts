/** Viewport/editor state (zustand) — committed model parameters. */
import { create } from "zustand";

import type { BoxParams } from "../api/tessellate";

/** The first-light reference box (mm). */
export const INITIAL_DIMENSIONS: BoxParams = { x: 10, y: 20, z: 30 };

interface ViewportState {
  /** Committed box dimensions (mm) — the tessellation request key. */
  dimensions: BoxParams;
  setDimensions: (dimensions: BoxParams) => void;
}

export const useViewportStore = create<ViewportState>()((set) => ({
  dimensions: INITIAL_DIMENSIONS,
  setDimensions: (dimensions) => set({ dimensions }),
}));
