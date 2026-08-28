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
import { useEffect, useMemo, useRef, useState } from "react";

import type { Vec3 } from "../api/measure";
import { occtToScene, polylineAt } from "../measure/geometry";
import {
  ANCHOR_FRAME_BUDGET,
  ANCHOR_SAMPLE_BUDGET,
  chooseAnchor,
  type EdgeAnchor,
} from "./edgeMarkAnchor";

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
  /** Round-robin position, deliberately NOT reset when the camera moves. */
  const cursor = useRef(0);
  const working = useRef<EdgeMarkAnchor[]>(fallback);

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
    // The offer changed shape: start over rather than reading a stale
    // previous-anchor list against different polylines.
    if (working.current.length !== edges.length) {
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
      stampSeats("pending");
    }
    if (owed.current === 0 || edges.length === 0) {
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
        return addressable(
          occtToScene(polylineAt(polyline, fraction)),
          ordinal,
        );
      }, ANCHOR_SAMPLE_BUDGET);
      working.current[i] = {
        position: occtToScene(polylineAt(polyline, anchor.at)),
        buried: anchor.buried,
      };
    }

    if (!samePlacement(published.current, working.current)) {
      published.current = working.current.slice();
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
