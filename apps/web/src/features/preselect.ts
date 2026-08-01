/**
 * Pre-selection — what the cursor has already chosen, kept alive across the
 * command that consumes it (UI-W3).
 *
 * The founder's report: "placement face looks like a text box? Shouldn't it
 * know based on the face I select with the cursor?" It didn't. Every pick
 * session in this app was born and died inside one editor: you clicked a face,
 * the editor closed, the pick was gone, and the next command opened with an
 * empty reference and asked you to ARM a pick mode and click the same face
 * again. Fusion/Plasticity work the other way round — the selection is the
 * subject and the command applies to it — which is why they feel immediate.
 *
 * So a pick made ANYWHERE (the sketch-on-face picker, a datum slot, a hole's
 * placement face, the shell/draft face set, the fillet/chamfer edge set) is
 * remembered here, and every face/edge-consuming editor SEEDS from it on open.
 * Arming a pick is then what it should always have been: the way to CHANGE a
 * reference, not the only way to set one.
 *
 * Two rules keep it honest:
 *
 *  1. **A pre-selection belongs to the body it was taken from.** Every pick
 *     carries the body-affecting feature it was anchored to, and reads as EMPTY
 *     once that is no longer the tip of the body chain. Drill a hole and the
 *     face you picked it on may not exist any more; prefilling the next feature
 *     with a reference that cannot resolve would be worse than prefilling
 *     nothing. (Anchor, not tree version: adding a sketch or a datum bumps the
 *     version without touching the body, and a selection should survive that.)
 *  2. **It is a suggestion, never a commitment.** Seeding fills a form field
 *     the user can still re-pick, and nothing is written until they submit.
 *
 * Pure helpers live here (unit-tested without a DOM); the store is the bridge
 * between the in-canvas overlays and PartPage, exactly as the edge/face pick
 * stores are.
 */
import { create } from "zustand";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";

/**
 * A pre-selected planar face: the full-precision stage-1 signature plus the
 * body-affecting feature whose body owns it (the `SubshapeRef` anchor). The
 * same pair the hole/datum editors already carry — one shape, not a third.
 */
export interface PreselectedFace {
  signature: PlanarFaceSignature;
  anchorId: string;
}

/** The picks, as stored. Read them through the helpers below, never raw. */
export interface PreselectSelection {
  /** Faces picked in the viewport, in pick order (newest last). */
  faces: readonly PreselectedFace[];
  /** Edges picked in the viewport, in pick order (newest last). */
  edges: readonly EdgeSignature[];
  /** The body-affecting feature the edges were picked on, or null when none. */
  edgeAnchorId: string | null;
}

export interface PreselectState extends PreselectSelection {
  /** Remember a face pick set (replaces — a pick session owns the selection). */
  rememberFaces: (faces: readonly PreselectedFace[]) => void;
  /** Remember an edge pick set on one body anchor (replaces). */
  rememberEdges: (
    edges: readonly EdgeSignature[],
    anchorId: string | null,
  ) => void;
  /** Drop everything. */
  clear: () => void;
}

const EMPTY: PreselectSelection = {
  faces: [],
  edges: [],
  edgeAnchorId: null,
};

export const usePreselectStore = create<PreselectState>((set) => ({
  ...EMPTY,
  rememberFaces: (faces) => set({ faces: [...faces] }),
  rememberEdges: (edges, anchorId) =>
    set({ edges: [...edges], edgeAnchorId: anchorId }),
  clear: () => set({ ...EMPTY }),
}));

/**
 * The faces a command may seed from — only those picked on the body that is
 * still the tip of the chain (rule 1 above).
 */
export function preselectedFaces(
  state: Pick<PreselectSelection, "faces">,
  bodyFeatureId: string | null,
): readonly PreselectedFace[] {
  if (bodyFeatureId === null) return [];
  return state.faces.filter((face) => face.anchorId === bodyFeatureId);
}

/**
 * The ONE face a single-reference command (hole placement, on_face datum,
 * sketch-on-face) seeds from: the most recent live pick, or null.
 *
 * Most recent rather than first because a second click is a correction — the
 * user's last word on what they meant.
 */
export function preselectedFace(
  state: Pick<PreselectSelection, "faces">,
  bodyFeatureId: string | null,
): PreselectedFace | null {
  const faces = preselectedFaces(state, bodyFeatureId);
  return faces.length > 0 ? (faces[faces.length - 1] as PreselectedFace) : null;
}

/**
 * The edges a command may seed from. `limit` caps the seed for single-edge
 * verbs (the edge flange / hem fold ONE edge): those take the most recent pick
 * rather than an arbitrary member of a set their form cannot hold.
 */
export function preselectedEdges(
  state: Pick<PreselectSelection, "edges" | "edgeAnchorId">,
  bodyFeatureId: string | null,
  limit?: number,
): readonly EdgeSignature[] {
  if (bodyFeatureId === null || state.edgeAnchorId !== bodyFeatureId) return [];
  const edges = state.edges;
  if (limit === undefined || edges.length <= limit) return edges;
  return edges.slice(edges.length - limit);
}
