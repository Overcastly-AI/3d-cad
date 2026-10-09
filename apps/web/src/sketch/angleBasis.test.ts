import { describe, expect, it } from "vitest";

import { angleBasis, edgeLine, originAxisLine } from "./angleBasis";
import { resolveDatumBasis, type AnyDatumParams } from "./plane";

const close = (a: readonly number[], b: readonly number[]) => {
  a.forEach((v, i) => expect(v).toBeCloseTo(b[i] as number, 12));
};

describe("angleBasis — the kernel's plane_at_angle, ported", () => {
  it("0 deg is the plane through the line parallel to the reference", () => {
    const basis = angleBasis(
      { point: [5, 3, 7], direction: [0, 2, 0] },
      [0, 0, 1],
      0,
      false,
    );
    expect(basis).not.toBeNull();
    close(basis?.normal ?? [], [0, 0, 1]);
    close(basis?.u ?? [], [0, 1, 0]);
    // The line's point nearest the world origin.
    close(basis?.origin ?? [], [5, 0, 7]);
  });

  it("turns right-handed about the line; flip keeps u", () => {
    const s = Math.sin(Math.PI / 6);
    const c = Math.cos(Math.PI / 6);
    const basis = angleBasis(originAxisLine("X"), [0, 0, 1], 30, false);
    close(basis?.normal ?? [], [0, -s, c]);
    const flipped = angleBasis(originAxisLine("X"), [0, 0, 1], 30, true);
    close(flipped?.normal ?? [], [0, s, -c]);
    close(flipped?.u ?? [], [1, 0, 0]);
  });

  it("refuses a line that pierces the reference (the server's 422 twin)", () => {
    expect(
      angleBasis(
        { point: [0, 0, 0], direction: [1, 0, 1] },
        [0, 0, 1],
        10,
        false,
      ),
    ).toBeNull();
  });

  it("reads a picked edge end_a -> end_b, and refuses a curve", () => {
    const signature = {
      subshape_type: "edge" as const,
      curve: "line" as const,
      end_a: { x: 40, y: 0, z: 10 },
      end_b: { x: 40, y: 20, z: 10 },
      midpoint: { x: 40, y: 10, z: 10 },
      length_mm: 20,
    };
    const ref = {
      kind: "subshape" as const,
      feature_id: "body",
      subshape_type: "edge" as const,
      selector: { selector_version: 1 as const, signature },
    };
    expect(edgeLine(ref)).toEqual({
      point: [40, 0, 10],
      direction: [0, 20, 0],
    });
    expect(
      edgeLine({
        ...ref,
        selector: {
          ...ref.selector,
          signature: { ...signature, curve: "circle" },
        },
      }),
    ).toBeNull();
  });
});

describe("resolveDatumBasis — an angle datum about a sketch line", () => {
  it("maps the line through its sketch's datum and follows an edit", () => {
    // The steering-head plane: a line along -Y at x = -32 on XY + 495, turned
    // 25 deg from XY: normal (-sin25, 0, cos25), origin the apex.
    const byId = new Map<string, AnyDatumParams>([
      ["d0", { kind: "offset", base: "XY", offset_mm: 495, flip: false }],
      [
        "d1",
        {
          kind: "angle",
          line: {
            kind: "sketch_line",
            sketch: { kind: "feature", feature_id: "s1" },
            entity: "head",
          },
          reference: { kind: "datum_plane", plane: "XY" },
          angle_deg: 25,
          flip: false,
        },
      ],
    ]);
    const sketches = (x: number) =>
      new Map([
        [
          "s1",
          {
            plane: { kind: "feature" as const, feature_id: "d0" },
            entities: [
              {
                id: "head",
                kind: "line" as const,
                construction: true,
                start: { x, y: 10 },
                end: { x, y: -10 },
              },
            ],
          },
        ],
      ]);
    const rake = (25 * Math.PI) / 180;
    const basis = resolveDatumBasis("d1", byId, new Set(), sketches(-32));
    close(basis?.normal ?? [], [-Math.sin(rake), 0, Math.cos(rake)]);
    close(basis?.origin ?? [], [-32, 0, 495]);
    close(
      resolveDatumBasis("d1", byId, new Set(), sketches(-50))?.origin ?? [],
      [-50, 0, 495],
    );
    // Without the sketch table the client cannot place it — null, not a guess.
    expect(resolveDatumBasis("d1", byId)).toBeNull();
  });
});
