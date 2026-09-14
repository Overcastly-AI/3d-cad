/**
 * THE SCENE HALF OF THE SOLVE OFFER (FLOW-B1) — project one solved profile to
 * the frame and publish where its note should point.
 *
 * It draws nothing. It exists because the note is DOM in the HUD layer and the
 * camera is in the canvas, and the projection has to happen where the camera
 * is. `useEdgeMarkAnchors` next door has the same shape for the same reason:
 * the DECISION is pure and lives elsewhere ({@link loopAnchor}), what is here
 * is the three.js plumbing and the frame budget.
 *
 * ## What it costs, and why that is the whole design
 *
 * One `Vector3.project` per loop point per frame, and only while the DOM side
 * has asked for a subject — which is the handful of frames between a sketch
 * solving and the user taking or dismissing the offer. Nothing is allocated in
 * the loop: the world points are built once per profile, the scratch vector and
 * the screen-point array are held across frames, and the publish is gated on
 * movement so a still frame costs a projection and no React render at all.
 *
 * ## Why it tracks rather than freezing
 *
 * The hover note deliberately LATCHES its placement (a target that runs from
 * the hand reaching for it is hostile). This one cannot: leaving a sketch flies
 * the camera back to the model pose over several frames, so a point frozen at
 * the instant of the solve would be stale before anyone could read it. A
 * pointer gesture — the only thing that moves the camera afterwards — withdraws
 * the note outright, so the note never moves under a hand that is reaching for
 * it either way.
 */
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Vector3 } from "three";

import { planeToWorld, type Point2D } from "../sketch/plane";
import { signedArea, profileRegions } from "./profileLoops";
import { loopAnchor, useProposalAnchorStore } from "./proposalAnchor";
import type { SolvedSketchLayer } from "./SketchScene";

/** Move this many px before the DOM is told — sub-pixel jitter renders nothing. */
const PUBLISH_EPSILON_PX = 0.5;

/** Scratch, held across frames so the render loop allocates nothing. */
const scratch = new Vector3();

/**
 * The loop a note about this sketch is about: the outer boundary of its LARGEST
 * solid region.
 *
 * Largest by area rather than first in the entity list, because a profile with
 * two islands (a plate and a small tab drawn beside it) reads as one thing with
 * a main body, and the tab is the wrong place to hang the note. Holes are
 * irrelevant here — the centroid of the outer boundary is where a draughtsman
 * would run a leader from, whether or not the plate is bored.
 */
function noteLoop(layer: SolvedSketchLayer): [number, number, number][] | null {
  const regions = profileRegions(layer.entities);
  if (regions.length === 0) return null;
  let best: readonly Point2D[] | null = null;
  let bestArea = -1;
  for (const region of regions) {
    const area = Math.abs(signedArea(region.outer));
    if (area > bestArea) {
      bestArea = area;
      best = region.outer;
    }
  }
  if (best === null) return null;
  return best.map((point) => planeToWorld(layer.basis, point));
}

export interface SolveProposalAnchorProps {
  /** Every solved sketch layer the workspace has, in build order. */
  layers: readonly SolvedSketchLayer[];
}

export function SolveProposalAnchor({ layers }: SolveProposalAnchorProps) {
  const subject = useProposalAnchorStore((state) => state.subject);
  const publishAnchor = useProposalAnchorStore((state) => state.publishAnchor);
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const invalidate = useThree((state) => state.invalidate);

  /**
   * The subject's own loop in world mm, or null when it has none — which is the
   * HARD GATE the direction asks for, arrived at by construction: a sketch that
   * did not solve, whose plane cannot be resolved, or whose entities close no
   * region is simply absent from `layers` or yields no loop, so no anchor is
   * ever published and no chip can be written for it.
   */
  const world = useMemo(() => {
    if (subject === null) return null;
    const layer = layers.find((candidate) => candidate.featureId === subject);
    return layer === undefined ? null : noteLoop(layer);
  }, [layers, subject]);

  /** Screen points, sized to the loop and REUSED — see the module note. */
  const screen = useMemo<Point2D[]>(
    () => (world === null ? [] : world.map(() => ({ x: 0, y: 0 }) as Point2D)),
    [world],
  );
  const frame = useRef({ width: 0, height: 0 });
  const published = useRef<{ x: number; y: number } | null>(null);

  // A new subject (or a new profile) owes one frame: with `frameloop="demand"`
  // nothing else is guaranteed to schedule it, and a note that waits for the
  // user to jiggle the mouse is a note that never arrives.
  useEffect(() => {
    invalidate();
  }, [world, size.width, size.height, invalidate]);

  // Requested and then unmounted (leaving the part, or the scene tearing down)
  // must not leave the DOM holding a point from a workspace that is gone.
  useEffect(
    () => () => {
      published.current = null;
      useProposalAnchorStore.getState().publishAnchor(null);
    },
    [],
  );

  useFrame(() => {
    if (world === null) {
      if (published.current !== null) {
        published.current = null;
        publishAnchor(null);
      }
      return;
    }
    let visible = true;
    for (let i = 0; i < world.length; i += 1) {
      const point = world[i] as [number, number, number];
      scratch.set(point[0], point[1], point[2]).project(camera);
      // Behind the eye (or beyond the far plane) the projection is not a
      // point on this screen at all — it mirrors through the centre. One such
      // vertex makes the whole centroid meaningless, so refuse the lot.
      if (scratch.z < -1 || scratch.z > 1) {
        visible = false;
        break;
      }
      const target = screen[i] as Point2D;
      target.x = ((scratch.x + 1) / 2) * size.width;
      target.y = ((1 - scratch.y) / 2) * size.height;
    }
    frame.current.width = size.width;
    frame.current.height = size.height;
    const next = visible ? loopAnchor(screen, frame.current) : null;
    const last = published.current;
    if (next === null) {
      if (last !== null) {
        published.current = null;
        publishAnchor(null);
      }
      return;
    }
    if (
      last !== null &&
      Math.abs(last.x - next.x) < PUBLISH_EPSILON_PX &&
      Math.abs(last.y - next.y) < PUBLISH_EPSILON_PX
    ) {
      return;
    }
    published.current = next;
    publishAnchor({
      x: next.x,
      y: next.y,
      frame: { width: size.width, height: size.height },
    });
  });

  return null;
}
