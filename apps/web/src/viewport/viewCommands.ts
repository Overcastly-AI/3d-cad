/**
 * View navigation commands (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-2).
 * The DOM view rail, the keyboard accelerators, and the in-canvas reference
 * cube all issue commands through this one store; the camera rig inside the
 * Canvas consumes them (nonce-keyed so repeats re-fire). Pure state — the
 * camera math lives in the rig.
 */
import { useEffect } from "react";
import { create } from "zustand";

import { isTypingTarget } from "../lib/isTypingTarget";

/** A named view snap, a fit, or a raw cube direction. */
export type ViewCommand =
  | { kind: "home" | "fit" | "front" | "top" | "right" | "iso"; nonce: number }
  | {
      kind: "direction";
      /** World-axis direction TO the camera (from the reference cube). */
      dir: readonly [number, number, number];
      nonce: number;
    };

interface ViewCommandState {
  command: ViewCommand | null;
  request: (kind: Exclude<ViewCommand["kind"], "direction">) => void;
  requestDirection: (dir: readonly [number, number, number]) => void;
}

export const useViewCommandStore = create<ViewCommandState>((set, get) => ({
  command: null,
  request: (kind) =>
    set({ command: { kind, nonce: (get().command?.nonce ?? 0) + 1 } }),
  requestDirection: (dir) =>
    set({
      command: {
        kind: "direction",
        dir,
        nonce: (get().command?.nonce ?? 0) + 1,
      },
    }),
}));

/**
 * Camera directions of the named views, in SCENE coordinates (Y-up; the GLB
 * bakes the kernel's Z-up→Y-up rotation). "Top" therefore looks down scene
 * −Y — the kernel's plan view — with up = −Z so kernel +y reads up-screen.
 */
export const VIEW_DIRECTIONS = {
  /** The studio iso the shell has always opened with. */
  iso: [1, 0.68, 1.35],
  front: [0, 0, 1],
  top: [0, 1, 0],
  right: [1, 0, 0],
} as const;

/** Keyboard accelerators for the view rail (one numeric vocabulary). */
export const VIEW_SHORTCUTS: Record<
  string,
  Exclude<ViewCommand["kind"], "direction">
> = {
  "1": "front",
  "2": "top",
  "3": "right",
  "4": "iso",
  "0": "fit",
  Home: "home",
};

/**
 * Global view accelerators. Numeric on purpose: the letter vocabulary belongs
 * to the sketch/feature verbs, and digits are free in every workspace. Only
 * armed while the view rig owns the camera (`enabled` = not sketching).
 */
export function useViewHotkeys(enabled: boolean): void {
  const request = useViewCommandStore((state) => state.request);
  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey)
        return;
      if (isTypingTarget(event.target)) return;
      const kind = VIEW_SHORTCUTS[event.key];
      if (kind === undefined) return;
      event.preventDefault();
      request(kind);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, request]);
}
