/**
 * Constraint authoring + solve-feedback logic — pure functions, no store,
 * no three.js. Constraint shapes are the generated client's (pydantic →
 * OpenAPI → TS, the CLAUDE.md DRY rule); this module turns selections into
 * constraints, constraints into in-viewport glyphs (engineering-drawing
 * notation), and solver payloads into DRO feedback.
 */
import type { components } from "@loft/ts-client/gateway";

import { isDatumId, isDatumPin, selectionTouchesDatum } from "./datum";
import type { Point2D } from "./plane";
import type { SketchPick } from "./pick";
import { TOOL_SHORTCUTS, type SketchEntity } from "./tools";

export type SketchConstraint =
  components["schemas"]["SketchParamsV1"]["constraints"][number];
export type EntityPointRef = components["schemas"]["EntityPointRef"];
export type SolveStatus = components["schemas"]["SolvedSketchData"]["status"];
/**
 * One solved dimension readout, lined to its authored constraint by
 * `constraint_index`: for a DRIVING dim `value_mm` is the evaluated
 * expression/literal; for a DRIVEN dim it is measured from the solved geometry.
 */
export type SolvedDimension = components["schemas"]["SolvedDimension"];
/**
 * One solved ANGULAR readout, in degrees, on the same `constraint_index` space
 * as {@link SolvedDimension}. The contract keeps the two lists apart on purpose
 * — there is no honest millimetre value for an angle, and `value_mm` is a
 * required field every linear consumer reads unconditionally — so the merge
 * happens here, once, in {@link solvedReadouts}.
 */
export type SolvedAngle = components["schemas"]["SolvedAngle"];

/**
 * THE readout the sketcher shows for one dimension, whatever its unit — the
 * single merge point for `SolvedSketch.dimensions` + `SolvedSketch.angles`.
 *
 * QA-R2: the two wire lists were never merged, so `apps/web/src` read the
 * linear list alone and NOTHING read `angles`. An angle driven by an expression
 * therefore kept the placeholder degrees the client had guessed while the
 * solver moved the model: authored 30, re-driven `15*3`, the geometry went to
 * 45.000 and the glyph read `30°` forever. An annotation that contradicts the
 * geometry is worse than an absent one, because it looks authoritative.
 *
 * `value` is in the constraint's OWN unit and `unit` says which, so a consumer
 * cannot read degrees out of something named for millimetres — the property the
 * split existed to protect, kept without forcing every reader to merge lists.
 */
export interface SolvedReadout {
  constraint_index: number;
  driving: boolean;
  expression: string | null;
  name: string | null;
  /** The solved value in `unit`: evaluated if driving, measured if driven. */
  value: number;
  unit: "mm" | "deg";
}

/**
 * Merge the solver's two per-dimension lists into one lookup by
 * `constraint_index`. A constraint is linear or angular and never both, so an
 * index collision means the payload disagrees with itself; the LINEAR entry
 * wins and the angular one is dropped, but the unit rides along either way, so
 * the readers below still refuse a readout whose unit does not match the
 * constraint they are drawing. Silently showing the wrong unit is the failure
 * this whole split exists to prevent.
 */
export function solvedReadouts(
  dimensions: readonly SolvedDimension[],
  angles: readonly SolvedAngle[],
): Map<number, SolvedReadout> {
  const byIndex = new Map<number, SolvedReadout>();
  for (const angle of angles) {
    byIndex.set(angle.constraint_index, {
      constraint_index: angle.constraint_index,
      driving: angle.driving,
      expression: angle.expression ?? null,
      name: angle.name ?? null,
      value: angle.value_deg,
      unit: "deg",
    });
  }
  for (const dimension of dimensions) {
    byIndex.set(dimension.constraint_index, {
      constraint_index: dimension.constraint_index,
      driving: dimension.driving,
      expression: dimension.expression ?? null,
      name: dimension.name ?? null,
      value: dimension.value_mm,
      unit: "mm",
    });
  }
  return byIndex;
}

/** The readout for `index`, or undefined unless its unit is the one asked for. */
export function readoutIn(
  solved: ReadonlyMap<number, SolvedReadout> | undefined,
  index: number | null | undefined,
  unit: "mm" | "deg",
): SolvedReadout | undefined {
  if (solved === undefined || index === null || index === undefined) {
    return undefined;
  }
  const readout = solved.get(index);
  return readout?.unit === unit ? readout : undefined;
}

/** Constraint verbs — the keyboard-first strip actions. */
export type ConstraintAction =
  | "horizontal"
  | "vertical"
  | "distance"
  | "radius"
  | "diameter"
  | "angle"
  | "fixed"
  | "coincident"
  | "parallel"
  | "perpendicular"
  | "collinear"
  | "tangent"
  | "equal"
  | "symmetric"
  | "midpoint"
  | "concentric";

/**
 * Key → verb while the selection is non-empty (see `resolveSketchKey`).
 *
 * Relational verbs relating whole entities: **P** parallel (∥), **T** tangent,
 * **L** perpendicular (⊥ — the right angle reads as an "L", and L is the
 * line-tool key reused in the constraint vocabulary, the same cross-vocabulary
 * reuse H/V/D/R/X/C already lean on). The size/shape trio the 3b slice left
 * free: **E** equal (=), **S** symmetric (⟷ about an axis), **O** cOncentric
 * (◎) — E/S initial their verb; O takes coNcentric's stressed letter (C is
 * already coincident). None of E/S/O is a draw tool (tools are L/R/C/A), so
 * they only ever read as constraint verbs.
 *
 * SKETCH-VOCAB-1's five late verbs join on the same rules: **A** angle and
 * **M** midpoint initial their verb; **I** takes collInear's first free letter
 * (C/O/L/E are all spoken for), the cOncentric-O precedent. `a` and `i` are
 * also the Arc and Mirror TOOL keys, which is the H/V/D/R/C/S reuse the two
 * vocabularies already run on — selection presence decides, with no chord.
 *
 * DIAMETER GETS NO KEY OF ITS OWN, deliberately: **D is "dimension"**, and the
 * selection says which dimension it is. On a line D is the length; on a circle
 * or arc it is the diameter (`applyConstraintAction`'s `distance` arm routes
 * it). That is how every CAD tool's one Dimension verb behaves, and inventing a
 * second letter for the same intent would be vocabulary, not affordance —
 * whereas `d` on a circle previously answered "Select one line to dimension."
 */
export const CONSTRAINT_SHORTCUTS: Readonly<Record<string, ConstraintAction>> =
  {
    h: "horizontal",
    v: "vertical",
    d: "distance",
    r: "radius",
    a: "angle",
    x: "fixed",
    c: "coincident",
    p: "parallel",
    l: "perpendicular",
    i: "collinear",
    t: "tangent",
    e: "equal",
    s: "symmetric",
    m: "midpoint",
    o: "concentric",
  };

/**
 * Construction toggle verb — N (coNstruction), same selection-presence
 * pattern as the constraint verbs. Flips the selected entities between
 * profile geometry (the closed loop extrude/revolve consume) and
 * reference-only construction geometry (centerlines, mirror axes, diagonals).
 */
export const CONSTRUCTION_SHORTCUT = "n";

/**
 * One keyboard, two vocabularies: with an EMPTY selection the letters arm
 * drawing tools (L/R/C/A); with a selection they are constraint verbs
 * (H/V/D/R/X/C plus P/L/T for parallel/perpendicular/tangent, E/S/O for
 * equal/symmetric/concentric, and A/I/M for angle/collinear/midpoint) plus the
 * construction toggle (N). Selection presence is the mode — deterministic, no
 * chords.
 */
export function resolveSketchKey(
  key: string,
  hasSelection: boolean,
):
  | { type: "constraint"; action: ConstraintAction }
  | { type: "construction" }
  | { type: "tool" }
  | null {
  const lower = key.toLowerCase();
  if (hasSelection) {
    if (lower === CONSTRUCTION_SHORTCUT) return { type: "construction" };
    const action = CONSTRAINT_SHORTCUTS[lower];
    return action === undefined ? null : { type: "constraint", action };
  }
  if (TOOL_SHORTCUTS[lower] !== undefined) return { type: "tool" };
  // D WITH NOTHING SELECTED IS NOT A NO-OP ANY MORE. It used to fall through
  // to null — no tool owns `d` — so the one key the strip advertises for
  // dimensioning did literally nothing at the moment a user reaches for it
  // (right after drawing, when there is no selection and no way to make one
  // while the draw tool holds the clicks). It now hands `distance` to the
  // store, which ARMS the verb and takes the next entity click. Radius keeps
  // its selection-first path only: `r` is the Rectangle tool with an empty
  // selection, and a drawing key must never turn into a dimension key.
  return lower === "d" ? { type: "constraint", action: "distance" } : null;
}

// ---------------------------------------------------------------------------
// Constraint reconciliation — after a stateless trim/extend rewrite
// ---------------------------------------------------------------------------

/**
 * Every entity id a constraint binds to. All ids listed here MUST exist in the
 * sketch for the constraint to solve — a reference to a missing id is a
 * dangling constraint the solver rejects.
 */
export function constraintEntityRefs(constraint: SketchConstraint): string[] {
  switch (constraint.kind) {
    case "horizontal":
    case "vertical":
    case "distance":
    case "radius":
    case "diameter":
      return [constraint.entity];
    case "fixed":
      return [constraint.point.entity];
    case "coincident":
      return [constraint.a.entity, constraint.b.entity];
    case "parallel":
    case "perpendicular":
    case "tangent":
    case "equal":
    case "concentric":
    case "angle":
    case "collinear":
      // `angle` and `collinear` relate two whole lines by id like the rest of this group; its
      // VALUE lives on the constraint, not in the reference set. Listed here so
      // a deleted line takes its angle dimension with it — an angle whose line
      // is gone is a dangling reference the solver rejects.
      return [constraint.a, constraint.b];
    case "symmetric":
      return [constraint.a.entity, constraint.b.entity, constraint.line];
    case "symmetric_lines":
      return [constraint.a, constraint.b, constraint.line];
    case "midpoint":
      return [constraint.point.entity, constraint.line];
  }
}

export interface ReconcileResult {
  /** The surviving constraints, original order preserved. */
  constraints: SketchConstraint[];
  /** How many constraints were dropped (for the "N removed" readout). */
  removed: number;
}

/**
 * Reconcile the sketch's constraints against the entity set a trim/extend
 * returned. The geometry endpoint is stateless and constraint-FREE — it
 * rewrites geometry only — so a trim that DELETES an entity, or drops the
 * second (`{target}.{n}`) piece of a split, would otherwise leave constraints
 * pointing at ids that no longer exist and the next solve would error on the
 * dangling reference.
 *
 * v1 rule (pragmatic, and stated honestly in the UI copy): a constraint
 * survives iff EVERY entity id it references is still present in the result;
 * any constraint touching a vanished id is dropped. A split keeps the first
 * piece's id, so constraints on the original stay bound to that first piece —
 * we do NOT try to re-attach them to the new second piece (that would need
 * geometric intent we don't have here). Constraints do not magically follow
 * the cut; the removed count is surfaced to the user.
 */
export function reconcileConstraints(
  constraints: readonly SketchConstraint[],
  entities: readonly SketchEntity[],
): ReconcileResult {
  const ids = new Set(entities.map((e) => e.id));
  const kept = constraints.filter((c) =>
    constraintEntityRefs(c).every((id) => ids.has(id)),
  );
  return { constraints: kept, removed: constraints.length - kept.length };
}

/**
 * Toggle construction on the selection's entities (points address no curve,
 * so they are ignored). If every selected entity is already construction the
 * group reverts to profile geometry; otherwise the whole group becomes
 * construction — the familiar toggle-group rule. Returns the next entity
 * array, or null when the selection addresses no entity (the caller hints).
 */
/**
 * Which entities a construction toggle would actually flip. ONE derivation,
 * shared by the verb and by the button's pressed state, so a control that reads
 * "engaged" can never be a control that then declines: `sketch-construction`
 * rendered pressed for a datum selection and hinted "Select an entity to toggle
 * construction" when pressed, because the two answered the question separately
 * and an unmaterialised axis matches no entity, making `[].every(…)` true.
 *
 * The frame is construction by definition and is excluded here: flipping an
 * axis to profile geometry would put it in the wire that extrude consumes.
 */
function constructionTargetIds(selection: readonly SketchPick[]): Set<string> {
  return new Set(
    selection.flatMap((pick) =>
      pick.kind === "entity" && !isDatumId(pick.id) ? [pick.id] : [],
    ),
  );
}

export function toggleConstruction(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): SketchEntity[] | null {
  const ids = constructionTargetIds(selection);
  if (ids.size === 0) return null;
  const selected = entities.filter((e) => ids.has(e.id));
  const target = !selected.every((e) => e.construction);
  return entities.map((e) =>
    ids.has(e.id) ? { ...e, construction: target } : e,
  );
}

/**
 * Whether the toggle is currently ON: the selection addresses at least one
 * entity the verb would flip, and every one of them is already construction.
 * False for a selection the verb would refuse — the button is only pressed
 * where pressing it does something.
 */
export function selectionAllConstruction(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): boolean {
  const ids = constructionTargetIds(selection);
  if (ids.size === 0) return false;
  const addressed = entities.filter((e) => ids.has(e.id));
  if (addressed.length === 0) return false;
  return addressed.every((e) => e.construction);
}

/** The four dimension verbs — the ones whose value is typed, not inferred. */
export type DimensionKind = "distance" | "radius" | "diameter" | "angle";

/** Field label per dimension verb — the editor's noun and the a11y name. */
export const DIMENSION_NOUN: Readonly<Record<DimensionKind, string>> = {
  distance: "Distance",
  radius: "Radius",
  diameter: "Diameter",
  angle: "Angle",
};

/**
 * The unit the editor cell suffixes. `deg` rather than `°` in the FIELD (the
 * cell sets at 2xs, where a lone degree ring is a smudge) while the in-canvas
 * glyph keeps the drawing convention `30°` — the same split a drawing makes
 * between its title block and its annotation.
 */
export const DIMENSION_UNIT: Readonly<Record<DimensionKind, string>> = {
  distance: "mm",
  radius: "mm",
  diameter: "mm",
  angle: "deg",
};

/** A dimension editor request: which value the inline field is driving. */
export interface DimensionEditorTarget {
  kind: DimensionKind;
  /** The dimensioned entity — the FIRST line of an `angle`. */
  entity: string;
  /** The second line of an `angle`; null for the single-entity dimensions. */
  entityB: string | null;
  /** The cell's label ({@link DIMENSION_NOUN}) — never re-derived downstream. */
  noun: string;
  /** The cell's unit suffix ({@link DIMENSION_UNIT}): `mm`, or `deg`. */
  unit: string;
  /**
   * Prefill in the target's OWN unit — mm for the linear dims, DEGREES for an
   * angle. Named for the quantity, not for millimetres, because a field called
   * `initialMm` holding degrees is exactly the mislabelling `SolvedAngle` was
   * split off `SolvedDimension` to prevent.
   */
  initialValue: number;
  /** Existing expression source (`width/2`), or null for a bare literal / new. */
  initialExpression: string | null;
  /** Existing reference name, or null (unnamed / new). */
  initialName: string | null;
  /** false = driven (measured, informational); true = driving (default). */
  initialDriving: boolean;
  /** Existing constraint being edited, or null when creating a new one. */
  constraintIndex: number | null;
}

/**
 * The full spec the inline editor commits: a positive `value_mm` (the literal,
 * or a positive placeholder while an expression drives), an optional
 * `expression` (driving only — it supersedes `value_mm`), an optional reference
 * `name`, and the driving/driven flag (`false` = driven).
 */
export interface DimensionCommit {
  /** In the target's own unit — mm, or DEGREES for an `angle`. */
  value: number;
  expression: string | null;
  name: string | null;
  driving: boolean;
}

export type ConstraintActionResult =
  | { outcome: "added"; constraints: SketchConstraint[] }
  | { outcome: "editor"; target: DimensionEditorTarget }
  | {
      outcome: "hint";
      hint: string;
      /**
       * The verb was refused because the relation IS ALREADY THERE, as opposed
       * to the selection being wrong for it. The two read the same on screen
       * and are not the same event: the second is a mistake, the first is the
       * user stating something true that the tool had already inferred.
       *
       * SNAP-5 made that distinction load-bearing. Before it, pressing H on a
       * line you drew horizontal AUTHORED the constraint and bound the sketch;
       * after it, the draw has usually inferred the same fact already, so the
       * keystroke fell through to "Already horizontal." and the sketch stayed
       * unbound — the user's explicit act producing no effect at all, which is
       * the dead-end class CLAUDE.md's flow rule forbids. The store adopts
       * this flag as intent (`userConstrained`); nothing else consumes it, and
       * a consumer that ignores it behaves exactly as before.
       */
      already?: true;
    };

const hint = (text: string): ConstraintActionResult => ({
  outcome: "hint",
  hint: text,
});

/** A refusal whose cause is "you already have this" — see `already`. */
const alreadyHint = (text: string): ConstraintActionResult => ({
  outcome: "hint",
  hint: text,
  already: true,
});

/**
 * Verbs that would make the sketch frame the SUBJECT of a constraint rather
 * than its target — dimensioning an axis, making the origin "fixed" (it
 * already is), forcing an axis horizontal, calling an axis equal to an edge.
 * Every one is either redundant with the frame's own pins or an attempt to
 * move the sketch's zero.
 */
const DATUM_SUBJECT_REFUSED: ReadonlySet<ConstraintAction> = new Set([
  "horizontal",
  "vertical",
  "distance",
  "radius",
  "fixed",
  "equal",
]);

const DATUM_SUBJECT_HINT =
  "The origin and axes are fixed — constrain TO them (coincident, symmetric, parallel, perpendicular).";

function selectedLineIds(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): string[] {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const ids: string[] = [];
  for (const pick of selection) {
    if (pick.kind !== "entity") continue;
    if (byId.get(pick.id)?.kind === "line" && !ids.includes(pick.id)) {
      ids.push(pick.id);
    }
  }
  return ids;
}

/** Selected circles/arcs, in click order — the radius/diameter subjects. */
function selectedRoundIds(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): string[] {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const ids: string[] = [];
  for (const pick of selection) {
    if (pick.kind !== "entity" || ids.includes(pick.id)) continue;
    const kind = byId.get(pick.id)?.kind;
    if (kind === "circle" || kind === "arc") ids.push(pick.id);
  }
  return ids;
}

/**
 * How close to 0/180 counts as "already parallel" for the angle verb. Not a
 * geometric tolerance — the SOLVER's own domain edge, stated by
 * `AngleConstraint` (`0 < value_deg < 180`). A tenth of a degree is finer than
 * anything a user can draw by hand and coarser than any float wobble, so the
 * verb refuses exactly the selections the server would 422.
 */
const ANGLE_MIN_DEG = 0.1;

/** Selected whole-entity picks, resolved to `{ id, kind }`, in click order. */
function selectedEntities(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): Array<{ id: string; kind: SketchEntity["kind"] }> {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const out: Array<{ id: string; kind: SketchEntity["kind"] }> = [];
  for (const pick of selection) {
    if (pick.kind !== "entity") continue;
    const entity = byId.get(pick.id);
    if (entity !== undefined && !out.some((o) => o.id === entity.id)) {
      out.push({ id: entity.id, kind: entity.kind });
    }
  }
  return out;
}

const sameRef = (a: EntityPointRef, b: EntityPointRef): boolean =>
  a.entity === b.entity && a.point === b.point;

/** Structural equality — used to refuse exact duplicates. */
export function sameConstraint(
  a: SketchConstraint,
  b: SketchConstraint,
): boolean {
  if (a.kind !== b.kind) return false;
  switch (a.kind) {
    case "horizontal":
    case "vertical":
      return a.entity === (b as typeof a).entity;
    case "distance":
    case "radius":
    case "diameter":
      // A diameter and a radius on one circle are the SAME dimension in two
      // units and are mutually redundant, but they are different `kind`s, so
      // the early `a.kind !== b.kind` guard already keeps them apart here; the
      // solver reports the redundancy.
      return a.entity === (b as typeof a).entity;
    case "fixed":
      return sameRef(a.point, (b as typeof a).point);
    case "coincident": {
      const other = b as typeof a;
      return (
        (sameRef(a.a, other.a) && sameRef(a.b, other.b)) ||
        (sameRef(a.a, other.b) && sameRef(a.b, other.a))
      );
    }
    // parallel/perpendicular/tangent and equal/concentric each relate two
    // whole entities by id; every one is symmetric (order immaterial), so an
    // unordered id-pair match dedupes them.
    case "parallel":
    case "perpendicular":
    case "tangent":
    case "equal":
    case "concentric":
    case "angle":
    case "collinear": {
      // An `angle` on the same (unordered) pair is the same DIMENSION whatever
      // number it carries — dedupe by the pair, exactly as `distance` dedupes
      // by its entity rather than by its value. Two angles on one pair is the
      // over-constraint, not two different constraints.
      const other = b as typeof a;
      return (
        (a.a === other.a && a.b === other.b) ||
        (a.a === other.b && a.b === other.a)
      );
    }
    // symmetric_lines ties two whole lines about an axis: same axis, and the
    // same (unordered) line pair.
    case "symmetric_lines": {
      const other = b as typeof a;
      return (
        a.line === other.line &&
        ((a.a === other.a && a.b === other.b) ||
          (a.a === other.b && a.b === other.a))
      );
    }
    // midpoint ties ONE point to one line: same point, same line.
    case "midpoint": {
      const other = b as typeof a;
      return sameRef(a.point, other.point) && a.line === other.line;
    }
    // symmetric ties two points about a line: same axis, and the same
    // (unordered) point pair.
    case "symmetric": {
      const other = b as typeof a;
      return (
        a.line === other.line &&
        ((sameRef(a.a, other.a) && sameRef(a.b, other.b)) ||
          (sameRef(a.a, other.b) && sameRef(a.b, other.a)))
      );
    }
  }
}

const measuredLength = (entity: SketchEntity): number =>
  entity.kind === "line"
    ? Math.hypot(entity.end.x - entity.start.x, entity.end.y - entity.start.y)
    : 0;

/** A line's two named ends — the only points an angle's corner can sit on. */
type LineEnd = "start" | "end";

const isLineEnd = (point: string): point is LineEnd =>
  point === "start" || point === "end";

/**
 * The corner two lines are JOINED at, read symbolically from the sketch's own
 * `coincident` constraints — never from a coordinate-proximity test, which
 * would need an epsilon and would silently change meaning as geometry moved
 * (the rule `AngleConstraint` states, applied client-side so the number we
 * prefill is the number the solver will report back).
 */
function sharedCorner(
  a: string,
  b: string,
  constraints: readonly SketchConstraint[],
): { a: LineEnd; b: LineEnd } | null {
  for (const constraint of constraints) {
    if (constraint.kind !== "coincident") continue;
    for (const [p, q] of [
      [constraint.a, constraint.b],
      [constraint.b, constraint.a],
    ] as const) {
      if (
        p.entity === a &&
        q.entity === b &&
        isLineEnd(p.point) &&
        isLineEnd(q.point)
      ) {
        return { a: p.point, b: q.point };
      }
    }
  }
  return null;
}

/** A line's direction taken AWAY from `end` (its far end minus that end). */
function directionFrom(entity: SketchEntity, end: LineEnd | null): Point2D {
  if (entity.kind !== "line") return { x: 0, y: 0 };
  const [from, to] =
    end === "end" ? [entity.end, entity.start] : [entity.start, entity.end];
  return { x: to.x - from.x, y: to.y - from.y };
}

/**
 * The angle two selected lines currently subtend, in degrees, by
 * `AngleConstraint`'s convention: measured away from the corner they are
 * joined at when they have one (the interior angle a user sees at a profile
 * corner), else between their authored start→end directions. Unsigned, in
 * [0, 180] — the side is the geometry's, never the number's.
 */
export function measuredAngleDeg(
  a: SketchEntity,
  b: SketchEntity,
  constraints: readonly SketchConstraint[],
): number {
  const corner = sharedCorner(a.id, b.id, constraints);
  const u = directionFrom(a, corner?.a ?? null);
  const v = directionFrom(b, corner?.b ?? null);
  const scale = Math.hypot(u.x, u.y) * Math.hypot(v.x, v.y);
  if (scale === 0) return 0;
  const cos = Math.min(1, Math.max(-1, (u.x * v.x + u.y * v.y) / scale));
  return (Math.acos(cos) * 180) / Math.PI;
}

const measuredRadius = (entity: SketchEntity): number => {
  if (entity.kind === "circle") return entity.radius;
  if (entity.kind === "arc") {
    return Math.hypot(
      entity.start.x - entity.center.x,
      entity.start.y - entity.center.y,
    );
  }
  return 0;
};

/** The typed value already on a dimension constraint, in its own unit. */
export interface PriorDimension {
  value: number;
  expression: string | null;
  name: string | null;
  driving: boolean;
}

/**
 * Read a constraint's dimension fields, or null when it carries no typed value.
 * ONE reader for all four dimension kinds, so `angle`'s degrees can never be
 * picked up through a `value_mm` path.
 */
export function priorDimension(
  constraint: SketchConstraint | undefined,
): PriorDimension | null {
  if (constraint === undefined) return null;
  switch (constraint.kind) {
    case "distance":
    case "radius":
    case "diameter":
      return {
        value: constraint.value_mm,
        expression: constraint.expression ?? null,
        name: constraint.name ?? null,
        driving: constraint.driving !== false,
      };
    case "angle":
      return {
        value: constraint.value_deg,
        expression: constraint.expression ?? null,
        name: constraint.name ?? null,
        driving: constraint.driving !== false,
      };
    default:
      return null;
  }
}

const targetOf = (
  kind: DimensionKind,
  entity: string,
  entityB: string | null,
  prior: PriorDimension,
  constraintIndex: number | null,
): DimensionEditorTarget => ({
  kind,
  entity,
  entityB,
  noun: DIMENSION_NOUN[kind],
  unit: DIMENSION_UNIT[kind],
  initialValue: prior.value,
  initialExpression: prior.expression,
  initialName: prior.name,
  initialDriving: prior.driving,
  constraintIndex,
});

/**
 * A dimension verb's answer: open the inline editor on the target, prefilled
 * from the dimension already there (so pressing the verb twice EDITS rather
 * than stacking a second, redundant dimension) or from the measured geometry.
 */
function dimensionEditor(
  kind: DimensionKind,
  entity: string,
  entityB: string | null,
  measured: number,
  constraints: readonly SketchConstraint[],
): ConstraintActionResult {
  // The probe's value is immaterial: `sameConstraint` dedupes a dimension by
  // its SUBJECT (the entity, or the unordered line pair), never by its number.
  const probe: SketchConstraint =
    kind === "angle"
      ? { kind, a: entity, b: entityB ?? entity, value_deg: measured }
      : { kind, entity, value_mm: measured };
  const index = constraints.findIndex((c) => sameConstraint(c, probe));
  const prior = priorDimension(
    index === -1 ? undefined : constraints[index],
  ) ?? {
    value: measured,
    expression: null,
    name: null,
    driving: true,
  };
  return {
    outcome: "editor",
    target: targetOf(kind, entity, entityB, prior, index === -1 ? null : index),
  };
}

/** Open the editor on an EXISTING dimension (a glyph click, not a verb). */
export function dimensionEditorTarget(
  constraint: SketchConstraint,
  constraintIndex: number,
): DimensionEditorTarget | null {
  const prior = priorDimension(constraint);
  if (prior === null) return null;
  switch (constraint.kind) {
    case "distance":
    case "radius":
    case "diameter":
      return targetOf(
        constraint.kind,
        constraint.entity,
        null,
        prior,
        constraintIndex,
      );
    case "angle":
      return targetOf(
        "angle",
        constraint.a,
        constraint.b,
        prior,
        constraintIndex,
      );
    default:
      return null;
  }
}

/**
 * Apply a constraint verb to the current selection. Dimensions (distance /
 * radius / diameter / angle) answer with an inline-editor request instead of a
 * constraint — the value drives, so the value gets typed. Invalid selections
 * answer with a hint, never silence.
 */
export function applyConstraintAction(
  action: ConstraintAction,
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): ConstraintActionResult {
  const byId = new Map(entities.map((e) => [e.id, e]));
  // THE SKETCH FRAME IS A TARGET, NOT A SUBJECT (SKETCH-2). The origin and the
  // two axes are selectable so a profile can be GROUNDED to them — coincident,
  // symmetric, parallel, perpendicular. The verbs that would DRIVE the frame
  // instead are refused here rather than silently fighting its pins: they
  // would author a constraint the solver must then reconcile against a fixed
  // point, and the honest answer to "dimension the X axis" is that the axis is
  // not yours to move.
  if (DATUM_SUBJECT_REFUSED.has(action) && selectionTouchesDatum(selection)) {
    return hint(DATUM_SUBJECT_HINT);
  }
  switch (action) {
    case "horizontal":
    case "vertical": {
      const lines = selectedLineIds(selection, entities);
      if (lines.length === 0) {
        return hint(`Select a line to make ${action}.`);
      }
      const added: SketchConstraint[] = [];
      for (const entity of lines) {
        const constraint: SketchConstraint = { kind: action, entity };
        if (!constraints.some((c) => sameConstraint(c, constraint))) {
          added.push(constraint);
        }
      }
      if (added.length === 0) return alreadyHint(`Already ${action}.`);
      return { outcome: "added", constraints: added };
    }
    case "distance": {
      const lines = selectedLineIds(selection, entities);
      const entity = lines[0];
      if (lines.length !== 1 || entity === undefined) {
        // D IS "DIMENSION", AND THE SELECTION SAYS WHICH ONE. A round under D
        // used to answer "Select one line to dimension." — a refusal aimed at
        // someone who had already said exactly what they wanted to dimension,
        // and the reason `diameter` shipped in the contract unreachable. Fall
        // through to the diameter arm before refusing.
        const rounds = selectedRoundIds(selection, entities);
        if (lines.length === 0 && rounds.length === 1) {
          return applyConstraintAction(
            "diameter",
            selection,
            entities,
            constraints,
          );
        }
        return hint("Select one line to dimension.");
      }
      return dimensionEditor(
        "distance",
        entity,
        null,
        measuredLength(byId.get(entity) as SketchEntity),
        constraints,
      );
    }
    case "radius":
    case "diameter": {
      const rounds = selectedRoundIds(selection, entities);
      const entity = rounds[0];
      if (rounds.length !== 1 || entity === undefined) {
        return hint(`Select one circle or arc to dimension the ${action}.`);
      }
      const measured = measuredRadius(byId.get(entity) as SketchEntity);
      return dimensionEditor(
        action,
        entity,
        null,
        action === "diameter" ? measured * 2 : measured,
        constraints,
      );
    }
    case "angle": {
      const lines = selectedLineIds(selection, entities);
      const [a, b] = lines;
      if (lines.length !== 2 || a === undefined || b === undefined) {
        return hint("Select two lines to dimension the angle between them.");
      }
      const measured = measuredAngleDeg(
        byId.get(a) as SketchEntity,
        byId.get(b) as SketchEntity,
        constraints,
      );
      // The contract's own bound: `value_deg` is strictly inside (0, 180),
      // because the open ends ARE the parallel degeneracy and a single
      // unsigned number cannot say which side b sits on. Name the verb that
      // does own that case instead of letting the server 422.
      if (measured < ANGLE_MIN_DEG || measured > 180 - ANGLE_MIN_DEG) {
        return hint(
          "These lines are already parallel — use Parallel (P), or move one line off the other's direction first.",
        );
      }
      return dimensionEditor("angle", a, b, measured, constraints);
    }
    case "collinear": {
      const lines = selectedLineIds(selection, entities);
      const [a, b] = lines;
      if (lines.length !== 2 || a === undefined || b === undefined) {
        return hint("Select two lines to put them on one line.");
      }
      const constraint: SketchConstraint = { kind: "collinear", a, b };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already collinear.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "midpoint": {
      const points = selection.filter((pick) => pick.kind === "point");
      const point = points[0];
      const lines = selectedLineIds(selection, entities);
      const line = lines[0];
      if (points.length !== 1 || point === undefined) {
        return hint("Select one point and one line to centre the point on it.");
      }
      if (lines.length !== 1 || line === undefined) {
        return hint(
          "Midpoint needs one line for the point to sit halfway along.",
        );
      }
      if (point.entity === line) {
        return hint(
          "Pick a point on OTHER geometry — a line's own end cannot be its middle.",
        );
      }
      const constraint: SketchConstraint = {
        kind: "midpoint",
        point: { entity: point.entity, point: point.point },
        line,
      };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already at the midpoint.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "fixed": {
      const points = selection.filter((pick) => pick.kind === "point");
      if (points.length === 0) return hint("Select a point to fix.");
      const added: SketchConstraint[] = [];
      for (const pick of points) {
        const constraint: SketchConstraint = {
          kind: "fixed",
          point: { entity: pick.entity, point: pick.point },
        };
        if (!constraints.some((c) => sameConstraint(c, constraint))) {
          added.push(constraint);
        }
      }
      if (added.length === 0) return alreadyHint("Already fixed.");
      return { outcome: "added", constraints: added };
    }
    case "coincident": {
      const points = selection.filter((pick) => pick.kind === "point");
      const [a, b] = points;
      if (points.length !== 2 || a === undefined || b === undefined) {
        return hint("Select two points to make coincident.");
      }
      if (a.entity === b.entity && a.point === b.point) {
        return hint("Pick two different points.");
      }
      const constraint: SketchConstraint = {
        kind: "coincident",
        a: { entity: a.entity, point: a.point },
        b: { entity: b.entity, point: b.point },
      };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already coincident.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "parallel":
    case "perpendicular": {
      const lines = selectedLineIds(selection, entities);
      const [a, b] = lines;
      if (lines.length !== 2 || a === undefined || b === undefined) {
        return hint(`Select two lines to make ${action}.`);
      }
      const constraint: SketchConstraint = { kind: action, a, b };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint(`Already ${action}.`);
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "tangent": {
      const curves = selectedEntities(selection, entities).filter(
        (e) => e.kind === "line" || e.kind === "circle" || e.kind === "arc",
      );
      const [a, b] = curves;
      if (curves.length !== 2 || a === undefined || b === undefined) {
        return hint(
          "Select two curves — a line and an arc/circle, or two curves — to make tangent.",
        );
      }
      if (a.kind === "line" && b.kind === "line") {
        return hint("Two lines can't be tangent — pick an arc or circle.");
      }
      const constraint: SketchConstraint = {
        kind: "tangent",
        a: a.id,
        b: b.id,
      };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already tangent.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "equal": {
      const picks = selectedEntities(selection, entities).filter(
        (e) => e.kind === "line" || e.kind === "circle" || e.kind === "arc",
      );
      const [a, b] = picks;
      if (picks.length !== 2 || a === undefined || b === undefined) {
        return hint("Select two lines, or two circles/arcs, to make equal.");
      }
      const aRound = a.kind === "circle" || a.kind === "arc";
      const bRound = b.kind === "circle" || b.kind === "arc";
      // Equal length (two lines) or equal radius (two rounds) — never mixed.
      if (!((a.kind === "line" && b.kind === "line") || (aRound && bRound))) {
        return hint(
          "Equal needs two of a kind — two lines, or two circles/arcs.",
        );
      }
      const constraint: SketchConstraint = { kind: "equal", a: a.id, b: b.id };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already equal.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "concentric": {
      const rounds = selectedEntities(selection, entities).filter(
        (e) => e.kind === "circle" || e.kind === "arc",
      );
      const [a, b] = rounds;
      if (rounds.length !== 2 || a === undefined || b === undefined) {
        return hint("Select two circles or arcs to make concentric.");
      }
      const constraint: SketchConstraint = {
        kind: "concentric",
        a: a.id,
        b: b.id,
      };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already concentric.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "symmetric": {
      const points = selection.filter((pick) => pick.kind === "point");
      const lines = selectedLineIds(selection, entities);
      // TWO LINES ABOUT A CENTERLINE IS THE COMMON CASE, and until now it was
      // the one selection this verb REFUSED — "Select two points and a line"
      // answered to someone holding exactly the mirrored pair a symmetric
      // profile is made of (docs/AUDIT-PRODUCT.md; `symmetric_lines` shipped in
      // the contract with no way to author it). The axis is the CONSTRUCTION
      // line in the selection — a centerline or a datum axis, both construction
      // by definition — which also disambiguates without asking for click
      // order: profile geometry is the pair, reference geometry is the mirror.
      if (points.length === 0 && lines.length === 3) {
        const byLine = new Map(entities.map((e) => [e.id, e]));
        const axes = lines.filter(
          (id) => byLine.get(id)?.construction === true,
        );
        const line = axes[0];
        if (axes.length !== 1 || line === undefined) {
          return hint(
            "Mark the mirror line as construction (N) — the centerline is what the other two are symmetric about.",
          );
        }
        const [a, b] = lines.filter((id) => id !== line);
        if (a === undefined || b === undefined) {
          return hint("Select two lines and the centerline between them.");
        }
        const constraint: SketchConstraint = {
          kind: "symmetric_lines",
          a,
          b,
          line,
        };
        if (constraints.some((c) => sameConstraint(c, constraint))) {
          return alreadyHint("Already symmetric about that line.");
        }
        return { outcome: "added", constraints: [constraint] };
      }
      const [a, b] = points;
      if (points.length !== 2 || a === undefined || b === undefined) {
        return hint(
          "Select two points and a line — or two lines and a centerline — to make symmetric.",
        );
      }
      const line = lines[0];
      if (lines.length !== 1 || line === undefined) {
        return hint(
          "Symmetric needs one line for the mirror axis — a construction centerline reads cleanest.",
        );
      }
      if (a.entity === b.entity && a.point === b.point) {
        return hint("Pick two different points.");
      }
      const constraint: SketchConstraint = {
        kind: "symmetric",
        a: { entity: a.entity, point: a.point },
        b: { entity: b.entity, point: b.point },
        line,
      };
      if (constraints.some((c) => sameConstraint(c, constraint))) {
        return alreadyHint("Already symmetric about that line.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
  }
}

// ---------------------------------------------------------------------------
// Glyphs — in-viewport engineering-drawing notation
// ---------------------------------------------------------------------------

/** One constraint rendered as annotation ink near its geometry. */
export interface ConstraintGlyph {
  /** Index into the sketch's constraint list (the solver's index space). */
  index: number;
  kind: SketchConstraint["kind"];
  /** Bare mono text: "H", "V", "C", "FIX", "40", "R12.5", "(40)" (driven). */
  label: string;
  /** Anchor in sketch-plane mm. */
  anchor: Point2D;
  /** Dimensions open the inline editor on click; others select. */
  editable: boolean;
  /**
   * A DRIVEN (reference) dimension — measured from geometry, not fed to the
   * solver. Rendered in the drawing's reference notation (parentheses, quiet
   * ink), never brass. False for driving dims and every geometric constraint.
   */
  driven: boolean;
  /** The dimension's expression source, echoed for tooltips/a11y (or null). */
  expression: string | null;
}

/** Dimension text: trailing zeros trimmed, mm implied (drawing convention). */
export function formatDimensionMm(value: number): string {
  const text = value.toFixed(2).replace(/\.?0+$/, "");
  return text === "" || text === "-" ? "0" : text;
}

/**
 * A dimension glyph's label, in the drawing's own notation: a length is bare
 * ("40"), a radius takes the R prefix ("R12.5"), a diameter the ⌀ ring
 * ("⌀25"), an angle the degree ring ("30°"). DRIVEN (reference) dims wear the
 * drafting convention — parentheses, "(40)" — so a measured, informational
 * value is never mistaken for a driving one.
 */
export function formatDimensionLabel(
  kind: DimensionKind,
  value: number,
  driven: boolean,
): string {
  const text = formatDimensionMm(value);
  const core =
    kind === "radius"
      ? `R${text}`
      : kind === "diameter"
        ? `⌀${text}`
        : kind === "angle"
          ? `${text}°`
          : text;
  return driven ? `(${core})` : core;
}

function lineAnnotationAnchor(entity: SketchEntity, offsetMm: number): Point2D {
  if (entity.kind !== "line") return { x: 0, y: 0 };
  const mid = {
    x: (entity.start.x + entity.end.x) / 2,
    y: (entity.start.y + entity.end.y) / 2,
  };
  const dx = entity.end.x - entity.start.x;
  const dy = entity.end.y - entity.start.y;
  const length = Math.hypot(dx, dy);
  if (length === 0) return mid;
  // Left-hand normal: H/V sit on one side, dimensions on the other.
  return {
    x: mid.x + (-dy / length) * offsetMm,
    y: mid.y + (dx / length) * offsetMm,
  };
}

function pointOf(
  ref: EntityPointRef,
  byId: ReadonlyMap<string, SketchEntity>,
): Point2D {
  const entity = byId.get(ref.entity);
  if (entity === undefined) return { x: 0, y: 0 };
  switch (ref.point) {
    case "position":
      return entity.kind === "point" ? entity.position : { x: 0, y: 0 };
    case "center":
      return entity.kind === "circle" || entity.kind === "arc"
        ? entity.center
        : { x: 0, y: 0 };
    case "start":
      return entity.kind === "line" || entity.kind === "arc"
        ? entity.start
        : { x: 0, y: 0 };
    case "end":
      return entity.kind === "line" || entity.kind === "arc"
        ? entity.end
        : { x: 0, y: 0 };
    default: {
      // A spline fit point ("fit0", "fit1", …) resolves to its Nth fit
      // coordinate (EntityPointRef contract, constrainable-splines backend
      // leg). Keeps this annotation-anchor helper total now that `point`
      // widened past the fixed named points; the fit-point pick/constrain UI
      // is a separate follow-up.
      const fit = /^fit(0|[1-9][0-9]*)$/.exec(ref.point);
      if (fit && entity.kind === "spline") {
        return entity.points[Number(fit[1])] ?? { x: 0, y: 0 };
      }
      return { x: 0, y: 0 };
    }
  }
}

function radiusAnchor(entity: SketchEntity, offsetMm: number): Point2D {
  if (entity.kind === "circle") {
    const r = entity.radius + offsetMm;
    const cos45 = Math.SQRT1_2;
    return {
      x: entity.center.x + r * cos45,
      y: entity.center.y + r * cos45,
    };
  }
  if (entity.kind === "arc") {
    const radius = Math.hypot(
      entity.start.x - entity.center.x,
      entity.start.y - entity.center.y,
    );
    const startAngle = Math.atan2(
      entity.start.y - entity.center.y,
      entity.start.x - entity.center.x,
    );
    const endAngle = Math.atan2(
      entity.end.y - entity.center.y,
      entity.end.x - entity.center.x,
    );
    let sweep = endAngle - startAngle;
    if (sweep <= 0) sweep += Math.PI * 2;
    const mid = startAngle + sweep / 2;
    const r = radius + offsetMm;
    return {
      x: entity.center.x + r * Math.cos(mid),
      y: entity.center.y + r * Math.sin(mid),
    };
  }
  return { x: 0, y: 0 };
}

/** A representative annotation anchor near any entity's ink (lines: midpoint
 * normal; rounds: the radius mark) — where a relational glyph (∥/⊥/T) sits. */
function entityGlyphAnchor(entity: SketchEntity, offsetMm: number): Point2D {
  if (entity.kind === "line") return lineAnnotationAnchor(entity, offsetMm);
  if (entity.kind === "circle" || entity.kind === "arc") {
    return radiusAnchor(entity, offsetMm);
  }
  // A v1 spline carries no relational glyphs (non-constrained); only bare
  // points reach here with a meaningful anchor.
  if (entity.kind === "point") {
    return { x: entity.position.x + offsetMm, y: entity.position.y + offsetMm };
  }
  return { x: 0, y: 0 };
}

/**
 * Where an angle dimension is written: just inside the wedge, on the bisector
 * of the corner the two lines share — exactly where a draughtsman puts it,
 * because that is the only place the number is unambiguous about WHICH of the
 * two supplementary angles it names. With no shared corner (two free lines)
 * it falls back to the midpoint between the two lines' own marks.
 */
function angleAnchor(
  a: SketchEntity,
  b: SketchEntity,
  constraints: readonly SketchConstraint[],
  offsetMm: number,
): Point2D {
  const corner = sharedCorner(a.id, b.id, constraints);
  if (corner === null || a.kind !== "line" || b.kind !== "line") {
    const pa = entityGlyphAnchor(a, offsetMm);
    const pb = entityGlyphAnchor(b, offsetMm);
    return { x: (pa.x + pb.x) / 2, y: (pa.y + pb.y) / 2 };
  }
  const at = corner.a === "end" ? a.end : a.start;
  const u = directionFrom(a, corner.a);
  const v = directionFrom(b, corner.b);
  const nu = Math.hypot(u.x, u.y);
  const nv = Math.hypot(v.x, v.y);
  if (nu === 0 || nv === 0) return { x: at.x + offsetMm, y: at.y + offsetMm };
  const bx = u.x / nu + v.x / nv;
  const by = u.y / nu + v.y / nv;
  const nb = Math.hypot(bx, by);
  // Anti-parallel legs leave no bisector; the angle verb refuses that case, so
  // this only guards a constraint authored before the lines moved.
  if (nb === 0) return { x: at.x + offsetMm, y: at.y + offsetMm };
  // Three glyph offsets out along the bisector: far enough clear of the corner
  // vertex (where the coincident C mark already sits) to read as its own text.
  const reach = offsetMm * 3;
  return { x: at.x + (bx / nb) * reach, y: at.y + (by / nb) * reach };
}

/**
 * Whole-entity relational marks — engineering-drawing notation, one bare
 * mono glyph each. Equal is the `=` sign; concentric is the bullseye ◎ (a
 * circle inside a circle — the relation drawn as its own picture).
 */
const RELATIONAL_LABEL: Record<
  | "parallel"
  | "perpendicular"
  | "tangent"
  | "equal"
  | "concentric"
  | "collinear",
  string
> = {
  parallel: "∥",
  perpendicular: "⊥",
  tangent: "T",
  equal: "=",
  concentric: "◎",
  // Collinear has no single-character drawing sign the way ∥ and ⊥ do, so it
  // takes the two-letter stamp FIX already established rather than an invented
  // pictograph nobody would read.
  collinear: "CL",
};

/**
 * Constraints → annotation glyphs at their current (solved) geometry.
 * Letters and numbers only — Fragment Mono native, no icon font, no badge.
 *
 * `solved` (keyed by `constraint_index`, built by {@link solvedReadouts}) carries
 * the per-dimension solve readouts in their own units: a driving dim shows its
 * EVALUATED value (an expression `width/2` reads as `10`, `15*3` as `45°`), a
 * driven dim its MEASURED value in reference parentheses. Pre-solve (no map)
 * the glyph falls back to the authored `value_mm` / `value_deg` and flag.
 */
export function constraintGlyphs(
  constraints: readonly SketchConstraint[],
  entities: readonly SketchEntity[],
  offsetMm: number,
  solved?: ReadonlyMap<number, SolvedReadout>,
): ConstraintGlyph[] {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const glyphs: ConstraintGlyph[] = [];
  /** Every geometric (non-dimension) mark is driving-agnostic ink. */
  const geometric = { driven: false, expression: null } as const;
  constraints.forEach((constraint, index) => {
    // The sketch frame's own pins carry no glyph: the user authored none of
    // them, and a FIX mark standing permanently on the origin would be chrome
    // describing the tool rather than the model (CLAUDE.md mandate 3a).
    if (isDatumPin(constraint)) return;
    switch (constraint.kind) {
      case "horizontal":
      case "vertical": {
        const entity = byId.get(constraint.entity);
        if (entity === undefined) return;
        glyphs.push({
          index,
          kind: constraint.kind,
          label: constraint.kind === "horizontal" ? "H" : "V",
          anchor: lineAnnotationAnchor(entity, offsetMm),
          editable: false,
          ...geometric,
        });
        return;
      }
      case "distance":
      case "radius":
      case "diameter": {
        const entity = byId.get(constraint.entity);
        if (entity === undefined) return;
        const readout = readoutIn(solved, index, "mm");
        const driven =
          readout !== undefined
            ? !readout.driving
            : constraint.driving === false;
        const value = readout?.value ?? constraint.value_mm;
        glyphs.push({
          index,
          kind: constraint.kind,
          label: formatDimensionLabel(constraint.kind, value, driven),
          // Opposite side from H/V marks — annotations never stack.
          anchor:
            constraint.kind === "distance"
              ? lineAnnotationAnchor(entity, -offsetMm)
              : radiusAnchor(entity, offsetMm),
          editable: true,
          driven,
          expression: readout?.expression ?? constraint.expression ?? null,
        });
        return;
      }
      case "angle": {
        const a = byId.get(constraint.a);
        const b = byId.get(constraint.b);
        if (a === undefined || b === undefined) return;
        // Degrees ride `SolvedSketch.angles` and reach this builder through the
        // SAME merged map as the linear readouts (`readoutIn` refuses a
        // millimetre reading here, so the split's guarantee is kept by the
        // lookup rather than by withholding the list). QA-R2: without it the
        // label was the authored `value_deg` — true for a bare literal, and a
        // LIE for an expression or a reference angle, where the solver holds a
        // value the client never computed. Pre-solve it still falls back to the
        // authored number, which is the best available reading then.
        const readout = readoutIn(solved, index, "deg");
        const driven =
          readout !== undefined
            ? !readout.driving
            : constraint.driving === false;
        glyphs.push({
          index,
          kind: "angle",
          label: formatDimensionLabel(
            "angle",
            readout?.value ?? constraint.value_deg,
            driven,
          ),
          anchor: angleAnchor(a, b, constraints, offsetMm),
          editable: true,
          driven,
          expression: readout?.expression ?? constraint.expression ?? null,
        });
        return;
      }
      case "fixed": {
        const at = pointOf(constraint.point, byId);
        glyphs.push({
          index,
          kind: "fixed",
          label: "FIX",
          anchor: { x: at.x + offsetMm, y: at.y - offsetMm },
          editable: false,
          ...geometric,
        });
        return;
      }
      case "coincident": {
        const at = pointOf(constraint.a, byId);
        glyphs.push({
          index,
          kind: "coincident",
          label: "C",
          anchor: { x: at.x + offsetMm, y: at.y + offsetMm },
          editable: false,
          ...geometric,
        });
        return;
      }
      case "parallel":
      case "perpendicular":
      case "tangent":
      case "equal":
      case "concentric":
      case "collinear": {
        // Anchor on the first entity of the pair; skip if it's gone mid-edit.
        const entity = byId.get(constraint.a);
        if (entity === undefined) return;
        glyphs.push({
          index,
          kind: constraint.kind,
          label: RELATIONAL_LABEL[constraint.kind],
          anchor: entityGlyphAnchor(entity, offsetMm),
          editable: false,
          ...geometric,
        });
        return;
      }
      case "symmetric": {
        // The mark sits at the midpoint of the mirrored pair — which lies on
        // the axis once solved — nudged clear of the centerline. Skip if
        // either point's entity is gone mid-edit.
        if (!byId.has(constraint.a.entity) || !byId.has(constraint.b.entity)) {
          return;
        }
        const pa = pointOf(constraint.a, byId);
        const pb = pointOf(constraint.b, byId);
        glyphs.push({
          index,
          kind: "symmetric",
          label: "⟷",
          anchor: {
            x: (pa.x + pb.x) / 2 + offsetMm,
            y: (pa.y + pb.y) / 2 + offsetMm,
          },
          editable: false,
          ...geometric,
        });
        return;
      }
      case "symmetric_lines": {
        // Same relation, same ⟷ mark as the point-pair symmetric — a user who
        // learned the sign on one reads it on the other. It sits between the
        // two mirrored lines' midpoints, i.e. on the axis once solved.
        const a = byId.get(constraint.a);
        const b = byId.get(constraint.b);
        if (a === undefined || b === undefined) return;
        const pa = entityGlyphAnchor(a, 0);
        const pb = entityGlyphAnchor(b, 0);
        glyphs.push({
          index,
          kind: "symmetric_lines",
          label: "⟷",
          anchor: {
            x: (pa.x + pb.x) / 2,
            y: (pa.y + pb.y) / 2 + offsetMm,
          },
          editable: false,
          ...geometric,
        });
        return;
      }
      case "midpoint": {
        if (!byId.has(constraint.point.entity) || !byId.has(constraint.line)) {
          return;
        }
        const at = pointOf(constraint.point, byId);
        glyphs.push({
          index,
          kind: "midpoint",
          label: "M",
          anchor: { x: at.x + offsetMm, y: at.y - offsetMm },
          editable: false,
          ...geometric,
        });
        return;
      }
    }
  });
  return glyphs;
}

/**
 * Anchor for a dimension editor opened on an entity with no constraint yet.
 * The editor opens exactly where the glyph will land, so applying a value
 * never moves the number the user was just looking at.
 */
export function dimensionEditorAnchor(
  target: DimensionEditorTarget,
  entities: readonly SketchEntity[],
  offsetMm: number,
  constraints: readonly SketchConstraint[] = [],
): Point2D {
  const entity = entities.find((e) => e.id === target.entity);
  if (entity === undefined) return { x: 0, y: 0 };
  if (target.kind === "distance")
    return lineAnnotationAnchor(entity, -offsetMm);
  if (target.kind !== "angle") return radiusAnchor(entity, offsetMm);
  const other = entities.find((e) => e.id === target.entityB);
  if (other === undefined) return entityGlyphAnchor(entity, offsetMm);
  return angleAnchor(entity, other, constraints, offsetMm);
}

// ---------------------------------------------------------------------------
// Solve feedback
// ---------------------------------------------------------------------------

/**
 * The DRO/diagnostic view of one evaluate round-trip for the bound sketch.
 * `"invalid"` is the sketcher's local status for a `sketch_invalid` feature
 * error (bad expression / cycle / unknown or driven reference / div-by-zero) —
 * the sketch didn't solve at all, so it has no solver status; `message` carries
 * the server's descriptive text for the diagnostic stamp.
 */
export interface SolveInfo {
  status: SolveStatus | "invalid";
  dof: number | null;
  conflicting: number[];
  redundant: number[];
  /** The `sketch_invalid` message when `status === "invalid"`; else absent. */
  message?: string;
}

// Conflicting sketches now carry their offending constraint ids in the TYPED
// `FeatureError.sketch_diagnosis` field (BACKLOG #6), read directly in
// PartPage — the former `parseConflictIndices` regex over the human message
// was removed once the backend promoted the ids to a structured field.

/** DRO SOLVE cell: value text + ink. Status vocabulary stays terse (DRO). */
export function formatSolveCell(
  info: SolveInfo | null,
  busy: boolean,
): { value: string; tone: "brass" | "mist" | "flag" | "gauge" } {
  if (busy) return { value: "SOLVING…", tone: "gauge" };
  if (info === null) return { value: "—", tone: "gauge" };
  switch (info.status) {
    case "converged":
      return { value: "DOF 0 · CONVERGED", tone: "brass" };
    case "underconstrained":
      return {
        value: `DOF ${info.dof ?? "?"} · UNDER-CONSTRAINED`,
        tone: "mist",
      };
    case "overconstrained":
      return { value: "OVER-CONSTRAINED", tone: "flag" };
    case "conflicting":
      return { value: "CONFLICT", tone: "flag" };
    case "diverged":
      return { value: "DIVERGED", tone: "flag" };
    case "invalid":
      return { value: "INVALID EXPRESSION", tone: "flag" };
  }
}

/** The in-viewport diagnostic stamp for a sick solve; null when healthy. */
export function solveDiagnostic(
  info: SolveInfo | null,
): { title: string; body: string } | null {
  if (info === null) return null;
  switch (info.status) {
    case "conflicting":
      return {
        title: "Solve conflict",
        body:
          info.conflicting.length > 0
            ? `${info.conflicting.length} constraints cannot all hold — they are flagged in the sketch. Remove or edit one.`
            : // Nothing is flagged, so do not claim there is. The solver
              // located the conflict only in constraints the user cannot
              // reach — in practice the frame's own pins, which are the only
              // hidden constraints there are (`sketch/datum.ts`). Never
              // silenced: a conflicting sketch did not solve, so the geometry
              // on screen is wrong and saying so is mandatory. Point at the
              // one place it can be, instead of at a flag that is not there.
              "The constraints cannot all hold, and the conflict is with the origin and axes — the frame cannot move. Remove or edit a constraint that reaches for it.",
      };
    case "overconstrained":
      return {
        title: "Over-constrained",
        body:
          info.redundant.length > 0
            ? "A redundant constraint is flagged in the sketch. Remove it — the geometry is already determined without it."
            : "The sketch has one constraint more than it needs, and the solver could not say which. Remove the last one you added.",
      };
    case "invalid":
      return {
        title: "Dimension expression",
        body:
          info.message ??
          "A dimension expression could not be evaluated. Check the names it references, and for cycles or division by zero.",
      };
    case "diverged":
      return {
        title: "Solve diverged",
        body: "The solver could not converge from the current positions. Edit a dimension or remove the last constraint.",
      };
    default:
      return null;
  }
}

/**
 * Constraints the USER authored — the frame's pins excluded. The "N applied"
 * readout counts these: grounding a corner to the origin is one constraint the
 * user made, and reporting the pin that came with it would be the readout
 * claiming work nobody did.
 */
export function authoredConstraintCount(
  constraints: readonly SketchConstraint[],
): number {
  return constraints.filter((c) => !isDatumPin(c)).length;
}

/** Short selection readout for the constraint strip ("1 line · 2 pts"). */
export function describeSelection(selection: readonly SketchPick[]): string {
  const entities = selection.filter((p) => p.kind === "entity").length;
  const points = selection.length - entities;
  if (selection.length === 0) return "nothing selected";
  const parts: string[] = [];
  if (entities > 0)
    parts.push(`${entities} ${entities === 1 ? "ent" : "ents"}`);
  if (points > 0) parts.push(`${points} ${points === 1 ? "pt" : "pts"}`);
  return parts.join(" · ");
}

/** A surfaced keyboard verb — the key to press and its plain-verb label. */
export interface SketchVerbHint {
  key: string;
  label: string;
  /** The verb the key runs, so the keycap can also be CLICKED to run it. */
  action: ConstraintAction;
}

/**
 * The verbs the offer rail may propose, MOST SPECIFIC FIRST.
 *
 * Order is the whole design. Every verb below is already reachable by key, and
 * a list of everything the selection accepts would be a menu — which is the
 * thing the user was already failing to read. So the rail proposes the verbs
 * that this PARTICULAR selection unlocks and a general toolbar cannot: the
 * dimension the selection implies, then the relations that need a specific
 * shape of pick (an angle needs two lines; symmetric needs a centerline in the
 * selection). The broad relations that apply to almost any pair — parallel,
 * perpendicular, equal — come last and usually fall off the end.
 */
const VERB_OFFER_ORDER: readonly ConstraintAction[] = [
  "angle",
  // Diameter before distance: on a round, D routes to diameter, so both verbs
  // accept the same selection and the more specific label must win the key.
  "diameter",
  "distance",
  "radius",
  "collinear",
  "symmetric",
  "midpoint",
  "concentric",
  "tangent",
  "equal",
  "parallel",
  "perpendicular",
];

/** Plain-verb labels — what the user is about to do, in their words. */
const VERB_LABEL: Readonly<Record<ConstraintAction, string>> = {
  horizontal: "horizontal",
  vertical: "vertical",
  distance: "dimension",
  radius: "radius",
  diameter: "diameter",
  angle: "angle",
  fixed: "fix",
  coincident: "join",
  parallel: "parallel",
  perpendicular: "perpendicular",
  collinear: "collinear",
  tangent: "tangent",
  equal: "equal",
  symmetric: "symmetric",
  midpoint: "midpoint",
  concentric: "concentric",
};

/**
 * The key a verb answers to. Inverted from {@link CONSTRAINT_SHORTCUTS} so the
 * rail can never advertise a key the keyboard does not honour — the two used to
 * be written out twice and that is exactly how a hint becomes a lie.
 */
const VERB_KEY: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(CONSTRAINT_SHORTCUTS).map(([key, action]) => [
    action,
    key.toUpperCase(),
  ]),
);

/** Diameter has no key of its own — D is the dimension key (see the doc there). */
const verbKey = (action: ConstraintAction): string =>
  action === "diameter" ? "D" : (VERB_KEY[action] ?? "");

/** How many verbs the rail will show. Three is a glance; five is a menu. */
const MAX_VERB_HINTS = 3;

/**
 * THE SELECTION OFFERS THE VERBS THAT APPLY TO IT — the reachability mechanism
 * for SKETCH-VOCAB-1, and the generalisation of the single dimension hint this
 * replaced (FINDINGS #12: select-then-D was invisible, the probable novice
 * give-up point). Five verbs shipped in the contract with no way for a user to
 * find them; a sixth toolbar row would not have fixed that, because the problem
 * was never that the button was missing — it was that nothing told you your
 * current selection had made a verb available.
 *
 * Truthful by construction: an offer appears only when
 * {@link applyConstraintAction} would actually DO something with this exact
 * selection — open an editor, or add a constraint that is not already there.
 * There is no parallel rule to drift out of sync, and the rail can never
 * propose a key that answers "Select two lines…".
 */
export function selectionVerbHints(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): SketchVerbHint[] {
  if (selection.length === 0) return [];
  const hints: SketchVerbHint[] = [];
  for (const action of VERB_OFFER_ORDER) {
    if (hints.length === MAX_VERB_HINTS) break;
    const key = verbKey(action);
    // One cap per key: distance and diameter share D, and a rail offering the
    // same keycap twice would be asking the user to choose what the selection
    // has already decided.
    if (hints.some((h) => h.key === key)) continue;
    const result = applyConstraintAction(
      action,
      selection,
      entities,
      constraints,
    );
    if (result.outcome === "hint") continue;
    hints.push({ key, label: VERB_LABEL[action], action });
  }
  return hints;
}
