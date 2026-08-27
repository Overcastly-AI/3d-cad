/**
 * THE PICK RAYCAST — report the nearest DRAWN triangle, not the nearest
 * triangle.
 *
 * SEL-6. A hidden body in front of a drawn one used to eat the pick for the
 * body behind it: with the wall of `seedOccludedEdgePlate` switched off, only
 * **8.5 %** of the plate's lit pixels could still address a face (27 of 317,
 * against 98.0 % with both bodies drawn) — below the >= 50 % floor SEL-4 itself
 * establishes. The 27 survivors were exactly the plate's overhangs outside the
 * hidden wall's span.
 *
 * ## Why the refusal could not live in the handler
 *
 * Read in the vendored source rather than inferred, because the comments this
 * replaces got the REASON wrong while getting the conclusion right. In
 * `three@0.185.1`, `Mesh.js`'s `checkIntersection()` consults only
 * `material.side`; it never looks at `material.visible`. So a hidden body —
 * which we express as a draw group whose material is `visible: false` — is
 * raycast exactly like a drawn one, and that is true whether the mesh takes a
 * SINGLE material or a material ARRAY. (The array branch of
 * `_computeIntersections` does fetch `material[group.materialIndex]`, but only
 * to hand it to the same `side` check.)
 *
 * Then `@react-three/fiber@9.6.1` dedupes intersections per object —
 * `makeId` is `uuid + '/' + index + instanceId`, and `Mesh.raycast` sets
 * `faceIndex` but never `index` — so a fused pick mesh contributes exactly ONE
 * hit to the event: the nearest triangle, hidden or not. A guard in the handler
 * can therefore only REFUSE that hit; there is no second hit for it to fall
 * back to, so it can never see PAST the hidden body. The filter has to run
 * inside `raycast`, before r3f dedupes — which is what this module is.
 *
 * Pure and node-testable on purpose (`.ts`, the `unit` vitest project, same
 * precedent as `edgeBand.ts` and `bodyPartition.ts`): "which triangle does an
 * armed pick address" is precisely the decision a screenshot cannot check, and
 * three's raycaster needs no DOM, so the fix is asserted against REAL three
 * geometry rather than against a mock of it.
 */
import { Mesh } from "three";
import type { BufferGeometry, Intersection, Raycaster } from "three";

import { faceOrdinalOfTriangle } from "./glbGeometry";

/**
 * Is the triangle a hit struck part of a body that is NOT drawn?
 *
 * Takes the raw `faceIndex` an intersection carries rather than a resolved
 * ordinal, so the whole triangle → body decision stays in one place.
 */
export type HiddenTriangleTest = (
  faceIndex: number | null | undefined,
) => boolean;

/** Nothing is hidden — a stable identity, so "one visible body" costs nothing. */
const NOTHING_HIDDEN: HiddenTriangleTest = () => false;

/**
 * The hidden-triangle test for one pick mesh and one set of hidden B-rep face
 * ordinals.
 *
 * A triangle with NO ordinal is KEPT. "No ordinal" is not "no material": a mesh
 * carrying no B-rep partition is still solid, it just cannot say which face it
 * is — the invariant `edgeBand.test.ts` pins as "still occludes when the
 * surface has no B-rep partition at all". Dropping those would turn this filter
 * into "discard everything unresolvable", which is a different and much worse
 * bug than the one it fixes.
 */
export function hiddenTriangleTest(
  geometry: BufferGeometry | null,
  hidden: ReadonlySet<number>,
): HiddenTriangleTest {
  if (geometry === null || hidden.size === 0) return NOTHING_HIDDEN;
  return (faceIndex) => {
    if (faceIndex === undefined || faceIndex === null) return false;
    const ordinal = faceOrdinalOfTriangle(geometry, faceIndex);
    return ordinal !== null && hidden.has(ordinal);
  };
}

/** As much of an `Intersection` as the nearest-drawn scan reads. */
export interface DepthSortedHit {
  /** Ray origin → hit, in scene mm. */
  distance: number;
  /** The struck triangle, as `Mesh.raycast` reports it. */
  faceIndex?: number | null;
}

/**
 * The nearest hit whose triangle is DRAWN, or null when every hit is hidden.
 *
 * Strict minimum, so the FIRST of equally-near hits wins — three emits
 * triangles in index-buffer order, which makes the tie deterministic and
 * matches what `Raycaster.intersectObject`'s own stable sort would keep.
 */
export function nearestDrawnHit<T extends DepthSortedHit>(
  hits: readonly T[],
  isHidden: HiddenTriangleTest,
): T | null {
  let nearest: T | null = null;
  for (const hit of hits) {
    if (isHidden(hit.faceIndex)) continue;
    if (nearest === null || hit.distance < nearest.distance) nearest = hit;
  }
  return nearest;
}

/**
 * A drop-in `Object3D.raycast` that reports the nearest DRAWN triangle of the
 * mesh instead of the nearest triangle.
 *
 * A `function` expression and not an arrow, deliberately: three calls
 * `object.raycast(raycaster, intersects)`, so `this` IS the binding that says
 * which mesh is being tested.
 *
 * It pushes ONE intersection rather than every surviving one. That is
 * equivalent, not a shortcut — `Raycaster.intersectObject` sorts by distance
 * and r3f then dedupes to the nearest hit per object, so every other survivor
 * would be discarded a moment later. And it is not a new cost: `Mesh.raycast`
 * already allocated one intersection per struck triangle and r3f already sorted
 * them; the only addition here is one scratch array per raycast.
 */
export function drawnSurfaceRaycast(
  isHidden: HiddenTriangleTest,
): (this: Mesh, raycaster: Raycaster, intersects: Intersection[]) => void {
  return function drawnRaycast(
    this: Mesh,
    raycaster: Raycaster,
    intersects: Intersection[],
  ): void {
    const struck: Intersection[] = [];
    Mesh.prototype.raycast.call(this, raycaster, struck);
    const nearest = nearestDrawnHit(struck, isHidden);
    if (nearest !== null) intersects.push(nearest);
  };
}

/**
 * The nearest DRAWN hit per distinct B-rep face, near → far — the whole column
 * of surfaces the ray pierces, not just the first one.
 *
 * MATE-1. `nearestDrawnHit` answers "what is in front", which is the right
 * answer for aiming and the wrong one for a face that is BURIED: a bracket
 * seated on a plate has its bottom face coincident with the plate's top, so
 * whichever way the camera looks, one of the two bodies is between the eye and
 * the face you want. Measured on that fixture — 528 pointer samples over a
 * 1280x800 frame, four cameras — the bracket's bottom face was addressable at
 * ZERO of them. There is no camera to find; the pick has to see through.
 *
 * Two mechanics make the column survive to the handler, and BOTH are needed:
 *
 *  - `Mesh.raycast` reports every struck triangle, but only FRONT faces unless
 *    the material is `DoubleSide` — so the far wall of a body, which is exactly
 *    where a seated part's contact face lives, is not even tested. The pick
 *    mesh draws nothing, so `PickSurface` gives it `DoubleSide` when depth is
 *    asked for; that adds deeper candidates and cannot change the nearest one,
 *    because on a closed body the near wall is always struck first.
 *
 *  - `@react-three/fiber@9.6.1` keys its per-object dedupe on
 *    `uuid + '/' + index + instanceId` (`makeId`), and `Mesh.raycast` never
 *    sets `index` — so ALL of one mesh's hits collapse to one and the handler
 *    can never see past the first. Stamping `index` with the FACE ORDINAL is
 *    what keeps them distinct, and it says something true: for this mesh the
 *    thing being addressed is a B-rep face, not a triangle. The consumer reads
 *    the same field back ({@link mateDepthStack}), so the two cannot drift.
 *
 * One hit per ordinal, not per triangle: a face is one candidate however many
 * triangles the tessellator gave it, and the nearest of them is where the ray
 * enters it.
 */
export function faceColumnRaycast(
  isHidden: HiddenTriangleTest,
  ordinalOf: (faceIndex: number | null | undefined) => number | null,
): (this: Mesh, raycaster: Raycaster, intersects: Intersection[]) => void {
  return function columnRaycast(
    this: Mesh,
    raycaster: Raycaster,
    intersects: Intersection[],
  ): void {
    const struck: Intersection[] = [];
    Mesh.prototype.raycast.call(this, raycaster, struck);
    struck.sort((a, b) => a.distance - b.distance);
    const seen = new Set<number>();
    for (const hit of struck) {
      if (isHidden(hit.faceIndex)) continue;
      const ordinal = ordinalOf(hit.faceIndex);
      if (ordinal === null || seen.has(ordinal)) continue;
      seen.add(ordinal);
      hit.index = ordinal;
      intersects.push(hit);
    }
  };
}
