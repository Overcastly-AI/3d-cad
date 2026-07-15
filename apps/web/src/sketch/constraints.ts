/**
 * Constraint authoring + solve-feedback logic — pure functions, no store,
 * no three.js. Constraint shapes are the generated client's (pydantic →
 * OpenAPI → TS, the CLAUDE.md DRY rule); this module turns selections into
 * constraints, constraints into in-viewport glyphs (engineering-drawing
 * notation), and solver payloads into DRO feedback.
 */
import type { components } from "@loft/ts-client/gateway";

import type { Point2D } from "./plane";
import type { SketchPick } from "./pick";
import { TOOL_SHORTCUTS, type SketchEntity } from "./tools";

export type SketchConstraint =
  components["schemas"]["SketchParamsV1"]["constraints"][number];
export type EntityPointRef = components["schemas"]["EntityPointRef"];
export type SolveStatus = components["schemas"]["SolvedSketchData"]["status"];

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
  return TOOL_SHORTCUTS[lower] !== undefined ? { type: "tool" } : null;
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
      return [constraint.a, constraint.b];
    case "symmetric":
      return [constraint.a.entity, constraint.b.entity, constraint.line];
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
export function toggleConstruction(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): SketchEntity[] | null {
  const ids = new Set(
    selection.flatMap((pick) => (pick.kind === "entity" ? [pick.id] : [])),
  );
  if (ids.size === 0) return null;
  const selected = entities.filter((e) => ids.has(e.id));
  const target = !selected.every((e) => e.construction);
  return entities.map((e) =>
    ids.has(e.id) ? { ...e, construction: target } : e,
  );
}

/** Whether the selection is non-empty and every addressed entity is construction. */
export function selectionAllConstruction(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
): boolean {
  const ids = new Set(
    selection.flatMap((pick) => (pick.kind === "entity" ? [pick.id] : [])),
  );
  if (ids.size === 0) return false;
  return entities.filter((e) => ids.has(e.id)).every((e) => e.construction);
}

/** A dimension editor request: which value the inline mm field is driving. */
export interface DimensionEditorTarget {
  kind: "distance" | "radius";
  entity: string;
  /** Prefill: the existing driving value, or the measured current one. */
  initialMm: number;
  /** Existing constraint being edited, or null when creating a new one. */
  constraintIndex: number | null;
}

export type ConstraintActionResult =
  | { outcome: "added"; constraints: SketchConstraint[] }
  | { outcome: "editor"; target: DimensionEditorTarget }
  | { outcome: "hint"; hint: string };

const hint = (text: string): ConstraintActionResult => ({
  outcome: "hint",
  hint: text,
});

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
    case "concentric": {
      const other = b as typeof a;
      return (
        (a.a === other.a && a.b === other.b) ||
        (a.a === other.b && a.b === other.a)
      );
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
      return {
        outcome: "editor",
        target: {
          kind: "distance",
          entity,
          initialMm:
            existingConstraint?.kind === "distance"
              ? existingConstraint.value_mm
              : measuredLength(byId.get(entity) as SketchEntity),
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
      return {
        outcome: "editor",
        target: {
          kind: "radius",
          entity,
          initialMm:
            existingConstraint?.kind === "radius"
              ? existingConstraint.value_mm
              : measuredRadius(byId.get(entity) as SketchEntity),
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
  /** Bare mono text: "H", "V", "C", "FIX", "40", "R12.5". */
  label: string;
  /** Anchor in sketch-plane mm. */
  anchor: Point2D;
  /** Dimensions open the inline editor on click; others select. */
  editable: boolean;
}

/** Dimension text: trailing zeros trimmed, mm implied (drawing convention). */
export function formatDimensionMm(value: number): string {
  const text = value.toFixed(2).replace(/\.?0+$/, "");
  return text === "" || text === "-" ? "0" : text;
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
 */
export function constraintGlyphs(
  constraints: readonly SketchConstraint[],
  entities: readonly SketchEntity[],
  offsetMm: number,
): ConstraintGlyph[] {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const glyphs: ConstraintGlyph[] = [];
  constraints.forEach((constraint, index) => {
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
        });
        return;
      }
      case "distance": {
        const entity = byId.get(constraint.entity);
        if (entity === undefined) return;
        glyphs.push({
          index,
          kind: "distance",
          label: formatDimensionMm(constraint.value_mm),
          // Opposite side from H/V marks — annotations never stack.
          anchor: lineAnnotationAnchor(entity, -offsetMm),
          editable: true,
        });
        return;
      }
      case "radius": {
        const entity = byId.get(constraint.entity);
        if (entity === undefined) return;
        glyphs.push({
          index,
          kind: "radius",
          label: `R${formatDimensionMm(constraint.value_mm)}`,
          anchor: radiusAnchor(entity, offsetMm),
          editable: true,
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

/** The DRO/diagnostic view of one evaluate round-trip for the bound sketch. */
export interface SolveInfo {
  status: SolveStatus;
  dof: number | null;
  conflicting: number[];
  redundant: number[];
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
            : "The constraints cannot all hold. Remove or edit one.",
      };
    case "overconstrained":
      return {
        title: "Over-constrained",
        body: "A redundant constraint is flagged in the sketch. Remove it — the geometry is already determined without it.",
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
