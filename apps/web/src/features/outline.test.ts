/**
 * BUILDING-OUTLINE: an outline's lines are named by the way their walls face,
 * walked clockwise from the sketch's first line (`loft_wire.plugins
 * .SegmentsInput`), and a side pick finds its outline through the wall.
 */
import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import type { PluginManifest } from "../api/plugins";
import type { SketchEntity } from "../sketch/tools";
import {
  INTERIOR_WALL,
  facingOf,
  outlineSides,
  partitionSides,
  segmentSides,
  segmentsOutlineSketch,
  segmentsPickPartitions,
  sideName,
  splitLines,
  supersededInputs,
} from "./outline";

type P = [number, number];

/** A loop of lines e1..en through *corners*, in the order given. */
function loop(corners: P[], extra: SketchEntity[] = []): SketchEntity[] {
  const lines = corners.map(([x, y], k) => {
    const [nx, ny] = corners[(k + 1) % corners.length] as P;
    return {
      id: `e${k + 1}`,
      kind: "line",
      construction: false,
      start: { x, y },
      end: { x: nx, y: ny },
    } as SketchEntity;
  });
  return [...extra, ...lines];
}

const ORIGIN = {
  id: "origin",
  kind: "point",
  construction: true,
  position: { x: 0, y: 0 },
} as SketchEntity;

/** B7: the Rectangle tool from the origin, counter-clockwise. */
const B7 = loop(
  [
    [0, 0],
    [288, 0],
    [288, 192],
    [0, 192],
  ],
  [ORIGIN],
);

function names(entities: SketchEntity[]) {
  return outlineSides(entities)?.map((s) => [s.lineId, s.name]);
}

describe("outlineSides", () => {
  it("walks B7 clockwise from its first line: front, left, back, right", () => {
    expect(names(B7)).toEqual([
      ["e1", "Front"],
      ["e4", "Left"],
      ["e3", "Back"],
      ["e2", "Right"],
    ]);
    const front = outlineSides(B7)?.[0];
    // Walked clockwise, the front runs from its far end to the origin.
    expect(front?.start).toEqual({ x: 288, y: 0 });
    expect(front?.end).toEqual({ x: 0, y: 0 });
  });

  it("reads a clockwise drawing the same, from its own first line", () => {
    const cw = loop([
      [0, 0],
      [0, 192],
      [288, 192],
      [288, 0],
    ]);
    expect(names(cw)).toEqual([
      ["e1", "Left"],
      ["e2", "Back"],
      ["e3", "Right"],
      ["e4", "Front"],
    ]);
  });

  it("numbers two lines facing one way along the walk", () => {
    // An L: 240 x 192 less a 96 x 72 notch at the back right.
    const l = loop([
      [0, 0],
      [240, 0],
      [240, 120],
      [144, 120],
      [144, 192],
      [0, 192],
    ]);
    expect(names(l)).toEqual([
      ["e1", "Front"],
      ["e6", "Left"],
      ["e5", "Back 1"],
      ["e4", "Right 1"],
      ["e3", "Back 2"],
      ["e2", "Right 2"],
    ]);
  });

  it("joins lines drawn either way round and skips construction", () => {
    const flipped = B7.map((e) =>
      e.kind === "line" && e.id === "e3"
        ? ({ ...e, start: e.end, end: e.start } as SketchEntity)
        : e,
    );
    const axis = {
      id: "c1",
      kind: "line",
      construction: true,
      start: { x: 0, y: 96 },
      end: { x: 288, y: 96 },
    } as SketchEntity;
    expect(names([...flipped, axis])).toEqual(names(B7));
  });

  it("is null for lines that do not close one loop", () => {
    expect(outlineSides(B7.slice(0, 4))).toBeNull();
    const gap = B7.map((e) =>
      e.kind === "line" && e.id === "e2"
        ? ({ ...e, end: { x: 288, y: 190 } } as SketchEntity)
        : e,
    );
    expect(outlineSides(gap)).toBeNull();
    // Two loops: the second rectangle's lines never join the first.
    const two = [
      ...B7,
      ...loop([
        [400, 0],
        [500, 0],
        [500, 100],
      ]).map((e) => ({ ...e, id: `x${e.id}` }) as SketchEntity),
    ];
    expect(outlineSides(two)).toBeNull();
  });

  it("faces a slanted line by its nearer axis, a tie to front/back", () => {
    expect(facingOf({ x: 10, y: 0 }, { x: 0, y: 1 })).toBe("front");
    expect(facingOf({ x: 0, y: 0 }, { x: 1, y: 1 })).toBe("back");
    expect(facingOf({ x: 0, y: 0 }, { x: 1, y: 10 })).toBe("left");
    expect(sideName(outlineSides(B7), "e3")).toBe("Back");
    expect(sideName(null, "e3")).toBe("e3");
  });
});

function row(id: string, feature: unknown): FeatureResponse {
  return {
    id,
    part_id: "p",
    order_index: 0,
    name: id,
    feature,
    rolled_back: false,
    created_at: "",
    updated_at: "",
  } as unknown as FeatureResponse;
}

const SKETCH = row("s1", {
  type: "sketch",
  version: 1,
  params: { entities: B7, constraints: [], plane: {} },
});
const OUTLINE_WALL = row("w1", {
  type: "custom",
  version: 1,
  params: {
    plugin_id: "loft.wall",
    plugin_version: "1.3.0",
    inputs: { outline: { kind: "feature", feature_id: "s1" } },
  },
});
const LINE_WALL = row("w2", {
  type: "custom",
  version: 1,
  params: { plugin_id: "loft.wall", plugin_version: "1.2.0", inputs: {} },
});

const ROOF = {
  id: "loft.roof",
  version: "1.4.0",
  title: "Roof",
  description: "",
  members: [],
  inputs: [
    {
      kind: "features",
      name: "walls",
      label: "Walls",
      feature_types: ["custom"],
      plugin_ids: ["loft.wall"],
      min_items: 0,
      max_items: 8,
    },
    {
      kind: "segments",
      name: "slope_walls",
      label: "Defines slope",
      outline_input: "walls",
      min_items: 0,
      max_items: 32,
    },
    {
      kind: "length",
      name: "span_mm",
      label: "Span",
      default: 3048,
      superseded_by: "walls",
    },
  ],
} as unknown as PluginManifest;

const SLOPE = ROOF.inputs[1] as Extract<
  PluginManifest["inputs"][number],
  { kind: "segments" }
>;

describe("segmentsOutlineSketch", () => {
  const tree = [SKETCH, OUTLINE_WALL, LINE_WALL];
  it("finds the outline through the first picked outline wall", () => {
    expect(
      segmentsOutlineSketch(ROOF, SLOPE, { walls: "w1,w2" }, tree)?.id,
    ).toBe("s1");
  });
  it("is null for no pick, a line wall, or a sketch it cannot find", () => {
    expect(segmentsOutlineSketch(ROOF, SLOPE, { walls: "" }, tree)).toBeNull();
    expect(
      segmentsOutlineSketch(ROOF, SLOPE, { walls: "w2" }, tree),
    ).toBeNull();
    expect(
      segmentsOutlineSketch(ROOF, SLOPE, { walls: "w1" }, [OUTLINE_WALL]),
    ).toBeNull();
  });
  it("takes a picked sketch as the outline itself", () => {
    expect(segmentsOutlineSketch(ROOF, SLOPE, { walls: "s1" }, tree)?.id).toBe(
      "s1",
    );
  });
});

describe("supersededInputs", () => {
  it("hides a typed input once the pick that replaces it is set", () => {
    expect([...supersededInputs(ROOF, { walls: "" })]).toEqual([]);
    expect([...supersededInputs(ROOF, { walls: "w1" })]).toEqual(["span_mm"]);
  });

  it("hides a window's typed size on every Size but its superseded_unless", () => {
    const window = {
      ...ROOF,
      inputs: [
        {
          kind: "choice",
          name: "size",
          label: "Size",
          options: [
            { value: "window_3040", label: "3040" },
            { value: "custom", label: "Custom" },
          ],
          default: "window_3040",
        },
        {
          kind: "length",
          name: "width_mm",
          label: "Custom width",
          default: 914.4,
          superseded_by: "size",
          superseded_unless: "custom",
        },
      ],
    } as unknown as PluginManifest;
    expect([...supersededInputs(window, { size: "window_3040" })]).toEqual([
      "width_mm",
    ]);
    expect([...supersededInputs(window, { size: "custom" })]).toEqual([]);
  });
});

/** B10 (INTERIOR-WALLS): B7 plus P1 (X 180, drawn from the back) and P2
 * (Y 132, from the right wall to P1), each ending on another line's middle. */
const PARTITIONS = [
  {
    id: "e5",
    kind: "line",
    construction: false,
    start: { x: 180, y: 192 },
    end: { x: 180, y: 0 },
  },
  {
    id: "e6",
    kind: "line",
    construction: false,
    start: { x: 288, y: 132 },
    end: { x: 180, y: 132 },
  },
] as SketchEntity[];
const B10 = [...B7, ...PARTITIONS];

describe("splitLines and partitionSides", () => {
  it("keeps B7's sides when partitions are drawn on its outline", () => {
    expect(names(B10)).toEqual(names(B7));
    const { loop: sides, off } = splitLines(B10);
    expect(sides.map((l) => l.id)).toEqual(["e1", "e2", "e3", "e4"]);
    expect(off.map((l) => l.id)).toEqual(["e5", "e6"]);
  });
  it("names the lines off the loop as partitions, in sketch order", () => {
    expect(partitionSides(B10).map((s) => [s.lineId, s.name])).toEqual([
      ["e5", "Partition 1"],
      ["e6", "Partition 2"],
    ]);
    expect(partitionSides(B7)).toEqual([]);
    // A separate sketch of partitions alone: every line is one.
    expect(
      partitionSides([ORIGIN, ...PARTITIONS]).map((s) => s.lineId),
    ).toEqual(["e5", "e6"]);
  });
});

describe("a door in a partition", () => {
  const PLAN = row("s1", {
    type: "sketch",
    version: 1,
    params: { entities: B10, constraints: [], plane: {} },
  });
  const INTERIOR = row("i1", {
    type: "custom",
    version: 1,
    params: {
      plugin_id: INTERIOR_WALL,
      plugin_version: "1.0.0",
      inputs: { host_wall: { kind: "feature", feature_id: "w1" } },
    },
  });
  const DOOR = {
    id: "loft.door",
    version: "1.4.0",
    title: "Door",
    description: "",
    members: [],
    inputs: [
      {
        kind: "feature",
        name: "host_wall",
        label: "Host wall",
        feature_types: ["custom"],
        plugin_ids: ["loft.wall", INTERIOR_WALL],
        host: true,
      },
      {
        kind: "segments",
        name: "wall_segment",
        label: "Wall",
        outline_input: "host_wall",
        min_items: 0,
        max_items: 1,
      },
    ],
  } as unknown as PluginManifest;
  const WALL = DOOR.inputs[1] as Extract<
    PluginManifest["inputs"][number],
    { kind: "segments" }
  >;
  const tree = [PLAN, OUTLINE_WALL, INTERIOR];

  it("picks a partition of the Interior wall's plan, through its walls", () => {
    const values = { host_wall: "i1" };
    expect(segmentsOutlineSketch(DOOR, WALL, values, tree)?.id).toBe("s1");
    expect(segmentsPickPartitions(DOOR, WALL, values, tree)).toBe(true);
    expect(segmentSides(true, B10)?.map((s) => s.name)).toEqual([
      "Partition 1",
      "Partition 2",
    ]);
  });
  it("picks a side of an outline wall as before", () => {
    const values = { host_wall: "w1" };
    expect(segmentsPickPartitions(DOOR, WALL, values, tree)).toBe(false);
    expect(segmentSides(false, B10)?.map((s) => s.name)).toEqual([
      "Front",
      "Left",
      "Back",
      "Right",
    ]);
  });
});
