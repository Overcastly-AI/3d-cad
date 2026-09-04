/**
 * View navigation commands (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-2).
 * The DOM view rail, the keyboard accelerators, and the in-canvas reference
 * cube all issue commands through this one store; the camera rig inside the
 * Canvas consumes them (nonce-keyed so repeats re-fire). Pure state — the
 * camera math lives in the rig.
 */
import { useEffect } from "react";
import { Vector3 } from "three";
import { create } from "zustand";

import { isTypingTarget } from "../lib/isTypingTarget";

/**
 * A camera pose in SCENE world coordinates — everything needed to put the view
 * back exactly where it was, and nothing that belongs to a projection.
 *
 * `zoom` is carried only because a PARALLEL camera frames by zoom rather than
 * by distance, so restoring an orthographic pose without it would return the
 * right attitude at the wrong apparent size. It is absent for a perspective
 * pose and ignored by a perspective camera.
 */
export interface ViewPose {
  position: readonly [number, number, number];
  up: readonly [number, number, number];
  target: readonly [number, number, number];
  zoom?: number;
}

/** A named view snap, a fit, a raw cube direction, or a remembered pose. */
export type ViewCommand =
  | { kind: "home" | "fit" | "front" | "top" | "right" | "iso"; nonce: number }
  | {
      kind: "direction";
      /** World-axis direction TO the camera (from the reference cube). */
      dir: readonly [number, number, number];
      nonce: number;
    }
  | {
      /**
       * Put the camera back where it was (CAMRESTORE-1). Issued when the
       * SKETCHER hands the camera back, carrying the pose it took it from.
       */
      kind: "restore";
      pose: ViewPose;
      nonce: number;
    };

/**
 * How the camera projects. Not a cosmetic preference — a perspective FRONT view
 * cannot be used for the job people open FRONT to do (ORTHO-1, four audit
 * passes): parallel edges converge, so equal features at different depths
 * measure differently and the view lies about the alignment you opened it to
 * check. Every incumbent (Fusion, SolidWorks, Onshape) opens a named view
 * orthographic.
 */
export type Projection = "orthographic" | "perspective";

/**
 * WHICH COMMANDS ARM ORTHOGRAPHIC, in one place, because the rule has to hold
 * for every caller — the view rail, the numeric snaps, the viewport context
 * menu and the reference cube all route through this store, and a policy
 * bolted onto one of them is a policy the other three break.
 *
 * A command that ORIENTS the camera (a named view, or a cube facet/edge/corner
 * pick — the same act by another instrument) means "look along this axis", and
 * looking along an axis to read it is what orthographic is for.
 *
 * `fit` is deliberately NOT here: it FRAMES, it does not orient, so it must
 * leave the projection exactly as the modeler left it.
 *
 * Nor is `restore`, for the stronger version of the same reason: it puts the
 * camera back at an attitude the modeler already had, so it is not a request to
 * look along an axis and must not silently change how they were looking. The
 * projection they left the sketcher with is restored by `ProjectionRig` from
 * `projection`, which this must therefore not touch.
 */
function orients(command: ViewCommand): boolean {
  return command.kind !== "fit" && command.kind !== "restore";
}

interface ViewCommandState {
  command: ViewCommand | null;
  /** What the camera does RIGHT NOW; the view rail's cell reads it back. */
  projection: Projection;
  request: (
    kind: Exclude<ViewCommand["kind"], "direction" | "restore">,
  ) => void;
  requestDirection: (dir: readonly [number, number, number]) => void;
  /** Put the camera back at a remembered pose (see {@link ViewPose}). */
  requestPose: (pose: ViewPose) => void;
  toggleProjection: () => void;
}

export const useViewCommandStore = create<ViewCommandState>((set, get) => ({
  command: null,
  // A part opens in perspective: the resting iso bench view reads better with
  // depth, and free orbit is where the incumbents keep perspective too. The
  // first named view the modeler asks for switches it (see `orients`).
  projection: "perspective",
  request: (kind) => {
    const command = { kind, nonce: (get().command?.nonce ?? 0) + 1 } as const;
    set(
      orients(command) ? { command, projection: "orthographic" } : { command },
    );
  },
  requestDirection: (dir) => {
    const command = {
      kind: "direction",
      dir,
      nonce: (get().command?.nonce ?? 0) + 1,
    } as const;
    set({ command, projection: "orthographic" });
  },
  requestPose: (pose) => {
    const command = {
      kind: "restore",
      pose,
      nonce: (get().command?.nonce ?? 0) + 1,
    } as const;
    set({ command });
  },
  toggleProjection: () =>
    set({
      projection:
        get().projection === "orthographic" ? "perspective" : "orthographic",
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

/**
 * How parallel a view direction and an up vector may be before the pair is
 * degenerate. cos 8.1° — well clear of any attitude a hand on a trackpad
 * produces, and tight enough that the substitution only fires on a genuinely
 * axis-aligned pose.
 */
const PARALLEL_DOT = 0.99;

/**
 * Camera up for a view direction — top/bottom need a non-parallel up.
 *
 * `dir` points from the target TO the camera (the convention every pose in the
 * viewport uses). Looking straight down, +Y is parallel to the view, so the
 * convention is up = −Z: kernel +y then reads up-screen in plan.
 */
export function upFor(dir: Vector3): Vector3 {
  return Math.abs(dir.y) > PARALLEL_DOT
    ? new Vector3(0, 0, dir.y > 0 ? -1 : 1)
    : new Vector3(0, 1, 0);
}

/**
 * The live camera's up, unless it is parallel to where the camera is looking —
 * in which case the axis convention above.
 *
 * A pose only needs an up to build a camera basis: `right = up × dir`. When the
 * two are parallel that cross product collapses, and long before it reaches
 * zero its DIRECTION is decided by rounding error — so the roll of the framing
 * is arbitrary and can differ between two runs of the same flow.
 *
 * Reachable in one line of the product: leaving the sketcher parks the camera
 * normal-on to the plane just drawn and restores world up (+Y), which for a
 * sketch on XY is |up · dir| ≈ 0.9996. The next fit adopts the live up and
 * hands `framePose` exactly that pair. Both arguments are expected to be unit
 * length; the live `up` is returned as-is (not cloned) when it is usable.
 */
export function safeUp(dir: Vector3, up: Vector3): Vector3 {
  return Math.abs(up.dot(dir)) > PARALLEL_DOT ? upFor(dir) : up;
}

/**
 * Keyboard accelerators for the view rail (one numeric vocabulary).
 *
 * `restore` is excluded with `direction` because neither is a view a user ASKS
 * for by name — both carry an argument no key could supply, and both are issued
 * by an instrument (the reference cube; the sketcher handing the camera back).
 */
export const VIEW_SHORTCUTS: Record<
  string,
  Exclude<ViewCommand["kind"], "direction" | "restore">
> = {
  "1": "front",
  "2": "top",
  "3": "right",
  "4": "iso",
  "0": "fit",
  Home: "home",
};

/**
 * The projection toggle's accelerator — the next free digit after the four
 * named views, so the whole view vocabulary stays numeric and adjacent.
 */
export const PROJECTION_SHORTCUT = "5";

/**
 * Global view accelerators. Numeric on purpose: the letter vocabulary belongs
 * to the sketch/feature verbs, and digits are free in every workspace. Only
 * armed while the view rig owns the camera (`enabled` = not sketching).
 */
export function useViewHotkeys(enabled: boolean): void {
  const request = useViewCommandStore((state) => state.request);
  const toggleProjection = useViewCommandStore(
    (state) => state.toggleProjection,
  );
  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey)
        return;
      if (isTypingTarget(event.target)) return;
      if (event.key === PROJECTION_SHORTCUT) {
        event.preventDefault();
        toggleProjection();
        return;
      }
      const kind = VIEW_SHORTCUTS[event.key];
      if (kind === undefined) return;
      event.preventDefault();
      request(kind);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, request, toggleProjection]);
}
