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
import { edgeSignatureKey, isEdgePicked, toggleEdge } from "./edge";

export interface EdgePickState {
  /** A fillet/chamfer editor is open (create or edit). */
  active: boolean;
  /** "Pick edges" mode is armed — the overlay is shown + hittable. */
  picking: boolean;
  /**
   * Single-edge mode (the edge flange picks ONE straight edge to fold off): a
   * click REPLACES the current pick instead of appending. Fillet/chamfer open
   * multi-select (false); the edge flange opens single-select (true). The
   * shared overlay stays unchanged — it always calls `toggle`, which honours
   * this flag.
   */
  singleSelect: boolean;
  /** Pickable geometry of the current body, or null until it loads. */
  overlay: OverlayResult | null;
  /** Overlay-fetch failure message (422 envelope), or null. */
  overlayError: string | null;
  /** The chosen edges, by full-precision signature (order = pick order). */
  picked: EdgeSignature[];
  /** Overlay edge index under the pointer / focus, or null. */
  hoverEdge: number | null;
  /**
   * A re-pick is waiting for the body's edges (`repickMoved` before the
   * overlay arrived): the next `setOverlay` drops the moved picks, once.
   */
  pruneOnOverlay: boolean;

  /** Open a fresh pick session, seeding it (edit → persisted refs; create → []). */
  open: (
    picked: readonly EdgeSignature[],
    picking: boolean,
    singleSelect?: boolean,
  ) => void;
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
  /**
   * RE-PICK THE MOVED EDGES (EDGE-RESOLVE-WARN-1): arm picking and drop every
   * pick that is no longer an edge of the body being picked on. Those are the
   * ones the kernel re-found by adjacency; the rest still name real edges and
   * stay. Waits for the overlay when it has not arrived yet.
   */
  repickMoved: () => void;
  setHoverEdge: (index: number | null) => void;
}

export const useEdgePickStore = create<EdgePickState>((set) => ({
  active: false,
  picking: false,
  singleSelect: false,
  overlay: null,
  overlayError: null,
  picked: [],
  hoverEdge: null,
  pruneOnOverlay: false,

  open: (picked, picking, singleSelect = false) =>
    set({
      active: true,
      picking,
      singleSelect,
      picked: [...picked],
      overlay: null,
      overlayError: null,
      hoverEdge: null,
      pruneOnOverlay: false,
    }),
  close: () =>
    set({
      active: false,
      picking: false,
      singleSelect: false,
      overlay: null,
      overlayError: null,
      picked: [],
      hoverEdge: null,
      pruneOnOverlay: false,
    }),
  setPicking: (picking) => set({ picking, hoverEdge: null }),
  setOverlay: (overlay) =>
    set((state) =>
      state.pruneOnOverlay && overlay !== null
        ? {
            overlay,
            overlayError: null,
            pruneOnOverlay: false,
            picked: stillOnBody(state.picked, overlay),
          }
        : { overlay, overlayError: null },
    ),
  setOverlayError: (overlayError) => set({ overlayError }),
  toggle: (signature) =>
    set((state) => ({
      // Single-edge mode: a click replaces the pick (or clears it on a repeat);
      // multi mode appends/removes as fillet/chamfer expect.
      picked: state.singleSelect
        ? isEdgePicked(state.picked, signature)
          ? []
          : [signature]
        : toggleEdge(state.picked, signature),
    })),
  clearPicks: () => set({ picked: [] }),
  repickMoved: () =>
    set((state) =>
      state.overlay === null
        ? { picking: true, pruneOnOverlay: true }
        : {
            picking: true,
            pruneOnOverlay: false,
            picked: stillOnBody(state.picked, state.overlay),
          },
    ),
  setHoverEdge: (hoverEdge) => set({ hoverEdge }),
}));

/** The picks that are still edges of `overlay`'s body, in pick order. */
function stillOnBody(
  picked: readonly EdgeSignature[],
  overlay: OverlayResult,
): EdgeSignature[] {
  const onBody = new Set(
    overlay.edges.map((edge) => edgeSignatureKey(edge.signature)),
  );
  return picked.filter((signature) => onBody.has(edgeSignatureKey(signature)));
}
