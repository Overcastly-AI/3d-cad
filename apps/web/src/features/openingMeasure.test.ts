import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  convertDistance,
  endDistances,
  hostWallLine,
  type HostWallLine,
  type MeasureFrom,
  nearerEnd,
  withReference,
} from "./openingMeasure";

const IN = 25.4;

/** B7's front wall: 288 in, walked clockwise from X 288 back to X 0. */
const FRONT: HostWallLine = {
  start: { x: 288 * IN, y: 0 },
  end: { x: 0, y: 0 },
  lengthMm: 288 * IN,
};
/** A wall walked from the origin out. */
const OUT: HostWallLine = {
  start: { x: 0, y: 0 },
  end: { x: 240 * IN, y: 0 },
  lengthMm: 240 * IN,
};

describe("convertDistance", () => {
  // A window 48 in from the start of a 240 in wall: 192 from its end, 72
  // before its centre.
  const at: Record<Exclude<MeasureFrom, "nearer">, number> = {
    start: 48 * IN,
    end: 192 * IN,
    centre: -72 * IN,
  };
  const refs = ["start", "end", "centre"] as const;
  for (const from of refs) {
    for (const to of refs) {
      it(`${from} -> ${to} keeps the opening put`, () => {
        expect(convertDistance(at[from], from, to, OUT)).toBeCloseTo(at[to], 9);
      });
    }
  }

  it("signs the centre distance: positive towards the wall's end", () => {
    expect(convertDistance(200 * IN, "start", "centre", OUT)).toBeCloseTo(
      80 * IN,
      9,
    );
    expect(convertDistance(40 * IN, "start", "centre", OUT)).toBeCloseTo(
      -80 * IN,
      9,
    );
    expect(convertDistance(-80 * IN, "centre", "end", OUT)).toBeCloseTo(
      200 * IN,
      9,
    );
  });

  it("reads Nearer the origin as the end it is, both ways", () => {
    expect(nearerEnd(FRONT)).toBe("end");
    expect(nearerEnd(OUT)).toBe("start");
    expect(convertDistance(60 * IN, "nearer", "start", FRONT)).toBeCloseTo(
      228 * IN,
      9,
    );
    expect(convertDistance(60 * IN, "nearer", "end", FRONT)).toBeCloseTo(
      60 * IN,
      9,
    );
    expect(convertDistance(60 * IN, "nearer", "centre", FRONT)).toBeCloseTo(
      84 * IN,
      9,
    );
    expect(convertDistance(228 * IN, "start", "nearer", FRONT)).toBeCloseTo(
      60 * IN,
      9,
    );
  });

  it("takes the start on a tie, as nearer_end does", () => {
    const centred: HostWallLine = {
      start: { x: -60 * IN, y: 0 },
      end: { x: 60 * IN, y: 0 },
      lengthMm: 120 * IN,
    };
    expect(nearerEnd(centred)).toBe("start");
  });
});

describe("withReference", () => {
  const values = { measure_from: "end", offset_mm: "60", width_mm: "36" };

  it("converts an inch part's distance and keeps the other fields", () => {
    expect(withReference(values, "start", FRONT, "in", undefined)).toEqual({
      measure_from: "start",
      offset_mm: "228",
      width_mm: "36",
    });
    expect(
      withReference(values, "centre", FRONT, "in", undefined).offset_mm,
    ).toBe("84");
    const centre = { ...values, measure_from: "centre", offset_mm: "-84" };
    expect(withReference(centre, "end", FRONT, "in", undefined).offset_mm).toBe(
      "228",
    );
  });

  it("converts a mm part's distance", () => {
    const mm = { measure_from: "start", offset_mm: "1219.2" };
    expect(withReference(mm, "end", OUT, "mm", undefined).offset_mm).toBe(
      "4876.8",
    );
    expect(withReference(mm, "centre", OUT, "mm", undefined).offset_mm).toBe(
      "-1828.8",
    );
  });

  it("round-trips to the stored value's own text", () => {
    const stored = 60 * IN;
    const there = withReference(values, "start", FRONT, "in", stored);
    const back = withReference(there, "end", FRONT, "in", stored);
    expect(back.offset_mm).toBe("60");
  });

  it("only changes the reference when there is nothing to convert", () => {
    expect(withReference(values, "start", null, "in", undefined)).toEqual({
      ...values,
      measure_from: "start",
    });
    const blank = { ...values, offset_mm: "" };
    expect(withReference(blank, "start", FRONT, "in", undefined)).toEqual({
      ...blank,
      measure_from: "start",
    });
    // Nearer the origin IS the end here: the same point, the same number.
    expect(withReference(values, "nearer", FRONT, "in", undefined)).toEqual({
      ...values,
      measure_from: "nearer",
    });
  });
});

describe("endDistances", () => {
  it("reads the centre from both ends", () => {
    const ends = endDistances(60 * IN, "end", FRONT);
    expect(ends?.start).toBeCloseTo(228 * IN, 9);
    expect(ends?.end).toBeCloseTo(60 * IN, 9);
    expect(endDistances(null, "end", FRONT)).toBeNull();
    expect(endDistances(60 * IN, "end", null)).toBeNull();
  });
});

function row(id: string, feature: unknown): FeatureResponse {
  return { id, name: id, feature } as unknown as FeatureResponse;
}

function section(
  name: string | null,
  a: [number, number],
  b: [number, number],
) {
  const p = (x: number, y: number) => ({ x, y });
  return {
    id: `s-${name ?? "x"}`,
    role: "section",
    index: 0,
    name: name === null ? null : `section/${name}`,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        constraints: [],
        entities: [
          { id: "e1", kind: "line", start: p(...a), end: p(...b) },
          { id: "e2", kind: "line", start: p(...b), end: p(b[0], 140) },
        ],
      },
    },
  };
}

function member(role: string, name: string | null) {
  return {
    id: `m-${name ?? role}`,
    role,
    index: 0,
    name,
    feature: { type: "extrude", version: 1, params: {} },
  };
}

describe("hostWallLine", () => {
  const single = row("w1", {
    type: "custom",
    version: 1,
    params: {
      plugin_id: "loft.wall",
      plugin_version: "1.0.0",
      inputs: {},
      expansion: [
        section(null, [0, 0], [100, 0]),
        member("stud", null),
        section(null, [10, 20], [10 + 3000, 20]),
        member("top_plate", null),
      ],
    },
  });
  const outline = row("w2", {
    type: "custom",
    version: 1,
    params: {
      plugin_id: "loft.wall",
      plugin_version: "1.3.0",
      inputs: { outline: { kind: "feature", feature_id: "s1" } },
      expansion: [
        section("e1/top", [7315.2, 0], [0, 0]),
        member("top_plate", "e1/course/1"),
        section("e2/top", [0, 0], [0, 4597.4]),
        member("top_plate", "e2/course/1"),
      ],
    },
  });

  it("reads a single wall's length and ends from its top plate", () => {
    const line = hostWallLine([single], "w1", "");
    expect(line?.lengthMm).toBeCloseTo(3000, 9);
    expect(line?.start).toEqual({ x: 10, y: 20 });
    expect(hostWallLine([single], "w1", "e1")).toBeNull();
  });

  it("reads an outline wall's line by its sketch line", () => {
    expect(hostWallLine([outline], "w2", "e1")).toEqual({
      start: { x: 7315.2, y: 0 },
      end: { x: 0, y: 0 },
      lengthMm: 7315.2,
    });
    expect(hostWallLine([outline], "w2", "e2")?.lengthMm).toBeCloseTo(
      4597.4,
      9,
    );
    expect(hostWallLine([outline], "w2", "")).toBeNull();
    expect(hostWallLine([outline], "w2", "e9")).toBeNull();
    expect(hostWallLine([outline], "nope", "e1")).toBeNull();
  });
});
