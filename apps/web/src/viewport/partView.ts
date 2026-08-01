/**
 * PART-workspace VIEW state (UI-W2, part half — `docs/design/ui-wave-tool-grade.md`
 * Surface 2). Founder-raised in these words: *"what about the ability to enable
 * planes, sketches and bodies? Similar to fusion?"*
 *
 * The assembly half shipped first and set the vocabulary; this is deliberately
 * the SAME vocabulary applied to the three things a part is made of, because a
 * second dialect for one idea is the design-system failure this repo reviews as
 * a defect:
 *
 *   · the EYE on every row (`EyeIcon` / `EyeGhostIcon` / `EyeOffIcon`);
 *   · SOLID · GHOST · HIDE disclosed under the ADDRESSED row;
 *   · ISOLATE as a right-click verb with `V` / `⇧V`, `⇧V` doubling as the way
 *     back so no chord can strand you in an empty scene;
 *   · a DERIVED `ISOLATED` stamp that renders only while something is hidden.
 *
 * It reuses `instanceVisibility.ts`'s pure verbs outright — they are keyed on an
 * opaque id string and never knew anything about instances — so there is one
 * implementation of "hidden and ghost are two orthogonal facts", not two.
 *
 * ## Why a store and not props
 *
 * The three categories are authored in DOM panels and drawn in WebGL, and the
 * two sides sit on opposite branches of the workspace tree. `viewCommands.ts`
 * already solved exactly this for the view rail ↔ camera rig: a small zustand
 * store both ends read. Same pattern, same reason — and it keeps the whole
 * surface inside the viewport/panel layer instead of threading eight props
 * through the workspace.
 *
 * ## What the categories are, and what a stop MEANS for each
 *
 * `origin:*`  — the three principal planes and the three axes. They are pure
 *               client-side datum geometry (no server, no solve). They start
 *               HIDDEN, as Fusion's do, so a part that needs no datum work is
 *               not permanently cluttered; the store therefore SEEDS the six
 *               keys hidden rather than special-casing "absent means hidden",
 *               which keeps every verb in `instanceVisibility.ts` reusable
 *               unchanged.
 * `sketch:*`  — a solved sketch's profile drawn in the 3D scene. Its DEFAULT is
 *               derived, not stored: a sketch shows while the part has no solid
 *               (it is the only thing to look at) and recedes once a body exists
 *               (coincident scribe ink only z-fights the solid it made). An
 *               explicit stop overrides that default in either direction — which
 *               is precisely the control the founder was missing.
 * `body:*`     — one solid body, keyed by its base feature id (the same identity
 *               `features/bodies.ts` and the kernel partition use). SOLID /
 *               GHOST / HIDE, matching the assembly's per-instance behaviour.
 *
 * ## Scope of the state
 *
 * View state is CLIENT-ONLY and unversioned: hiding a body changes no solve, no
 * export, no feature tree, and nothing is written back through the graph. It is
 * scoped to one part by `subjectId` — opening another part resets it, so a
 * hidden body can never follow you to a different document.
 */
import { useEffect } from "react";
import { create } from "zustand";

import { isTypingTarget } from "../lib/isTypingTarget";
import {
  instanceView,
  isolateInstance,
  showAllInstances,
  toggleInstanceHidden,
  visibilityModeOf,
  withVisibilityMode,
  type VisibilityMode,
  type VisibilityState,
} from "./instanceVisibility";

/** The three principal planes, in the order the browser lists them. */
export const ORIGIN_PLANES = ["XY", "XZ", "YZ"] as const;
export type OriginPlaneName = (typeof ORIGIN_PLANES)[number];

/** The three principal axes. */
export const ORIGIN_AXES = ["X", "Y", "Z"] as const;
export type OriginAxisName = (typeof ORIGIN_AXES)[number];

/** Entity key of one origin plane. */
export function originPlaneKey(plane: OriginPlaneName): string {
  return `origin:plane:${plane}`;
}

/** Entity key of one origin axis. */
export function originAxisKey(axis: OriginAxisName): string {
  return `origin:axis:${axis}`;
}

/** Entity key of one solved sketch, by its feature id. */
export function sketchKey(featureId: string): string {
  return `sketch:${featureId}`;
}

/** Entity key of one solid body, by its BASE (creating) feature id. */
export function bodyKey(baseFeatureId: string): string {
  return `body:${baseFeatureId}`;
}

/**
 * One body as the scene needs to know it: its key, in tree order, plus how many
 * disjoint LUMPS it holds. The lump count is what lets the renderer split ONE
 * fused GLB back into per-body face sets (see `bodyPartition.ts`) — the evaluate
 * payload ships a single merged mesh, never a mesh per body.
 */
export interface PartBodyView {
  /** `bodyKey(baseFeatureId)`. */
  readonly key: string;
  /** Human label, for the isolate stamp ("Body 2"). */
  readonly label: string;
  /** Disjoint solids in this body (≥1); 1 when the evaluate did not say. */
  readonly lumps: number;
}

/** Every origin key, seeded hidden — the resting state of a fresh part. */
function seededOriginState(): VisibilityState {
  const seed: Record<string, { hidden: boolean; ghost: boolean }> = {};
  for (const plane of ORIGIN_PLANES) {
    seed[originPlaneKey(plane)] = { hidden: true, ghost: false };
  }
  for (const axis of ORIGIN_AXES) {
    seed[originAxisKey(axis)] = { hidden: true, ghost: false };
  }
  return seed;
}

interface PartViewState {
  /** The part this state belongs to; changing it resets everything. */
  subjectId: string | null;
  view: VisibilityState;
  /** Bodies in tree order — published by the Bodies panel, read by the scene. */
  bodies: readonly PartBodyView[];
  /**
   * Does the part currently render a solid? Published by the mesh (the one
   * place that actually knows), read by the sketch layer AND by the browser, so
   * a sketch row's eye and the ink on screen can never disagree.
   */
  bodyPresent: boolean;
  /**
   * Could the fused mesh be split back into per-body face sets? Published by
   * the mesh, read by the Bodies panel so the two ends AGREE about when the
   * per-body eye is offered — a row whose eye is present but inert would be
   * worse than a row that says why it cannot.
   */
  partitioned: boolean;
  /** The row `V` / `⇧V` act on — the browser's addressed entity. */
  addressedKey: string | null;

  setSubject: (subjectId: string) => void;
  setBodies: (bodies: readonly PartBodyView[]) => void;
  setBodyPresent: (present: boolean) => void;
  setPartitioned: (partitioned: boolean) => void;
  setAddressed: (key: string | null) => void;
  toggle: (key: string) => void;
  setMode: (key: string, mode: VisibilityMode) => void;
  isolate: (key: string) => void;
  showAll: () => void;
}

export const usePartViewStore = create<PartViewState>((set, get) => ({
  subjectId: null,
  view: seededOriginState(),
  bodies: [],
  bodyPresent: false,
  partitioned: false,
  addressedKey: null,

  setSubject: (subjectId) => {
    if (get().subjectId === subjectId) return;
    set({
      subjectId,
      view: seededOriginState(),
      bodies: [],
      bodyPresent: false,
      partitioned: false,
      addressedKey: null,
    });
  },
  setBodies: (bodies) => {
    const current = get().bodies;
    if (sameBodies(current, bodies)) return;
    set({ bodies });
  },
  setBodyPresent: (bodyPresent) => {
    if (get().bodyPresent === bodyPresent) return;
    set({ bodyPresent });
  },
  setPartitioned: (partitioned) => {
    if (get().partitioned === partitioned) return;
    set({ partitioned });
  },
  setAddressed: (addressedKey) => {
    if (get().addressedKey === addressedKey) return;
    set({ addressedKey });
  },
  toggle: (key) =>
    set({ view: togglePartEntity(get().view, key, get().bodyPresent) }),
  setMode: (key, mode) =>
    set({ view: withVisibilityMode(get().view, key, mode) }),
  isolate: (key) =>
    set({
      view: isolateInstance(
        get().view,
        get().bodies.map((body) => body.key),
        key,
      ),
    }),
  showAll: () =>
    set({
      view: showAllInstances(
        get().view,
        get().bodies.map((body) => body.key),
      ),
    }),
}));

/** Identity check that avoids a store write (and a scene re-render) per poll. */
function sameBodies(
  a: readonly PartBodyView[],
  b: readonly PartBodyView[],
): boolean {
  if (a.length !== b.length) return false;
  return a.every((body, i) => {
    const other = b[i];
    return (
      other !== undefined &&
      other.key === body.key &&
      other.label === body.label &&
      other.lumps === body.lumps
    );
  });
}

/**
 * The eye, one click. Bodies and origin rows store their stop, so this is the
 * plain flip. A SKETCH row's stop may still be DERIVED (never touched, so it is
 * showing whatever "does this part have a solid" implies), and the flip has to
 * start from what the row is SHOWING — otherwise the first click on an
 * already-receded sketch writes "hidden" over a derived hidden and nothing
 * happens on screen, which is the exact class of bug that makes a toggle feel
 * broken.
 */
export function togglePartEntity(
  view: VisibilityState,
  key: string,
  bodyPresent: boolean,
): VisibilityState {
  if (view[key] === undefined && key.startsWith("sketch:")) {
    return withVisibilityMode(view, key, bodyPresent ? "solid" : "hidden");
  }
  return toggleInstanceHidden(view, key);
}

/**
 * Is this solved sketch drawn? The DERIVED default (see the module doc): shown
 * while the part has no solid, receded once a body exists — and an explicit stop
 * wins over the default either way.
 */
export function sketchIsDrawn(
  view: VisibilityState,
  featureId: string,
  bodyPresent: boolean,
): boolean {
  const stored = view[sketchKey(featureId)];
  if (stored === undefined) return !bodyPresent;
  return !stored.hidden;
}

/** The stop a sketch ROW shows — the same derivation the scene draws from. */
export function sketchRowMode(
  view: VisibilityState,
  featureId: string,
  bodyPresent: boolean,
): "solid" | "hidden" {
  return sketchIsDrawn(view, featureId, bodyPresent) ? "solid" : "hidden";
}

/** Is this entity drawn at all (origin rows and bodies, which store no default)? */
export function entityIsDrawn(view: VisibilityState, key: string): boolean {
  return !instanceView(view, key).hidden;
}

/** The three-stop projection for one body row. */
export function bodyMode(view: VisibilityState, key: string): VisibilityMode {
  return visibilityModeOf(view, key);
}

/**
 * `V` toggles the addressed row, `⇧V` isolates it — and, when anything is
 * already hidden, `⇧V` is the way BACK (show all), so the one accelerator can
 * never leave a modeler staring at an empty scene with no way out. Copied
 * deliberately, behaviour for behaviour, from the assembly half.
 *
 * Armed only while a part is registered as the subject (the part browser mounts
 * and registers it), so the assembly workspace's own `V` binding is untouched.
 */
export function usePartViewHotkeys(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key.toLowerCase() !== "v") return;
      const state = usePartViewStore.getState();
      if (state.subjectId === null) return;
      event.preventDefault();
      if (event.shiftKey) {
        if (hiddenBodyCount(state.view, state.bodies) > 0) state.showAll();
        else if (state.addressedKey !== null) state.isolate(state.addressedKey);
      } else if (state.addressedKey !== null) {
        state.toggle(state.addressedKey);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled]);
}

/**
 * How many BODIES are not drawn. The stamp counts solids only: a hidden sketch
 * or a hidden datum plane is never the "where did my part go" moment the banner
 * answers, and counting them would make the banner cry wolf on a scene the
 * modeler can see perfectly well.
 */
export function hiddenBodyCount(
  view: VisibilityState,
  bodies: readonly PartBodyView[],
): number {
  return bodies.filter((body) => instanceView(view, body.key).hidden).length;
}

/**
 * The isolated body's label, or null — DERIVED from the state, never a stored
 * "am I isolated" flag, so the stamp cannot claim something the scene
 * contradicts. Hiding everything but one BY HAND therefore earns the same
 * banner and the same way back, which is the actual failure mode.
 */
export function isolatedBodyLabel(
  view: VisibilityState,
  bodies: readonly PartBodyView[],
): string | null {
  if (bodies.length < 2) return null;
  const shown = bodies.filter((body) => !instanceView(view, body.key).hidden);
  return shown.length === 1 ? (shown[0]?.label ?? null) : null;
}
