/**
 * ONE PORTAL HOST FOR EVERY PICK MARK (board item #70).
 *
 * ## The defect this removes
 *
 * `PickMark` used to render a drei `<Html>` per mark. Read in the shipped
 * source (`@react-three/drei/web/Html.js`), `Html` calls
 * `ReactDOM.createRoot(el)` **per instance** and then re-renders that root from
 * a `useLayoutEffect` **with no dependency array** — so N marks are N
 * independent React roots, each with its own fiber tree, its own container and
 * its own full set of delegated DOM event listeners (React 19 calls
 * `listenToAllSupportedEvents` once per root container), and each re-rendering
 * on every render of its parent. It also calls `useFrame` per instance, and
 * r3f's `subscribe` re-SORTS the subscriber array on every subscription, so
 * mounting N marks is O(N^2 log N) in that array alone.
 *
 * Measured on the buggy 10 665-face golden the audit filed this under: **452
 * marks at ~3.3 ms each ≈ 13 s of main-thread script.** That is a hang, not a
 * slowdown — the tab is unresponsive while a pick arms.
 *
 * ## The shape of the fix
 *
 * One host `div` over the canvas, one `ReactDOM` root inside it, one slot per
 * mark, and ONE frame callback that projects every slot. N cheap style writes
 * replace N reconciliations. The per-mark cost that remains is a keyed child in
 * a single commit plus two string writes a frame.
 *
 * ## Why a second ReactDOM root at all
 *
 * Because the marks' JSX lives inside `<Canvas>`, where the active reconciler
 * is r3f's — `react-dom`'s `createPortal` from in there would try to construct
 * a `div` as a THREE object. Crossing back to the DOM needs a DOM root. drei
 * reached that conclusion too; the defect was never the root, it was that
 * there was one PER MARK. There is exactly one here, and it is shared by every
 * overlay because `PickMark` is the one primitive all of them mount through.
 *
 * The cost of the root boundary is that React context does not cross it. That
 * is not a regression: drei's `Html` had the identical boundary, so anything
 * that renders in a mark today renders in a mark now.
 *
 * ## Why the arithmetic is somewhere else
 *
 * `pickMarkProjection.ts`, and it is drei's own arithmetic transcribed. The
 * only thing this change is allowed to alter is cost, so the projection, the
 * depth→z-index mapping and the behind-camera cutoff are pinned by unit tests
 * against hand-computed values rather than left to be "obviously the same".
 *
 * ## What the slot must keep being
 *
 * Inert. The slot carries `pointer-events: none` and `PickNode` opts ITSELF
 * back in, which is MEASURE-PROXY-1's fix: a wrapper takes the BOX of a mark
 * that is a Ø24 circle, so its corners were a pointer target that did nothing
 * and sat on a neighbour's centre. The host is inert for the same reason —
 * it spans nothing (0x0) and yields the pointer regardless, so a click on
 * empty canvas still reaches the canvas.
 *
 * The host sets no `z-index` and no `transform` of its own, deliberately:
 * either would make it a stacking context and trap every mark's depth-derived
 * `z-index` inside it, which is the one thing that decides whether a vertex
 * mark stacks over an edge mark and both under the HUD.
 */
import { type CSSProperties, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Vector3 } from "three";
import type { Object3D } from "three";
import type { RootState, RootStore } from "@react-three/fiber";

import {
  depthZIndex,
  isBehindCamera,
  projectToScreen,
  type ScreenPoint,
  slotTransform,
} from "./pickMarkProjection";

/**
 * How far a mark must move on screen before its transform is rewritten, in CSS
 * pixels. drei's `eps`, and the same value: below this the write is invisible
 * and a still camera should cost nothing at all.
 */
const EPS = 0.001;

/** The host: spans nothing, styles nothing, stacks nothing. See the docblock. */
const HOST_STYLE =
  "position:absolute;top:0;left:0;width:0;height:0;pointer-events:none;";

/**
 * Every slot's style, shared and frozen — React skips a style diff entirely
 * when the object is identical, and `transform`/`z-index` are absent from it
 * on purpose so React never clobbers what the frame pass writes.
 */
const SLOT_STYLE: CSSProperties = Object.freeze({
  position: "absolute",
  top: 0,
  left: 0,
  transformOrigin: "0 0",
  pointerEvents: "none",
});

/** One mark's registration with the layer. */
export interface PickMarkSlot {
  /** Stable across the mark's life; React's key and the registry's identity. */
  readonly id: number;
  /** The mark's anchor in the scene graph — a real `Object3D`, because a mark
   * may sit under a transformed group (an assembly instance's pose) and its
   * world matrix is the only honest answer to "where is this". */
  object: Object3D | null;
  /** The depth→z-index band this class of mark occupies. */
  zIndexRange: readonly [number, number];
  /** What the mark renders. */
  node: ReactNode;
  /** The slot element, once the host root has committed it. */
  el: HTMLDivElement | null;
  /** Last written screen position, so a still camera writes nothing. */
  lastX: number;
  lastY: number;
  /** Last written zoom, because an orthographic zoom moves marks without
   * moving the projected centre of one that sits on the camera axis. */
  lastZoom: number;
  /** Last written visibility, so `display` is touched only on a transition. */
  visible: boolean;
  /** Has this slot ever been placed? An unplaced slot must not be trusted to
   * have a meaningful `lastX`/`lastY`. */
  placed: boolean;
}

let nextSlotId = 0;

/** A fresh, unregistered slot. */
export function createPickMarkSlot(
  zIndexRange: readonly [number, number],
  node: ReactNode,
): PickMarkSlot {
  nextSlotId += 1;
  return {
    id: nextSlotId,
    object: null,
    zIndexRange,
    node,
    el: null,
    lastX: 0,
    lastY: 0,
    lastZoom: 0,
    visible: true,
    placed: false,
  };
}

/** The slots, in mount order — the host renders them in exactly this order. */
function SlotList({
  slots,
  onMount,
}: {
  slots: readonly PickMarkSlot[];
  onMount: (slot: PickMarkSlot) => void;
}) {
  return (
    <>
      {slots.map((slot) => (
        <div
          key={slot.id}
          style={SLOT_STYLE}
          ref={(el: HTMLDivElement | null) => {
            slot.el = el;
            // Queue the first placement. Without it the slot would sit at the
            // canvas's top-left corner until the next frame — and under
            // `frameloop="demand"` "the next frame" can be a long time, so a
            // whole overlay's worth of marks would pile up in the corner. drei
            // avoided the same flash by writing the initial transform in its
            // layout effect; this lands in a microtask, which is still before
            // the browser paints.
            if (el !== null) onMount(slot);
          }}
        >
          {slot.node}
        </div>
      ))}
    </>
  );
}

// Scratch, module-level and reused: the frame pass must not allocate.
const worldPos = new Vector3();
const cameraPos = new Vector3();
const cameraDir = new Vector3();
const scratch = new Vector3();
const screen: ScreenPoint = { x: 0, y: 0 };

/**
 * The one host for one r3f root. Created by the first mark that mounts,
 * disposed by the last one that leaves.
 */
export class PickMarkLayer {
  private readonly store: RootStore;
  private readonly host: HTMLDivElement;
  private readonly root: Root;
  private readonly unsubscribe: () => void;
  private slots: PickMarkSlot[] = [];
  private renderQueued = false;
  private disposed = false;
  /** Slots whose element has just committed and has never been positioned. */
  private pendingPlacement: PickMarkSlot[] = [];
  private placeQueued = false;
  /** r3f wants a ref object; this is the frame callback's home. */
  private readonly frameRef: { current: (state: RootState) => void };

  constructor(store: RootStore) {
    this.store = store;
    const state = store.getState();

    this.host = document.createElement("div");
    this.host.style.cssText = HOST_STYLE;
    this.host.dataset.testid = "pick-mark-layer";
    hostTarget(state).appendChild(this.host);

    this.root = createRoot(this.host);

    // Subscribed ONCE, through the same seam `useFrame` uses, rather than once
    // per mark: r3f re-sorts `internal.subscribers` on every subscription, so
    // 452 `useFrame` calls is 452 sorts of a growing array before a single
    // frame runs.
    this.frameRef = { current: () => this.project() };
    this.unsubscribe = state.internal.subscribe(this.frameRef, 0, store);
  }

  /** Register a mark. Returns nothing; removal is `remove`. */
  add(slot: PickMarkSlot): void {
    this.slots.push(slot);
    this.scheduleRender();
  }

  remove(slot: PickMarkSlot): void {
    const at = this.slots.indexOf(slot);
    if (at >= 0) this.slots.splice(at, 1);
    slot.el = null;
    this.scheduleRender();
  }

  /**
   * Ask for ONE reconciliation covering every change made in this task. Called
   * by every mark on every render; the microtask fold is what turns N calls
   * into one `root.render`, which is the whole point of the class.
   */
  scheduleRender(): void {
    if (this.renderQueued || this.disposed) return;
    this.renderQueued = true;
    queueMicrotask(() => {
      this.renderQueued = false;
      this.flush();
    });
  }

  /** Render the host now — one reconciliation for every pending change. */
  private flush(): void {
    if (this.disposed) return;
    // A copy, because the render is concurrent and `slots` keeps mutating.
    const snapshot = this.slots.slice();
    this.root.render(
      <SlotList
        slots={snapshot}
        onMount={(slot) => this.queuePlacement(slot)}
      />,
    );
    // ONE invalidate for the whole batch. `frameloop="demand"` means a mark
    // whose anchor moved needs a frame drawn, and asking per mark would be 452
    // calls to say the same thing.
    this.store.getState().invalidate();
  }

  /**
   * Tear down. Deferred to a microtask because the last mark's unmount runs
   * inside the r3f root's commit, and unmounting another root synchronously
   * from there is exactly the re-entrancy React warns about.
   */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.unsubscribe();
    queueMicrotask(() => {
      this.root.unmount();
      this.host.remove();
    });
  }

  /**
   * A newly-committed slot needs its first transform before the browser
   * paints. Batched into ONE pass rather than run per slot, because the camera
   * walk it needs is identical for all of them — per-mark it was 452 redundant
   * matrix traversals during a mount, which is the exact shape of the defect
   * this class exists to remove.
   */
  private queuePlacement(slot: PickMarkSlot): void {
    this.pendingPlacement.push(slot);
    if (this.placeQueued || this.disposed) return;
    this.placeQueued = true;
    queueMicrotask(() => {
      this.placeQueued = false;
      const pending = this.pendingPlacement;
      this.pendingPlacement = [];
      if (this.disposed || pending.length === 0) return;
      const state = this.store.getState();
      this.readCamera(state);
      for (const waiting of pending) this.write(waiting, state);
    });
  }

  /** The single per-frame pass over every mark. Allocation-free. */
  private project(): void {
    if (this.slots.length === 0) return;
    const state = this.store.getState();
    this.readCamera(state);
    for (const slot of this.slots) this.write(slot, state);
  }

  /** The camera facts every mark in a pass shares. Hoisted once per pass. */
  private readCamera(state: RootState): void {
    state.camera.updateMatrixWorld();
    cameraPos.setFromMatrixPosition(state.camera.matrixWorld);
    state.camera.getWorldDirection(cameraDir);
  }

  /**
   * One mark's screen state. Reads `cameraPos`/`cameraDir`, which the caller
   * refreshed for the whole frame.
   */
  private write(slot: PickMarkSlot, state: RootState): void {
    const el = slot.el;
    const object = slot.object;
    if (el === null || object === null) return;

    object.updateWorldMatrix(true, false);
    worldPos.setFromMatrixPosition(object.matrixWorld);
    projectToScreen(
      worldPos,
      state.camera,
      state.size.width,
      state.size.height,
      scratch,
      screen,
    );

    const zoom = state.camera.zoom;
    if (
      slot.placed &&
      Math.abs(slot.lastZoom - zoom) <= EPS &&
      Math.abs(slot.lastX - screen.x) <= EPS &&
      Math.abs(slot.lastY - screen.y) <= EPS
    ) {
      return;
    }

    const visible = !isBehindCamera(worldPos, cameraPos, cameraDir, scratch);
    if (visible !== slot.visible || !slot.placed) {
      slot.visible = visible;
      el.style.display = visible ? "block" : "none";
    }

    const z = depthZIndex(
      worldPos.distanceTo(cameraPos),
      state.camera,
      slot.zIndexRange,
    );
    if (z !== null) el.style.zIndex = `${z}`;
    el.style.transform = slotTransform(screen.x, screen.y);

    slot.lastX = screen.x;
    slot.lastY = screen.y;
    slot.lastZoom = zoom;
    slot.placed = true;
  }
}

/**
 * Where the host hangs. drei's own answer, so the marks keep the containing
 * block — and therefore the coordinate origin and the stacking context — they
 * have always had.
 */
function hostTarget(state: RootState): HTMLElement {
  const connected: unknown = state.events.connected;
  if (connected instanceof HTMLElement) return connected;
  const parent = state.gl.domElement.parentElement;
  if (parent !== null) return parent;
  return document.body;
}

/** One layer per r3f root, reference-counted by the marks it carries. */
const layers = new Map<RootStore, { layer: PickMarkLayer; refs: number }>();

export function acquirePickMarkLayer(store: RootStore): PickMarkLayer {
  const held = layers.get(store);
  if (held !== undefined) {
    held.refs += 1;
    return held.layer;
  }
  const layer = new PickMarkLayer(store);
  layers.set(store, { layer, refs: 1 });
  return layer;
}

export function releasePickMarkLayer(store: RootStore): void {
  const held = layers.get(store);
  if (held === undefined) return;
  held.refs -= 1;
  if (held.refs > 0) return;
  layers.delete(store);
  held.layer.dispose();
}

/** Test seam: how many layers exist. One canvas must only ever have one. */
export function pickMarkLayerCount(): number {
  return layers.size;
}
