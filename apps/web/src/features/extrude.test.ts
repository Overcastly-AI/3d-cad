import { describe, expect, it } from "vitest";

import type { ExtrudeParams, FeatureResponse } from "../api/parts";
import {
  canSubmitExtrude,
  defaultExtrudeForm,
  defaultProfileId,
  distanceError,
  formFromParams,
  parseDistanceMm,
  profileOptions,
} from "./extrude";

function sketch(id: string, name: string): FeatureResponse {
  return {
    id,
    name,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
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
}

function extrude(id: string, profileId: string): FeatureResponse {
  return {
    ...sketch(id, "Extrude1"),
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: profileId },
        distance_mm: 12,
        operation: "cut",
        direction: "reverse",
      },
    },
  };
}

describe("parseDistanceMm", () => {
  it("accepts positive numbers, rejects empty/non-numeric/non-positive", () => {
    expect(parseDistanceMm("10")).toBe(10);
    expect(parseDistanceMm(" 2.5 ")).toBe(2.5);
    expect(parseDistanceMm("")).toBeNull();
    expect(parseDistanceMm("abc")).toBeNull();
    expect(parseDistanceMm("0")).toBeNull();
    expect(parseDistanceMm("-4")).toBeNull();
  });
});

describe("distanceError", () => {
  it("is quiet while empty (pending) and flags invalid non-empty input", () => {
    expect(distanceError("")).toBeNull();
    expect(distanceError("10")).toBeNull();
    expect(distanceError("0")).toContain("positive");
    expect(distanceError("nope")).toContain("positive");
  });
});

describe("defaultExtrudeForm", () => {
  it("is 10 mm / add / normal against the given profile", () => {
    expect(defaultExtrudeForm("sk")).toEqual({
      profileFeatureId: "sk",
      distanceInput: "10",
      operation: "add",
      direction: "normal",
    });
  });
});

describe("formFromParams", () => {
  it("round-trips an existing extrude's params into editable form state", () => {
    const params: ExtrudeParams = {
      profile: { kind: "feature", feature_id: "sk" },
      distance_mm: 6.5,
      operation: "cut",
      direction: "reverse",
    };
    expect(formFromParams(params)).toEqual({
      profileFeatureId: "sk",
      distanceInput: "6.5",
      operation: "cut",
      direction: "reverse",
    });
  });
});

describe("canSubmitExtrude", () => {
  it("needs both a profile and a valid distance", () => {
    expect(canSubmitExtrude(defaultExtrudeForm("sk"))).toBe(true);
    expect(canSubmitExtrude(defaultExtrudeForm(""))).toBe(false);
    expect(
      canSubmitExtrude({ ...defaultExtrudeForm("sk"), distanceInput: "0" }),
    ).toBe(false);
  });
});

describe("profileOptions / defaultProfileId", () => {
  it("offers only sketches and defaults to the last one", () => {
    const features = [
      sketch("s1", "Sketch1"),
      extrude("x1", "s1"),
      sketch("s2", "Sketch2"),
    ];
    expect(profileOptions(features).map((p) => p.id)).toEqual(["s1", "s2"]);
    expect(defaultProfileId(features)).toBe("s2");
    expect(defaultProfileId([])).toBe("");
  });
});
