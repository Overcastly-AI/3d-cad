import { Box3, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { DATUM_X_AXIS_ID } from "../sketch/datum";
import { sceneOriginBasis } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";
import { MIN_SKETCH_FIT_MM, sketchWorldBox } from "./sketchFit";

const XY = sceneOriginBasis("XY");

function line(
  id: string,
  a: [number, number],
  b: [number, number],
): SketchEntity {
  return {
    id,
    kind: "line",
    construction: false,
    start: { x: a[0], y: a[1] },
    end: { x: b[0], y: b[1] },
  };
}

describe("sketchWorldBox", () => {
  it("is null for an empty sketch — nothing drawn is nothing to frame", () => {
    expect(sketchWorldBox([], XY, new Box3())).toBeNull();
  });

  it("frames the drawn ink in SCENE coordinates (XY is the ground: kernel y -> scene -z)", () => {
    const box = sketchWorldBox(
      [line("a", [150, 0], [230, 0]), line("b", [230, 0], [230, 40])],
      XY,
      new Box3(),
    );
    expect(box).not.toBeNull();
    expect(box!.min.toArray()).toEqual([150, 0, -40]);
    expect(box!.max.toArray()).toEqual([230, 0, 0]);
  });

  it("counts a circle's RIM, not only its centre", () => {
    const circle: SketchEntity = {
      id: "c",
      kind: "circle",
      construction: false,
      center: { x: 100, y: 0 },
      radius: 25,
    };
    const box = sketchWorldBox([circle], XY, new Box3())!;
    expect(box.min.x).toBeCloseTo(75, 6);
    expect(box.max.x).toBeCloseTo(125, 6);
  });

  it("ignores the plane's own datum frame — that is furniture, not ink", () => {
    const withFrame = [
      line("a", [10, 10], [20, 10]),
      line(DATUM_X_AXIS_ID, [-500, 0], [500, 0]),
    ];
    const box = sketchWorldBox(withFrame, XY, new Box3())!;
    expect(box.min.x).toBe(10);
    expect(box.max.x).toBe(20);
    expect(sketchWorldBox([withFrame[1]!], XY, new Box3())).toBeNull();
  });

  it("never hands back a zero-size box: a lone point is grown to the floor", () => {
    const point: SketchEntity = {
      id: "p",
      kind: "point",
      construction: false,
      position: { x: 40, y: 0 },
    };
    const box = sketchWorldBox([point], XY, new Box3())!;
    const size = box.getSize(new Vector3()).length();
    expect(size).toBeCloseTo(MIN_SKETCH_FIT_MM, 6);
    const centre = box.getCenter(new Vector3());
    expect(centre.x).toBeCloseTo(40, 9);
    expect(Math.abs(centre.y) + Math.abs(centre.z)).toBeCloseTo(0, 9);
  });

  it("writes into the caller's box (no allocation per fit)", () => {
    const into = new Box3();
    expect(sketchWorldBox([line("a", [0, 0], [30, 0])], XY, into)).toBe(into);
  });
});
