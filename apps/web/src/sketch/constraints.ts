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

/** Constraint verbs — the keyboard-first strip actions. */
export type ConstraintAction =
  | "horizontal"
  | "vertical"
  | "distance"
  | "radius"
  | "fixed"
  | "coincident"
  | "parallel"
  | "perpendicular"
  | "tangent"
  | "equal"
  | "symmetric"
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
 */
export const CONSTRAINT_SHORTCUTS: Readonly<Record<string, ConstraintAction>> =
  {
    h: "horizontal",
    v: "vertical",
    d: "distance",
    r: "radius",
    x: "fixed",
    c: "coincident",
    p: "parallel",
    l: "perpendicular",
    t: "tangent",
    e: "equal",
    s: "symmetric",
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
 * (H/V/D/R/X/C plus P/L/T for parallel/perpendicular/tangent and E/S/O for
 * equal/symmetric/concentric) plus the construction toggle (N). Selection
 * presence is the mode — deterministic, no chords.
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
      // `angle` relates two whole lines by id like the rest of this group; its
      // VALUE lives on the constraint, not in the reference set. Listed here so
      // a deleted line takes its angle dimension with it — an angle whose line
      // is gone is a dangling reference the solver rejects.
      return [constraint.a, constraint.b];
    case "symmetric":
      return [constraint.a.entity, constraint.b.entity, constraint.line];
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

/** A dimension editor request: which value the inline mm field is driving. */
export interface DimensionEditorTarget {
  kind: "distance" | "radius";
  entity: string;
  /** Prefill: the existing driving value, or the measured current one. */
  initialMm: number;
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
  valueMm: number;
  expression: string | null;
  name: string | null;
  driving: boolean;
}

export type ConstraintActionResult =
  | { outcome: "added"; constraints: SketchConstraint[] }
  | { outcome: "editor"; target: DimensionEditorTarget }
  | { outcome: "hint"; hint: string };

const hint = (text: string): ConstraintActionResult => ({
  outcome: "hint",
  hint: text,
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
    case "angle": {
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

/**
 * Apply a constraint verb to the current selection. Dimensions (distance /
 * radius) answer with an inline-editor request instead of a constraint —
 * the value drives, so the value gets typed. Invalid selections answer with
 * a hint, never silence.
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
      if (added.length === 0) return hint(`Already ${action}.`);
      return { outcome: "added", constraints: added };
    }
    case "distance": {
      const lines = selectedLineIds(selection, entities);
      const entity = lines[0];
      if (lines.length !== 1 || entity === undefined) {
        return hint("Select one line to dimension.");
      }
      const existing = constraints.findIndex(
        (c) => c.kind === "distance" && c.entity === entity,
      );
      const existingConstraint = constraints[existing];
      const prior =
        existingConstraint?.kind === "distance" ? existingConstraint : null;
      return {
        outcome: "editor",
        target: {
          kind: "distance",
          entity,
          initialMm:
            prior?.value_mm ?? measuredLength(byId.get(entity) as SketchEntity),
          initialExpression: prior?.expression ?? null,
          initialName: prior?.name ?? null,
          initialDriving: prior?.driving !== false,
          constraintIndex: existing === -1 ? null : existing,
        },
      };
    }
    case "radius": {
      const rounds = selection.flatMap((pick) => {
        if (pick.kind !== "entity") return [];
        const kind = byId.get(pick.id)?.kind;
        return kind === "circle" || kind === "arc" ? [pick.id] : [];
      });
      const entity = rounds[0];
      if (rounds.length !== 1 || entity === undefined) {
        return hint("Select one circle or arc to dimension.");
      }
      const existing = constraints.findIndex(
        (c) => c.kind === "radius" && c.entity === entity,
      );
      const existingConstraint = constraints[existing];
      const prior =
        existingConstraint?.kind === "radius" ? existingConstraint : null;
      return {
        outcome: "editor",
        target: {
          kind: "radius",
          entity,
          initialMm:
            prior?.value_mm ?? measuredRadius(byId.get(entity) as SketchEntity),
          initialExpression: prior?.expression ?? null,
          initialName: prior?.name ?? null,
          initialDriving: prior?.driving !== false,
          constraintIndex: existing === -1 ? null : existing,
        },
      };
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
      if (added.length === 0) return hint("Already fixed.");
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
        return hint("Already coincident.");
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
        return hint(`Already ${action}.`);
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
        return hint("Already tangent.");
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
        return hint("Already equal.");
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
        return hint("Already concentric.");
      }
      return { outcome: "added", constraints: [constraint] };
    }
    case "symmetric": {
      const points = selection.filter((pick) => pick.kind === "point");
      const [a, b] = points;
      if (points.length !== 2 || a === undefined || b === undefined) {
        return hint(
          "Select two points and a line (the mirror axis) to make symmetric.",
        );
      }
      const lines = selectedLineIds(selection, entities);
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
        return hint("Already symmetric about that line.");
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
 * A dimension glyph's label. Driving dims read bare ("40", "R12.5"); DRIVEN
 * (reference) dims wear the drafting convention — parentheses, "(40)" /
 * "(R12.5)" — so a measured, informational value is never mistaken for a
 * driving one.
 */
export function formatDimensionLabel(
  kind: "distance" | "radius",
  value: number,
  driven: boolean,
): string {
  const core =
    kind === "radius"
      ? `R${formatDimensionMm(value)}`
      : formatDimensionMm(value);
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
 * Whole-entity relational marks — engineering-drawing notation, one bare
 * mono glyph each. Equal is the `=` sign; concentric is the bullseye ◎ (a
 * circle inside a circle — the relation drawn as its own picture).
 */
const RELATIONAL_LABEL: Record<
  "parallel" | "perpendicular" | "tangent" | "equal" | "concentric",
  string
> = {
  parallel: "∥",
  perpendicular: "⊥",
  tangent: "T",
  equal: "=",
  concentric: "◎",
};

/**
 * Constraints → annotation glyphs at their current (solved) geometry.
 * Letters and numbers only — Fragment Mono native, no icon font, no badge.
 *
 * `solved` (keyed by `constraint_index`) carries the per-dimension solve
 * readouts: a driving dim shows its EVALUATED value (an expression `width/2`
 * reads as `10`), a driven dim its MEASURED value in reference parentheses.
 * Pre-solve (no map) the glyph falls back to the authored `value_mm`/flag.
 */
export function constraintGlyphs(
  constraints: readonly SketchConstraint[],
  entities: readonly SketchEntity[],
  offsetMm: number,
  solved?: ReadonlyMap<number, SolvedDimension>,
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
      case "radius": {
        const entity = byId.get(constraint.entity);
        if (entity === undefined) return;
        const readout = solved?.get(index);
        const driven =
          readout !== undefined
            ? !readout.driving
            : constraint.driving === false;
        const value = readout?.value_mm ?? constraint.value_mm;
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
      case "concentric": {
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
    }
  });
  return glyphs;
}

/** Anchor for a dimension editor opened on an entity with no constraint yet. */
export function dimensionEditorAnchor(
  target: DimensionEditorTarget,
  entities: readonly SketchEntity[],
  offsetMm: number,
): Point2D {
  const entity = entities.find((e) => e.id === target.entity);
  if (entity === undefined) return { x: 0, y: 0 };
  return target.kind === "distance"
    ? lineAnnotationAnchor(entity, -offsetMm)
    : radiusAnchor(entity, offsetMm);
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
}

/**
 * The dimension verb the CURRENT selection makes available, surfaced as a quiet
 * status-bar affordance so select-then-D stops being invisible (FINDINGS #12 —
 * the probable novice give-up point). Reuses {@link applyConstraintAction}'s own
 * acceptance: a hint appears only when the key would actually open the dimension
 * editor (one line → **D** distance, one circle/arc → **R** radius), never a key
 * that would just print "Select one line to dimension." Truthful by construction
 * — the same predicate the keypress runs, no parallel rule to drift.
 */
export function dimensionVerbHint(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): SketchVerbHint | null {
  if (selection.length === 0) return null;
  if (
    applyConstraintAction("distance", selection, entities, constraints)
      .outcome === "editor"
  ) {
    return { key: "D", label: "dimension" };
  }
  if (
    applyConstraintAction("radius", selection, entities, constraints)
      .outcome === "editor"
  ) {
    return { key: "R", label: "add a radius" };
  }
  return null;
}
