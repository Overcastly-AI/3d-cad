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
 * The sketch's non-construction lines as one clockwise loop from its first
 * line, each named by side; null when they do not close exactly one loop
 * (the plugin then refuses the outline with the reason).
 */
export function outlineSides(
  entities: readonly SketchEntity[],
): OutlineSide[] | null {
  const lines = entities.filter(isLoopLine);
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

/**
 * The inputs hidden by a pick (`superseded_by`): a wall's typed start and
 * length once an Outline is picked, its base elevation once a Floor is. Their
 * stored values are kept; the form neither shows nor checks them.
 */
export function supersededInputs(
  manifest: PluginManifest,
  values: Readonly<Record<string, string>>,
): Set<string> {
  const hidden = new Set<string>();
  for (const input of manifest.inputs) {
    const by = input.superseded_by ?? null;
    if (by !== null && (values[by] ?? "") !== "") hidden.add(input.name);
  }
  return hidden;
}
