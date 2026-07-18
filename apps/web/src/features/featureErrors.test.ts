import { describe, expect, it } from "vitest";

import { friendlyFeatureError } from "./featureErrors";

describe("friendlyFeatureError", () => {
  it("humanises the boolean rebuild codes", () => {
    expect(friendlyFeatureError("boolean_empty", "raw kernel text")).toMatch(
      /don't overlap|whole body/i,
    );
    expect(friendlyFeatureError("boolean_disjoint", "raw kernel text")).toMatch(
      /separate pieces|isn't supported/i,
    );
  });

  it("falls back to the server message for unmapped codes", () => {
    expect(friendlyFeatureError("axis_intersects_profile", "server msg")).toBe(
      "server msg",
    );
  });
});
