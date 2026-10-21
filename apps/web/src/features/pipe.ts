/**
 * Pipe-feature view logic (PIPE-ALONG-PATH) — Fusion 360's Pipe: a round bar
 * or, with a wall, a tube swept along picked curves. Pure functions the
 * PipeEditor and the part page share, unit-tested without a DOM.
 *
 * THE PATH is a chain of picked curves: sketch curves of earlier sketches
 * (construction lines count — a skeleton is drawn in them) and model edges
 * selected before the command. One skeleton sketch feeds every tube, so the
 * picker lists each sketch's curves by name and length, and CHAIN SELECTION
 * (on by default, Fusion's tangent chain) extends a pick through every joint
 * where exactly two curves meet TANGENTIALLY — it stops at a corner or a
 * branch, so picking one line of a skeleton picks that one tube, and picking
 * one side of a filleted bend picks the whole bent tube. The server orders the picks
 * along the path and refuses a branched or broken pick by name
 * (`sweep_path_not_connected`).
 *
 * THE SECTION is the outside diameter, and with Hollow a wall thickness. Both
 * fields take numbers or formulas (`/outer_diameter_mm`, `/wall_thickness_mm`).
 * THE OPERATION is Join / New body / Cut (the wire's `add`+`merge` / `cut`).
 */
import type { LengthUnit } from "@loft/design";
import {
  cutBodiesBlocker,
  cutBodiesField,
  type CutBodiesChoice,
  NEW_CUT_BODIES,
  seedCutBodies,
} from "./cutBodies";

import type {
  EdgeSignature,
  FeatureCreate,
  FeatureResponse,
  FeatureUpdate,
  PathSegment,
  PipeFeature,
  PipeParams,
  SolvedSketch3DData,
} from "../api/parts";
import { parsePositiveLengthMm } from "../units/length";
import { storedLengthInput, storedLengthMm } from "./storedNumber";
import { fieldBlocker } from "./submitBlocker";

/** Join, New body or Cut (Fusion's Pipe operations). */
export type PipeOperation = "join" | "newBody" | "cut";

/** A sketch-plane point, or a 3D sketch's world point (with `z`). */
type Point = { x: number; y: number; z?: number };

/** One curve of an earlier sketch the path can take. */
export interface PipeCurveOption {
  /** `<sketch id>:<entity id>` — the curve's identity in the form. */
  key: string;
  sketchId: string;
  sketchName: string;
  entityId: string;
  kind: "line" | "arc" | "circle" | "spline";
  construction: boolean;
  /** The curve's two ends (null for a closed curve, a circle). */
  ends: readonly [Point, Point] | null;
  /** Its length (mm) as stored, for the label; null when not computed. */
  lengthMm: number | null;
  /** Unit travel directions at its start and end (null for a circle). */
  tangents: readonly [Point, Point] | null;
}

/** A model edge picked before the command, as the form carries it. */
export interface PipeEdge {
  signature: EdgeSignature;
  /** The body-affecting feature whose body owns the edge (the ref anchor). */
  anchorId: string;
}

/** The editable pipe form. */
export interface PipeForm {
  /** Picked sketch curves, by {@link PipeCurveOption.key}, in pick order. */
  curves: string[];
  /** Picked model edges. */
  edges: PipeEdge[];
  /** Chain selection: a pick takes its unbranched chain with it. */
  chain: boolean;
  odInput: string;
  hollow: boolean;
  wallInput: string;
  operation: PipeOperation;
  /**
   * Objects To Cut (CUT-OBJECTS-TO-CUT, `./cutBodies`): every body the cut
   * meets, the ticked bodies, or `undefined` for a cut saved before the list
   * (its active body only). Read on a cut only.
   */
  cutBodies?: CutBodiesChoice;
  /** The params as STORED, when editing (a no-op Save sends them back). */
  stored?: PipeParams;
}

/** The key of a sketch curve. */
export function curveKey(sketchId: string, entityId: string): string {
  return `${sketchId}:${entityId}`;
}

function unit(v: Point): Point {
  const z = v.z ?? 0;
  const n = Math.hypot(v.x, v.y, z);
  if (n === 0) return { x: 0, y: 0 };
  return v.z === undefined
    ? { x: v.x / n, y: v.y / n }
    : { x: v.x / n, y: v.y / n, z: z / n };
}

function minus(a: Point, b: Point): Point {
  return a.z === undefined && b.z === undefined
    ? { x: a.x - b.x, y: a.y - b.y }
    : { x: a.x - b.x, y: a.y - b.y, z: (a.z ?? 0) - (b.z ?? 0) };
}

/** Counter-clockwise travel direction of an arc about `c` at `p`. */
function arcTangent(c: Point, p: Point): Point {
  return unit({ x: -(p.y - c.y), y: p.x - c.x });
}

function arcLength(c: Point, a: Point, b: Point): number {
  const r = Math.hypot(a.x - c.x, a.y - c.y);
  let sweep =
    Math.atan2(b.y - c.y, b.x - c.x) - Math.atan2(a.y - c.y, a.x - c.x);
  if (sweep <= 0) sweep += 2 * Math.PI;
  return r * sweep;
}

/** Every curve of every sketch in the tree, in tree then entity order. */
export function pipeCurveOptions(
  features: readonly FeatureResponse[],
  solved3d: ReadonlyMap<string, SolvedSketch3DData> = new Map(),
): PipeCurveOption[] {
  const options: PipeCurveOption[] = [];
  for (const f of features) {
    if (f.feature.type === "sketch_3d") {
      // A 3D sketch's lines, at their solved positions when the rebuild has
      // them (a length dimension moves an end off where it was typed).
      const at = new Map<string, Point>();
      for (const e of f.feature.params.entities) {
        if (e.kind === "point") at.set(e.id, e.position);
      }
      for (const p of solved3d.get(f.id)?.points ?? [])
        at.set(p.id, p.position);
      for (const e of f.feature.params.entities) {
        if (e.kind !== "line") continue;
        const a = at.get(e.start);
        const b = at.get(e.end);
        if (a === undefined || b === undefined) continue;
        const d = minus(b, a);
        options.push({
          key: curveKey(f.id, e.id),
          sketchId: f.id,
          sketchName: f.name,
          entityId: e.id,
          construction: e.construction === true,
          kind: "line",
          ends: [a, b],
          lengthMm: Math.hypot(d.x, d.y, d.z ?? 0),
          tangents: [unit(d), unit(d)],
        });
      }
      continue;
    }
    if (f.feature.type !== "sketch") continue;
    for (const e of f.feature.params.entities) {
      const base = {
        key: curveKey(f.id, e.id),
        sketchId: f.id,
        sketchName: f.name,
        entityId: e.id,
        construction: e.construction === true,
      };
      if (e.kind === "line") {
        options.push({
          ...base,
          kind: "line",
          ends: [e.start, e.end],
          lengthMm: Math.hypot(e.end.x - e.start.x, e.end.y - e.start.y),
          tangents: [
            unit({ x: e.end.x - e.start.x, y: e.end.y - e.start.y }),
            unit({ x: e.end.x - e.start.x, y: e.end.y - e.start.y }),
          ],
        });
      } else if (e.kind === "arc") {
        options.push({
          ...base,
          kind: "arc",
          ends: [e.start, e.end],
          lengthMm: arcLength(e.center, e.start, e.end),
          tangents: [
            arcTangent(e.center, e.start),
            arcTangent(e.center, e.end),
          ],
        });
      } else if (e.kind === "circle") {
        options.push({
          ...base,
          kind: "circle",
          ends: null,
          lengthMm: 2 * Math.PI * e.radius,
          tangents: null,
        });
      } else if (e.kind === "spline") {
        const first = e.points[0];
        const second = e.points[1];
        const before = e.points[e.points.length - 2];
        const last = e.points[e.points.length - 1];
        if (!first || !second || !before || !last) continue;
        options.push({
          ...base,
          kind: "spline",
          ends: [first, last],
          lengthMm: null,
          // The end chords: an interpolating spline's end tangent leans off
          // them, so a spline joint chains only within the tolerance below.
          tangents: [
            unit({ x: second.x - first.x, y: second.y - first.y }),
            unit({ x: last.x - before.x, y: last.y - before.y }),
          ],
        });
      }
    }
  }
  return options;
}

/** How a curve reads in the picker: `line e2 · 150 mm`. */
export function curveLabel(option: PipeCurveOption): string {
  const length =
    option.lengthMm === null
      ? ""
      : ` · ${Math.round(option.lengthMm * 10) / 10} mm`;
  const construction = option.construction ? " (construction)" : "";
  return `${option.kind} ${option.entityId}${length}${construction}`;
}

/** Two stored curve ends this close (mm) are one joint. */
const JOINT_TOLERANCE_MM = 1e-3;

function same(a: Point, b: Point): boolean {
  return (
    Math.abs(a.x - b.x) <= JOINT_TOLERANCE_MM &&
    Math.abs(a.y - b.y) <= JOINT_TOLERANCE_MM &&
    Math.abs((a.z ?? 0) - (b.z ?? 0)) <= JOINT_TOLERANCE_MM
  );
}

/** Two travel directions this close (as a chord of unit vectors) are tangent. */
const TANGENT_TOLERANCE = 1e-2;

/** The direction pointing OUT of `o` at its end `index`. */
function outward(o: PipeCurveOption, index: 0 | 1): Point | null {
  if (o.tangents === null) return null;
  const t = o.tangents[index];
  if (index !== 0) return t;
  return t.z === undefined
    ? { x: -t.x, y: -t.y }
    : { x: -t.x, y: -t.y, z: -t.z };
}

function endAt(o: PipeCurveOption, at: Point): 0 | 1 {
  return o.ends !== null && same(o.ends[0], at) ? 0 : 1;
}

/** Whether `a` and `b` meet at `at` smoothly (one continues the other). */
function tangentJoint(
  a: PipeCurveOption,
  b: PipeCurveOption,
  at: Point,
): boolean {
  const oa = outward(a, endAt(a, at));
  const ob = outward(b, endAt(b, at));
  if (oa === null || ob === null) return false;
  // The outward directions of a smooth joint are opposite.
  const dz = (oa.z ?? 0) + (ob.z ?? 0);
  return Math.hypot(oa.x + ob.x, oa.y + ob.y, dz) <= TANGENT_TOLERANCE;
}

/**
 * The tangent chain through `key` within its sketch: from the picked curve,
 * through every end where exactly one other curve of the same sketch meets it
 * tangentially (a corner or a branch stops it). A circle is its own chain. The picked curve comes first, then the chain
 * outwards — the server orders them along the path anyway.
 */
export function chainOf(
  options: readonly PipeCurveOption[],
  key: string,
): string[] {
  const start = options.find((o) => o.key === key);
  if (start === undefined) return [];
  const siblings = options.filter(
    (o) => o.sketchId === start.sketchId && o.ends !== null,
  );
  const chain = [start.key];
  const visited = new Set(chain);
  const queue: Point[] = start.ends === null ? [] : [...start.ends];
  while (queue.length > 0) {
    const at = queue.shift() as Point;
    const meeting = siblings.filter(
      (o) => o.ends !== null && (same(o.ends[0], at) || same(o.ends[1], at)),
    );
    if (meeting.length !== 2) continue; // a free end or a branch: stop
    const [a, b] = meeting as [PipeCurveOption, PipeCurveOption];
    if (!tangentJoint(a, b, at)) continue; // a corner: a tube joint
    for (const next of meeting) {
      if (visited.has(next.key) || next.ends === null) continue;
      visited.add(next.key);
      chain.push(next.key);
      queue.push(same(next.ends[0], at) ? next.ends[1] : next.ends[0]);
    }
  }
  return chain;
}

/**
 * Toggle one curve in the form: picking adds it (and, with chain selection,
 * its unbranched chain); picking a picked curve removes it alone.
 */
export function toggleCurve(
  form: PipeForm,
  options: readonly PipeCurveOption[],
  key: string,
): PipeForm {
  if (form.curves.includes(key)) {
    return { ...form, curves: form.curves.filter((k) => k !== key) };
  }
  const adding = form.chain ? chainOf(options, key) : [key];
  const next = [...form.curves];
  for (const k of adding) if (!next.includes(k)) next.push(k);
  return { ...form, curves: next };
}

/** The new-pipe form, seeded with the model edges selected before Pipe. */
export function defaultPipeForm(edges: readonly PipeEdge[] = []): PipeForm {
  return {
    curves: [],
    edges: [...edges],
    chain: true,
    odInput: "25",
    hollow: true,
    wallInput: "2",
    operation: "join",
    cutBodies: NEW_CUT_BODIES,
  };
}

/** Seed the form from an existing pipe for editing (lengths in `unit`). */
export function formFromPipeParams(
  params: PipeParams,
  unit: LengthUnit,
): PipeForm {
  const curves: string[] = [];
  const edges: PipeEdge[] = [];
  for (const segment of params.path) {
    if (segment.kind === "sketch_curve") {
      curves.push(curveKey(segment.sketch.feature_id, segment.entity));
    } else {
      edges.push({
        signature: segment.selector.signature,
        anchorId: segment.feature_id,
      });
    }
  }
  const wall = params.wall_thickness_mm;
  return {
    curves,
    edges,
    chain: true,
    odInput: storedLengthInput(params.outer_diameter_mm, unit),
    hollow: wall !== null && wall !== undefined,
    wallInput:
      wall === null || wall === undefined ? "2" : storedLengthInput(wall, unit),
    operation:
      params.operation === "cut"
        ? "cut"
        : params.merge === false
          ? "newBody"
          : "join",
    cutBodies: seedCutBodies(params),
    stored: params,
  };
}

function segments(form: PipeForm): PathSegment[] {
  const out: PathSegment[] = [];
  for (const key of form.curves) {
    const cut = key.indexOf(":");
    out.push({
      kind: "sketch_curve",
      sketch: { kind: "feature", feature_id: key.slice(0, cut) },
      entity: key.slice(cut + 1),
    });
  }
  for (const edge of form.edges) {
    out.push({
      kind: "subshape",
      feature_id: edge.anchorId,
      subshape_type: "edge",
      selector: { selector_version: 1, signature: edge.signature },
    });
  }
  return out;
}

function diameter(form: PipeForm, unit: LengthUnit): number | null {
  return storedLengthMm(
    form.odInput,
    unit,
    form.stored?.outer_diameter_mm,
    parsePositiveLengthMm,
  );
}

function wall(form: PipeForm, unit: LengthUnit): number | null {
  return storedLengthMm(
    form.wallInput,
    unit,
    form.stored?.wall_thickness_mm,
    parsePositiveLengthMm,
  );
}

/** Field message for the wall, or null when valid (empty is pending). */
export function wallError(form: PipeForm, unit: LengthUnit): string | null {
  if (!form.hollow || form.wallInput.trim() === "") return null;
  const w = wall(form, unit);
  if (w === null) return "Wall must be a positive length.";
  const od = diameter(form, unit);
  if (od !== null && w >= od / 2) return "Wall must be less than the radius.";
  return null;
}

/** WHY the pipe cannot be created yet, or null (REASON-GATE-1). */
export function pipeSubmitBlocker(
  form: PipeForm,
  unit: LengthUnit,
): string | null {
  if (form.curves.length + form.edges.length === 0) {
    return "Pick the path curves.";
  }
  const od = fieldBlocker(form.odInput, diameter(form, unit), "diameter");
  if (od !== null) return od;
  const scope = cutBodiesBlocker(
    form.operation === "cut" ? "cut" : "add",
    form.cutBodies,
  );
  if (scope !== null) return scope;
  if (!form.hollow) return null;
  const w = fieldBlocker(form.wallInput, wall(form, unit), "wall");
  if (w !== null) return w;
  return wallError(form, unit) === null ? null : "Make the wall thinner.";
}

/** The params the form means, or null while it is blocked. */
export function buildPipeParams(
  form: PipeForm,
  unit: LengthUnit,
): PipeParams | null {
  if (pipeSubmitBlocker(form, unit) !== null) return null;
  const od = diameter(form, unit);
  if (od === null) return null;
  const params: PipeParams = {
    path: segments(form),
    outer_diameter_mm: od,
    operation: form.operation === "cut" ? "cut" : "add",
    merge: form.operation !== "newBody",
    ...cutBodiesField(
      form.operation === "cut" ? "cut" : "add",
      form.stored === undefined
        ? (form.cutBodies ?? NEW_CUT_BODIES)
        : form.cutBodies,
    ),
  };
  if (form.hollow) {
    const w = wall(form, unit);
    if (w === null) return null;
    params.wall_thickness_mm = w;
  }
  return params;
}

function envelope(params: PipeParams): PipeFeature {
  return { type: "pipe", version: 1, params };
}

/** The create payload for a pipe feature. */
export function pipeFeatureCreate(
  name: string,
  params: PipeParams,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: envelope(params),
  };
}

/** The PATCH payload that re-parametrizes an existing pipe (no rename). */
export function pipeFeatureUpdate(
  params: PipeParams,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: envelope(params),
  };
}
