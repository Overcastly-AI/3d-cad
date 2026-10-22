/**
 * 3D sketch view logic (SKETCH-3D) — SolidWorks' 3D Sketch and Fusion's 3D
 * sketch, scoped to a frame skeleton. Pure functions the Sketch3DEditor, the
 * viewport layer and the store share, unit-tested without a DOM.
 *
 * DRAWING is a chain, as the 2D Line tool's is: every point placed (typed
 * X Tab Y Tab Z Enter, or a snap clicked in the viewport) joins the previous
 * one with a line until the chain is ended (Esc, or "End chain"). Placing a
 * point on one the sketch already has — clicking its mark — continues the
 * chain from there, so a skeleton shares its joints. A SNAP (the origin, a
 * sketch point, a model vertex) is stored as a relation and follows its
 * target on every rebuild.
 *
 * RELATIONS are added to the selection: one line takes Along X / Y / Z or a
 * Length, two points a Distance or Coincident, one point Fix. The geometry
 * service solves them (RESEARCH §28); the editor shows the typed positions
 * and the solved ones once saved.
 */
import { formatLength, type LengthUnit } from "@loft/design";

import type {
  FeatureCreate,
  FeatureResponse,
  FeatureUpdate,
  Sketch3DConstraint,
  Sketch3DFeature,
  Sketch3DParams,
  Sketch3DSnap,
  SolvedSketch3DData,
  Vec3,
} from "../api/parts";
import { parseSignedLengthMm } from "../units/length";

export interface Sketch3DFormPoint {
  id: string;
  position: Vec3;
  snap: Sketch3DSnap | null;
}

export interface Sketch3DFormLine {
  id: string;
  start: string;
  end: string;
  construction: boolean;
}

/** The editable 3D sketch. */
export interface Sketch3DForm {
  points: Sketch3DFormPoint[];
  lines: Sketch3DFormLine[];
  constraints: Sketch3DConstraint[];
  /** The point the next placed point joins with a line, or null. */
  chainFrom: string | null;
  /** Selected point and line ids, in click order (relations act on these). */
  selected: string[];
}

export type Axis = "x" | "y" | "z";

/** Two positions this close (mm) are one point when a snap is placed. */
const SAME_MM = 1e-9;

export function emptySketch3DForm(): Sketch3DForm {
  return {
    points: [],
    lines: [],
    constraints: [],
    chainFrom: null,
    selected: [],
  };
}

/** The stored params as a form (the chain is not resumed). */
export function formFromSketch3DParams(params: Sketch3DParams): Sketch3DForm {
  const form = emptySketch3DForm();
  for (const e of params.entities) {
    if (e.kind === "point") {
      form.points.push({
        id: e.id,
        position: e.position,
        snap: e.snap ?? null,
      });
    } else {
      form.lines.push({
        id: e.id,
        start: e.start,
        end: e.end,
        construction: e.construction === true,
      });
    }
  }
  form.constraints = [...(params.constraints ?? [])];
  return form;
}

function nextId(form: Sketch3DForm, prefix: string): string {
  const taken = new Set([
    ...form.points.map((p) => p.id),
    ...form.lines.map((l) => l.id),
  ]);
  let n = 1;
  while (taken.has(`${prefix}${n}`)) n += 1;
  return `${prefix}${n}`;
}

function sameSnap(a: Sketch3DSnap | null, b: Sketch3DSnap | null): boolean {
  return a !== null && b !== null && JSON.stringify(a) === JSON.stringify(b);
}

function samePosition(a: Vec3, b: Vec3): boolean {
  return (
    Math.abs(a.x - b.x) <= SAME_MM &&
    Math.abs(a.y - b.y) <= SAME_MM &&
    Math.abs(a.z - b.z) <= SAME_MM
  );
}

/** Join `from` -> `to` with a new line unless one already joins them. */
function joined(form: Sketch3DForm, from: string, to: string): Sketch3DForm {
  if (from === to) return form;
  const exists = form.lines.some(
    (l) =>
      (l.start === from && l.end === to) || (l.start === to && l.end === from),
  );
  if (exists) return form;
  return {
    ...form,
    lines: [
      ...form.lines,
      { id: nextId(form, "l"), start: from, end: to, construction: false },
    ],
  };
}

/** Continue the chain to an existing point of this sketch. */
export function continueTo(form: Sketch3DForm, pointId: string): Sketch3DForm {
  if (!form.points.some((p) => p.id === pointId)) return form;
  const next =
    form.chainFrom === null ? form : joined(form, form.chainFrom, pointId);
  return { ...next, chainFrom: pointId };
}

/**
 * Place a point at `position` (world mm), attached to `snap` when given, and
 * join it to the chain. A snap the sketch already holds (the same target)
 * reuses that point, so clicking the origin twice is one joint.
 */
export function placePoint(
  form: Sketch3DForm,
  position: Vec3,
  snap: Sketch3DSnap | null = null,
): Sketch3DForm {
  const existing = form.points.find(
    (p) =>
      (snap !== null && sameSnap(p.snap, snap)) ||
      (snap === null && p.snap === null && samePosition(p.position, position)),
  );
  if (existing !== undefined) return continueTo(form, existing.id);
  const id = nextId(form, "p");
  const withPoint: Sketch3DForm = {
    ...form,
    points: [...form.points, { id, position, snap }],
  };
  return continueTo(withPoint, id);
}

/** End the chain: the next point starts a new one. */
export function endChain(form: Sketch3DForm): Sketch3DForm {
  return { ...form, chainFrom: null };
}

/** Parse the X / Y / Z cells (document unit) into world mm, or null. */
export function parseCoordinate(
  cells: readonly [string, string, string],
  unit: LengthUnit,
): Vec3 | null {
  const [x, y, z] = cells.map((c) => parseSignedLengthMm(c, unit));
  if (x == null || y == null || z == null) return null;
  return { x, y, z };
}

/** Toggle one point or line in the selection. */
export function toggleSelected(form: Sketch3DForm, id: string): Sketch3DForm {
  return form.selected.includes(id)
    ? { ...form, selected: form.selected.filter((s) => s !== id) }
    : { ...form, selected: [...form.selected, id] };
}

function selectedPoints(form: Sketch3DForm): string[] {
  return form.selected.filter((id) => form.points.some((p) => p.id === id));
}

function selectedLines(form: Sketch3DForm): string[] {
  return form.selected.filter((id) => form.lines.some((l) => l.id === id));
}

/** Which relations the selection can take (the editor's buttons). */
export function availableRelations(form: Sketch3DForm): {
  line: string | null;
  points: [string, string] | null;
  point: string | null;
} {
  const lines = selectedLines(form);
  const points = selectedPoints(form);
  return {
    line: lines.length === 1 && points.length === 0 ? (lines[0] ?? null) : null,
    points:
      points.length === 2 && lines.length === 0
        ? [points[0] as string, points[1] as string]
        : null,
    point:
      points.length === 1 && lines.length === 0 ? (points[0] ?? null) : null,
  };
}

function withConstraint(
  form: Sketch3DForm,
  constraint: Sketch3DConstraint,
): Sketch3DForm {
  return {
    ...form,
    constraints: [...form.constraints, constraint],
    selected: [],
  };
}

/** Along X / Y / Z on the one selected line. */
export function addAlong(form: Sketch3DForm, axis: Axis): Sketch3DForm {
  const { line } = availableRelations(form);
  if (line === null) return form;
  return withConstraint(form, { kind: "along", line, axis });
}

/** A driving length on the selected line, or distance between two points. */
export function addDimension(
  form: Sketch3DForm,
  valueMm: number,
): Sketch3DForm {
  if (!(valueMm > 0)) return form;
  const { line, points } = availableRelations(form);
  if (line !== null) {
    return withConstraint(form, { kind: "length", line, value_mm: valueMm });
  }
  if (points !== null) {
    return withConstraint(form, {
      kind: "distance",
      a: points[0],
      b: points[1],
      value_mm: valueMm,
    });
  }
  return form;
}

/** Coincident on two selected points. */
export function addCoincident(form: Sketch3DForm): Sketch3DForm {
  const { points } = availableRelations(form);
  if (points === null) return form;
  return withConstraint(form, {
    kind: "coincident",
    a: points[0],
    b: points[1],
  });
}

/** Fix the one selected point where it is. */
export function addFixed(form: Sketch3DForm): Sketch3DForm {
  const { point } = availableRelations(form);
  if (point === null) return form;
  return withConstraint(form, { kind: "fixed", point });
}

function names(c: Sketch3DConstraint): string[] {
  switch (c.kind) {
    case "coincident":
    case "distance":
      return [c.a, c.b];
    case "fixed":
      return [c.point];
    case "along":
    case "length":
      return [c.line];
  }
}

/** Delete a point (with its lines) or a line, and every relation on them. */
export function removeEntity(form: Sketch3DForm, id: string): Sketch3DForm {
  const lines = form.lines.filter(
    (l) => l.id !== id && l.start !== id && l.end !== id,
  );
  const gone = new Set([
    id,
    ...form.lines.filter((l) => !lines.includes(l)).map((l) => l.id),
  ]);
  return {
    points: form.points.filter((p) => p.id !== id),
    lines,
    constraints: form.constraints.filter(
      (c) => !names(c).some((n) => gone.has(n)),
    ),
    chainFrom: form.chainFrom === id ? null : form.chainFrom,
    selected: form.selected.filter((s) => !gone.has(s)),
  };
}

export function removeConstraint(
  form: Sketch3DForm,
  index: number,
): Sketch3DForm {
  return {
    ...form,
    constraints: form.constraints.filter((_, i) => i !== index),
  };
}

/** Toggle a line between real and construction. */
export function toggleConstruction(
  form: Sketch3DForm,
  id: string,
): Sketch3DForm {
  return {
    ...form,
    lines: form.lines.map((l) =>
      l.id === id ? { ...l, construction: !l.construction } : l,
    ),
  };
}

/** How a relation reads in the list: `Length l1 = 500 mm`. */
export function constraintLabel(
  c: Sketch3DConstraint,
  unit: LengthUnit,
): string {
  switch (c.kind) {
    case "coincident":
      return `Coincident ${c.a} ${c.b}`;
    case "fixed":
      return `Fix ${c.point}`;
    case "along":
      return `Along ${c.axis.toUpperCase()} ${c.line}`;
    case "length":
      return `Length ${c.line} = ${formatLength(c.value_mm, unit)}`;
    case "distance":
      return `Distance ${c.a} ${c.b} = ${formatLength(c.value_mm, unit)}`;
  }
}

/** How a snap reads beside its point. */
export function snapLabel(snap: Sketch3DSnap | null): string | null {
  if (snap === null) return null;
  if (snap.kind === "origin") return "on origin";
  if (snap.kind === "vertex") return "on model vertex";
  return `on sketch point ${snap.entity}.${snap.point}`;
}

/** WHY the sketch cannot be saved yet, or null. */
export function sketch3DSubmitBlocker(form: Sketch3DForm): string | null {
  return form.points.length === 0 ? "Place a point first." : null;
}

export function buildSketch3DParams(form: Sketch3DForm): Sketch3DParams {
  return {
    entities: [
      ...form.points.map((p) =>
        p.snap === null
          ? { id: p.id, kind: "point" as const, position: p.position }
          : {
              id: p.id,
              kind: "point" as const,
              position: p.position,
              snap: p.snap,
            },
      ),
      ...form.lines.map((l) => ({
        id: l.id,
        kind: "line" as const,
        start: l.start,
        end: l.end,
        construction: l.construction,
      })),
    ],
    constraints: form.constraints,
  };
}

function envelope(params: Sketch3DParams): Sketch3DFeature {
  return { type: "sketch_3d", version: 1, params };
}

export function sketch3DFeatureCreate(
  name: string,
  params: Sketch3DParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: envelope(params),
  };
}

export function sketch3DFeatureUpdate(
  params: Sketch3DParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: envelope(params),
  };
}

/** Every ok 3D sketch's solve in an evaluation, by feature id. */
export function solvedSketch3DMap(
  results: readonly { feature_id: string; data?: unknown }[] | undefined,
): Map<string, SolvedSketch3DData> {
  const out = new Map<string, SolvedSketch3DData>();
  for (const r of results ?? []) {
    const data = r.data as SolvedSketch3DData | null | undefined;
    if (data?.kind === "solved_sketch_3d") out.set(r.feature_id, data);
  }
  return out;
}

/** A 3D sketch in the tree with its solved points (null when not solved). */
export interface Sketch3DLayer {
  featureId: string;
  name: string;
  points: Map<string, Vec3>;
  lines: { id: string; start: string; end: string; construction: boolean }[];
  solved: boolean;
}

/**
 * Every 3D sketch of the tree as drawn: the SOLVED point positions when the
 * evaluation has them, else the stored ones.
 */
export function sketch3DLayers(
  features: readonly FeatureResponse[],
  solved: ReadonlyMap<string, SolvedSketch3DData>,
): Sketch3DLayer[] {
  const out: Sketch3DLayer[] = [];
  for (const f of features) {
    if (f.feature.type !== "sketch_3d") continue;
    const data = solved.get(f.id);
    const points = new Map<string, Vec3>();
    const lines: Sketch3DLayer["lines"] = [];
    for (const e of f.feature.params.entities) {
      if (e.kind === "point") points.set(e.id, e.position);
      else
        lines.push({
          id: e.id,
          start: e.start,
          end: e.end,
          construction: e.construction === true,
        });
    }
    for (const p of data?.points ?? []) points.set(p.id, p.position);
    out.push({
      featureId: f.id,
      name: f.name,
      points,
      lines,
      solved: data !== undefined,
    });
  }
  return out;
}
