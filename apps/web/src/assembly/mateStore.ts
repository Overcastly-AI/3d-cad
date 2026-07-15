/**
 * Mate-authoring session (zustand) — the bridge between the command band /
 * HUD (a DOM sibling of the Canvas) and the in-canvas per-instance pick
 * overlays, the same pattern the fillet edge-pick + shell face-pick stores use.
 *
 * A mate is authored by choosing a tool, then picking the mating geometry on
 * TWO DIFFERENT instances: a planar face on each → Coincident, a circular edge
 * on each → Concentric, or the two instances themselves → Lock. The store owns
 * the tool + the (≤ 2) collected picks; the parent watches for a complete pair,
 * POSTs the mate, re-evaluates (the snap), and calls `resetPicks` to chain.
 *
 * Signatures pass through UNCHANGED (full precision) — the SAME
 * `PlanarFaceSignature` / `EdgeSignature` the sketch-on-face / edge-pick UI
 * already emits (CLAUDE.md DRY rule), resolved server-side against each
 * instance's part body in its local frame.
 */
import { create } from "zustand";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";

export type MateTool = "coincident" | "concentric" | "lock";

/** One collected pick: a face (coincident), an axis (concentric), or an instance (lock). */
export type MatePick =
  | {
      kind: "face";
      instanceId: string;
      /** Transient overlay face index — for the selected-highlight cue only. */
      faceIndex: number;
      signature: PlanarFaceSignature;
    }
  | {
      kind: "axis";
      instanceId: string;
      /** Transient overlay edge index — for the selected-highlight cue only. */
      edgeIndex: number;
      signature: EdgeSignature;
    }
  | { kind: "instance"; instanceId: string };

export interface MateAuthoringState {
  tool: MateTool | null;
  /** Collected picks, in order (≤ 2). A complete pair is on distinct instances. */
  picks: MatePick[];
  /** A rejected pick's reason (e.g. same instance twice), or null. */
  error: string | null;

  /** Arm a tool (or disarm with null); always starts a fresh pick pair. */
  setTool: (tool: MateTool | null) => void;
  /** Toggle-arm: choosing the active tool again disarms it. */
  toggleTool: (tool: MateTool) => void;
  pickFace: (
    instanceId: string,
    faceIndex: number,
    signature: PlanarFaceSignature,
  ) => void;
  pickAxis: (
    instanceId: string,
    edgeIndex: number,
    signature: EdgeSignature,
  ) => void;
  pickInstance: (instanceId: string) => void;
  /** Keep the tool armed, drop the collected picks (chain another mate). */
  resetPicks: () => void;
  /** Disarm entirely (tool + picks) — e.g. leaving the workspace. */
  clear: () => void;
}

/** A pick is only valid as the SECOND of a pair on a DIFFERENT instance. */
function acceptSecond(
  picks: MatePick[],
  instanceId: string,
): { ok: boolean; error: string | null } {
  const first = picks[0];
  if (first === undefined) return { ok: true, error: null };
  if (picks.length >= 2) return { ok: false, error: null };
  if (first.instanceId === instanceId) {
    return {
      ok: false,
      error: "Pick the mating geometry on the OTHER part, not the same one.",
    };
  }
  return { ok: true, error: null };
}

export const useMateAuthoringStore = create<MateAuthoringState>((set) => ({
  tool: null,
  picks: [],
  error: null,

  setTool: (tool) => set({ tool, picks: [], error: null }),
  toggleTool: (tool) =>
    set((state) =>
      state.tool === tool
        ? { tool: null, picks: [], error: null }
        : { tool, picks: [], error: null },
    ),

  pickFace: (instanceId, faceIndex, signature) =>
    set((state) => {
      if (state.tool !== "coincident") return state;
      const { ok, error } = acceptSecond(state.picks, instanceId);
      if (!ok) return { ...state, error };
      return {
        picks: [
          ...state.picks,
          { kind: "face", instanceId, faceIndex, signature },
        ],
        error: null,
      };
    }),

  pickAxis: (instanceId, edgeIndex, signature) =>
    set((state) => {
      if (state.tool !== "concentric") return state;
      const { ok, error } = acceptSecond(state.picks, instanceId);
      if (!ok) return { ...state, error };
      return {
        picks: [
          ...state.picks,
          { kind: "axis", instanceId, edgeIndex, signature },
        ],
        error: null,
      };
    }),

  pickInstance: (instanceId) =>
    set((state) => {
      if (state.tool !== "lock") return state;
      const { ok, error } = acceptSecond(state.picks, instanceId);
      if (!ok) return { ...state, error };
      return {
        picks: [...state.picks, { kind: "instance", instanceId }],
        error: null,
      };
    }),

  resetPicks: () => set({ picks: [], error: null }),
  clear: () => set({ tool: null, picks: [], error: null }),
}));
