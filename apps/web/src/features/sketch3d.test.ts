import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import { chainOf, pipeCurveOptions } from "./pipe";
import {
  addAlong,
  addCoincident,
  addDimension,
  addFixed,
  buildSketch3DParams,
  constraintLabel,
  continueTo,
  emptySketch3DForm,
  endChain,
  formFromSketch3DParams,
  parseCoordinate,
  placePoint,
  removeEntity,
  solvedSketch3DMap,
  toggleSelected,
} from "./sketch3d";
import { snapTargets } from "./sketch3dSnaps";

const v = (x: number, y: number, z: number) => ({ x, y, z });

describe("3D sketch drawing", () => {
  it("chains typed points into lines and ends the chain on request", () => {
    let form = emptySketch3DForm();
    form = placePoint(form, v(0, 0, 0), { kind: "origin" });
    form = placePoint(form, v(-142, 0, 479));
    form = placePoint(form, v(390, 0, 570));
    expect(form.points.map((p) => p.id)).toEqual(["p1", "p2", "p3"]);
    expect(form.lines).toEqual([
      { id: "l1", start: "p1", end: "p2", construction: false },
      { id: "l2", start: "p2", end: "p3", construction: false },
    ]);
    form = endChain(form);
    form = placePoint(form, v(434, 0, 427));
    expect(form.lines).toHaveLength(2);
    // Clicking an own point continues the chain there; a repeat is no line.
    form = continueTo(form, "p1");
    expect(form.lines.at(-1)).toEqual({
      id: "l3",
      start: "p4",
      end: "p1",
      construction: false,
    });
    form = continueTo(form, "p4");
    expect(form.lines).toHaveLength(3);
  });

  it("reuses a point for the same snap target", () => {
    let form = placePoint(emptySketch3DForm(), v(0, 0, 0), { kind: "origin" });
    form = placePoint(form, v(10, 0, 0));
    form = placePoint(form, v(0, 0, 0), { kind: "origin" });
    expect(form.points).toHaveLength(2);
    // p2 -> p1 is the line already drawn: no second line, the chain is at p1.
    expect(form.lines).toHaveLength(1);
    expect(form.chainFrom).toBe("p1");
  });

  it("parses the three cells in the document unit", () => {
    expect(parseCoordinate(["1", "-2", "0.5"], "in")).toEqual(
      v(25.4, -50.8, 12.7),
    );
    expect(parseCoordinate(["1", "", "0"], "mm")).toBeNull();
  });
});

describe("3D sketch relations", () => {
  const base = () => {
    let form = placePoint(emptySketch3DForm(), v(0, 0, 0));
    form = placePoint(form, v(0, 64, 0));
    return form;
  };

  it("puts a line's relations on the selected line", () => {
    let form = toggleSelected(base(), "l1");
    form = addAlong(form, "y");
    expect(form.constraints).toEqual([
      { kind: "along", line: "l1", axis: "y" },
    ]);
    expect(form.selected).toEqual([]);
    form = addDimension(toggleSelected(form, "l1"), 65);
    expect(form.constraints.at(-1)).toEqual({
      kind: "length",
      line: "l1",
      value_mm: 65,
    });
  });

  it("puts distance and coincident on two points, fix on one", () => {
    let form = toggleSelected(toggleSelected(base(), "p1"), "p2");
    form = addDimension(form, 130);
    expect(form.constraints).toEqual([
      { kind: "distance", a: "p1", b: "p2", value_mm: 130 },
    ]);
    form = addCoincident(toggleSelected(toggleSelected(form, "p1"), "p2"));
    expect(form.constraints.at(-1)).toEqual({
      kind: "coincident",
      a: "p1",
      b: "p2",
    });
    form = addFixed(toggleSelected(form, "p1"));
    expect(form.constraints.at(-1)).toEqual({ kind: "fixed", point: "p1" });
    // A line relation needs exactly one line selected.
    expect(addAlong(toggleSelected(form, "p1"), "x")).toEqual(
      toggleSelected(form, "p1"),
    );
  });

  it("deleting a point takes its lines and every relation on them", () => {
    let form = addAlong(toggleSelected(base(), "l1"), "y");
    form = addFixed(toggleSelected(form, "p2"));
    form = removeEntity(form, "p2");
    expect(form.points.map((p) => p.id)).toEqual(["p1"]);
    expect(form.lines).toEqual([]);
    expect(form.constraints).toEqual([]);
  });

  it("labels relations in the document unit", () => {
    expect(
      constraintLabel({ kind: "length", line: "l1", value_mm: 25.4 }, "in"),
    ).toBe("Length l1 = 1 in");
    expect(
      constraintLabel({ kind: "along", line: "l2", axis: "z" }, "mm"),
    ).toBe("Along Z l2");
  });
});

describe("3D sketch params", () => {
  it("round-trips through the wire shape", () => {
    let form = placePoint(emptySketch3DForm(), v(0, 0, 0), { kind: "origin" });
    form = placePoint(form, v(1, 2, 3));
    form = addDimension(toggleSelected(form, "l1"), 10);
    const params = buildSketch3DParams(form);
    expect(params.entities[0]).toEqual({
      id: "p1",
      kind: "point",
      position: v(0, 0, 0),
      snap: { kind: "origin" },
    });
    expect(params.entities[1]).toEqual({
      id: "p2",
      kind: "point",
      position: v(1, 2, 3),
    });
    const back = formFromSketch3DParams(params);
    expect(buildSketch3DParams(back)).toEqual(params);
  });

  it("reads the solved payload out of an evaluation", () => {
    const map = solvedSketch3DMap([
      { feature_id: "a", data: { kind: "solved_sketch", entities: [] } },
      {
        feature_id: "b",
        data: { kind: "solved_sketch_3d", points: [], dof: 0 },
      },
      { feature_id: "c" },
    ]);
    expect([...map.keys()]).toEqual(["b"]);
  });
});

function sketch3d(): FeatureResponse {
  return {
    id: "s3",
    name: "Skeleton",
    feature: {
      type: "sketch_3d",
      version: 1,
      params: {
        entities: [
          { id: "bb", kind: "point", position: v(0, 0, 0) },
          { id: "dl", kind: "point", position: v(-404, 64, 70) },
          { id: "dr", kind: "point", position: v(-404, -64, 70) },
          { id: "cs_l", kind: "line", start: "bb", end: "dl" },
          { id: "cs_r", kind: "line", start: "bb", end: "dr" },
        ],
        constraints: [],
      },
    },
  } as unknown as FeatureResponse;
}

describe("Pipe on 3D sketch lines", () => {
  it("lists them at their solved positions and chains only straight on", () => {
    const solved = new Map([
      [
        "s3",
        {
          kind: "solved_sketch_3d" as const,
          dof: 3,
          points: [{ id: "dl", position: v(-404, 65, 70) }],
        },
      ],
    ]);
    const options = pipeCurveOptions([sketch3d()], solved);
    expect(options.map((o) => o.key)).toEqual(["s3:cs_l", "s3:cs_r"]);
    expect(options[0]?.lengthMm).toBeCloseTo(Math.hypot(404, 65, 70), 9);
    // The two stays meet at the BB at an angle: a corner, so one pick is one tube.
    expect(chainOf(options, "s3:cs_l")).toEqual(["s3:cs_l"]);
  });
});

describe("3D sketch snap targets", () => {
  it("offers the origin, earlier sketch points and model vertices once each", () => {
    const signature = {
      curve: "line" as const,
      end_a: v(0, 0, 0),
      end_b: v(0, 0, 10),
      midpoint: v(0, 0, 5),
      length_mm: 10,
    };
    const targets = snapTargets({
      flat: [],
      sketches3d: [
        {
          featureId: "s3",
          name: "Skeleton",
          points: new Map([["bb", v(1, 2, 3)]]),
          lines: [],
          solved: true,
        },
      ],
      edges: [
        { signature, polyline: [] },
        { signature: { ...signature, end_b: v(5, 0, 0) }, polyline: [] },
      ] as never,
      anchorId: "body",
    });
    expect(targets.map((t) => t.key)).toEqual([
      "origin",
      "Skeleton-bb",
      "vertex-0-a",
      "vertex-0-b",
      "vertex-1-b",
    ]);
    expect(targets[1]?.snap).toEqual({
      kind: "sketch_point",
      sketch: { kind: "feature", feature_id: "s3" },
      entity: "bb",
      point: "position",
    });
    expect(targets[3]?.snap).toMatchObject({ kind: "vertex", end: "b" });
    // A 3D sketch's joints are offered as points (`position`) only, never as
    // a line's start or end, which the kernel does not resolve.
    for (const t of targets) {
      if (t.snap.kind === "sketch_point") {
        expect(t.snap.point).toBe("position");
      }
    }
  });
});
