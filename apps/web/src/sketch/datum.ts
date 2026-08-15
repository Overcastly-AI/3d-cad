/**
 * THE SKETCH FRAME AS SELECTABLE GEOMETRY — the origin point and the two plane
 * axes, given real pick geometry and a real identity the solver accepts.
 * Pure math, no three.js, no store.
 *
 * ## The defect this closes (SKETCH-2, founder report 2026-08-14)
 *
 * The founder reported *"snap points do not work"*. The SNAP-1 investigation
 * measured snap DETECTION as correct in every configuration it could build —
 * grid on and off, origin/x-axis/endpoint/midpoint, drag, re-opened sketch, XZ
 * and YZ planes, face-seated sketch — and reproduced this instead, with a
 * positive control in the same test:
 *
 *     click the drawn line   -> selection-readout = "1 ent"
 *     click the origin ring  -> "nothing selected"
 *     click the X axis       -> "nothing selected"
 *
 * `SketchOrigin` drew the frame as pure `InkSegments` — decorative canvas ink
 * with nothing behind it to hit — and the only DOM at (0,0) was a
 * screen-reader-only `<span role="img">`. So you could AIM at the origin (the
 * snap fires, the point lands exact) and could not SELECT it, which from the
 * user's chair is the same complaint.
 *
 * It is a bigger gap than one missed click. A sketch that cannot be constrained
 * to its own origin and axes is not parametric: the only way to ground a
 * profile was `Fixed` at absolute coordinates, which does not re-centre when
 * the profile's size changes, so "this plate is symmetric about the origin" was
 * not expressible at all.
 *
 * ## How it is made real without a second representation
 *
 * The solver only knows entities that are IN the sketch (`planegcs_solver`
 * resolves every constraint ref against `sketch.entities` and raises on an
 * unknown id), so a pseudo-id the client understands and the kernel does not
 * would fail at the first solve. The frame is therefore materialised as
 * ordinary CONSTRUCTION geometry with reserved ids — but LAZILY, the first time
 * a constraint actually references it:
 *
 *   · `origin`  — a construction point at (0,0), pinned by one `fixed`.
 *   · `x-axis` / `y-axis` — construction lines through it, each pinned by a
 *     `fixed` on both endpoints.
 *
 * Three properties follow, and each is why this shape was chosen:
 *
 * 1. **Zero cost to a sketch that never uses it.** Nothing is added to an
 *    untouched sketch, so entity counts, the "unstarted" Escape rung, profile
 *    closure and every existing payload are byte-identical to before.
 * 2. **The pins are DOF-neutral.** Each datum entity adds exactly as many
 *    degrees of freedom as its pins remove, so the sketch's solved DOF — the
 *    number the user reads — is unchanged by grounding to the frame.
 * 3. **One representation, so re-open is free.** A saved sketch hands the datum
 *    entities straight back as normal entities; nothing has to be reconstituted
 *    and no id can drift, which is what makes a constraint to the origin
 *    survive save + re-open.
 *
 * Construction geometry is excluded from the closed-wire profile that
 * extrude/revolve consume (`SketchEntityBase.construction`), so grounding a
 * profile can never open it.
 *
 * The ids are reserved words: `entityId` mints `e1`, `e2`, … so a drawn entity
 * can never collide with one.
 */
import type { SketchConstraint } from "./constraints";
import { ORIGIN_AXIS_FRACTION, ORIGIN_RING_FRACTION } from "./origin";
import { pickCandidates, type SketchPick } from "./pick";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/** The plane's zero — a construction point the solver can be constrained to. */
export const DATUM_ORIGIN_ID = "origin";
/** The plane's +X axis (the DRO's own X), as a construction line. */
export const DATUM_X_AXIS_ID = "x-axis";
/** The plane's +Y axis (the DRO's own Y), as a construction line. */
export const DATUM_Y_AXIS_ID = "y-axis";

/** Which member of the frame a pick addresses. */
export type DatumKind = "origin" | "x-axis" | "y-axis";

export const DATUM_IDS: readonly DatumKind[] = [
  DATUM_ORIGIN_ID,
  DATUM_X_AXIS_ID,
  DATUM_Y_AXIS_ID,
];

/** Reserved-id test — the one predicate every other module asks. */
export function isDatumId(id: string): id is DatumKind {
  return (
    id === DATUM_ORIGIN_ID || id === DATUM_X_AXIS_ID || id === DATUM_Y_AXIS_ID
  );
}

/** The pick a click on the frame produces (the origin is a POINT pick). */
export const DATUM_PICKS: Readonly<Record<DatumKind, SketchPick>> = {
  [DATUM_ORIGIN_ID]: {
    kind: "point",
    entity: DATUM_ORIGIN_ID,
    point: "position",
  },
  [DATUM_X_AXIS_ID]: { kind: "entity", id: DATUM_X_AXIS_ID },
  [DATUM_Y_AXIS_ID]: { kind: "entity", id: DATUM_Y_AXIS_ID },
};

/** Which datum a pick addresses, or null for ordinary geometry. */
export function datumOf(pick: SketchPick): DatumKind | null {
  const id = pick.kind === "entity" ? pick.id : pick.entity;
  return isDatumId(id) ? id : null;
}

/** Does this selection address the frame at all? */
export function selectionTouchesDatum(
  selection: readonly SketchPick[],
): boolean {
  return selection.some((pick) => datumOf(pick) !== null);
}

/**
 * The frame's drawn size in plane mm — the SAME derivation `SketchOrigin` uses
 * to draw it, so the region you can hit is the ink you can see. Deriving both
 * from `origin.ts`'s fractions is the whole point: a pick region that drifted
 * from the ink would reproduce the original defect in a subtler form.
 */
export interface DatumFrame {
  /** Radius of the centre-punch ring at (0,0). */
  ringRadiusMm: number;
  /** How far each axis runs from the origin, per side. */
  axisHalfLengthMm: number;
}

/**
 * Fallback frame half-height (mm) for a store that has not been told the
 * camera's framing yet — the datum-sheet parking frame
 * (`SKETCH_CAMERA_DISTANCE_MM` at the default field of view). The scene
 * overwrites it with the measured value on entry (`setDatumFrame`).
 */
export const DEFAULT_FRAME_HALF_HEIGHT_MM = 80;

export function datumFrame(frameHalfHeightMm: number): DatumFrame {
  const half =
    frameHalfHeightMm > 0 ? frameHalfHeightMm : DEFAULT_FRAME_HALF_HEIGHT_MM;
  return {
    ringRadiusMm: half * ORIGIN_RING_FRACTION,
    axisHalfLengthMm: half * ORIGIN_AXIS_FRACTION,
  };
}

/** The three datum entities, sized to the drawn frame. */
export function datumEntities(frame: DatumFrame): SketchEntity[] {
  const L = frame.axisHalfLengthMm;
  return [
    {
      id: DATUM_ORIGIN_ID,
      kind: "point",
      position: { x: 0, y: 0 },
      construction: true,
    },
    {
      id: DATUM_X_AXIS_ID,
      kind: "line",
      start: { x: -L, y: 0 },
      end: { x: L, y: 0 },
      construction: true,
    },
    {
      id: DATUM_Y_AXIS_ID,
      kind: "line",
      start: { x: 0, y: -L },
      end: { x: 0, y: L },
      construction: true,
    },
  ];
}

/** Everything the user drew — the frame removed. */
export function withoutDatums(
  entities: readonly SketchEntity[],
): SketchEntity[] {
  return entities.filter((entity) => !isDatumId(entity.id));
}

/**
 * The entity list a CONSTRAINT VERB reasons over: what is drawn, plus the frame
 * (materialised or not), so `applyConstraintAction` can resolve a datum ref
 * before the datum exists in the buffer.
 */
export function withDatums(
  entities: readonly SketchEntity[],
  frame: DatumFrame,
): SketchEntity[] {
  const present = new Set(entities.map((e) => e.id));
  return [
    ...entities,
    ...datumEntities(frame).filter((e) => !present.has(e.id)),
  ];
}

/**
 * The pins that hold one datum entity still. Without them the frame is free
 * geometry: a coincident between a corner and the origin would be satisfied
 * just as happily by moving the ORIGIN, which would silently take the sketch's
 * zero — and every dimension measured from it — with it.
 */
export function datumPins(id: DatumKind): SketchConstraint[] {
  if (id === DATUM_ORIGIN_ID) {
    return [{ kind: "fixed", point: { entity: id, point: "position" } }];
  }
  return [
    { kind: "fixed", point: { entity: id, point: "start" } },
    { kind: "fixed", point: { entity: id, point: "end" } },
  ];
}

/**
 * Is this one of the frame's own pins? Pins are always a `fixed` on a datum
 * point, so the test is exact rather than heuristic. Used to keep them out of
 * the glyph layer and the "N applied" readout: the user authored none of them,
 * and a FIX mark standing permanently on the origin would be chrome that
 * describes the tool rather than the model.
 */
export function isDatumPin(constraint: SketchConstraint): boolean {
  return constraint.kind === "fixed" && isDatumId(constraint.point.entity);
}

/**
 * Bring into the buffer whatever part of the frame a new constraint references,
 * with its pins. Idempotent: a datum already present (drawn from a re-opened
 * sketch, or grounded earlier in this session) is left exactly as it is, so its
 * persisted geometry — not a freshly-derived one — stays authoritative.
 */
export function groundDatums(
  entities: readonly SketchEntity[],
  referenced: readonly string[],
  frame: DatumFrame,
): { entities: SketchEntity[]; constraints: SketchConstraint[] } {
  const present = new Set(entities.map((e) => e.id));
  const needed = DATUM_IDS.filter(
    (id) => referenced.includes(id) && !present.has(id),
  );
  if (needed.length === 0) return { entities: [...entities], constraints: [] };
  const byId = new Map(datumEntities(frame).map((e) => [e.id, e]));
  return {
    entities: [
      ...entities,
      ...needed.map((id) => byId.get(id) as SketchEntity),
    ],
    constraints: needed.flatMap((id) => datumPins(id)),
  };
}

/**
 * The frame's picks under a click, best first.
 *
 * The origin's grab region is the RING's disc plus the usual tolerance, not the
 * bare point tolerance — and that difference is the founder's exact gesture.
 * The ring is drawn at `ORIGIN_RING_FRACTION` of the frame half-height, which
 * is ~10 screen px from centre at the parked camera, so an 8 px point tolerance
 * measured from (0,0) misses a click that lands precisely ON the mark. The
 * thing you aim at is the thing you hit.
 *
 * An axis hits within tolerance of the span that is DRAWN (plus one tolerance
 * of overrun, so the tip is reachable), and the origin orders first because it
 * is the finer target — click-through then cycles origin -> X -> Y for someone
 * who wants the axis under the ring.
 */
export function datumPickCandidates(
  at: Point2D,
  toleranceMm: number,
  frame: DatumFrame,
): SketchPick[] {
  const out: SketchPick[] = [];
  const reach = frame.axisHalfLengthMm + toleranceMm;
  if (Math.hypot(at.x, at.y) <= frame.ringRadiusMm + toleranceMm) {
    out.push(DATUM_PICKS[DATUM_ORIGIN_ID]);
  }
  if (Math.abs(at.y) <= toleranceMm && Math.abs(at.x) <= reach) {
    out.push(DATUM_PICKS[DATUM_X_AXIS_ID]);
  }
  if (Math.abs(at.x) <= toleranceMm && Math.abs(at.y) <= reach) {
    out.push(DATUM_PICKS[DATUM_Y_AXIS_ID]);
  }
  return out;
}

/**
 * Every pick under a select-tool click — THE one picking path for select, so
 * hover and click can never disagree about what is under the pointer.
 *
 * The frame lies UNDER everything, and the two click grains want different
 * things from that:
 *
 * · A PLAIN click takes drawn geometry whenever any is in range, and the frame
 *   only where nothing drawn is. So every plain click that resolved to
 *   something before resolves to the same thing now — the change is strictly
 *   additive, reaching only the clicks that used to answer "nothing selected".
 *   In particular a plain click never CYCLES off a line into the axis beneath
 *   it: click-through exists for geometry the user stacked, not for the sheet's
 *   own datum.
 * · A MODIFIER click (the multi-select grain, and the only way to hold two
 *   points at once for a coincident) appends the frame to the candidates, so a
 *   corner already sitting on the origin can still be joined TO the origin —
 *   the second Shift-click adds the datum under the one already held.
 */
export function pickWithDatums(
  entities: readonly SketchEntity[],
  at: Point2D,
  toleranceMm: number,
  frame: DatumFrame,
  mode: "replace" | "add" = "replace",
): SketchPick[] {
  const drawn = pickCandidates(withoutDatums(entities), at, toleranceMm);
  const datums = datumPickCandidates(at, toleranceMm, frame);
  if (mode === "add") return [...drawn, ...datums];
  return drawn.length > 0 ? drawn : datums;
}

/** What the frame looks like right now, per member: the pick affordance. */
export type DatumPickState = "idle" | "hover" | "selected";

export function datumPickState(
  id: DatumKind,
  selection: readonly SketchPick[],
  hoverPick: SketchPick | null,
): DatumPickState {
  if (selection.some((pick) => datumOf(pick) === id)) return "selected";
  if (hoverPick !== null && datumOf(hoverPick) === id) return "hover";
  return "idle";
}

/** The frame member's name, in the user's words (for a11y and hints). */
export const DATUM_LABELS: Readonly<Record<DatumKind, string>> = {
  [DATUM_ORIGIN_ID]: "Origin",
  [DATUM_X_AXIS_ID]: "X axis",
  [DATUM_Y_AXIS_ID]: "Y axis",
};
