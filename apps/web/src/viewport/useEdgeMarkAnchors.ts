/**
 * THE SCENE HALF OF PICKMARK-OCCLUDE-1 — walk each edge's own polyline until a
 * point the BAND answers with is found, and publish that as the mark's seat.
 *
 * The decision is in `edgeMarkAnchor.ts`, which is pure. What is here is the
 * frame budget it has to respect, and that budget is the reason this was split
 * out of SEL-8 rather than smuggled into it: a hit-test per mark per frame is
 * the obvious way to write this and the obvious way to lose 60 fps on a part
 * with 21 edges.
 *
 * ## The oracle is the BAND ITSELF, not a cheaper stand-in
 *
 * The first draft asked a weaker question — "is this point in front of the
 * drawn surface?" — using its own detached probe mesh. It is a reasonable
 * approximation and it made the census WORSE: 8/21 agreeing became 9/21 while
 * the wrong-edge count went 5 -> 10, because a point can clear the surface test
 * and still lose the band to a nearer edge crossing the same 24 px corridor.
 * Two hit-tests that disagree is the whole defect; a fix that adds a THIRD is
 * not a fix. So the caller supplies `addressable`, which runs
 * `resolveBandIntersections` over a real raycast of the real band and the real
 * pick surface — the same function, the same objects and the same bias the
 * pointer will use a moment later. Whatever it answers, the mark cannot be
 * wrong about.
 *
 * ## What keeps it inside the budget
 *
 *  · **The mid-span first.** The convention is tried before anything else, so
 *    an edge whose mid-span is fine costs ONE hit-test and does not move.
 *  · **A camera gate.** The answer can only change when the camera moves or the
 *    offer changes, so a still frame costs nothing at all.
 *  · **No allocation in the loop** — the scratch below is held across frames.
 */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Vector3 } from "three";
import type { Camera } from "three";

import type { Vec3 } from "../api/measure";
import { occtToScene, polylineAt } from "../measure/geometry";
import {
  ANCHOR_FRAME_BUDGET,
  ANCHOR_SAMPLE_BUDGET,
  chooseAnchor,
  type EdgeAnchor,
} from "./edgeMarkAnchor";

/**
 * A SEAT UNDER A GAUGE IS NOT A SEAT (board item #76).
 *
 * The band answers whether the WebGL hit-test reaches a point; it knows
 * nothing about DOM chrome stacked above the canvas. The one piece of chrome
 * that lands on marks is a gauge: its grip and hit sleeve are live pointer
 * targets stacked ABOVE the edge marks, and a fillet/chamfer gauge seats at
 * its picked edge's mid-span — exactly where that edge's own mark sits.
 * Measured on the audit's housing: pick `edge-pick-0`, and the sleeve lands on
 * `edge-pick-0` itself, so a real click on the mark hits the gauge and the pick
 * cannot be undone except by clearing EVERY pick. The mark was drawn, visible,
 * and not a control — a dead end.
 *
 * So the question a seat has to answer is the pointer's whole question: does
 * the band answer this edge here, AND is no gauge sitting on the mark's 24 px
 * box? A seat that fails the second walks along its OWN edge exactly as a
 * buried one does, so the mark is still drawn on its subject — it just stands
 * on the part of it the gauge is not covering.
 *
 * Scoped to `[data-gauge]` deliberately, not "any element on top": other pick
 * marks are on top of the canvas too, and a probe that treated every DOM node
 * as an occluder would make marks flee each other and the band. A gauge is a
 * handful of nodes (a grip plus a few sleeve bands), so reading them is
 * bounded; with none mounted this costs one empty `querySelectorAll`.
 */
const MAX_KEEP_OUTS = 16;
/** Half of `PickNode`'s 24 px target — the box a seat must keep clear. */
const MARK_HALF_PX = 12;
/**
 * Keep-outs are quantised before they re-owe the seats, so a gauge settling by
 * a sub-pixel does not restart the pass. Coarser than that and a mark could be
 * left a few pixels under a sleeve that moved.
 */
const KEEP_OUT_QUANTUM_PX = 4;
/**
 * Frames to wait, after the seats React COMMITTED match the ones this pass
 * published, before the stamp may say `settled`.
 *
 * `settled` is a claim about the SCREEN — specs read mark boxes the moment it
 * appears — and a published seat reaches the screen through three more hops:
 * this hook's commit, the owning overlay's commit (the measure overlay copies
 * the seats through an effect), and the pick-mark layer's projection frame.
 * Measured without this (board #76, `edge-highlight.spec.ts`): the stamp read
 * `settled` while the measure mark for edge 18 was still drawn at its mid-span
 * fallback, 93 px from the seat the pass had already published; the next hover
 * frame moved it. Waiting for the commit is exact; the frames after it cover
 * the two hops this hook cannot observe, and cost ~50 ms once per settle.
 */
export const SEAT_CONFIRM_FRAMES = 3;

/**
 * The gauge chrome a mark must keep clear of: every element a gauge tags
 * `data-gauge` (grip and hit sleeve) AND that gauge's value readout, which is a
 * live control of its own ("the readout IS the input") rendered in a separate
 * positioned wrapper that carries no `data-gauge`. Measured: pick
 * `shell-face-4` and `shell-thickness-readout` lands on its mark, so a click
 * there opened the value field instead of un-picking the face.
 *
 * The readout is found as `<id>-readout` for an `<id>` that a `data-gauge`
 * element actually names — NEVER by the bare `-readout` suffix. The suffix is
 * not gauge-specific: `measure-readout`, `selection-readout` and four more HUD
 * panels end in it, and matching them would steer marks out from under HUD
 * chrome in whichever overlays happen to share the screen with that panel —
 * the same edge seated in two places depending on the tool. A `data-gauge`
 * tag on the readout in `ParametricGauge.tsx` would let this collapse to one
 * selector.
 */
const GAUGE_TAG = "[data-gauge]";
const READOUT_SUFFIX = "-readout";

/**
 * The gauges currently on screen, as keep-out rectangles in client px — ONE
 * implementation for every seat pass (edge marks here, face marks in
 * `useSurfaceMarkBurial`), because two copies of "is this mark under a gauge"
 * that drift apart would put a mark under a gauge in one overlay only.
 *
 * Holds its rectangles in a preallocated buffer, so a frame that re-reads them
 * allocates nothing beyond the `NodeList` the query itself returns.
 */
export class GaugeKeepOuts {
  private readonly rects = new Float64Array(MAX_KEEP_OUTS * 4);
  private count = 0;
  private stamp = 0;
  private readonly probe = new Vector3();
  private queued = false;

  /**
   * Re-read the gauges AFTER the current frame, and call `onChange` if they
   * moved. Call it from a frame callback, every frame.
   *
   * WHY AFTER, by construction rather than by measurement: a gauge's grip is
   * positioned by drei `Html` in ITS own frame callback, and nothing orders
   * that callback relative to this pass. Read at the top of the pass, the
   * grip's transform may be a frame old — and on the gauge's LAST frame, with
   * `frameloop="demand"`, no later frame would come to correct it. A microtask
   * queued here runs once every callback of this frame has returned, so it
   * reads the transforms the frame actually wrote; if they changed, `onChange`
   * re-owes the seats and asks for the frame that re-seats them.
   *
   * Said plainly so nobody over-trusts it: the case that first looked like this
   * race (`fillet-radius-handle` on a live "settled" mark) was NOT it — the
   * diagnostics showed the keep-out reading the grip correctly and the seat
   * already recomputed; the seat was simply never PUBLISHED (see the working
   * array's reset in `useEdgeMarkAnchors`). This ordering is the version that
   * cannot read a stale grip, not a fix for a measured one.
   */
  refreshAfterFrame(onChange: () => void): void {
    if (this.queued) return;
    this.queued = true;
    queueMicrotask(() => {
      this.queued = false;
      if (this.refresh()) onChange();
    });
  }

  /**
   * Re-read every `[data-gauge]` element that has area, and report whether the
   * set CHANGED (quantised to `KEEP_OUT_QUANTUM_PX`). A gauge mounting does not
   * move the camera, so a seat pass that only re-owes on camera motion would
   * never revisit the mark the gauge has just covered — callers re-owe on
   * `true`.
   */
  refresh(): boolean {
    const nodes = document.querySelectorAll<HTMLElement>(GAUGE_TAG);
    this.count = 0;
    let stamp = nodes.length;
    let lastGauge: string | null = null;
    for (let n = 0; n < nodes.length && this.count < MAX_KEEP_OUTS; n += 1) {
      const node = nodes[n] as HTMLElement;
      stamp = this.keepOut(node, stamp);
      // Grip and sleeve of one gauge are adjacent in document order, so the
      // readout is looked up once per gauge rather than once per element.
      const gauge = node.getAttribute("data-gauge");
      if (gauge === null || gauge === "" || gauge === lastGauge) continue;
      lastGauge = gauge;
      const readout = document.querySelector<HTMLElement>(
        `[data-testid="${CSS.escape(gauge + READOUT_SUFFIX)}"]`,
      );
      if (readout !== null && this.count < MAX_KEEP_OUTS) {
        stamp = this.keepOut(readout, stamp);
      }
    }
    if (stamp === this.stamp) return false;
    this.stamp = stamp;
    return true;
  }

  /** Record one element's box as a keep-out; returns the updated stamp. */
  private keepOut(node: HTMLElement, stamp: number): number {
    const r = node.getBoundingClientRect();
    // `display:none` sleeve bands and unmeasured grips have no area and are
    // no pointer target; they must not push a seat anywhere.
    if (r.width <= 0 || r.height <= 0) return stamp;
    const at = this.count * 4;
    this.rects[at] = r.left;
    this.rects[at + 1] = r.top;
    this.rects[at + 2] = r.right;
    this.rects[at + 3] = r.bottom;
    this.count += 1;
    let next = (stamp * 31 + Math.round(r.left / KEEP_OUT_QUANTUM_PX)) | 0;
    next = (next * 31 + Math.round(r.top / KEEP_OUT_QUANTUM_PX)) | 0;
    next = (next * 31 + Math.round(r.right / KEEP_OUT_QUANTUM_PX)) | 0;
    return (next * 31 + Math.round(r.bottom / KEEP_OUT_QUANTUM_PX)) | 0;
  }

  /** Is the 24 px mark box centred on this scene point clear of every gauge? */
  clear(
    point: readonly [number, number, number],
    camera: Camera,
    canvas: HTMLElement,
  ): boolean {
    if (this.count === 0) return true;
    const box = canvas.getBoundingClientRect();
    this.probe.set(point[0], point[1], point[2]).project(camera);
    // Behind the camera: not on screen at all, so no gauge can cover it.
    if (this.probe.z > 1) return true;
    const x = box.left + ((this.probe.x + 1) / 2) * box.width;
    const y = box.top + ((1 - this.probe.y) / 2) * box.height;
    for (let k = 0; k < this.count; k += 1) {
      if (
        x + MARK_HALF_PX > (this.rects[k * 4] as number) &&
        x - MARK_HALF_PX < (this.rects[k * 4 + 2] as number) &&
        y + MARK_HALF_PX > (this.rects[k * 4 + 1] as number) &&
        y - MARK_HALF_PX < (this.rects[k * 4 + 3] as number)
      ) {
        return false;
      }
    }
    return true;
  }
}

/** One edge's mark placement, as the overlays consume it. */
export interface EdgeMarkAnchor {
  /** Scene-space point to draw the diamond at. */
  position: [number, number, number];
  /** No sampled point of this edge is addressable from the current camera. */
  buried: boolean;
}

/** The polylines to place marks on, in the overlays' own order. */
export interface EdgeMarkInput {
  /** The ordinal the band reports for this edge. */
  index: number;
  /** The edge's tessellated polyline, in OCCT world mm. */
  polyline: readonly Vec3[];
}

/**
 * Does the band, right now, answer `edgeIndex` at this scene-space point?
 * Supplied by `EdgeBandLayer`, which owns both raycast targets.
 */
export type AddressableAt = (
  point: readonly [number, number, number],
  edgeIndex: number,
) => boolean;

function samePlacement(
  a: readonly EdgeMarkAnchor[],
  b: readonly EdgeMarkAnchor[],
): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    const x = a[i] as EdgeMarkAnchor;
    const y = b[i] as EdgeMarkAnchor;
    if (x.buried !== y.buried) return false;
    if (
      x.position[0] !== y.position[0] ||
      x.position[1] !== y.position[1] ||
      x.position[2] !== y.position[2]
    ) {
      return false;
    }
  }
  return true;
}

/** The conventional seat: the edge's arc-length mid-point, not buried. */
function midSpanPlacement(edges: readonly EdgeMarkInput[]): EdgeMarkAnchor[] {
  return edges.map((edge) => ({
    position: occtToScene(polylineAt(edge.polyline, 0.5)),
    buried: false,
  }));
}

/**
 * Where each edge's diamond belongs, recomputed when the camera or the offer
 * moves. With no oracle (`addressable` absent) every mark keeps its mid-span
 * and nothing is ever buried — the behaviour that predates this module.
 */
export function useEdgeMarkAnchors(
  edges: readonly EdgeMarkInput[],
  addressable?: AddressableAt,
): EdgeMarkAnchor[] {
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);
  const canvas = useThree((s) => s.gl.domElement);

  const ordinals = useMemo(() => edges.map((edge) => edge.index), [edges]);
  const fallback = useMemo(() => midSpanPlacement(edges), [edges]);

  const [anchors, setAnchors] = useState<EdgeMarkAnchor[]>(fallback);
  const cameraStamp = useRef("");
  const published = useRef<EdgeMarkAnchor[]>(fallback);
  /** Edges still owed a refresh for the current camera. */
  const owed = useRef(0);
  /** The gauges on screen — see `GaugeKeepOuts`. */
  const keepOuts = useMemo(() => new GaugeKeepOuts(), []);
  /** Round-robin position, deliberately NOT reset when the camera moves. */
  const cursor = useRef(0);
  const working = useRef<EdgeMarkAnchor[]>(fallback);
  /** The input `working` was built for — see the reset in the frame. */
  const workingFor = useRef<readonly unknown[] | null>(null);
  /** The seats React last COMMITTED — see `SEAT_CONFIRM_FRAMES`. */
  const committed = useRef<readonly EdgeMarkAnchor[]>(fallback);
  /** Frames since `committed` caught up with `published`. */
  const confirmed = useRef(0);
  useLayoutEffect(() => {
    committed.current = anchors;
  }, [anchors]);

  /**
   * `data-edge-mark-seats` on the viewport — `pending` while the rotating
   * budget still owes an edge an answer, `settled` once every mark has been
   * placed against the CURRENT camera.
   *
   * The same QA-stamp posture as `useViewportPickStamp`, and load-bearing for
   * the same reason: the placement is settled asynchronously over several
   * frames, so a spec that censused the seats after a fixed number of frames
   * would be measuring a half-drained pass. Written imperatively rather than
   * through React because it changes on frames where nothing else does.
   */
  const stampSeats = (state: "pending" | "settled") => {
    if (addressable === undefined) return;
    const node = canvas.closest<HTMLElement>('[data-testid="viewport"]');
    if (node !== null && node.dataset["edgeMarkSeats"] !== state) {
      node.dataset["edgeMarkSeats"] = state;
    }
  };

  useEffect(() => {
    if (addressable === undefined) return;
    const node = canvas.closest<HTMLElement>('[data-testid="viewport"]');
    return () => {
      if (node !== null) delete node.dataset["edgeMarkSeats"];
    };
  }, [canvas, addressable]);

  useFrame(() => {
    // A gauge arrived, left or moved: every seat is owed a fresh answer.
    // Gauges are read AFTER this frame (see `refreshAfterFrame`); a change
    // re-owes every seat and asks for the frame that re-seats them.
    if (addressable !== undefined) {
      keepOuts.refreshAfterFrame(() => {
        cameraStamp.current = "";
        invalidate();
      });
    }

    // The offer changed shape: start over rather than reading a stale
    // previous-anchor list against different polylines.
    // THE WORKING ARRAY MUST NEVER BE THE PUBLISHED ONE (board item #76).
    //
    // `working` and `published` were both initialised with the SAME `fallback`
    // array — which is also the initial React state. So the pass wrote new seats
    // INTO the published array in place, `samePlacement(published, working)`
    // compared that array with itself, came back true, and the setter was never
    // called. The overlay showed the new seats only when it happened to
    // re-render for some unrelated reason — which is exactly the measured
    // symptom: seven edge marks drawn live at their mid-span while the pass had
    // already buried them, flipping to buried the instant the pointer moved and
    // a hover re-rendered the overlay. The mark vanished from under the user's
    // pointer, and a real click on it fell through to the body. Also reset when
    // the INPUT changes identity, not only its length: a refetched offer with
    // the same count is different polylines, and its seats are owed afresh.
    if (workingFor.current !== edges) {
      workingFor.current = edges;
      working.current = fallback.slice();
      cursor.current = 0;
      cameraStamp.current = "";
    }

    /*
      QUANTISED, and that is not tidiness. `OrbitControls` damping decays
      asymptotically, so the camera matrix keeps changing by ever-smaller
      amounts long after the orbit has visibly stopped — and since this
      callback asks for a frame whenever it has work, a raw comparison makes
      the two feed each other: every micro-change owes 21 fresh answers, the
      recompute schedules the frame that produces the next micro-change, and
      the seats never report settled. Measured: `data-edge-mark-seats` stayed
      `pending` for the full 30 s after a 60-step drag. Three decimals is
      0.001 mm of camera travel, far below anything that can move a 24 px mark.
    */
    const stamp = camera.matrixWorld.elements
      .map((value) => value.toFixed(3))
      .join(",");
    if (stamp !== cameraStamp.current) {
      cameraStamp.current = stamp;
      // A new pose owes every edge a fresh answer. The CURSOR is not reset:
      // during a continuous orbit the camera changes every frame, and starting
      // each pass at zero would mean only the first few edges were ever
      // refreshed while the rest kept a pose-old seat indefinitely.
      owed.current = edges.length;
      confirmed.current = 0;
      stampSeats("pending");
    }
    if (owed.current === 0 || edges.length === 0) {
      // Settled only once the published seats are what is ON SCREEN.
      if (
        addressable !== undefined &&
        (committed.current !== published.current ||
          confirmed.current < SEAT_CONFIRM_FRAMES)
      ) {
        confirmed.current =
          committed.current === published.current ? confirmed.current + 1 : 0;
        stampSeats("pending");
        invalidate();
        return;
      }
      stampSeats("settled");
      return;
    }

    if (addressable === undefined) {
      owed.current = 0;
      if (!samePlacement(published.current, fallback)) {
        published.current = fallback;
        setAnchors(fallback);
      }
      return;
    }

    let spent = 0;
    while (owed.current > 0 && spent < ANCHOR_FRAME_BUDGET) {
      const i = cursor.current % edges.length;
      cursor.current = (cursor.current + 1) % edges.length;
      owed.current -= 1;
      const polyline = (edges[i] as EdgeMarkInput).polyline;
      const ordinal = ordinals[i] as number;
      const anchor: EdgeAnchor = chooseAnchor((fraction) => {
        spent += 1;
        const point = occtToScene(polylineAt(polyline, fraction));
        // The cheap screen test first: a seat under a gauge is refused before
        // it costs a raycast.
        return (
          keepOuts.clear(point, camera, canvas) && addressable(point, ordinal)
        );
      }, ANCHOR_SAMPLE_BUDGET);
      working.current[i] = {
        position: occtToScene(polylineAt(polyline, anchor.at)),
        buried: anchor.buried,
      };
    }

    if (!samePlacement(published.current, working.current)) {
      published.current = working.current.slice();
      confirmed.current = 0;
      setAnchors(published.current);
    }
    // ASK FOR ONE MORE FRAME, for two reasons that both end in a stale seat.
    // (a) Work is carried across frames by the budget above, and with
    // `frameloop="demand"` nothing else will schedule the frame that finishes
    // it. (b) This callback is registered by an overlay that mounts BEFORE
    // `CameraRig`, so within a frame it reads the camera the rig is about to
    // move; on the LAST frame of a fit or an orbit the settled pose lands after
    // this has run, and on a junction edge one pose of lag is the difference
    // between the right edge and its neighbour. Either way the loop converges:
    // once nothing is owed, the guard above returns before this line.
    invalidate();
  });

  return anchors.length === edges.length ? anchors : fallback;
}
