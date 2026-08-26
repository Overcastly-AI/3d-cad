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
 *
 * A SNAP IS AN INTENT, NOT A COORDINATE (SNAP-3 / SNAP-2, 2026-08-17). Aiming
 * at a corner and taking its coordinate is only half of what the gesture meant:
 * the user said "here, ON that", and until this landed we recorded only the
 * "here". The sketch then LOOKED joined and came apart on the first re-drive,
 * with nothing on screen having ever distinguished the two. So every candidate
 * that names a point the constraint layer can address now carries that address
 * ({@link SnapCandidate.ref}), and {@link inferredCoincidents} turns the
 * addresses a placement actually consumed into the coincidents that hold it
 * together. Fusion and SolidWorks both do this at draw time; it is the
 * difference between "the aim landed exactly" and "it stays".
 */
import type { SketchConstraint, EntityPointRef } from "./constraints";
import { sameConstraint } from "./constraints";
import { DATUM_ORIGIN_ID } from "./datum";
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
  /**
   * The CONSTRAINT-ADDRESSABLE point this snap took its coordinate from, when
   * it has one — the seam that lets a placement author the coincident the
   * gesture meant (SNAP-3). Present for the kinds that ARE a named point:
   * `endpoint` and `center` (a drawn entity's `namedPoints`), and `origin` (the
   * datum point `sketch/datum.ts` materialises on demand).
   *
   * ABSENT, deliberately, for the other five, and each absence is a different
   * reason rather than an oversight:
   *
   * · `midpoint` — a line's middle is not an `EntityPointRef`; the schema has
   *   no midpoint constraint, so there is nothing honest to author.
   * · `intersection`, `tangent`, `perpendicular` — derived locations, not named
   *   points. Each has a real constraint that would express it (a coincident on
   *   both curves, `tangent`, `perpendicular`), but each is a claim about the
   *   NEW curve's whole shape rather than about where one click landed, and
   *   inferring that from an aim would author relations the user did not ask
   *   for. Left to the explicit verbs.
   * · `x-axis` / `y-axis` — the target is a LINE and the point lies ANYWHERE
   *   along it, which is a point-on-object relation. The constraint vocabulary
   *   (`SketchParamsV1`, 12 kinds) has none: `coincident` joins two named
   *   points and `fixed` pins both coordinates, so the only expressible reading
   *   would nail the free coordinate too — silently converting "on the X axis"
   *   into "at this exact spot on the X axis", which is a stronger claim than
   *   the gesture made. Authoring nothing is the honest answer until a
   *   `point_on_object` constraint exists kernel-side. Snapping ONTO the origin
   *   (where the axes cross) is unaffected — that is a named point and is
   *   covered above.
   */
  ref?: EntityPointRef;
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
    ref?: EntityPointRef;
  }> = [];
  const offer = (
    kind: CandidateSnapKind,
    point: Point2D,
    ids: string[],
    extra: { label?: string; ref?: EntityPointRef } = {},
  ): void => {
    const d = dist(at, point);
    // Rule 1: the mark never jumps away from the cursor.
    if (d <= toleranceMm)
      found.push({ kind, at: point, entities: ids, d, ...extra });
  };

  for (const entity of entities) {
    for (const named of namedPoints(entity)) {
      // `namedPoints` is the SAME set the constraint layer addresses, so a
      // snap and a coincident constraint can never disagree about where an
      // endpoint is. Only a circle/arc `center` is a centre; start/end/
      // position/fitN are all ends of something.
      //
      // That shared derivation is exactly why the snap can hand a constraint
      // ref straight out: the address is not reconstructed from a coordinate
      // afterwards (which is the guessing game a later re-pick would play), it
      // is the address the point came FROM.
      offer(
        named.point === "center" ? "center" : "endpoint",
        named.at,
        [entity.id],
        { ref: { entity: entity.id, point: named.point } },
      );
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
    offer("origin", { x: 0, y: 0 }, [], {
      label: origin.label,
      // The plane's zero IS a constraint-addressable point — `datum.ts`
      // materialises it as a pinned construction point the moment something
      // references it — so a corner snapped here can be GROUNDED, not merely
      // placed at (0,0). That is SNAP-2, and it needs no path of its own.
      ref: { entity: DATUM_ORIGIN_ID, point: "position" },
    });
    // The two axes carry no `ref` — see `SnapCandidate.ref`.
    offer("x-axis", { x: snapValue(at.x, origin.gridStepMm), y: 0 }, []);
    offer("y-axis", { x: 0, y: snapValue(at.y, origin.gridStepMm) }, []);
  }

  // Rule 2: rank first (stable under jitter), distance only within a class.
  found.sort((a, b) => RANK[a.kind] - RANK[b.kind] || a.d - b.d);
  return found.map(({ kind, at: point, entities: ids, label, ref }) => ({
    kind,
    at: point,
    entities: ids,
    ...(label === undefined ? {} : { label }),
    ...(ref === undefined ? {} : { ref }),
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

// ---------------------------------------------------------------------------
// Snap → constraint inference (SNAP-3, which subsumes SNAP-2)
// ---------------------------------------------------------------------------

/**
 * A snap the user actually SPENT — one click of an in-progress placement that
 * took its coordinate from an addressable point. Held by the store across the
 * clicks of a sequence, because the click that matters most (a line's start, a
 * rectangle's first corner) happens while no entity exists to constrain yet.
 */
export interface SnapAnchor {
  /** The coordinate the click took (plane mm) — copied, not recomputed. */
  at: Point2D;
  /** The point it took that coordinate FROM. */
  ref: EntityPointRef;
}

/**
 * The anchor a click leaves behind, or null when the aim took the grid, a
 * modifier-suppressed free point, an axis, or any other kind with no address.
 */
export function snapAnchorOf(
  candidate: SnapCandidate | null,
  at: Point2D,
): SnapAnchor | null {
  const ref = candidate?.ref;
  return ref === undefined ? null : { at, ref };
}

/**
 * Placed coordinates closer than this are the same point. This is NOT a user
 * tolerance: the placement copies the snapped coordinate verbatim into the
 * entity, so a match here is bit-identical in every real case and the epsilon
 * only absorbs the arithmetic `rectangleCorners` does on the way (min/max of
 * two numbers — exact, but the arc's projection is not).
 */
const ANCHOR_MM = 1e-9;

/**
 * The coincidents a placement earned: one per anchor whose coordinate a
 * just-emitted entity actually landed a named point on.
 *
 * MATCHING BY COORDINATE, NOT BY POSITION IN THE SEQUENCE, is what makes this
 * ONE path for every tool instead of five (the DRY rule; two snap-to-constraint
 * implementations would be the defect, not the fix). Each tool routes its
 * clicks into different slots of a different shape — a line's second click is
 * an `end`, a rectangle's is two corners away from where it started, a
 * spline's is `fitN` — and every one of them lands the SNAPPED COORDINATE,
 * unchanged, on the point that click created. So "which named point did this
 * click become?" is answered by looking, and three behaviours fall out for
 * free rather than being special-cased:
 *
 * · A RECTANGLE corner is shared by two of the four lines, and only the first
 *   is bound (`break`). Binding both would state the same fact twice and, with
 *   the corner coincidences a rectangle already carries, report an ordinary
 *   sketch as OVER-CONSTRAINED — a worse defect than the one being fixed.
 * · A CIRCLE's rim click has no named point at that coordinate (a circle is
 *   `center` + radius), so a snap there authors nothing — correct, because
 *   what the user constrained is not representable as a point.
 * · An ARC's third click is PROJECTED onto the arc's circle, so the emitted
 *   `end` is generally NOT where the user clicked; no match, no constraint.
 *   Where the target does lie on the circle the coordinates agree and the
 *   constraint is authored, which is exactly when it is true.
 *
 * `existing` is checked so a re-drawn edge cannot stack a duplicate of a
 * relation already on the sketch — the same `sameConstraint` guard the explicit
 * `C` verb uses, so the automatic and manual paths agree on what "already
 * coincident" means.
 */
export function inferredCoincidents(
  anchors: readonly SnapAnchor[],
  emitted: readonly SketchEntity[],
  existing: readonly SketchConstraint[] = [],
): SketchConstraint[] {
  const out: SketchConstraint[] = [];
  for (const anchor of anchors) {
    for (const entity of emitted) {
      // A point cannot be coincident with itself; an emitted entity can never
      // be the anchor's target (ids are freshly minted), but the guard keeps
      // that a property of this function rather than of its caller.
      if (entity.id === anchor.ref.entity) continue;
      const named = namedPoints(entity).find(
        (candidate) => dist(candidate.at, anchor.at) <= ANCHOR_MM,
      );
      if (named === undefined) continue;
      const constraint: SketchConstraint = {
        kind: "coincident",
        a: { entity: entity.id, point: named.point },
        b: anchor.ref,
      };
      if (
        !existing.some((c) => sameConstraint(c, constraint)) &&
        !out.some((c) => sameConstraint(c, constraint))
      ) {
        out.push(constraint);
      }
      break;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Draw → axis inference (SNAP-5)
// ---------------------------------------------------------------------------

/**
 * The widest angle off an axis that still reads as "the user drew this
 * horizontal". It is a CEILING on the deviation rule below, not the rule
 * itself, and it exists for one case only: a stub so short that a deviation
 * measured in millimetres says nothing about its direction (a 3 mm line at 40°
 * deviates less than a 300 mm line at 0.5°). Three degrees is derived, not
 * chosen by taste: with the default 1 mm grid the SHORTEST edge of the
 * reference profile SNAP-5 was filed against (6 mm, the flanged-coupling
 * staircase) can express a deliberate slope of one grid step over its run —
 * `atan(1/6)` = 9.46° — so the ceiling sits at a third of the smallest slope
 * anyone can draw on purpose there. It also agrees, to the order, with what
 * the deviation rule yields unaided at working zoom: 12 px (the snap radius)
 * across a 30 mm edge that spans ~200 px is 3.4°.
 */
export const AXIS_INFERENCE_MAX_DEG = 3;

const AXIS_INFERENCE_MAX_TAN = Math.tan(
  (AXIS_INFERENCE_MAX_DEG * Math.PI) / 180,
);

/**
 * Coordinates this close to the axis ARE on it. Same role as {@link ANCHOR_MM}:
 * the placement copies its coordinate verbatim, so an axis-locked or
 * grid-landed line is bit-exact and this only absorbs arithmetic. It is also
 * the floor of the deviation limit, so an exactly-drawn line is inferred even
 * where the caller reports no tolerance at all.
 */
const AXIS_EXACT_MM = 1e-9;

/** What the placement knew about the click that ended the line. */
export interface AxisInferenceInput {
  /** Live grid step in mm; 0 when the grid is off (G). */
  gridStepMm: number;
  /** The snap radius in plane mm at this zoom ({@link SNAP_TOLERANCE_PX}). */
  toleranceMm: number;
  /** Ctrl/Cmd was held — every snap off, this inference with them. */
  suppressed: boolean;
}

/**
 * The horizontal / vertical constraints a freshly-drawn line EARNED (SNAP-5).
 *
 * WHY THE ORDINARY GESTURE NEEDED THIS. `shapeRigidity` gives a rectangle two
 * horizontals and two verticals because a rectangle IS axis-aligned by
 * construction; a line drawn line-by-line — the way anything that is not a
 * rectangle gets drawn — carried nothing at all. So an L-bracket outline that
 * LOOKS axis-aligned solved with every edge free to rotate: measured on the
 * six-edge staircase profile of the SOLVE-1 report, 12 DOF undimensioned and 8
 * with four driving dimensions, where the same shape with its axes stated
 * solves at 6 and 2. SOLVE-1 holds those free DOF at the author's input on an
 * edit, which keeps the sketch from wandering, but a safety net for looseness
 * is not the same thing as not being loose.
 *
 * THE RULE, and both halves are measured rather than taken from taste:
 *
 * · DEVIATION — the rise must be under `limit`, and the run over it. With the
 *   grid ON the limit is one grid step, because a grid-snapped placement can
 *   only land on multiples of it: a deviation of a whole step is a decision,
 *   and anything smaller than a step is exactly zero. With the grid OFF there
 *   is no quantum, so the limit is the snap radius the same click was aimed
 *   with — the distance inside which this module already treats two points as
 *   the same point. Requiring the RUN to clear the same limit is what keeps a
 *   near-degenerate stub from claiming an axis it does not have.
 * · CEILING — {@link AXIS_INFERENCE_MAX_DEG}, for the short-line case above.
 *
 * WHY IT LIVES HERE, beside {@link inferredCoincidents}, and not in
 * `shapeRigidity`: this is an inference from what the user AIMED — it depends
 * on the live tolerance and it stops when the user suppresses snapping —
 * whereas rigidity is a fact about the shape that is the same at every zoom.
 * Putting a tolerance inside `shapeRigidity` would make a rectangle's
 * rectangularity depend on the camera. One mechanism, one place: a rectangle's
 * four edges pass through here too and are deduped against the rigidity set by
 * `sameConstraint`, exactly as SNAP-3 dedupes against the explicit verb, so no
 * fact is ever authored twice (which would report an ordinary sketch as
 * OVER-CONSTRAINED — the RECT-1 lesson).
 *
 * THE OPT-OUT ALREADY EXISTED: Ctrl/Cmd. `resolveAim` refuses every snap while
 * it is held on the principle that an escape hatch has to be a whole one, and
 * an inferred constraint is the other half of a snap — so it is honoured here
 * too rather than a second gesture being invented for it.
 */
export function inferredAxisConstraints(
  emitted: readonly SketchEntity[],
  input: AxisInferenceInput,
  existing: readonly SketchConstraint[] = [],
): SketchConstraint[] {
  if (input.suppressed) return [];
  const limit = Math.max(
    input.gridStepMm > 0 ? input.gridStepMm : input.toleranceMm,
    AXIS_EXACT_MM,
  );
  const out: SketchConstraint[] = [];
  for (const entity of emitted) {
    if (entity.kind !== "line") continue;
    const run = Math.abs(entity.end.x - entity.start.x);
    const rise = Math.abs(entity.end.y - entity.start.y);
    const kind = alignedAxis(run, rise, limit);
    if (kind === null) continue;
    const constraint: SketchConstraint = { kind, entity: entity.id };
    if (
      !existing.some((c) => sameConstraint(c, constraint)) &&
      !out.some((c) => sameConstraint(c, constraint))
    ) {
      out.push(constraint);
    }
  }
  return out;
}

/**
 * Which axis a run/rise pair claims, or null. The two tests are mutually
 * exclusive by construction — each demands its own span clear the limit the
 * other must stay under — so a line can never claim both.
 */
function alignedAxis(
  run: number,
  rise: number,
  limit: number,
): "horizontal" | "vertical" | null {
  if (rise < limit && run > limit && rise <= run * AXIS_INFERENCE_MAX_TAN) {
    return "horizontal";
  }
  if (run < limit && rise > limit && run <= rise * AXIS_INFERENCE_MAX_TAN) {
    return "vertical";
  }
  return null;
}
