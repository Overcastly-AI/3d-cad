/**
 * THE SECTION AT THE CURSOR, as a store — the bridge between the in-canvas
 * mate pick (which knows what the ray crossed) and the DOM strip that lets you
 * choose among them (which has to be a real, focusable list).
 *
 * MATE-1. `viewport/mateDepthStack.ts` derives the column; this holds it, holds
 * which entry the pick is aimed at, and holds the scene's commit callback so a
 * row in the strip can pick its face directly instead of merely arming a depth
 * the user then has to click for. One row, one pick — the tool proposes, the
 * user disposes.
 *
 * WHY THE COLUMN OUTLIVES THE POINTER. `entries` is deliberately NOT cleared
 * when the pointer leaves the geometry: the strip is the affordance, and an
 * affordance that vanishes the moment you move toward it cannot be used. It is
 * cleared when the answer would be stale instead — the tool disarms, a pick
 * lands, or the offered set changes. The `data-mate-pick-hover` stamp is a
 * different statement ("what is the pointer on RIGHT NOW") and does still clear
 * on pointer-out, which is what `pick-affordance.spec.ts` pins.
 */
import { create } from "zustand";

import type { MateCandidate } from "../viewport/mateDepthStack";
import { clampDepth, columnKey } from "../viewport/mateDepthStack";

/** One entry of the column, with the words the strip shows. */
export interface MateColumnEntry extends MateCandidate {
  /** The instance's name in the tree ("Bracket 1") — how the user knows it. */
  instanceName: string;
  /** The face's accessible name, the SAME one its `PickNode` carries. */
  faceLabel: string;
  /**
   * The face centroid, "30, 20, 6" — what tells two candidates apart at a
   * glance. A machinist reads coordinates; "face 6" is our word for it, not
   * theirs, so the ordinal stays in the accessible name and the row shows the
   * position.
   */
  centroidLabel: string;
}

export interface MateColumnState {
  /** Offered faces under the cursor, near → far. Empty = nothing to choose. */
  entries: MateColumnEntry[];
  /** Which entry the pick is aimed at — always a valid index when non-empty. */
  depth: number;
  /**
   * Is the user AIMING right now — pointer on the geometry, or on a row of the
   * strip? The entries outlive the pointer (see above); the aim does not, and
   * the two are different statements.
   *
   * It is what the viewport highlight and the `data-mate-pick-hover` stamp both
   * read, which is the point: hovering a row in the strip lights that face in
   * the scene exactly as pointing at it would, because both are aiming. Parking
   * the pointer on empty canvas is not, so the stamp clears there —
   * `pick-affordance.spec.ts` pins that, and it should.
   */
  addressing: boolean;
  /**
   * Commit an entry as a mate pick. Registered by the scene while a
   * face-collecting tool is armed, null otherwise (the strip renders nothing
   * without it — a row you cannot act on is the decorative chrome the design
   * mandate calls a defect).
   */
  commit: ((entry: MateColumnEntry) => void) | null;

  /**
   * Publish a freshly-derived column.
   *
   * The chosen depth SURVIVES a re-derivation of the same column and resets
   * only when the column itself changes ({@link columnKey}) — otherwise every
   * pointer micro-move over one face would snap the choice back to the nearest
   * entry, and the deeper one could never be clicked.
   */
  setEntries: (entries: MateColumnEntry[]) => void;
  setDepth: (depth: number) => void;
  setAddressing: (addressing: boolean) => void;
  setCommit: (commit: ((entry: MateColumnEntry) => void) | null) => void;
  clear: () => void;
}

export const useMateColumnStore = create<MateColumnState>((set) => ({
  entries: [],
  depth: 0,
  addressing: false,
  commit: null,

  setEntries: (entries) =>
    set((state) => {
      if (columnKey(state.entries) === columnKey(entries)) {
        // Same faces, new distances: keep the object identity so React does no
        // work, and keep the user's chosen depth.
        return state;
      }
      return { entries, depth: 0 };
    }),

  setDepth: (depth) =>
    set((state) => ({ depth: clampDepth(depth, state.entries) })),

  setAddressing: (addressing) =>
    set((state) => (state.addressing === addressing ? state : { addressing })),

  setCommit: (commit) => set({ commit }),

  clear: () => set({ entries: [], depth: 0, addressing: false }),
}));

/** The entry the pick is aimed at, or null when the user is not aiming. */
export function activeEntry(state: MateColumnState): MateColumnEntry | null {
  if (!state.addressing) return null;
  return state.entries[clampDepth(state.depth, state.entries)] ?? null;
}
