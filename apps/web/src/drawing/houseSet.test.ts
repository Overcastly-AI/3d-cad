import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/partTypes";
import {
  HOUSE_SCALE,
  HOUSE_SET,
  drawingMembers,
  hasMaterialsView,
} from "./houseSet";

describe("the house set", () => {
  it("lays out a plan, four elevations and a materials list at 1:48", () => {
    expect(HOUSE_SET.map((sheet) => sheet.name)).toEqual([
      "Plan",
      "Elevations",
      "Materials",
    ]);
    expect(HOUSE_SET.flatMap((sheet) => sheet.views)).toEqual([
      "plan",
      "elevation_front",
      "elevation_back",
      "elevation_left",
      "elevation_right",
      "materials",
    ]);
    expect(HOUSE_SCALE).toEqual({ numerator: 1, denominator: 48 });
  });

  it("reads each plugin member's role from the stored expansion", () => {
    const features = [
      { id: "s", feature: { type: "sketch" } },
      {
        id: "w",
        feature: {
          type: "custom",
          params: {
            plugin_id: "loft.wall",
            expansion: [
              { id: "m1", role: "stud", feature: {} },
              { id: "m2", role: "header", feature: {} },
            ],
          },
        },
      },
    ] as unknown as FeatureResponse[];
    expect(drawingMembers(features)).toEqual([
      { feature_id: "m1", plugin_id: "loft.wall", role: "stud" },
      { feature_id: "m2", plugin_id: "loft.wall", role: "header" },
    ]);
  });

  it("knows a materials sheet by its view", () => {
    expect(hasMaterialsView([{ projection: "materials" }])).toBe(true);
    expect(hasMaterialsView([{ projection: "plan" }])).toBe(false);
  });
});
