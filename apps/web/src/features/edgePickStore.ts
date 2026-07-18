/**
 * Fillet/Chamfer edge-pick state (zustand) — the bridge between the editor
 * (a title-block strip) and the in-canvas `EdgePickOverlay`, which are sibling
 * subtrees that cannot pass props directly (the same problem the measure store
 * solves). The editor owns the size + mode; THIS store owns the shared
 * selection: the pickable overlay, the picked signatures, and hover feedback.
 * PartPage owns the network effect (fetch the overlay) and pushes it here.
 *
 * The picked set is keyed by full-precision `EdgeSignature` (see `./edge`), not
 * by transient overlay index, so it survives an overlay refetch and seeds
 * cleanly from a persisted `{kind:"edges"}` selector when editing.
 */
import { create } from "zustand";

import type { OverlayResult } from "../api/measure";
import type { EdgeSignature } from "../api/parts";
import { toggleEdge } from "./edge";

export interface EdgePickState {
  /** A fillet/chamfer editor is open (create or edit). */
  active: boolean;
  /** "Pick edges" mode is armed — the overlay is shown + hittable. */
  picking: boolean;
  /** Pickable geometry of the current body, or null until it loads. */
  overlay: OverlayResult | null;
  /** Overlay-fetch failure message (422 envelope), or null. */
  overlayError: string | null;
  /** The chosen edges, by full-precision signature (order = pick order). */
  picked: EdgeSignature[];
  /** Overlay edge index under the pointer / focus, or null. */
  hoverEdge: number | null;

  /** Open a fresh pick session, seeding it (edit → persisted refs; create → []). */
  open: (picked: readonly EdgeSignature[], picking: boolean) => void;
  /** Close the session and drop the overlay + picks. */
  close: () => void;
  /** Switch between "By rule" and "Pick edges" (keeps the picks). */
  setPicking: (picking: boolean) => void;
  setOverlay: (overlay: OverlayResult | null) => void;
  setOverlayError: (message: string | null) => void;
  /** Toggle one edge's signature in/out of the picked set. */
  toggle: (signature: EdgeSignature) => void;
  /** Drop every pick (the editor's Clear action). */
  clearPicks: () => void;
  setHoverEdge: (index: number | null) => void;
}

export const useEdgePickStore = create<EdgePickState>((set) => ({
  active: false,
  picking: false,
  overlay: null,
  overlayError: null,
  picked: [],
  hoverEdge: null,

  open: (picked, picking) =>
    set({
      active: true,
      picking,
      picked: [...picked],
      overlay: null,
      overlayError: null,
      hoverEdge: null,
    }),
  close: () =>
    set({
      active: false,
      picking: false,
      overlay: null,
      overlayError: null,
      picked: [],
      hoverEdge: null,
    }),
  setPicking: (picking) => set({ picking, hoverEdge: null }),
  setOverlay: (overlay) => set({ overlay, overlayError: null }),
  setOverlayError: (overlayError) => set({ overlayError }),
  toggle: (signature) =>
    set((state) => ({ picked: toggleEdge(state.picked, signature) })),
  clearPicks: () => set({ picked: [] }),
  setHoverEdge: (hoverEdge) => set({ hoverEdge }),
}));
