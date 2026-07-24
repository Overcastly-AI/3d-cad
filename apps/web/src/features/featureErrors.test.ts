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

  it("humanises the mirror rebuild codes", () => {
    expect(friendlyFeatureError("no_target_body", "raw")).toMatch(
      /no body to mirror/i,
    );
    expect(friendlyFeatureError("reference_unresolved", "raw")).toMatch(
      /mirror plane can no longer be found/i,
    );
    expect(friendlyFeatureError("mirror_failed", "raw")).toMatch(
      /reflection couldn't be joined/i,
    );
  });

  it("humanises the revolve rebuild codes", () => {
    expect(friendlyFeatureError("no_axis", "raw")).toMatch(
      /construction centerline|usable line/i,
    );
    expect(friendlyFeatureError("profile_not_closed", "raw")).toMatch(
      /closed region|construction centerline/i,
    );
    expect(friendlyFeatureError("axis_intersects_profile", "raw")).toMatch(
      /through the profile|to one side/i,
    );
  });

  it("keys profile_not_closed copy on the feature type (FINDINGS #13)", () => {
    // An open-profile EXTRUDE must not read revolve axis advice.
    const extrude = friendlyFeatureError(
      "profile_not_closed",
      "raw",
      "extrude",
    );
    expect(extrude).toMatch(/extrude/i);
    expect(extrude).not.toMatch(/centerline|axis/i);
    // A revolve keeps its axis-idiom guidance.
    const revolve = friendlyFeatureError(
      "profile_not_closed",
      "raw",
      "revolve",
    );
    expect(revolve).toMatch(/centerline/i);
    // Sweep and loft each name their own section, still never the axis.
    expect(friendlyFeatureError("profile_not_closed", "raw", "sweep")).toMatch(
      /swept|section/i,
    );
    expect(friendlyFeatureError("profile_not_closed", "raw", "loft")).toMatch(
      /section/i,
    );
  });

  it("uses the generic profile copy when no feature type is given", () => {
    const generic = friendlyFeatureError("profile_not_closed", "raw");
    expect(generic).toMatch(/closed region/i);
    expect(generic).not.toMatch(/centerline|axis/i);
  });

  it("falls back to friendly/server copy for a type without an override", () => {
    // A hole reuses the same profile code but has no override → generic copy.
    expect(
      friendlyFeatureError("profile_not_closed", "raw", "hole"),
    ).not.toMatch(/centerline|axis/i);
  });

  it("falls back to the server message for unmapped codes", () => {
    expect(friendlyFeatureError("revolve_failed", "server msg")).toBe(
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
