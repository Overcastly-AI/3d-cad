/**
 * Shell face-pick state (zustand) — the bridge between the ShellEditor (a
 * title-block strip in the HUD) and the in-canvas `ShellFaceOverlay`, which are
 * sibling subtrees that cannot pass props directly (the edge-pick store's
 * problem, for faces). The editor owns the thickness; THIS store owns the shared
 * selection: the pickable overlay, the picked-OPEN face signatures, and hover.
 * PartPage owns the network effect (fetch the overlay) and pushes it here.
 *
 * The picked set is keyed by full-precision `PlanarFaceSignature` (see
 * `./face`), not by transient overlay index, so it survives an overlay refetch
 * and seeds cleanly from a persisted `{kind:"faces"}` selector when editing.
 * Unlike the edge picker, an EMPTY set is a valid selection (a sealed hollow).
 */
import { create } from "zustand";

import type { OverlayResult } from "../api/measure";
import type { PlanarFaceSignature } from "../api/parts";
import { toggleFace } from "./face";

export interface FacePickState {
  /** A shell editor is open — the overlay is shown + hittable. */
  active: boolean;
  /** Pickable geometry of the current body, or null until it loads. */
  overlay: OverlayResult | null;
  /** Overlay-fetch failure message (422 envelope), or null. */
  overlayError: string | null;
  /** The faces to leave OPEN, by full-precision signature (order = pick order). */
  picked: PlanarFaceSignature[];
  /** Overlay face index under the pointer / focus, or null. */
  hoverFace: number | null;

  /** Open a session, seeding it (edit → persisted refs; create → []). */
  open: (picked: readonly PlanarFaceSignature[]) => void;
  /** Close the session and drop the overlay + picks. */
  close: () => void;
  setOverlay: (overlay: OverlayResult | null) => void;
  setOverlayError: (message: string | null) => void;
  /** Toggle one face's signature in/out of the open set. */
  toggle: (signature: PlanarFaceSignature) => void;
  /** Drop every pick (back to a sealed hollow). */
  clearPicks: () => void;
  setHoverFace: (index: number | null) => void;
}

export const useFacePickStore = create<FacePickState>((set) => ({
  active: false,
  overlay: null,
  overlayError: null,
  picked: [],
  hoverFace: null,

  open: (picked) =>
    set({
      active: true,
      picked: [...picked],
      overlay: null,
      overlayError: null,
      hoverFace: null,
    }),
  close: () =>
    set({
      active: false,
      overlay: null,
      overlayError: null,
      picked: [],
      hoverFace: null,
    }),
  setOverlay: (overlay) => set({ overlay, overlayError: null }),
  setOverlayError: (overlayError) => set({ overlayError }),
  toggle: (signature) =>
    set((state) => ({ picked: toggleFace(state.picked, signature) })),
  clearPicks: () => set({ picked: [] }),
  setHoverFace: (hoverFace) => set({ hoverFace }),
}));
