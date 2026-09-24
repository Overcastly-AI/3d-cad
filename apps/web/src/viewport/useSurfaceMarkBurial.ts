/**
 * WHERE A FACE MARK MAY STAND — on its OWN face, where the pointer can reach
 * that face, and not under a gauge.
 *
 * ## The defect (board item #76, problem 3)
 *
 * The edge overlays have had an occlusion oracle since PICKMARK-OCCLUDE-1
 * (`useEdgeMarkAnchors`). **The FACE overlays had none at all.** A face mark
 * was planted at the face's area centroid and left there, and a centroid is a
 * point in space, not a point on screen — so the BOTTOM face of a box, seen
 * from iso, projected its mark into the middle of the FRONT wall. The mark was
 * a live DOM button that never asked the scene anything, so it won the pixel
 * over the body's own raycast, and clicking what looked unambiguously like the
 * front wall opened the bottom one instead. Measured on the audit's housing
 * with shell armed: 3 of 6 face marks stood on a face they did not belong to.
 * On the shelled housing the same mechanism put a buried outer wall's mark a
 * few pixels from its visible inner twin — the audit's "9 px" pair.
 *
 * That is not a spacing problem, and moving marks apart would not have fixed
 * it: the mark was exactly where its subject is. What was missing is the
 * question every edge mark already asks — *can the pointer reach my subject
 * here?* This asks it.
 *
 * ## And a mark must not stand under the gauge its own pick mounted
 *
 * Problem 2, face side. Pick a shell face and the thickness gauge seats at that
 * face's centroid — measured: `shell-thickness-handle` on top of
 * `shell-face-0`'s mark, so a real click on the mark hit the grip and the pick
 * could not be undone. So a seat must also be clear of every gauge on screen
 * (`GaugeKeepOuts`, the one implementation shared with the edge pass).
 *
 * ## How it finds a seat: a walk IN THE FACE'S OWN PLANE
 *
 * An edge mark can slide along its edge; a face mark has a whole plane. The
 * centroid is tried first, so a face whose centroid is visible and clear costs
 * ONE raycast and does not move. Otherwise the walk tries points on two rings
 * around the centroid, in the plane spanned by the face's own normal, at radii
 * scaled by the face's size (`sqrt(area)`), and takes the first that is both
 * clear of gauges and ANSWERED BY THIS FACE. That second condition is what
 * keeps the mark honest: a candidate that has walked off the face, or onto a
 * part of it hidden behind other material, is answered by some other face (or
 * by nothing) and is refused. So wherever the mark ends up, a click there picks
 * the face it names.
 *
 * ## The oracle is the pick surface itself
 *
 * Not a cheaper stand-in. `useEdgeMarkAnchors`' docblock records what happened
 * when its first draft used a detached probe mesh: the census got WORSE,
 * because two hit-tests that disagree IS the defect and a third does not help.
 * So this casts through the very mesh `PickSurface` mounts — carrying the
 * SEL-6 hidden-body filter inside its own `raycast`, so a switched-off body
 * cannot absorb the ray — and resolves the struck triangle with the same
 * `ordinalAt` the pointer handlers use.
 *
 * ## The budget, and the settle
 *
 * A camera gate (quantised, because `OrbitControls` damping decays
 * asymptotically), a gauge gate, an oracle gate, and a per-frame budget on
 * raycasts — the edge pass's floor, plus a time slice that lets a cheap pass
 * finish in a frame or two (`SURFACE_SEAT_FRAME_MS`). `data-face-mark-seats`
 * on the viewport reads `pending` until every offered mark has an answer for
 * the CURRENT camera and gauges, `settled` after — deliberately a SEPARATE
 * attribute from `data-edge-mark-seats`, so a spec cannot wait on a settle
 * nothing is draining.
 */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Raycaster, Vector2, Vector3 } from "three";
import type { Intersection, Mesh } from "three";

import type { Vec3 } from "../api/measure";
import { occtToScene } from "../measure/geometry";
import { measuredFrameSeconds } from "./frameDelta";
import { GaugeKeepOuts, SEAT_CONFIRM_FRAMES } from "./useEdgeMarkAnchors";

/**
 * How many raycasts the pass may ALWAYS spend per frame. A subject's walk is
 * always finished once started (so a mark never publishes a half-searched
 * seat), which means one frame can overrun this by up to one walk.
 */
export const SURFACE_SEAT_FRAME_BUDGET = 24;

/**
 * The wall-clock slice, in ms, the pass may keep going for once the floor above
 * is spent: a THIRD OF WHAT A FRAME CURRENTLY COSTS (the share the edge pass's
 * budget was sized to at 60 fps), never less than `SURFACE_SEAT_FRAME_MS` and
 * never more than `SURFACE_SEAT_MAX_SLICE_MS`. See {@link seatSliceMs}.
 *
 * WHY A SLICE AND NOT ONLY A COUNT (PERF-REAL-1). The count was sized for a
 * raycast that cost a quarter of a millisecond on a small part. On the
 * gauntlet's 1 018-face gearbox the face pick offers 452 marks, most of them
 * buried — and a buried mark walks all 17 of its candidates, so one camera pose
 * owes thousands of raycasts. At 24 a frame that is ~190 frames before the pick
 * can settle; measured at the tip before this change, it had not settled after
 * 158 frames and eleven minutes. The raycast is now a hierarchy walk
 * (`pickBvh.ts`) costing microseconds, so the frame COUNT became the whole
 * remaining cost — and a count cannot know that its raycasts got cheap. A slice
 * does: a cheap pass drains in a frame or two, and an expensive one still
 * stops at the floor exactly as before.
 *
 * WHY PROPORTIONAL TO THE FRAME. A fixed 6 ms is right at 60 fps and wrong on a
 * machine where a frame of a 400 000-triangle part costs seconds (software GL,
 * which is where CI and the gauntlet run): there, 6 ms slices spread ~70 ms of
 * work over a dozen multi-second frames. A third of the frame keeps the pass's
 * share of the frame the same everywhere.
 *
 * ONLY WHEN `delta` IS A FRAME. The first frame after an idle spell carries the
 * idle time as its `delta` (`frameDelta.ts`), so a pass that starts there —
 * the first frame of an orbit — takes the floor, not a slice sized from the
 * idle span. Before the review of PERF-REAL-1 caught it, that frame took the
 * 250 ms ceiling: a visible hitch at the start of every orbit on a big part,
 * spent on seats the orbit's next frame threw away. The ceiling still bounds a
 * continuing frame that is merely very slow.
 */
export const SURFACE_SEAT_FRAME_MS = 6;

/** The ceiling on one frame's slice, in ms — see `SURFACE_SEAT_FRAME_MS`. */
export const SURFACE_SEAT_MAX_SLICE_MS = 250;

/**
 * The slice the pass may spend this frame, given r3f's `delta` and whether the
 * previous rendered frame was also a pass frame (`continuing`): a third of a
 * measured frame, clamped to [`SURFACE_SEAT_FRAME_MS`,
 * `SURFACE_SEAT_MAX_SLICE_MS`], or the floor when `delta` is not a frame.
 */
export function seatSliceMs(delta: number, continuing: boolean): number {
  const frame = measuredFrameSeconds(delta, continuing);
  if (frame === null) return SURFACE_SEAT_FRAME_MS;
  return Math.min(
    SURFACE_SEAT_MAX_SLICE_MS,
    Math.max(SURFACE_SEAT_FRAME_MS, (frame * 1000) / 3),
  );
}

/**
 * The walk's two rings, as fractions of the face's characteristic length
 * `sqrt(area)`, and how many points each ring tries. Small enough that the
 * inner ring stays well inside any reasonably-shaped face; the outer ring is
 * the last resort before the mark is declared buried.
 */
const RING_FRACTIONS = [0.18, 0.32] as const;
const RING_POINTS = 8;

/** A face mark to seat. */
export interface SurfaceMarkSubject {
  /** The B-rep face ordinal this mark addresses. */
  ordinal: number;
  /** The face's area centroid, OCCT world mm — the conventional seat. */
  point: Vec3;
  /** The face's outward unit normal, OCCT world — spans the walk's plane. */
  normal: Vec3;
  /** The face's area, mm² — scales the walk to the face. */
  areaMm2: number;
}

/** Where one face mark stands, as the overlays consume it. */
export interface SurfaceMarkSeat {
  /** Scene-space point to draw the mark at. */
  position: [number, number, number];
  /**
   * No tried point of this face is both reachable and clear of gauges. The
   * mark then stands at the centroid as a hidden-line ghost and takes no
   * pointer; the keyboard is its route.
   */
  buried: boolean;
}

/**
 * The candidate seats for one face, in SCENE space, centroid first. Computed
 * once per offer (not per frame) so the walk itself allocates nothing.
 */
export function faceSeatCandidates(
  subject: SurfaceMarkSubject,
): [number, number, number][] {
  const out: [number, number, number][] = [occtToScene(subject.point)];
  const { x: nx, y: ny, z: nz } = subject.normal;
  const nLen = Math.hypot(nx, ny, nz);
  const size = Math.sqrt(Math.max(subject.areaMm2, 0));
  if (nLen === 0 || size === 0) return out;
  const n = [nx / nLen, ny / nLen, nz / nLen] as const;
  // Any vector not parallel to n; cross twice for an orthonormal in-plane pair.
  const h = Math.abs(n[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  let u = [
    n[1] * (h[2] as number) - n[2] * (h[1] as number),
    n[2] * (h[0] as number) - n[0] * (h[2] as number),
    n[0] * (h[1] as number) - n[1] * (h[0] as number),
  ];
  const uLen = Math.hypot(u[0] as number, u[1] as number, u[2] as number);
  u = u.map((c) => c / uLen);
  const v = [
    n[1] * (u[2] as number) - n[2] * (u[1] as number),
    n[2] * (u[0] as number) - n[0] * (u[2] as number),
    n[0] * (u[1] as number) - n[1] * (u[0] as number),
  ];
  for (const fraction of RING_FRACTIONS) {
    const r = fraction * size;
    for (let k = 0; k < RING_POINTS; k += 1) {
      const a = (2 * Math.PI * k) / RING_POINTS;
      const cu = r * Math.cos(a);
      const cv = r * Math.sin(a);
      out.push(
        occtToScene({
          x: subject.point.x + cu * (u[0] as number) + cv * (v[0] as number),
          y: subject.point.y + cu * (u[1] as number) + cv * (v[1] as number),
          z: subject.point.z + cu * (u[2] as number) + cv * (v[2] as number),
        }),
      );
    }
  }
  return out;
}

// Scratch, module-level and reused: the pass must not allocate.
const probeRaycaster = new Raycaster();
const probeNdc = new Vector2();
const probeWorld = new Vector3();
const probeProjected = new Vector3();
const probeHits: Intersection[] = [];

function samePlacement(
  a: readonly SurfaceMarkSeat[],
  b: readonly SurfaceMarkSeat[],
): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    const x = a[i] as SurfaceMarkSeat;
    const y = b[i] as SurfaceMarkSeat;
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

/**
 * Where each face mark stands, recomputed when the camera, the gauges, the
 * oracle or the offer changes.
 *
 * With no surface yet (`meshRef.current === null`) every mark stays at its
 * centroid and live, which is the behaviour that predates this module: a mark
 * is live until the scene has told us otherwise, never the reverse. Guessing
 * "buried" from a missing oracle would silently disarm a whole overlay.
 */
export function useSurfaceMarkBurial(
  subjects: readonly SurfaceMarkSubject[],
  meshRef: { current: Mesh | null },
  ordinalAt: (faceIndex: number | null | undefined) => number | null,
): SurfaceMarkSeat[] {
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);
  const canvas = useThree((s) => s.gl.domElement);

  const candidates = useMemo(
    () => subjects.map(faceSeatCandidates),
    [subjects],
  );
  const fallback = useMemo<SurfaceMarkSeat[]>(
    () =>
      candidates.map((points) => ({
        position: points[0] as [number, number, number],
        buried: false,
      })),
    [candidates],
  );
  const [seats, setSeats] = useState<SurfaceMarkSeat[]>(fallback);
  const published = useRef<SurfaceMarkSeat[]>(fallback);
  const working = useRef<SurfaceMarkSeat[]>(fallback);
  /** The input `working` was built for — see the reset in the frame. */
  const workingFor = useRef<readonly unknown[] | null>(null);
  /** The seats React last COMMITTED — see `SEAT_CONFIRM_FRAMES`. */
  const committed = useRef<readonly SurfaceMarkSeat[]>(fallback);
  /** Frames since `committed` caught up with `published`. */
  const confirmed = useRef(0);
  useLayoutEffect(() => {
    committed.current = seats;
  }, [seats]);
  const cameraStamp = useRef("");
  /** Subjects still owed an answer for the current camera. */
  const owed = useRef(0);
  /**
   * THE ORACLE ITSELF IS AN INPUT, so a new one owes every mark a fresh answer.
   * Without this the pass could converge on a frame where the body mesh had
   * not mounted yet and then never revisit it — an answer not wrong so much as
   * never asked.
   */
  const oracle = useRef<Mesh | null>(null);
  /** Round-robin cursor, deliberately NOT reset when the camera moves. */
  const cursor = useRef(0);
  /**
   * Did the previous invocation of the frame callback ask for THIS frame? Only
   * then is `delta` a frame duration rather than an idle span — see
   * `frameDelta.ts`, and `seatSliceMs`, which is what reads it.
   */
  const requestedThisFrame = useRef(false);
  /** The gauges on screen — shared implementation with the edge pass. */
  const keepOuts = useMemo(() => new GaugeKeepOuts(), []);

  const stampSeats = (state: "pending" | "settled") => {
    const node = canvas.closest<HTMLElement>('[data-testid="viewport"]');
    if (node !== null && node.dataset["faceMarkSeats"] !== state) {
      node.dataset["faceMarkSeats"] = state;
    }
  };

  useEffect(() => {
    const node = canvas.closest<HTMLElement>('[data-testid="viewport"]');
    return () => {
      if (node !== null) delete node.dataset["faceMarkSeats"];
    };
  }, [canvas]);

  useFrame((_state, delta) => {
    const continuing = requestedThisFrame.current;
    requestedThisFrame.current = false;
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
    if (workingFor.current !== subjects) {
      workingFor.current = subjects;
      working.current = fallback.slice();
      cursor.current = 0;
      cameraStamp.current = "";
    }

    const mesh = meshRef.current;
    if (mesh !== oracle.current) {
      oracle.current = mesh;
      cameraStamp.current = "";
    }
    // A gauge arrived, left or moved: every seat is owed a fresh answer.
    // Read AFTER this frame (see `refreshAfterFrame`): a grip is positioned
    // by its own frame callback, which may run after this one.
    keepOuts.refreshAfterFrame(() => {
      cameraStamp.current = "";
      invalidate();
    });

    const stamp = camera.matrixWorld.elements
      .map((value) => value.toFixed(3))
      .join(",");
    if (stamp !== cameraStamp.current) {
      cameraStamp.current = stamp;
      owed.current = subjects.length;
      confirmed.current = 0;
      stampSeats("pending");
    }
    if (owed.current === 0 || subjects.length === 0) {
      // Settled only once the published seats are what is ON SCREEN.
      if (
        committed.current !== published.current ||
        confirmed.current < SEAT_CONFIRM_FRAMES
      ) {
        confirmed.current =
          committed.current === published.current ? confirmed.current + 1 : 0;
        stampSeats("pending");
        requestedThisFrame.current = true;
        invalidate();
        return;
      }
      stampSeats("settled");
      return;
    }

    if (mesh === null) {
      // No oracle yet. Keep every mark live at its centroid, but do NOT clear
      // the debt — the ref-change check above arms the pass when the mesh
      // commits. And no `invalidate()`: with nothing to compute, asking for a
      // frame per frame would spin the loop on a part that never loads.
      if (!samePlacement(published.current, fallback)) {
        published.current = fallback;
        setSeats(fallback);
      }
      return;
    }

    /** Does the pick surface answer `ordinal` at this scene point? */
    const answers = (point: readonly number[], ordinal: number): boolean => {
      probeWorld.set(point[0] ?? 0, point[1] ?? 0, point[2] ?? 0);
      probeProjected.copy(probeWorld).project(camera);
      probeNdc.set(probeProjected.x, probeProjected.y);
      probeRaycaster.setFromCamera(probeNdc, camera);
      probeHits.length = 0;
      probeRaycaster.intersectObject(mesh, false, probeHits);
      const nearest = probeHits[0];
      return nearest !== undefined && ordinalAt(nearest.faceIndex) === ordinal;
    };

    let spent = 0;
    const deadline = performance.now() + seatSliceMs(delta, continuing);
    while (
      owed.current > 0 &&
      (spent < SURFACE_SEAT_FRAME_BUDGET || performance.now() < deadline)
    ) {
      const i = cursor.current % subjects.length;
      cursor.current = (cursor.current + 1) % subjects.length;
      owed.current -= 1;
      const subject = subjects[i] as SurfaceMarkSubject;
      const points = candidates[i] as [number, number, number][];
      let seat: SurfaceMarkSeat | null = null;
      for (let c = 0; c < points.length; c += 1) {
        const point = points[c] as [number, number, number];
        // The cheap screen test first: a seat under a gauge is refused before
        // it costs a raycast.
        if (!keepOuts.clear(point, camera, canvas)) continue;
        spent += 1;
        if (answers(point, subject.ordinal)) {
          seat = { position: point, buried: false };
          break;
        }
      }
      working.current[i] = seat ?? {
        position: points[0] as [number, number, number],
        buried: true,
      };
    }

    if (!samePlacement(published.current, working.current)) {
      published.current = working.current.slice();
      confirmed.current = 0;
      setSeats(published.current);
    }
    // Ask for one more frame: the budget carries work across frames and
    // `frameloop="demand"` will not schedule the finishing one otherwise. The
    // loop converges because the guard above returns once nothing is owed.
    requestedThisFrame.current = true;
    invalidate();
  });

  return seats.length === subjects.length ? seats : fallback;
}
