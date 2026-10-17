/**
 * The pattern and mirror dialogs' viewport pick (zustand): the bridge between
 * a dialog (a DOM sibling of the Canvas) and the in-canvas overlays, the same
 * bridge the mate tools use (`mateStore`).
 *
 * While `picking` is set the scene offers geometry on every drawn part:
 * straight and circular edges for a pattern's direction or axis, circular
 * edges only for a seed hole, planar faces for a mirror plane
 * (ASM-MIRROR-COMPONENT). A click stores the edge in `picked` (or the face in
 * `pickedFace`) and ends the pick; the dialog reads it into its form.
 */
import { create } from "zustand";

import type { EdgeSignature } from "../api/parts";
import type { PlanarFaceSignature } from "../api/partTypes";
import type { PickedEdge } from "./patterns";

/** What the pick is for: a direction / axis edge, the seed's hole, or a
 * mirror plane's face. */
export type PatternPickTarget = "axis" | "hole" | "plane";

/** A planar face picked for a mirror plane. */
export interface PickedFace {
  instanceId: string;
  signature: PlanarFaceSignature;
}

interface PatternPickState {
  picking: PatternPickTarget | null;
  picked: (PickedEdge & { target: PatternPickTarget }) | null;
  pickedFace: PickedFace | null;
  /** Arm a pick (or disarm with null); clears the last pick. */
  arm: (target: PatternPickTarget | null) => void;
  pickEdge: (instanceId: string, signature: EdgeSignature) => void;
  pickFace: (instanceId: string, signature: PlanarFaceSignature) => void;
  clear: () => void;
}

export const usePatternPickStore = create<PatternPickState>((set) => ({
  picking: null,
  picked: null,
  pickedFace: null,
  arm: (picking) => set({ picking, picked: null, pickedFace: null }),
  pickEdge: (instanceId, signature) =>
    set((state) => {
      if (state.picking === null || state.picking === "plane") return state;
      if (state.picking === "hole" && signature.curve !== "circle") {
        return state;
      }
      return {
        picking: null,
        picked: { instanceId, signature, target: state.picking },
      };
    }),
  pickFace: (instanceId, signature) =>
    set((state) =>
      state.picking === "plane"
        ? { picking: null, pickedFace: { instanceId, signature } }
        : state,
    ),
  clear: () => set({ picking: null, picked: null, pickedFace: null }),
}));
