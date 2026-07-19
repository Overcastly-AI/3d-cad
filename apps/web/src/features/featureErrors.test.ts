import { describe, expect, it } from "vitest";

import type { BooleanParams, FeatureResponse } from "../api/parts";
import {
  friendlyFeatureError,
  offersBooleanDisjointRecovery,
} from "./featureErrors";

describe("friendlyFeatureError", () => {
  it("humanises the boolean rebuild codes", () => {
    expect(friendlyFeatureError("boolean_empty", "raw kernel text")).toMatch(
      /don't overlap|whole body/i,
    );
    // boolean_disjoint now guides the recovery instead of naming it unsupported.
    expect(friendlyFeatureError("boolean_disjoint", "raw kernel text")).toMatch(
      /keep as one body/i,
    );
  });

  it("falls back to the server message for unmapped codes", () => {
    expect(friendlyFeatureError("axis_intersects_profile", "server msg")).toBe(
      "server msg",
    );
  });
});

/** A boolean feature row with the given allow_disjoint state. */
function booleanFeature(allowDisjoint: boolean): FeatureResponse {
  const params: BooleanParams = {
    operation: "union",
    target: { kind: "feature", feature_id: "x1" },
    tool: { kind: "feature", feature_id: "x2" },
    allow_disjoint: allowDisjoint,
  };
  return {
    id: "b1",
    name: "Combine1",
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
    rolled_back: false,
    feature: { type: "boolean", version: 1, params },
  };
}

describe("offersBooleanDisjointRecovery", () => {
  it("offers recovery for a boolean_disjoint on a boolean with the opt-in off", () => {
    expect(
      offersBooleanDisjointRecovery(booleanFeature(false), "boolean_disjoint"),
    ).toBe(true);
  });

  it("does not offer recovery once allow_disjoint is already on", () => {
    expect(
      offersBooleanDisjointRecovery(booleanFeature(true), "boolean_disjoint"),
    ).toBe(false);
  });

  it("does not offer recovery for a different error code", () => {
    expect(
      offersBooleanDisjointRecovery(booleanFeature(false), "boolean_empty"),
    ).toBe(false);
  });

  it("does not offer recovery for a non-boolean feature", () => {
    const sketch: FeatureResponse = {
      id: "s1",
      name: "Sketch1",
      part_id: "p",
      order_index: 0,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
      rolled_back: false,
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [],
          constraints: [],
        },
      },
    };
    expect(offersBooleanDisjointRecovery(sketch, "boolean_disjoint")).toBe(
      false,
    );
  });
});
