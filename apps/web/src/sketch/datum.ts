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
import type { SketchConstraint, SolveInfo } from "./constraints";
import {
  ORIGIN_AXIS_FRACTION,
  ORIGIN_RING_FRACTION,
  parkedFrameHalfHeightMm,
} from "./origin";
import { pickCandidates, samePick, type SketchPick } from "./pick";
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
 * camera's framing yet — the datum-sheet parking frame. The scene overwrites it
 * with the measured value on entry (`setDatumFrame`), so this only governs the
 * pre-mount window and the unit tests that take the default.
 *
 * It is COMPUTED from the camera's own two numbers rather than written down;
 * the literal that used to sit here read `80` under a comment claiming it was
 * this derivation, and the derivation is 61.88 mm.
 */
export const DEFAULT_FRAME_HALF_HEIGHT_MM = parkedFrameHalfHeightMm();

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
 * hover and click can never disagree about what is under the pointer. That is
 * why the STANDING SELECTION is an argument: one of the two rules below reads
 * it, and a hover that did not would promise a pick the click will not make.
 *
 * The frame lies under everything, and it is mostly INVISIBLE where it lies:
 * the axes run 1.25 × the frame half-height (`ORIGIN_AXIS_FRACTION`), i.e. a
 * cross that spans the viewport, only ±8 px of which is ink. Both rules here
 * exist to keep that cross from quietly eating a gesture aimed past it.
 *
 * · A PLAIN click takes drawn geometry whenever any is in range, and the frame
 *   only where nothing drawn is — so a plain click never cycles off a line into
 *   the axis beneath it. **And where the frame is all there is, a standing
 *   selection wins: the click CLEARS.** "Click empty space to drop the
 *   selection" is a real, constant gesture, and before the frame was selectable
 *   every one of those clicks answered nothing; letting the invisible cross
 *   convert one into "you have now selected the X axis" turns a deselect into a
 *   silent multi-select whose next verb refuses. With nothing selected there is
 *   nothing to drop, so the click means what it looks like and takes the datum.
 * · A MODIFIER click is the multi-select grain, and the only way to hold two
 *   points at once for a coincident — so the frame must be reachable under
 *   geometry the user has already picked, and reachable in the SECOND click,
 *   which is what the gesture is for. Two rules do that. Only the ORIGIN joins:
 *   it is a drawn, ~9 px, deliberately-aimed-at mark, and stacking a corner on
 *   it is how you ground a profile you snapped there, whereas a line lying
 *   along an axis is the ordinary case rather than a stack — appending the axes
 *   cost the toggle its un-pick, two Shift-clicks on such a line giving
 *   `[e1]` then `[e1, x-axis]` where the grain says `[e1]` then `[]`. And it
 *   joins where the gesture needs it: a modifier click on a point already held
 *   reaches THROUGH to the origin under it, and anywhere else it queues behind
 *   the drawn points, so starting a selection at a corner still gives you the
 *   corner.
 *   Where nothing is drawn, every member is a candidate as before.
 */
export function pickWithDatums(
  entities: readonly SketchEntity[],
  at: Point2D,
  toleranceMm: number,
  frame: DatumFrame,
  mode: "replace" | "add" = "replace",
  selection: readonly SketchPick[] = [],
): SketchPick[] {
  const drawn = pickCandidates(withoutDatums(entities), at, toleranceMm);
  const datums = datumPickCandidates(at, toleranceMm, frame);
  if (mode === "add") {
    if (drawn.length === 0) return datums;
    const points = drawn.filter((pick) => pick.kind === "point");
    const origin = datums.filter((pick) => datumOf(pick) === DATUM_ORIGIN_ID);
    // CLICK THROUGH TO THE FRAME: a modifier click on a point you are ALREADY
    // holding reaches past it to the origin underneath. Anywhere else the
    // origin queues behind the drawn points, so starting a selection at a
    // corner still gives you the corner.
    //
    // That condition is what makes the advertised gesture two clicks instead of
    // unreachable. Appended flat, the origin sat behind every drawn candidate,
    // and a rectangle corner stacks FOUR of them (two endpoints, two edges): QA
    // measured the walk as `1 pt -> 2 pts -> 1 ent · 2 pts -> 2 ents · 2 pts ->
    // 2 ents · 3 pts`, at which point `coincident` refused with "Select two
    // points to make coincident." Merely sorting the origin in with the points
    // is not enough either — the corner's SECOND endpoint takes the click, and
    // the two endpoints are already coincident with each other, so the result
    // looks right ("2 pts", constraint accepted) and grounds the corner to
    // itself. The frame was selectable and the thing it was made selectable FOR
    // could not be done with a pointer.
    const holding = points.some((pick) =>
      selection.some((held) => samePick(held, pick)),
    );
    return holding
      ? [...origin, ...drawn]
      : [...points, ...origin, ...drawn.filter((p) => p.kind === "entity")];
  }
  if (drawn.length > 0) return drawn;
  return selection.length > 0 ? [] : datums;
}

/**
 * ONE SEAM: the solve report, with every reference to a hidden constraint taken
 * out of it. Everything that asks the user to ACT on the solve — the DRO cell,
 * the diagnostic banner, the flagged-glyph set — reads the result of this, so
 * none of them can name a constraint the user cannot see.
 *
 * ## Why this exists (the SKETCH-2 review's blocking finding)
 *
 * `symmetric` about a datum axis — the marquee verb the frame's own refusal
 * hint recommends — came back `OVER-CONSTRAINED` with `redundant = [10]`,
 * pointing at the axis's SECOND pin. The geometry was right (the profile
 * centres on the axis) and the banner said "a redundant constraint is flagged
 * in the sketch. Remove it" while nothing was flagged and nothing could be:
 * pins carry no glyph by design, and `removeConstraint` is only reachable
 * through a glyph. A dead end with an ambiguous exit.
 *
 * Measured against the real solver, which is what makes the attribution
 * trustworthy rather than a guess:
 *
 * | sketch                                    | status            | redundant |
 * |-------------------------------------------|-------------------|-----------|
 * | symmetric about an UNPINNED centreline     | underconstrained  | —         |
 * | symmetric about the axis with ONE pin      | underconstrained  | —         |
 * | symmetric about the axis with BOTH pins    | overconstrained   | `[10]`    |
 * | parallel/coincident against a pinned frame | underconstrained  | —         |
 *
 * So the redundancy is CAUSED by the second pin — remove it and it is gone —
 * and pinning both ends is still right (a line fixed at one end swings). The
 * report is what was wrong, not the geometry and not the pinning.
 *
 * ## What it does, and the two things it deliberately does NOT do
 *
 * 1. Indices naming a pin are dropped from `conflicting` / `redundant`.
 * 2. An `overconstrained` whose redundancy was ENTIRELY pins is restated at the
 *    DOF the solver measured — the sketch is not over-constrained in any sense
 *    the user can act on, and the geometry solved.
 * 3. **A `conflicting` is NEVER softened.** Redundancy is a warning about a
 *    sketch that solved; a conflict is a sketch that did NOT, so silence there
 *    would hide wrong geometry. When the conflict names only pins the status
 *    stands and {@link solveDiagnostic} says where to look instead.
 * 4. **A genuine over-constraint survives**, including one that also drags a
 *    pin in. planegcs reports the WHOLE dependent set, not one member of it —
 *    measured: a duplicated coincident on a pinned sketch returns
 *    `redundant = [1]`, its own index, and a user `fixed` fighting the origin
 *    pin returns `conflicting = [0, 1, 2]`, keeping both user indices. So
 *    filtering by index removes the unreachable members and leaves the
 *    reachable ones flagged.
 *
 * The general rule this encodes, which is bigger than the bug: **if you hide a
 * constraint from the user, you must guarantee the solver can never ask them to
 * delete it.**
 */
export function datumSafeSolve(
  info: SolveInfo,
  constraints: readonly SketchConstraint[],
): SolveInfo {
  const hidden = (index: number): boolean => {
    const constraint = constraints[index];
    return constraint !== undefined && isDatumPin(constraint);
  };
  const conflicting = info.conflicting.filter((i) => !hidden(i));
  const redundant = info.redundant.filter((i) => !hidden(i));
  if (
    conflicting.length === info.conflicting.length &&
    redundant.length === info.redundant.length
  ) {
    return info;
  }
  const allPinRedundancy =
    info.status === "overconstrained" &&
    info.redundant.length > 0 &&
    redundant.length === 0;
  return {
    ...info,
    conflicting,
    redundant,
    // `dof` is the solver's own count with the redundancy already accounted
    // for, so restating from it cannot invent a number. Left alone when the
    // solver could not produce one (a negative dof arrives as null) — an
    // unattributable diagnosis is reported, not smoothed over.
    status:
      allPinRedundancy && info.dof !== null
        ? info.dof > 0
          ? "underconstrained"
          : "converged"
        : info.status,
  };
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
