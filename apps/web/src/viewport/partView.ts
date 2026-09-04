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
 *               Its DEFAULT is derived too, on exactly the sketch layer's
 *               pattern: a body GHOSTS while a sketch is open (GHOST-1) and is
 *               solid otherwise. See {@link bodyView}.
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
import type { BufferGeometry } from "three";

import { isTypingTarget } from "../lib/isTypingTarget";
import {
  instanceView,
  isolateInstance,
  showAllInstances,
  toggleInstanceHidden,
  withVisibilityMode,
  type InstanceView,
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

/**
 * Shared empty set — a stable identity, so "nothing hidden" costs no render.
 *
 * Exported because it is the value the store resets to (`setSubject`,
 * `releasePickSubject` — the latter is what `ModelMesh` calls as it unmounts)
 * and every non-part consumer substitutes (`pickSurface.tsx`, whose
 * assembly instances carry their own geometry and no hidden ordinals). A
 * private copy per consumer is one more identity the store's `sameOrdinals`
 * guard has to walk instead of short-circuiting on `a === b`.
 */
export const NO_HIDDEN_FACES: ReadonlySet<number> = new Set<number>();

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
   * Is a sketch open on the drawing board right now? Published by `SketchScene`
   * (the one component that both reads the sketch store and is always mounted
   * in the part workspace), read by everything that has to know how a body is
   * drawn — see {@link bodyView} for what it means and why it is a published
   * fact rather than a cross-store import.
   */
  sketchOpen: boolean;
  /**
   * Could the fused mesh be split back into per-body face sets? Published by
   * the mesh, read by the Bodies panel so the two ends AGREE about when the
   * per-body eye is offered — a row whose eye is present but inert would be
   * worse than a row that says why it cannot.
   */
  partitioned: boolean;
  /** The row `V` / `⇧V` act on — the browser's addressed entity. */
  addressedKey: string | null;
  /**
   * The drawn mesh, published by `ModelMesh` so an armed pick overlay can
   * RAYCAST it (SEL-1 / spec A2) instead of relying on its 24 px centroid
   * buttons. The mesh is the only component that owns this object's lifetime,
   * so it publishes null before disposing — a consumer must treat null as "no
   * raycast target", never as "not loaded yet".
   */
  pickGeometry: BufferGeometry | null;
  /**
   * B-rep face ordinals of `pickGeometry` that are NOT drawn, because the body
   * owning them is hidden. Published together with the geometry and by the same
   * component, because they are one fact: *what a raycast against this mesh is
   * allowed to answer*.
   *
   * It has to be published rather than re-derived, and the reason is a three.js
   * detail worth writing down CORRECTLY — an earlier version of this comment
   * blamed the pick mesh's single material, which is wrong (SEL-6, read in the
   * vendored source). A hidden body is expressed as a draw group whose material
   * has `visible: false`; the renderer skips it, so nothing is drawn.
   * `Mesh.raycast` does not skip it, and the material-ARRAY branch does not
   * either: three 0.185's `checkIntersection()` consults only `material.side`
   * and never `material.visible`, so every triangle of the fused mesh is tested
   * whatever its body's state. A hidden body in FRONT would therefore swallow
   * the ray, and — since r3f keeps one hit per object — the drawn face behind it
   * would never be offered at all. `pickRaycast.ts` turns this set into the
   * filter that runs inside `raycast`, for the overlays and for `ModelMesh`'s
   * own hover alike, so the rule exists once rather than per consumer.
   *
   * It answers the MIRROR question too, in `hiddenPicks.ts`: an overlay lists
   * `/overlay`'s entities for the whole part, so without this set a
   * switched-off body's faces stay clickable through their centroid marks and
   * its edges through the band corridor. Same fact, both directions.
   */
  pickHiddenFaces: ReadonlySet<number>;

  setSubject: (subjectId: string) => void;
  setBodies: (bodies: readonly PartBodyView[]) => void;
  setBodyPresent: (present: boolean) => void;
  setSketchOpen: (open: boolean) => void;
  setPartitioned: (partitioned: boolean) => void;
  setPickGeometry: (geometry: BufferGeometry | null) => void;
  setPickHiddenFaces: (ordinals: ReadonlySet<number>) => void;
  /**
   * The publisher is going away: drop the mesh AND the ordinals that index it,
   * in one write.
   *
   * It exists as an ACTION rather than as two calls at the call site because
   * the two fields are one fact (see `pickHiddenFaces`), and a publisher that
   * released only half of it left a state describing a mesh that no longer
   * exists — the SEL-7 review defect. As one action there is no half to forget,
   * and the clearing itself is app code a test can invoke instead of imitating.
   */
  releasePickSubject: () => void;
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
  sketchOpen: false,
  partitioned: false,
  addressedKey: null,
  pickGeometry: null,
  pickHiddenFaces: NO_HIDDEN_FACES,

  setSubject: (subjectId) => {
    if (get().subjectId === subjectId) return;
    set({
      subjectId,
      view: seededOriginState(),
      bodies: [],
      bodyPresent: false,
      sketchOpen: false,
      partitioned: false,
      addressedKey: null,
      pickGeometry: null,
      pickHiddenFaces: NO_HIDDEN_FACES,
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
  setSketchOpen: (sketchOpen) => {
    if (get().sketchOpen === sketchOpen) return;
    set({ sketchOpen });
  },
  setPartitioned: (partitioned) => {
    if (get().partitioned === partitioned) return;
    set({ partitioned });
  },
  setPickGeometry: (pickGeometry) => {
    if (get().pickGeometry === pickGeometry) return;
    set({ pickGeometry });
  },
  setPickHiddenFaces: (pickHiddenFaces) => {
    if (sameOrdinals(get().pickHiddenFaces, pickHiddenFaces)) return;
    set({ pickHiddenFaces });
  },
  releasePickSubject: () => {
    const { pickGeometry, pickHiddenFaces } = get();
    if (pickGeometry === null && pickHiddenFaces.size === 0) return;
    set({ pickGeometry: null, pickHiddenFaces: NO_HIDDEN_FACES });
  },
  setAddressed: (addressedKey) => {
    if (get().addressedKey === addressedKey) return;
    set({ addressedKey });
  },
  toggle: (key) =>
    set({
      view: togglePartEntity(
        get().view,
        key,
        get().bodyPresent,
        get().sketchOpen,
      ),
    }),
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

/** Set equality — avoids a store write (and a scene re-render) per re-derive. */
function sameOrdinals(a: ReadonlySet<number>, b: ReadonlySet<number>): boolean {
  if (a === b) return true;
  if (a.size !== b.size) return false;
  for (const ordinal of a) if (!b.has(ordinal)) return false;
  return true;
}

/**
 * The eye, one click. An ORIGIN row stores its stop, so that is the plain flip.
 * A SKETCH row's stop and — since GHOST-1 — a BODY's may still be DERIVED
 * (never touched, so the row is showing whatever the context implies), and the
 * flip has to start from what the row is SHOWING. Otherwise the first click on
 * an already-receded sketch writes "hidden" over a derived hidden and nothing
 * happens on screen, which is the exact class of bug that makes a toggle feel
 * broken; and the first click on an auto-ghosted body would drop it to solid on
 * the way back, quietly discarding the state the row was displaying.
 */
export function togglePartEntity(
  view: VisibilityState,
  key: string,
  bodyPresent: boolean,
  sketchOpen: boolean,
): VisibilityState {
  if (view[key] === undefined && key.startsWith("sketch:")) {
    return withVisibilityMode(view, key, bodyPresent ? "solid" : "hidden");
  }
  if (view[key] === undefined && key.startsWith("body:") && sketchOpen) {
    // Materialise the ghost the row is currently showing, then hide. Un-hiding
    // therefore returns it to GHOST, which is what it looked like when touched.
    return { ...view, [key]: { hidden: true, ghost: true } };
  }
  return toggleInstanceHidden(view, key);
}

/**
 * How a body is drawn, DERIVED — the single answer the Bodies row and the WebGL
 * mesh both read, so the eye can never disagree with the pixels.
 *
 * GHOST-1: **a body ghosts automatically while a sketch is open.** Sketching on
 * a face with the solid sitting opaque in front of the work is the tool
 * declining to get out of the way — the founder's flow rule, and the reason
 * Fusion and Onshape both do this. The GHOST stop already existed; the sketcher
 * simply never used it.
 *
 * Two judgements are encoded here, and both are load-bearing.
 *
 * **It is a DEFAULT, not an override.** A stop the modeler has actually SET
 * wins, in either direction and at every moment — the auto-ghost applies only
 * to a body nothing has touched. That is the same contract `sketchIsDrawn` has
 * held since UI-W2, and it is what keeps the feature from being the thing the
 * ticket warned about: a body silently overridden on the way in and silently
 * restored on the way out. Nothing is stored on entry, so there is nothing to
 * restore on exit and nothing to get wrong; leaving the sketch simply stops the
 * condition being true. If the modeler changes a body's stop WHILE the sketch is
 * open, that writes an explicit stop, which wins immediately and keeps winning
 * after the sketch closes — their word is final and never quietly reverted.
 *
 * **It applies to EVERY body, not just the one being sketched on.** Occlusion
 * is a property of the camera and the plane, not of which face was picked: on a
 * multi-body part it is routinely a NEIGHBOURING solid standing between the eye
 * and the sketch. Ghosting only the host body would leave the defect intact on
 * exactly the parts where it hurts most. Ghost is see-through, not hidden, so
 * no context is lost — and a modeler who wants one body solid while sketching
 * says so once and it sticks.
 *
 * HIDE is never implied. Auto-ghosting changes `ghost` only, so `hidden` — and
 * with it isolate, show-all, the ISOLATED stamp and the pick-occlusion set —
 * behaves exactly as before.
 */
export function bodyView(
  view: VisibilityState,
  key: string,
  sketchOpen: boolean,
): InstanceView {
  const stored = view[key];
  if (stored !== undefined) return stored;
  return sketchOpen ? AUTO_GHOSTED : SHOWN_SOLID_BODY;
}

const AUTO_GHOSTED: InstanceView = { hidden: false, ghost: true };
const SHOWN_SOLID_BODY: InstanceView = { hidden: false, ghost: false };

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

/**
 * The three-stop projection for one body row — the flattening of
 * {@link bodyView}, so the row reads the same derivation the scene draws from.
 *
 * `sketchOpen` is REQUIRED rather than defaulted: a caller that forgot it would
 * show SOLID on a row the viewport is drawing see-through, which is the one
 * failure this whole design exists to prevent.
 */
export function bodyMode(
  view: VisibilityState,
  key: string,
  sketchOpen: boolean,
): VisibilityMode {
  const stop = bodyView(view, key, sketchOpen);
  return stop.hidden ? "hidden" : stop.ghost ? "ghost" : "solid";
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
