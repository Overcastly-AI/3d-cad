/**
 * WHERE A GAUGE STANDS ON A PICKED FACE OR PLANE, AND WHAT ITS PREVIEW DRAWS
 * (CRAFT-9b — shell thickness + datum offset).
 *
 * The same seam every other viewport manipulator makes (`extrudeHandle.ts` ↔
 * `ExtrudeDragHandle.tsx`, `extrudeGhost.ts` ↔ `ExtrudePreview.tsx`): the
 * arithmetic here, the meshes and the pointer in the `.tsx` beside it. A
 * decision buried in a `useMemo` inside a WebGL-only component is invisible
 * below a full browser run, and this module holds two decisions that are worth
 * a unit test each — where the instrument is seated, and what the preview it
 * drags is a picture OF.
 *
 * ## THE CONSTRAINT THIS MODULE EXISTS TO SATISFY (direction §8.4)
 *
 * *"A gauge whose drag changes a number and not the model is worse than the
 * form it replaces — it promises direct manipulation and delivers a slider."*
 * Both verbs here ship **route (b), a geometric line-work preview**: the shell
 * draws the INNER OFFSET OUTLINE of the picked face (the rim of the cavity the
 * thickness leaves), and the datum draws the OFFSET PLANE at the current
 * distance. Neither needs a kernel round-trip, both are idiom D line-work, and
 * both answer the only question the drag actually poses — *how big is that?*
 *
 * The shell preview is the stronger of the two because it is the SAME
 * measurement the arrow carries, drawn a second way: every point of the inner
 * outline is exactly `thickness` from the rim, so the outline is the locus of
 * the arrowhead swept around the boundary. When the two disagree, one of them
 * is wrong — which is a property a decorative preview cannot have.
 *
 * ## FRAME
 *
 * Everything returned by this module is SCENE space (three.js, Y-up). The
 * overlay and the face signatures arrive in OCCT world mm (Z-up) and are
 * rotated at the boundary, exactly as `FacePatch` and `MeasureOverlay` do. A
 * kernel-frame seat would stand the instrument ninety degrees off the body it
 * is measuring, which is FB-9 wearing a third hat.
 *
 * ## THE ANCHOR IS A VALUE, NEVER A STORE READ
 *
 * Nothing in this file (or in `ShellGauge` / `DatumGauge`) reaches into a pick
 * store. The caller resolves the anchor and passes it down. That is deliberate
 * and it is cheap now: W4's CRAFT-12 replaces today's per-editor pick state
 * with a persistent selection store, and a component that takes its anchor as a
 * prop is re-wired by that change rather than rewritten by it.
 */
import {
  addScaled,
  dot,
  type GaugeSeat,
  negate,
  sub,
  type Vec3,
} from "@loft/design";

import type { PlanarFaceSignature } from "../api/parts";
import type { OverlayResult, Vec3 as ApiVec3 } from "../api/measure";
import { occtToScene } from "../measure/geometry";
import {
  faceBasis,
  sceneOriginBasis,
  type DatumPlaneName,
  type PlaneBasis,
} from "../sketch/plane";

// --- Tuple arithmetic --------------------------------------------------------
// Still tuple-based, still no `Vector3`: these run inside `useMemo`s the drag
// re-enters and `Vector3` is mutable and allocating, so the r3f shell converts
// at its own boundary. They are no longer LOCAL — `sub`, `dot`, `negate` and
// `addScaled` are `@loft/design`'s `vec3`, one copy for the four modules that
// had grown one each (board #63). This file's `negate`, including the `+ 0`
// that normalises `-0`, is the version that was promoted; nothing it does here
// changed.

/**
 * How far off a plane a point may sit and still count as ON it, scene mm.
 *
 * The overlay's polylines are exact B-rep vertices (not tessellated points), so
 * a face's own edges land on its plane to float precision; this bound is for
 * accumulated float error, not for geometric slop. Deliberately far tighter
 * than the kernel's subshape tolerance: a loose bound here would sweep in an
 * edge from a face a hair out of plane and close a loop that is not a boundary.
 */
const PLANE_TOL_MM = 1e-4;

/** How close two loop endpoints must be to be the same vertex, scene mm. */
const JOIN_TOL_MM = 1e-4;

/**
 * Longest a mitred corner may run, as a multiple of the inset.
 *
 * A square corner mitres to 1.41x the inset; a sliver corner tends to infinity,
 * and an unbounded mitre draws a spike across the part. Past the limit the
 * corner falls back to the plain edge-normal offset — a bevel — which is the
 * drafting answer and what every offset tool does.
 */
const MITRE_LIMIT = 4;

/** Smallest seat radius, scene mm — a hairline face still gets a grabbable arrow. */
const MIN_SEAT_RADIUS_MM = 0.5;

/**
 * Half-extent of the drawn datum sheet for a plane with NO geometry of its own
 * (an origin datum, or a chain off one), scene mm.
 *
 * The sketcher draws its datum plane sheet 90 mm square, so a preview of the
 * SAME plane at another size would read as a different object. DRY NOTE: that
 * constant (`SketchScene`'s `PLANE_SIZE_MM`) is module-private and `SketchScene`
 * is not this item's territory, so the number is stated here rather than
 * forked silently — unifying the two means moving one value into
 * `packages/design`, which is CRAFT-8's file for this wave. Flagged, not
 * worked around.
 *
 * A plane seated on a FACE does not use it: that plane has a size, and the
 * sheet takes it ({@link datumAnchor} puts it in the seat radius, which
 * {@link datumOutline} draws from). A 90 mm sheet hung off a 40 mm face reads
 * as a sheet the part is sitting on rather than a plane about the face.
 */
export const DATUM_SHEET_HALF_MM = 45;

/** The shortest shell wall the gauge will pull to, mm. */
export const MIN_THICKNESS_MM = 0.1;

/** Absolute ceiling, mm — past anything this kernel is for (extrude's own). */
export const MAX_THICKNESS_MM = 10_000;

/** The shortest datum offset a DRAG will produce, mm. See {@link datumAnchor}. */
export const MIN_OFFSET_MM = 0.1;

/** Absolute ceiling for a datum offset, mm. */
export const MAX_OFFSET_MM = 10_000;

// --- The shell anchor --------------------------------------------------------

/** Where the shell gauge stands, and the rim its preview insets. */
export interface ShellAnchor {
  /** Seat for the gauge: the face centroid, running INTO the body. */
  seat: GaugeSeat;
  /**
   * The picked face's outer boundary in scene mm, open (no repeated first
   * point). Empty when the boundary could not be recovered from the overlay —
   * the gauge still mounts, the preview simply has nothing to draw, which is
   * honest and is the one case this module refuses to guess about.
   */
  loop: readonly Vec3[];
  /** Plane origin the loop is measured from (the face's area centroid). */
  origin: Vec3;
  /** In-plane axes — the frame the inset arithmetic runs in. */
  u: Vec3;
  v: Vec3;
}

/**
 * The seat and rim for a shell thickness gauge, or null when no face is picked.
 *
 * The seat is **the last picked face's centroid, running along the INWARD
 * normal** — the face the modeller just addressed is where their eye is, and
 * into the material is the direction a thickness grows. That is the direction
 * pass's anchor rule (§9: *"9b on the picked face's centroid along its
 * normal"*) with the sign chosen by what the number means.
 *
 * ONE OBSERVATION FOR THE NEXT DIRECTION PASS, recorded rather than acted on:
 * on a face that the shell leaves OPEN there is no wall along that normal — the
 * wall is at the RIM, measured in-plane, which is precisely where the preview
 * draws it. Seating the arrow on the rim rather than the centroid would make
 * the arrow and the outline the same drawing. The centroid seat is shipped
 * because the direction doc names it twice and this file is one of four
 * integrating into the same wave; the rim seat is a direction decision, not a
 * builder's.
 */
export function shellAnchor(
  overlay: OverlayResult | null,
  picked: readonly PlanarFaceSignature[],
): ShellAnchor | null {
  const face = picked[picked.length - 1];
  if (face === undefined) return null;
  const basis = faceBasis(face, 0);
  const origin = basis.origin as Vec3;
  const u = basis.u as Vec3;
  const v = basis.v as Vec3;
  const normal = basis.normal as Vec3;
  // Area-equivalent radius, the same reading `FacePatch` gives a face. The
  // OUTER area when the signature carries it: an area eaten by drilled holes
  // would shrink the instrument for a reason that has nothing to do with the
  // face's size.
  const area = Math.max(face.outer_area_mm2 ?? face.area_mm2, 0);
  const radius = Math.max(Math.sqrt(area / Math.PI), MIN_SEAT_RADIUS_MM);
  return {
    seat: { base: origin, dir: negate(normal), radius, arms: [u, v] },
    loop: overlay === null ? [] : faceLoop(overlay, origin, normal),
    origin,
    u,
    v,
  };
}

/**
 * The picked face's outer boundary, recovered from the overlay's edges.
 *
 * The overlay publishes faces and edges as two flat lists with no adjacency
 * between them, so the boundary is found GEOMETRICALLY: every edge whose whole
 * polyline lies in the face's plane is a candidate, the candidates are chained
 * into closed loops, and the loop enclosing the most area is the outer wire.
 * (A face with holes yields its hole loops too; they are smaller by
 * construction. A second, coplanar face elsewhere on the body yields its own
 * loop, and the nearest-centroid tie-break below keeps the one we are standing
 * on.)
 *
 * Returns an empty list rather than a guess when nothing closes.
 */
export function faceLoop(
  overlay: OverlayResult,
  origin: Vec3,
  normal: Vec3,
): readonly Vec3[] {
  const inPlane: Vec3[][] = [];
  for (const edge of overlay.edges) {
    const points = (edge.polyline as readonly ApiVec3[]).map(
      (p) => occtToScene(p) as Vec3,
    );
    if (points.length < 2) continue;
    if (
      points.every((p) => Math.abs(dot(sub(p, origin), normal)) <= PLANE_TOL_MM)
    ) {
      inPlane.push(points);
    }
  }
  const loops = chainLoops(inPlane);
  if (loops.length === 0) return [];
  // The outer wire is the one with the most enclosed area; among equals (a
  // symmetric part's coplanar twin) the one we are standing on is nearest.
  let best = loops[0] as Vec3[];
  let bestScore = -Infinity;
  for (const loop of loops) {
    const centre = centroidOf(loop);
    const score =
      loopArea(loop, origin, normal) -
      Math.hypot(...sub(centre, origin)) * PLANE_TOL_MM;
    if (score > bestScore) {
      bestScore = score;
      best = loop;
    }
  }
  return best;
}

/** Mean of a point list — the loop's crude centre, for the coplanar tie-break. */
function centroidOf(loop: readonly Vec3[]): Vec3 {
  let x = 0;
  let y = 0;
  let z = 0;
  for (const p of loop) {
    x += p[0];
    y += p[1];
    z += p[2];
  }
  const n = Math.max(loop.length, 1);
  return [x / n, y / n, z / n];
}

/** Absolute area a closed 3D loop encloses in its own plane, scene mm². */
function loopArea(loop: readonly Vec3[], origin: Vec3, normal: Vec3): number {
  // The projected cross-product sum — Stokes on a planar polygon, which needs
  // no in-plane basis and therefore cannot disagree with one.
  let sx = 0;
  let sy = 0;
  let sz = 0;
  for (let i = 0; i < loop.length; i += 1) {
    const a = sub(loop[i] as Vec3, origin);
    const b = sub(loop[(i + 1) % loop.length] as Vec3, origin);
    sx += a[1] * b[2] - a[2] * b[1];
    sy += a[2] * b[0] - a[0] * b[2];
    sz += a[0] * b[1] - a[1] * b[0];
  }
  return Math.abs(dot([sx / 2, sy / 2, sz / 2], normal));
}

/** Round a point to the join tolerance, as a map key. */
function joinKey(p: Vec3): string {
  const q = (n: number) => Math.round(n / JOIN_TOL_MM);
  return `${q(p[0])},${q(p[1])},${q(p[2])}`;
}

function samePoint(a: Vec3, b: Vec3): boolean {
  return (
    Math.abs(a[0] - b[0]) <= JOIN_TOL_MM &&
    Math.abs(a[1] - b[1]) <= JOIN_TOL_MM &&
    Math.abs(a[2] - b[2]) <= JOIN_TOL_MM
  );
}

/**
 * Chain polylines end-to-end into CLOSED loops, dropping anything that does not
 * close. Open chains are dropped deliberately: an open chain is either a
 * boundary we have failed to complete or an edge that merely happens to lie in
 * the plane, and insetting either one draws a line that means nothing.
 */
export function chainLoops(polylines: readonly (readonly Vec3[])[]): Vec3[][] {
  const used = new Array<boolean>(polylines.length).fill(false);
  // Endpoint index: both ends of every polyline, so a join is a map lookup
  // rather than a scan — a shelled plate's overlay carries hundreds of edges.
  const ends = new Map<string, number[]>();
  const push = (key: string, i: number) => {
    const at = ends.get(key);
    if (at === undefined) ends.set(key, [i]);
    else at.push(i);
  };
  polylines.forEach((line, i) => {
    push(joinKey(line[0] as Vec3), i);
    push(joinKey(line[line.length - 1] as Vec3), i);
  });

  const loops: Vec3[][] = [];
  for (let start = 0; start < polylines.length; start += 1) {
    if (used[start]) continue;
    used[start] = true;
    const chain: Vec3[] = [...(polylines[start] as readonly Vec3[])];
    const first = chain[0] as Vec3;
    let closed = false;
    for (;;) {
      const tail = chain[chain.length - 1] as Vec3;
      if (chain.length > 2 && samePoint(tail, first)) {
        chain.pop(); // the loop is stored OPEN — the closing edge is implicit
        closed = true;
        break;
      }
      const candidates = ends.get(joinKey(tail)) ?? [];
      const next = candidates.find((i) => !used[i]);
      if (next === undefined) break;
      used[next] = true;
      const line = polylines[next] as readonly Vec3[];
      const forward = samePoint(line[0] as Vec3, tail);
      const ordered = forward ? line.slice(1) : line.slice(0, -1).reverse();
      for (const p of ordered) chain.push(p);
    }
    if (closed && chain.length >= 3) loops.push(chain);
  }
  return loops;
}

// --- The inner offset outline (the shell's preview) --------------------------

/**
 * The picked face's boundary contracted by `inset`, as segment endpoint pairs
 * ready for a line layer — **the shell's route-(b) preview**.
 *
 * Every vertex is mitred, so the drawn outline is a true parallel curve of the
 * rim rather than a scaled copy of it: on a 60 x 30 rectangle a 5 mm wall gives
 * 50 x 20, which is the answer, where a uniform scale would give 55 x 27.5,
 * which looks plausible and is a lie.
 *
 * Returns an empty buffer when the wall has eaten the face — the offset polygon
 * reverses its winding, which is the standard collapse test. Drawing the
 * self-intersected result instead would paint a bow-tie across the part and
 * claim it was a cavity.
 */
export function insetOutline(anchor: ShellAnchor, inset: number): Float32Array {
  const { loop, origin, u, v } = anchor;
  if (loop.length < 3 || !(inset > 0)) return new Float32Array(0);
  const flat = loop.map((p): [number, number] => {
    const d = sub(p, origin);
    return [dot(d, u), dot(d, v)];
  });
  const inner = insetPolygon(flat, inset);
  if (inner === null) return new Float32Array(0);
  const out = new Float32Array(inner.length * 6);
  for (let i = 0; i < inner.length; i += 1) {
    const a = inner[i] as [number, number];
    const b = inner[(i + 1) % inner.length] as [number, number];
    const pa = addScaled(addScaled(origin, u, a[0]), v, a[1]);
    const pb = addScaled(addScaled(origin, u, b[0]), v, b[1]);
    out.set(pa, i * 6);
    out.set(pb, i * 6 + 3);
  }
  return out;
}

/** Signed area of a 2D polygon — positive when the winding is counterclockwise. */
export function signedArea(
  points: readonly (readonly [number, number])[],
): number {
  let total = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i] as readonly [number, number];
    const b = points[(i + 1) % points.length] as readonly [number, number];
    total += a[0] * b[1] - b[0] * a[1];
  }
  return total / 2;
}

/**
 * Contract a simple 2D polygon by `inset`, mitred at every vertex, or null when
 * the contraction collapses it.
 *
 * Exported for its own unit cases: the arithmetic is four lines and the
 * failure modes (a reversed winding, a spike at a sliver corner) are exactly
 * the kind that draw beautifully and mean nothing.
 */
export function insetPolygon(
  points: readonly (readonly [number, number])[],
  inset: number,
): [number, number][] | null {
  const n = points.length;
  if (n < 3 || !(inset > 0)) return null;
  const area = signedArea(points);
  if (area === 0) return null;
  // Interior is to the LEFT of each directed edge on a counterclockwise loop.
  const side = area > 0 ? 1 : -1;
  const dirs: [number, number][] = [];
  const normals: [number, number][] = [];
  for (let i = 0; i < n; i += 1) {
    const a = points[i] as readonly [number, number];
    const b = points[(i + 1) % n] as readonly [number, number];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len === 0) return null; // a repeated vertex has no direction to offset
    dirs.push([dx / len, dy / len]);
    normals.push([(-dy / len) * side, (dx / len) * side]);
  }
  const out: [number, number][] = [];
  for (let i = 0; i < n; i += 1) {
    const p = points[i] as readonly [number, number];
    const prev = (i + n - 1) % n;
    const na = normals[prev] as [number, number];
    const nb = normals[i] as [number, number];
    const da = dirs[prev] as [number, number];
    const db = dirs[i] as [number, number];
    const cross = da[0] * db[1] - da[1] * db[0];
    let x = p[0] + nb[0] * inset;
    let y = p[1] + nb[1] * inset;
    if (Math.abs(cross) > 1e-9) {
      // Intersect the two offset lines: P1 + k·da = P2 + m·db.
      const p1x = p[0] + na[0] * inset;
      const p1y = p[1] + na[1] * inset;
      const p2x = x;
      const p2y = y;
      const k = ((p2x - p1x) * db[1] - (p2y - p1y) * db[0]) / cross;
      const mx = p1x + da[0] * k;
      const my = p1y + da[1] * k;
      // A sliver corner mitres to a spike; bevel it instead of drawing a spear
      // through the part.
      if (Math.hypot(mx - p[0], my - p[1]) <= MITRE_LIMIT * inset) {
        x = mx;
        y = my;
      }
    }
    out.push([x, y]);
  }
  // THE COLLAPSE TEST — per EDGE, not on the total area, and the difference is
  // a defect this file shipped for an afternoon. A contraction past the medial
  // axis turns the polygon inside out, and the obvious test is "did the winding
  // reverse". It does not, reliably: on a 60 x 30 rim inset by 40 BOTH
  // dimensions invert (-20 x -50), the two sign flips cancel, and the
  // bow-tie comes back with a POSITIVE area of 1000 — a crisp, closed, utterly
  // wrong outline that the area test waves through. An offset is valid exactly
  // when every edge still runs the way it ran before, so that is what is asked.
  for (let i = 0; i < n; i += 1) {
    const a = out[i] as [number, number];
    const b = out[(i + 1) % n] as [number, number];
    const d = dirs[i] as [number, number];
    if ((b[0] - a[0]) * d[0] + (b[1] - a[1]) * d[1] <= 0) return null;
  }
  if (signedArea(out) === 0) return null;
  return out;
}

// --- The datum anchor --------------------------------------------------------

/**
 * Which plane a datum is offset FROM, as the editor knows it.
 *
 * The editor owns the form; the page owns the datum-resolution table; the gauge
 * owns nothing. This is the value that crosses between them — deliberately the
 * question ("offset from what?") rather than an answer, so the page resolves it
 * with the same walk it already uses for every other datum on screen.
 */
export type DatumGaugeSeed =
  | { plane: "origin"; base: DatumPlaneName; offsetMm: number }
  | { plane: "datum"; baseFeatureId: string; offsetMm: number }
  | { plane: "face"; signature: PlanarFaceSignature; offsetMm: number };

/** Where the datum gauge stands, and which way its plane has gone. */
export interface DatumAnchor {
  /** Seat: the BASE plane's origin, running toward the side the datum is on. */
  seat: GaugeSeat;
  /**
   * `+1` or `-1` — which side of the base plane the offset puts the datum.
   *
   * The gauge drives a MAGNITUDE along {@link seat}'s direction and this sign
   * puts it back, which is how a drafting dimension has always worked: the
   * number is a distance and the arrow carries the direction. The alternative
   * — a signed track — degrades visibly at the crossing, because `linearTrack`
   * draws no arrowhead and `ladderStops` refuses a ladder for a negative span,
   * so the instrument would lose its point and its scale exactly when the user
   * is looking hardest at it.
   */
  sign: 1 | -1;
  /** In-plane axes of the base plane — the frame the drawn sheet is squared to. */
  u: Vec3;
  v: Vec3;
}

/**
 * Seat a datum offset gauge on its base plane, or null when the base cannot be
 * resolved (a chained datum whose parent is an `on_face` plane, or one rolled
 * back out of the tree).
 *
 * The offset always runs along the base plane's own normal — `flip` reverses
 * the RESULTING plane's normal, not the direction the offset is measured in
 * (`offsetBasis`/`offsetFromBasis`), so the gauge must not read it.
 *
 * @param resolveDatum The page's datum table: feature id → its scene basis.
 */
export function datumAnchor(
  seed: DatumGaugeSeed | null,
  resolveDatum: (featureId: string) => PlaneBasis | null,
): DatumAnchor | null {
  if (seed === null) return null;
  let basis: PlaneBasis | null;
  let radius = DATUM_SHEET_HALF_MM;
  switch (seed.plane) {
    case "origin":
      basis = sceneOriginBasis(seed.base);
      break;
    case "datum":
      basis =
        seed.baseFeatureId === "" ? null : resolveDatum(seed.baseFeatureId);
      break;
    case "face": {
      basis = faceBasis(seed.signature, 0);
      const area = Math.max(
        seed.signature.outer_area_mm2 ?? seed.signature.area_mm2,
        0,
      );
      radius = Math.max(Math.sqrt(area / Math.PI), MIN_SEAT_RADIUS_MM);
      break;
    }
  }
  if (basis === null) return null;
  const sign = seed.offsetMm < 0 ? -1 : 1;
  const normal = basis.normal as Vec3;
  return {
    seat: {
      base: basis.origin as Vec3,
      dir: sign < 0 ? negate(normal) : normal,
      radius,
      arms: [basis.u as Vec3, basis.v as Vec3],
    },
    sign,
    u: basis.u as Vec3,
    v: basis.v as Vec3,
  };
}

/**
 * The datum plane drawn where the offset puts it — **the datum's route-(b)
 * preview**: a square sheet outline in the base plane's own axes, at the
 * current distance along the normal.
 *
 * An outline and not a filled sheet, deliberately: the committed datum planes
 * the sketcher draws ARE filled quads, and a preview that looked like one would
 * say "this exists" about a plane that has not been saved. Line-work says
 * "about to be", which is what every other preview in this app says.
 */
export function datumOutline(
  anchor: DatumAnchor,
  offsetMm: number,
  /**
   * Half-side of the drawn square, scene mm. Defaults to the SEAT's own scale,
   * which is the face's equivalent radius for an on-face datum and
   * {@link DATUM_SHEET_HALF_MM} for a plane that has no geometry to take a size
   * from — one rule, sized by what the plane is about.
   */
  half = anchor.seat.radius,
): Float32Array {
  const { seat, u, v } = anchor;
  // `seat.dir` already carries the sign, so the magnitude walks it.
  const centre = addScaled(seat.base, seat.dir, Math.abs(offsetMm));
  const corners: Vec3[] = [
    addScaled(addScaled(centre, u, -half), v, -half),
    addScaled(addScaled(centre, u, half), v, -half),
    addScaled(addScaled(centre, u, half), v, half),
    addScaled(addScaled(centre, u, -half), v, half),
  ];
  const out = new Float32Array(corners.length * 6);
  for (let i = 0; i < corners.length; i += 1) {
    out.set(corners[i] as Vec3, i * 6);
    out.set(corners[(i + 1) % corners.length] as Vec3, i * 6 + 3);
  }
  return out;
}

/**
 * Total drawn length of a segment-pair buffer, scene mm — the SHELL preview's
 * QA stamp.
 *
 * Derived from THE BUFFER THAT IS DRAWN, never from the value that produced it,
 * and that is the whole reason it exists: a stamp of the input reports a
 * preview which never redrew as working perfectly, which is the "gate measuring
 * the wrong input" trap this repo keeps paying for. The inner outline's
 * perimeter falls monotonically as the wall thickens, so one number witnesses
 * both that the preview exists and that it followed.
 *
 * It is the WRONG stamp for the datum preview, which translates rigidly: a
 * square's perimeter is invariant under translation, so this would report a
 * frozen plane as a moving one. That is {@link drawnAdvance}'s job, and the two
 * being different functions is the point rather than an inconvenience.
 */
export function drawnLength(positions: Float32Array): number {
  let total = 0;
  for (let i = 0; i + 5 < positions.length; i += 6) {
    total += Math.hypot(
      (positions[i + 3] as number) - (positions[i] as number),
      (positions[i + 4] as number) - (positions[i + 1] as number),
      (positions[i + 5] as number) - (positions[i + 2] as number),
    );
  }
  return total;
}

/**
 * Mean distance of a drawn buffer from `base` along `dir`, scene mm — the DATUM
 * preview's QA stamp, and the distance the drawn sheet actually stands at.
 *
 * Same discipline as {@link drawnLength}: it reads the vertices handed to the
 * renderer, so it cannot agree with an offset the picture never took.
 */
export function drawnAdvance(
  positions: Float32Array,
  base: Vec3,
  dir: Vec3,
): number {
  if (positions.length === 0) return 0;
  let total = 0;
  let count = 0;
  for (let i = 0; i + 2 < positions.length; i += 3) {
    const p: Vec3 = [
      positions[i] as number,
      positions[i + 1] as number,
      positions[i + 2] as number,
    ];
    total += dot(sub(p, base), dir);
    count += 1;
  }
  return total / count;
}
