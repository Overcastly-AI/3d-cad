/**
 * THE OUTLINE A BUILDING IS PICKED ON (BUILDING-OUTLINE, RESEARCH §23).
 *
 * A house's walls, floor and roof hang off one closed sketch. Its lines are
 * what an opening sits in and what a roof's Defines Slope picks, stored by
 * sketch line id (`e1`) in a `segments` input. Nobody should read or type
 * those ids, so the form names each line the way the walls on it face in the
 * world, as Revit and Chief Architect name a house's sides and as the roof
 * names its planes (`loft_wire.plugins.SegmentsInput`):
 *
 *  - the loop is walked CLOCKWISE from the sketch's first loop line;
 *  - a line's outward normal (the left of the clockwise direction) is
 *    `front` nearest -Y, `back` +Y, `left` -X and `right` +X, a tie going to
 *    front/back;
 *  - when two lines face one way they are numbered along that walk
 *    ("Right 1", "Right 2"); a side with one line is just its name.
 *
 * The plugin reads the loop from the sketch's constraints in closed form
 * (`loft_plugins.builtin.outline`); here the SOLVED drawing is enough, since
 * only the order and the facing are needed to name the lines, and a sketch
 * the plugin refuses says so on the feature itself.
 *
 * Pure: unit-tested without a DOM. The viewport pick lives in
 * `outlinePickStore` and `viewport/OutlinePickOverlay`.
 */
import type { FeatureResponse } from "../api/parts";
import type { PluginInput, PluginManifest } from "../api/plugins";
import type { SketchEntity } from "../sketch/tools";

export type Facing = "front" | "back" | "left" | "right";

export interface XY {
  readonly x: number;
  readonly y: number;
}

/** One line of an outline, in clockwise walk order. */
export interface OutlineSide {
  /** The sketch line's id, what a `segments` input stores. */
  readonly lineId: string;
  readonly facing: Facing;
  /** "Front", "Right 1": how the form and the viewport name it. */
  readonly name: string;
  /** The line's ends, walked clockwise (sketch-plane mm). */
  readonly start: XY;
  readonly end: XY;
}

const FACING_NAME: Record<Facing, string> = {
  front: "Front",
  back: "Back",
  left: "Left",
  right: "Right",
};

type Line = Extract<SketchEntity, { kind: "line" }>;

function isLoopLine(entity: SketchEntity): entity is Line {
  return entity.kind === "line" && entity.construction !== true;
}

/** Two sketch points are one corner within this (mm, the solver's slack). */
const JOIN_MM = 1e-3;

function same(a: XY, b: XY): boolean {
  return Math.abs(a.x - b.x) <= JOIN_MM && Math.abs(a.y - b.y) <= JOIN_MM;
}

/** Which way a line walked clockwise faces: its left normal, by octant. */
export function facingOf(start: XY, end: XY): Facing {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  // The outward normal of a clockwise walk is on its left.
  const nx = -dy;
  const ny = dx;
  if (Math.abs(ny) >= Math.abs(nx)) return ny < 0 ? "front" : "back";
  return nx < 0 ? "left" : "right";
}

/**
 * The sketch's non-construction lines split into the loop's and the rest
 * (INTERIOR-WALLS): a line with an end that meets no other line's end is off
 * the loop (a partition), as is every line meeting only such lines, as
 * `loft_plugins.builtin.outline.read_plan` reads it.
 */
export function splitLines(entities: readonly SketchEntity[]): {
  loop: Line[];
  off: Line[];
} {
  const all = entities.filter(isLoopLine);
  let alive = all;
  for (;;) {
    const meets = (at: XY, self: Line) =>
      alive.some(
        (other) =>
          other !== self && (same(other.start, at) || same(other.end, at)),
      );
    const next = alive.filter(
      (line) => meets(line.start, line) && meets(line.end, line),
    );
    if (next.length === alive.length) break;
    alive = next;
  }
  return { loop: alive, off: all.filter((line) => !alive.includes(line)) };
}

/**
 * The lines off a plan sketch's loop, each a partition's location line
 * (INTERIOR-WALLS), named "Partition 1", "Partition 2" in sketch order; every
 * line of a sketch with no loop (a separate partition sketch). A door in an
 * Interior wall picks its partition from these.
 */
export function partitionSides(
  entities: readonly SketchEntity[],
): OutlineSide[] {
  const { loop, off } = splitLines(entities);
  const lines = loop.length > 0 ? off : entities.filter(isLoopLine);
  return lines.map((line, k) => ({
    lineId: line.id,
    facing: facingOf(line.start, line.end),
    name: `Partition ${k + 1}`,
    start: line.start,
    end: line.end,
  }));
}

/**
 * The sketch's non-construction lines as one clockwise loop from its first
 * line, each named by side; null when they do not close exactly one loop
 * (the plugin then refuses the outline with the reason). Lines off the loop
 * (partitions, {@link splitLines}) are not the outline's.
 */
export function outlineSides(
  entities: readonly SketchEntity[],
): OutlineSide[] | null {
  const lines = splitLines(entities).loop;
  if (lines.length < 3) return null;
  // Chain from the first line, joining each end to the one line that meets it.
  const first = lines[0] as Line;
  const walk: { line: Line; start: XY; end: XY }[] = [
    { line: first, start: first.start, end: first.end },
  ];
  const used = new Set<string>([first.id]);
  while (walk.length < lines.length) {
    const at = (walk[walk.length - 1] as { end: XY }).end;
    const next = lines.filter(
      (line) =>
        !used.has(line.id) && (same(line.start, at) || same(line.end, at)),
    );
    if (next.length !== 1) return null;
    const line = next[0] as Line;
    used.add(line.id);
    walk.push(
      same(line.start, at)
        ? { line, start: line.start, end: line.end }
        : { line, start: line.end, end: line.start },
    );
  }
  if (!same((walk[walk.length - 1] as { end: XY }).end, first.start)) {
    return null;
  }
  // Shoelace: positive is counter-clockwise, so turn the walk round, keeping
  // the first line first.
  let twiceArea = 0;
  for (const { start, end } of walk) {
    twiceArea += start.x * end.y - end.x * start.y;
  }
  if (twiceArea === 0) return null;
  const clockwise =
    twiceArea < 0
      ? walk
      : [walk[0], ...walk.slice(1).reverse()].map((step) => ({
          line: (step as (typeof walk)[number]).line,
          start: (step as (typeof walk)[number]).end,
          end: (step as (typeof walk)[number]).start,
        }));
  const facings = clockwise.map(({ start, end }) => facingOf(start, end));
  const total = new Map<Facing, number>();
  for (const facing of facings) total.set(facing, (total.get(facing) ?? 0) + 1);
  const seen = new Map<Facing, number>();
  return clockwise.map(({ line, start, end }, k) => {
    const facing = facings[k] as Facing;
    const ordinal = (seen.get(facing) ?? 0) + 1;
    seen.set(facing, ordinal);
    const name =
      (total.get(facing) ?? 0) > 1
        ? `${FACING_NAME[facing]} ${ordinal}`
        : FACING_NAME[facing];
    return { lineId: line.id, facing, name, start, end };
  });
}

/** The side a stored line id names, else the id itself (a line since removed). */
export function sideName(
  sides: readonly OutlineSide[] | null,
  lineId: string,
): string {
  return sides?.find((side) => side.lineId === lineId)?.name ?? lineId;
}

/**
 * Sketch ids an input of this kind can lead to: a feature pick whose types
 * include `sketch` is an OUTLINE pick (a wall's or floor's Outline).
 */
export function isOutlinePick(
  input: PluginInput,
): input is Extract<PluginInput, { kind: "feature" }> {
  return input.kind === "feature" && input.feature_types.includes("sketch");
}

function firstPicked(text: string | undefined): string | null {
  if (text === undefined || text === "") return null;
  return text.split(",")[0] ?? null;
}

/**
 * The sketch a `segments` input picks lines of, by the form's current
 * values (`loft_wire.plugins.SegmentsInput`): its `outline_input`'s pick (the
 * first, for a feature list) is the sketch itself, or a custom feature whose
 * own `outline` input names it (a `loft.wall` in outline mode). Null while
 * that pick is empty or leads to no sketch (a wall on a typed line).
 */
export function segmentsOutlineSketch(
  manifest: PluginManifest,
  input: Extract<PluginInput, { kind: "segments" }>,
  values: Readonly<Record<string, string>>,
  features: readonly FeatureResponse[],
): FeatureResponse | null {
  const pick = manifest.inputs.find((i) => i.name === input.outline_input);
  if (pick === undefined) return null;
  const id = firstPicked(values[pick.name]);
  if (id === null) return null;
  const row = features.find((f) => f.id === id);
  if (row === undefined) return null;
  if (row.feature.type === "sketch") return row;
  if (row.feature.type !== "custom") return null;
  if (row.feature.params.plugin_id === INTERIOR_WALL) {
    return partitionSketch(row, features);
  }
  const outline = row.feature.params.inputs.outline;
  if (
    outline === undefined ||
    typeof outline !== "object" ||
    Array.isArray(outline)
  ) {
    return null;
  }
  const sketch = features.find((f) => f.id === outline.feature_id);
  return sketch?.feature.type === "sketch" ? sketch : null;
}

/** The plugin a door's host is when it stands in a partition. */
export const INTERIOR_WALL = "loft.interior_wall";

function pickedRef(value: unknown): string | null {
  if (
    value === undefined ||
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value)
  ) {
    return null;
  }
  const id = (value as { feature_id?: unknown }).feature_id;
  return typeof id === "string" ? id : null;
}

/**
 * The plan sketch an Interior wall's partitions are drawn on: its own
 * Sketch pick, else its exterior walls' Outline.
 */
function partitionSketch(
  row: FeatureResponse,
  features: readonly FeatureResponse[],
): FeatureResponse | null {
  if (row.feature.type !== "custom") return null;
  const inputs = row.feature.params.inputs;
  let id = pickedRef(inputs.sketch);
  if (id === null) {
    const host = features.find((f) => f.id === pickedRef(inputs.host_wall));
    if (host?.feature.type !== "custom") return null;
    id = pickedRef(host.feature.params.inputs.outline);
  }
  const sketch = features.find((f) => f.id === id);
  return sketch?.feature.type === "sketch" ? sketch : null;
}

/**
 * Whether a `segments` input picks partitions (its outline input names an
 * Interior wall: a door in a partition) rather than sides of an outline.
 */
export function segmentsPickPartitions(
  manifest: PluginManifest,
  input: Extract<PluginInput, { kind: "segments" }>,
  values: Readonly<Record<string, string>>,
  features: readonly FeatureResponse[],
): boolean {
  const pick = manifest.inputs.find((i) => i.name === input.outline_input);
  if (pick === undefined) return false;
  const id = firstPicked(values[pick.name]);
  const row = features.find((f) => f.id === id);
  return (
    row?.feature.type === "custom" &&
    row.feature.params.plugin_id === INTERIOR_WALL
  );
}

/**
 * The lines a `segments` input offers, named: an outline's sides, or an
 * Interior wall's partitions ({@link segmentsPickPartitions}).
 */
export function segmentSides(
  partitions: boolean,
  entities: readonly SketchEntity[],
): OutlineSide[] | null {
  return partitions ? partitionSides(entities) : outlineSides(entities);
}

/**
 * The inputs hidden by a pick (`superseded_by`): a wall's typed start and
 * length once an Outline is picked, its base elevation once a Floor is; a
 * window's typed size while Size is a call size rather than its
 * `superseded_unless` option (Custom). Their stored values are kept; the form
 * neither shows nor checks them.
 */
export function supersededInputs(
  manifest: PluginManifest,
  values: Readonly<Record<string, string>>,
): Set<string> {
  const hidden = new Set<string>();
  for (const input of manifest.inputs) {
    const by = input.superseded_by ?? null;
    if (by === null) continue;
    const value = values[by] ?? "";
    const unless = input.superseded_unless ?? null;
    if (value !== "" && value !== unless) hidden.add(input.name);
  }
  return hidden;
}
