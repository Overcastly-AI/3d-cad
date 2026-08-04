/**
 * Entity snapping for the sketcher — pure math, no three.js, no store.
 *
 * POLARITY (UI-W5, founder question "what about snapping to a face or point?
 * With control or command?"). Snapping is ON by default and the modifier
 * SUPPRESSES it — the inverse of the phrasing, deliberately. If you must hold
 * a key to get precision, you only get precision once you already know the
 * feature exists, and a novice never finds it; inverted, precision is the
 * default and you opt OUT for the rare freehand placement. Fusion does the
 * same. So: Ctrl/Cmd held = no snap at all (not even the grid), Shift = axis
 * lock, `G` still toggles the grid alone.
 *
 * HONESTY is the whole point of this module. A snap that silently grabs the
 * wrong thing is worse than no snap, because the sketch is subtly wrong and
 * nothing on screen said so. Every resolution therefore returns the CANDIDATE
 * it took — kind and source entities — so the viewport can name it at the
 * cursor BEFORE the click commits. A resolution with a null candidate took the
 * grid (or nothing), which is the one case that needs no mark.
 *
 * Two rules keep the mark truthful:
 *   1. A candidate only counts when it lies within tolerance OF THE CURSOR, so
 *      the mark never jumps away from where you are aiming. (AutoCAD's PER/TAN
 *      let the point fly off to the foot; that is precise and surprising, and
 *      surprise is exactly what this module refuses.)
 *   2. Class priority is strict, distance breaks ties WITHIN a class — so the
 *      resolution is stable while the cursor jitters, instead of flickering
 *      between two kinds a fraction of a millimetre apart.
 *
 * All geometry is analytic (line/circle/arc) so a snapped intersection is the
 * exact point, not a chord approximation. Splines are the one exception: they
 * fall back to the sampled interpolant the viewport draws (`sampleSpline`),
 * documented at the call site.
 *
 * TWO SOURCES OF CANDIDATE, one ranking: what has been DRAWN, and the sheet it
 * is drawn ON — the plane's origin and its two axes (`sketch/origin.ts`). The
 * second was missing until 2026-08-02, which meant every snap this module
 * offered required geometry to already exist, and the FIRST point of a sketch —
 * the one that decides where the part sits — could hold onto nothing at all.
 */
import { arcFrame, arcPointAt, entityPolylines } from "./geometry";
import { curveDistance, namedPoints } from "./pick";
import { snapPoint, snapValue, type Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/**
 * Snap magnet radius in *screen* pixels; the scene converts px → mm per event,
 * exactly as it does for `PICK_TOLERANCE_PX`. Deliberately a hair wider than
 * the pick tolerance (8): picking addresses something already drawn, while
 * snapping has to catch you on the way past.
 */
export const SNAP_TOLERANCE_PX = 12;

/** Snaps derived from the sketch entities themselves. */
export type EntitySnapKind =
  | "endpoint"
  | "midpoint"
  | "center"
  | "intersection"
  | "tangent"
  | "perpendicular";

/**
 * Snaps derived from the sketch PLANE rather than from anything drawn on it:
 * its origin and its two axes (`sketch/origin.ts`). They exist because every
 * entity snap needs geometry to already be there, so an EMPTY sketch had
 * nothing to hold onto — the founder's "there isn't an origin to start a
 * drawing from" (2026-08-02).
 */
export type PlaneSnapKind = "origin" | "x-axis" | "y-axis";

/** Everything that competes in the ranked candidate list. */
export type CandidateSnapKind = EntitySnapKind | PlaneSnapKind;

/**
 * Every kind the cursor can report. The two `axis-*` kinds are not candidates —
 * they are the Shift axis lock, reported through the same channel because they
 * answer the same question the mark exists to answer: what will this click
 * actually give me? (They are distinct from `x-axis`/`y-axis`, which are the
 * plane's own datum axes: the lock is relative to where you STARTED, the datum
 * axes are absolute.)
 */
export type SnapKind = CandidateSnapKind | "axis-h" | "axis-v";

export interface SnapCandidate {
  kind: SnapKind;
  /** The point the click will take (plane mm). */
  at: Point2D;
  /** Source entity ids — one, or two for an intersection; empty for the lock. */
  entities: readonly string[];
  /**
   * Overrides {@link SNAP_LABELS} for the word the mark carries. Exists for the
   * origin alone, whose honest name depends on what the plane's zero IS: a
   * datum's fixed zero, or a seated face's area centroid, which MOVES
   * (`sketch/origin.ts`). One kind, two truthful words.
   */
  label?: string;
}

export interface SnapResolution {
  /** The point to place at. */
  at: Point2D;
  /** What was taken, or null for a grid / free point (nothing to name). */
  candidate: SnapCandidate | null;
}

/**
 * Strict class priority (lower wins), distance breaking ties within a class.
 * The origin and endpoints share the top: both are exact, singular points a
 * user aims AT deliberately, and where they are within a hair of each other
 * they name the same coordinate anyway, so the NEARER one is what was meant and
 * the mark says which was taken. (Endpoints stack — two lines meeting at a
 * corner — which is why they earn the top rank in the first place.) Midpoint
 * and centre share a rank for the same nearer-one-wins reason; derived-from-a-
 * pair snaps rank below derived-from-one; the two that need an anchor point
 * (tangent, perpendicular) rank below those, since they only exist
 * mid-placement; and the plane's AXES rank last of all, just above the grid —
 * an axis is a whole line, so it is the weakest claim about where you are
 * aiming, and it must never beat a point that lies on it.
 */
const RANK: Record<CandidateSnapKind, number> = {
  origin: 0,
  endpoint: 0,
  midpoint: 1,
  center: 1,
  intersection: 2,
  tangent: 3,
  perpendicular: 3,
  "x-axis": 4,
  "y-axis": 4,
};

/** UI copy for each kind — the word the cursor mark carries. */
export const SNAP_LABELS: Record<SnapKind, string> = {
  endpoint: "Endpoint",
  midpoint: "Midpoint",
  center: "Centre",
  intersection: "Intersection",
  tangent: "Tangent",
  perpendicular: "Perpendicular",
  origin: "Origin",
  "x-axis": "X axis",
  "y-axis": "Y axis",
  "axis-h": "Horizontal",
  "axis-v": "Vertical",
};

/**
 * The plane's own frame, offered as snaps. Null suppresses them entirely (the
 * tools that PICK rather than PLACE).
 */
export interface OriginSnapSpec {
  /**
   * What this plane's zero is called — `originIdentity(plane).label`. Carried
   * rather than assumed because a face-seated sketch's origin is the face's
   * area centroid, and calling that "Origin" would imply a stability it does
   * not have.
   */
  label: string;
  /**
   * Grid step (mm) for the FREE coordinate of an axis snap; 0 = off. An axis
   * snap pins one coordinate to zero and leaves the other where you are
   * pointing, so without this you would get (24.87, 0) where you plainly meant
   * (25, 0). Same rule the Shift axis lock already follows.
   */
  gridStepMm: number;
}

/**
 * "Close enough to be ON the curve" (mm). Analytic intersections land within
 * ~1e-10 mm of both curves at sketch scale, so this only has to absorb float
 * noise — it is NOT a user-facing tolerance.
 */
const TOUCH_MM = 1e-6;

/** Two candidate points closer than this are the same point (tangency). */
const DUPLICATE_MM = 1e-7;

const dist = (a: Point2D, b: Point2D): number =>
  Math.hypot(b.x - a.x, b.y - a.y);

export interface Circle {
  center: Point2D;
  radius: number;
}

export interface Segment {
  a: Point2D;
  b: Point2D;
}

/** The entity's full circle (circles AND arcs), or null if it has none. */
function circleOf(entity: SketchEntity): Circle | null {
  if (entity.kind === "circle") {
    return { center: entity.center, radius: entity.radius };
  }
  if (entity.kind === "arc") {
    const frame = arcFrame(entity);
    return { center: frame.center, radius: frame.radius };
  }
  return null;
}

/** The entity's segment, or null if it is not a line. */
function lineOf(entity: SketchEntity): Segment | null {
  return entity.kind === "line" ? { a: entity.start, b: entity.end } : null;
}

/** True when `p` lies on the entity's drawn extent (segment bounds, arc sweep). */
function onCurve(entity: SketchEntity, p: Point2D): boolean {
  return curveDistance(p, entity) <= TOUCH_MM;
}

/** The entity's midpoint — lines and arcs only (a circle has none). */
export function midpointOf(entity: SketchEntity): Point2D | null {
  if (entity.kind === "line") {
    return {
      x: (entity.start.x + entity.end.x) / 2,
      y: (entity.start.y + entity.end.y) / 2,
    };
  }
  if (entity.kind === "arc") return arcPointAt(arcFrame(entity), 0.5);
  return null;
}

/** Intersection of two INFINITE lines, or null when (near-)parallel. */
function infiniteLineIntersection(p: Segment, q: Segment): Point2D | null {
  const r = { x: p.b.x - p.a.x, y: p.b.y - p.a.y };
  const s = { x: q.b.x - q.a.x, y: q.b.y - q.a.y };
  const denom = r.x * s.y - r.y * s.x;
  // Scale-relative parallel test: an absolute epsilon would call two long
  // near-parallel lines "crossing" and two short crossing ones "parallel".
  const scale = Math.hypot(r.x, r.y) * Math.hypot(s.x, s.y);
  if (scale === 0 || Math.abs(denom) < scale * 1e-9) return null;
  const t = ((q.a.x - p.a.x) * s.y - (q.a.y - p.a.y) * s.x) / denom;
  return { x: p.a.x + t * r.x, y: p.a.y + t * r.y };
}

/** Where an infinite line meets a full circle (0, 1 or 2 points). */
function lineCircleIntersections(line: Segment, circle: Circle): Point2D[] {
  const d = { x: line.b.x - line.a.x, y: line.b.y - line.a.y };
  const f = {
    x: line.a.x - circle.center.x,
    y: line.a.y - circle.center.y,
  };
  const a = d.x * d.x + d.y * d.y;
  if (a <= 0) return [];
  const b = 2 * (f.x * d.x + f.y * d.y);
  const c = f.x * f.x + f.y * f.y - circle.radius * circle.radius;
  const disc = b * b - 4 * a * c;
  if (disc < 0) return [];
  const root = Math.sqrt(disc);
  const ts = [(-b - root) / (2 * a), (-b + root) / (2 * a)];
  return ts.map((t) => ({ x: line.a.x + t * d.x, y: line.a.y + t * d.y }));
}

/** Where two full circles meet (0, 1 or 2 points). */
function circleCircleIntersections(p: Circle, q: Circle): Point2D[] {
  const dx = q.center.x - p.center.x;
  const dy = q.center.y - p.center.y;
  const d = Math.hypot(dx, dy);
  if (d === 0) return []; // concentric (identical circles included)
  if (d > p.radius + q.radius) return []; // apart
  if (d < Math.abs(p.radius - q.radius)) return []; // one inside the other
  const a = (p.radius * p.radius - q.radius * q.radius + d * d) / (2 * d);
  const hSq = p.radius * p.radius - a * a;
  const h = hSq <= 0 ? 0 : Math.sqrt(hSq);
  const mx = p.center.x + (a * dx) / d;
  const my = p.center.y + (a * dy) / d;
  if (h === 0) return [{ x: mx, y: my }];
  return [
    { x: mx + (h * dy) / d, y: my - (h * dx) / d },
    { x: mx - (h * dy) / d, y: my + (h * dx) / d },
  ];
}

/** Segment × segment, both parameters clamped to the drawn extent. */
function segmentIntersection(p: Segment, q: Segment): Point2D | null {
  const hit = infiniteLineIntersection(p, q);
  if (hit === null) return null;
  const within = (s: Segment): boolean => {
    const len = Math.hypot(s.b.x - s.a.x, s.b.y - s.a.y);
    if (len === 0) return false;
    const t =
      ((hit.x - s.a.x) * (s.b.x - s.a.x) + (hit.y - s.a.y) * (s.b.y - s.a.y)) /
      (len * len);
    return t >= -1e-9 && t <= 1 + 1e-9;
  };
  return within(p) && within(q) ? hit : null;
}

/**
 * Sampled fallback for pairs involving a SPLINE. The spline's true profile is
 * the server's C2 B-spline; the client only has the sampled interpolant it
 * draws, so a spline intersection is accurate to the drawn ink and no further.
 * Every other pair goes through the analytic paths above and is exact.
 */
function sampledIntersections(a: SketchEntity, b: SketchEntity): Point2D[] {
  const out: Point2D[] = [];
  for (const pa of entityPolylines(a)) {
    for (let i = 0; i + 1 < pa.length; i += 1) {
      const sa = { a: pa[i] as Point2D, b: pa[i + 1] as Point2D };
      for (const pb of entityPolylines(b)) {
        for (let j = 0; j + 1 < pb.length; j += 1) {
          const hit = segmentIntersection(sa, {
            a: pb[j] as Point2D,
            b: pb[j + 1] as Point2D,
          });
          if (hit !== null) out.push(hit);
        }
      }
    }
  }
  return out;
}

/** Every point where two entities actually cross, on their drawn extents. */
export function intersectEntities(a: SketchEntity, b: SketchEntity): Point2D[] {
  // A bare point entity has no curve to cross.
  if (a.kind === "point" || b.kind === "point") return [];
  if (a.kind === "spline" || b.kind === "spline") {
    return dedupe(sampledIntersections(a, b));
  }
  const lineA = lineOf(a);
  const lineB = lineOf(b);
  const circleA = circleOf(a);
  const circleB = circleOf(b);
  let raw: Point2D[] = [];
  if (lineA !== null && lineB !== null) {
    const hit = infiniteLineIntersection(lineA, lineB);
    raw = hit === null ? [] : [hit];
  } else if (lineA !== null && circleB !== null) {
    raw = lineCircleIntersections(lineA, circleB);
  } else if (circleA !== null && lineB !== null) {
    raw = lineCircleIntersections(lineB, circleA);
  } else if (circleA !== null && circleB !== null) {
    raw = circleCircleIntersections(circleA, circleB);
  }
  // The analytic solutions are for the INFINITE line / FULL circle; the drawn
  // extent (segment bounds, arc sweep) is what the user can actually snap to.
  return dedupe(raw.filter((p) => onCurve(a, p) && onCurve(b, p)));
}

function dedupe(points: readonly Point2D[]): Point2D[] {
  const out: Point2D[] = [];
  for (const p of points) {
    if (!out.some((q) => dist(p, q) <= DUPLICATE_MM)) out.push(p);
  }
  return out;
}

/**
 * The two points on `circle` where a line from `from` touches it tangentially.
 * Empty when `from` is inside or on the circle (no tangent exists).
 */
export function tangentPoints(from: Point2D, circle: Circle): Point2D[] {
  const dx = circle.center.x - from.x;
  const dy = circle.center.y - from.y;
  const d = Math.hypot(dx, dy);
  if (!(d > circle.radius + TOUCH_MM) || circle.radius <= 0) return [];
  // Rotate the centre→anchor unit vector by ±θ, cos θ = r / d.
  const cos = circle.radius / d;
  const sin = Math.sqrt(Math.max(0, 1 - cos * cos));
  const ux = -dx / d;
  const uy = -dy / d;
  return [
    {
      x: circle.center.x + circle.radius * (cos * ux - sin * uy),
      y: circle.center.y + circle.radius * (sin * ux + cos * uy),
    },
    {
      x: circle.center.x + circle.radius * (cos * ux + sin * uy),
      y: circle.center.y + circle.radius * (-sin * ux + cos * uy),
    },
  ];
}

/**
 * Foot of the perpendicular dropped from `from` onto the segment, or null when
 * the foot falls off the drawn extent (an off-segment foot is a point the user
 * cannot see, so it is not offered).
 */
export function perpendicularFoot(
  from: Point2D,
  segment: Segment,
): Point2D | null {
  const abx = segment.b.x - segment.a.x;
  const aby = segment.b.y - segment.a.y;
  const lenSq = abx * abx + aby * aby;
  if (lenSq <= 0) return null;
  const t =
    ((from.x - segment.a.x) * abx + (from.y - segment.a.y) * aby) / lenSq;
  if (t < 0 || t > 1) return null;
  return { x: segment.a.x + t * abx, y: segment.a.y + t * aby };
}

/**
 * Every entity snap within `toleranceMm` of `at`, best first (class rank, then
 * distance). `from` is the in-progress placement's anchor — the last pending
 * point — and is required for tangent/perpendicular, which are defined
 * relative to where the line is coming FROM; pass null when nothing is pending.
 */
export function snapCandidates(
  entities: readonly SketchEntity[],
  at: Point2D,
  from: Point2D | null,
  toleranceMm: number,
  origin: OriginSnapSpec | null = null,
): SnapCandidate[] {
  const found: Array<{
    kind: CandidateSnapKind;
    at: Point2D;
    entities: string[];
    d: number;
    label?: string;
  }> = [];
  const offer = (
    kind: CandidateSnapKind,
    point: Point2D,
    ids: string[],
    label?: string,
  ): void => {
    const d = dist(at, point);
    // Rule 1: the mark never jumps away from the cursor.
    if (d <= toleranceMm)
      found.push({ kind, at: point, entities: ids, d, label });
  };

  for (const entity of entities) {
    for (const named of namedPoints(entity)) {
      // `namedPoints` is the SAME set the constraint layer addresses, so a
      // snap and a coincident constraint can never disagree about where an
      // endpoint is. Only a circle/arc `center` is a centre; start/end/
      // position/fitN are all ends of something.
      offer(named.point === "center" ? "center" : "endpoint", named.at, [
        entity.id,
      ]);
    }
    const mid = midpointOf(entity);
    if (mid !== null) offer("midpoint", mid, [entity.id]);
  }

  // Only curves passing within tolerance of the cursor can CROSS within
  // tolerance of it, so this narrows the pair scan to the handful under the
  // pointer — and the same shortlist serves tangent/perpendicular.
  const near = entities.filter((e) => curveDistance(at, e) <= toleranceMm);
  for (let i = 0; i < near.length; i += 1) {
    for (let j = i + 1; j < near.length; j += 1) {
      const a = near[i] as SketchEntity;
      const b = near[j] as SketchEntity;
      for (const point of intersectEntities(a, b)) {
        offer("intersection", point, [a.id, b.id]);
      }
    }
  }

  if (from !== null) {
    for (const entity of near) {
      const circle = circleOf(entity);
      if (circle !== null) {
        for (const point of tangentPoints(from, circle)) {
          // An arc only offers the tangent points inside its sweep.
          if (onCurve(entity, point)) offer("tangent", point, [entity.id]);
        }
      }
      const line = lineOf(entity);
      if (line !== null) {
        const foot = perpendicularFoot(from, line);
        if (foot !== null) offer("perpendicular", foot, [entity.id]);
      }
    }
  }

  if (origin !== null) {
    // The plane's zero, and the feet of the perpendiculars onto its two axes.
    // Distance is measured to the point the click would TAKE (grid rounding
    // included), so rule 1 holds uniformly and an axis snap at the very edge of
    // the magnet is dropped rather than dragging the aim a whole grid step.
    //
    // Offered LAST deliberately. The sort below is stable, so among candidates
    // of equal rank AND equal distance the earlier one wins — and the case that
    // arises constantly is a corner you drew AT the origin, where the endpoint
    // and the origin are the same point to the last bit. The ink is the more
    // specific claim ("this corner", with an entity id a constraint can
    // address) and it is what the user can see, so it takes the tie. Nothing is
    // lost either way: the coordinate is identical, only the word differs.
    offer("origin", { x: 0, y: 0 }, [], origin.label);
    offer("x-axis", { x: snapValue(at.x, origin.gridStepMm), y: 0 }, []);
    offer("y-axis", { x: 0, y: snapValue(at.y, origin.gridStepMm) }, []);
  }

  // Rule 2: rank first (stable under jitter), distance only within a class.
  found.sort((a, b) => RANK[a.kind] - RANK[b.kind] || a.d - b.d);
  return found.map(({ kind, at: point, entities: ids, label }) => ({
    kind,
    at: point,
    entities: ids,
    ...(label === undefined ? {} : { label }),
  }));
}

export interface SnapInput {
  /** Raw pointer point in plane mm (unsnapped). */
  point: Point2D;
  entities: readonly SketchEntity[];
  /** The in-progress placement's anchor, or null (see `snapCandidates`). */
  from: Point2D | null;
  toleranceMm: number;
  /** Grid step in mm; 0 (or less) means the grid snap is off. */
  gridStepMm: number;
  /** Ctrl/Cmd held — freehand: no entity snap AND no grid. */
  suppressed: boolean;
  /** Shift held — lock the aim to the axis through `from`. */
  axisLock: boolean;
  /**
   * False for the tools that address existing geometry by raw coordinate
   * (select / trim / extend / offset / mirror / fillet / chamfer). They pick,
   * they do not place, so an entity snap would move the aim off the thing the
   * user is pointing at.
   */
  entitySnap: boolean;
  /**
   * The plane's own origin + axes, or null to suppress them — same reasoning as
   * `entitySnap`, held as a separate switch because the two answer to different
   * things (one to the drawing, one to the sheet).
   */
  originSnap: { label: string } | null;
}

/**
 * The one resolution the sketcher uses for every aim: modifier state first,
 * then entity snapping, then the grid. Returns both the point AND what it was,
 * so nothing can place a snapped point without the UI being able to say which
 * snap it took.
 */
export function resolveSnap(input: SnapInput): SnapResolution {
  const { point, from, gridStepMm } = input;
  // Ctrl/Cmd = freehand. Everything off, including the grid: "suppresses
  // snapping" has to mean ALL of it, or the escape hatch is not an escape.
  if (input.suppressed) return { at: point, candidate: null };

  // Shift = axis lock, measured from the placement anchor. Whichever axis the
  // cursor has travelled further along wins; the free coordinate still takes
  // the grid. Entity snaps are skipped: taking one would break the lock the
  // user is holding, which is exactly the silent-wrong-thing this module is
  // built to prevent.
  if (input.axisLock && from !== null) {
    const horizontal = Math.abs(point.x - from.x) >= Math.abs(point.y - from.y);
    const at = horizontal
      ? { x: snapValue(point.x, gridStepMm), y: from.y }
      : { x: from.x, y: snapValue(point.y, gridStepMm) };
    return {
      at,
      candidate: { kind: horizontal ? "axis-h" : "axis-v", at, entities: [] },
    };
  }

  // One ranked list, two sources: what is drawn (gated by `entitySnap`) and the
  // sheet it is drawn ON (gated by `originSnap`). They compete under the same
  // priority, so an endpoint sitting on the X axis still reads "Endpoint" and
  // the axis can never quietly outrank a point that lies along it.
  const best = snapCandidates(
    input.entitySnap ? input.entities : [],
    point,
    from,
    input.toleranceMm,
    input.originSnap === null
      ? null
      : { label: input.originSnap.label, gridStepMm },
  )[0];
  if (best !== undefined) return { at: best.at, candidate: best };

  // The grid is the floor, and it gets no mark: it is always catching, so a
  // mark for it would be permanent chrome that says nothing.
  return { at: snapPoint(point, gridStepMm), candidate: null };
}
