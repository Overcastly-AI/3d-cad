/**
 * The pattern dialog's viewport pick (zustand): the bridge between the dialog
 * (a DOM sibling of the Canvas) and the in-canvas edge overlays, the same
 * bridge the mate tools use (`mateStore`).
 *
 * While `picking` is set the scene offers edges on every drawn part: straight
 * and circular edges for a direction or axis, circular edges only for a seed
 * hole. A click stores the edge in `picked` and ends the pick; the dialog
 * reads it into its form.
 */
import { create } from "zustand";

import type { EdgeSignature } from "../api/parts";
import type { PickedEdge } from "./patterns";

/** What the pick is for: a direction / axis edge, or the seed's hole. */
export type PatternPickTarget = "axis" | "hole";

interface PatternPickState {
  picking: PatternPickTarget | null;
  picked: (PickedEdge & { target: PatternPickTarget }) | null;
  /** Arm a pick (or disarm with null); clears the last pick. */
  arm: (target: PatternPickTarget | null) => void;
  pickEdge: (instanceId: string, signature: EdgeSignature) => void;
  clear: () => void;
}

export const usePatternPickStore = create<PatternPickState>((set) => ({
  picking: null,
  picked: null,
  arm: (picking) => set({ picking, picked: null }),
  pickEdge: (instanceId, signature) =>
    set((state) => {
      if (state.picking === null) return state;
      if (state.picking === "hole" && signature.curve !== "circle") {
        return state;
      }
      return {
        picking: null,
        picked: { instanceId, signature, target: state.picking },
      };
    }),
  clear: () => set({ picking: null, picked: null }),
}));
