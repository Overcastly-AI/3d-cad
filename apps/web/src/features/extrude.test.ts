import { describe, expect, it } from "vitest";

import type { ExtrudeParams, FeatureResponse } from "../api/parts";
import {
  canSubmitExtrude,
  defaultExtrudeForm,
  defaultProfileId,
  distanceError,
  extrudePreviewState,
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
        merge: true,
      },
    },
  };
}

describe("parseDistanceMm", () => {
  it("accepts positive numbers, rejects empty/non-numeric/non-positive", () => {
    expect(parseDistanceMm("10", "mm")).toBe(10);
    expect(parseDistanceMm(" 2.5 ", "mm")).toBe(2.5);
    expect(parseDistanceMm("", "mm")).toBeNull();
    expect(parseDistanceMm("abc", "mm")).toBeNull();
    expect(parseDistanceMm("0", "mm")).toBeNull();
    expect(parseDistanceMm("-4", "mm")).toBeNull();
  });

  it("converts a bare number in the document unit to canonical mm", () => {
    expect(parseDistanceMm("2", "in")).toBe(50.8);
    expect(parseDistanceMm("1", "cm")).toBe(10);
  });

  it("honours an explicit suffix override", () => {
    expect(parseDistanceMm("25.4 mm", "in")).toBe(25.4);
    expect(parseDistanceMm("2in", "mm")).toBe(50.8);
  });
});

describe("distanceError", () => {
  it("is quiet while empty (pending) and flags invalid non-empty input", () => {
    expect(distanceError("", "mm")).toBeNull();
    expect(distanceError("10", "mm")).toBeNull();
    expect(distanceError("0", "mm")).toContain("positive");
    expect(distanceError("nope", "mm")).toContain("positive");
  });
});

describe("defaultExtrudeForm", () => {
  it("is 10 mm / add / normal / merge against the given profile", () => {
    expect(defaultExtrudeForm("sk")).toEqual({
      profileFeatureId: "sk",
      distanceInput: "10",
      operation: "add",
      direction: "normal",
      merge: true,
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
      merge: true,
    };
    expect(formFromParams(params, "mm")).toEqual({
      profileFeatureId: "sk",
      distanceInput: "6.5",
      operation: "cut",
      direction: "reverse",
      merge: true,
    });
  });

  it("carries a merge:false (new-body) add through the round-trip", () => {
    const params: ExtrudeParams = {
      profile: { kind: "feature", feature_id: "sk" },
      distance_mm: 6.5,
      operation: "add",
      direction: "normal",
      merge: false,
    };
    expect(formFromParams(params, "mm").merge).toBe(false);
  });

  it("seeds the edit form in the document unit (mm → in)", () => {
    const params: ExtrudeParams = {
      profile: { kind: "feature", feature_id: "sk" },
      distance_mm: 50.8,
      operation: "add",
      direction: "normal",
      merge: true,
    };
    expect(formFromParams(params, "in").distanceInput).toBe("2");
  });
});

describe("canSubmitExtrude", () => {
  it("needs both a profile and a valid distance", () => {
    expect(canSubmitExtrude(defaultExtrudeForm("sk"), "mm")).toBe(true);
    expect(canSubmitExtrude(defaultExtrudeForm(""), "mm")).toBe(false);
    expect(
      canSubmitExtrude(
        { ...defaultExtrudeForm("sk"), distanceInput: "0" },
        "mm",
      ),
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

describe("extrudePreviewState", () => {
  it("projects a valid form to the live-ghost shape (mm)", () => {
    const preview = extrudePreviewState(
      {
        ...defaultExtrudeForm("sk"),
        distanceInput: "12",
        direction: "reverse",
      },
      "mm",
    );
    expect(preview).toEqual({
      profileFeatureId: "sk",
      distanceMm: 12,
      direction: "reverse",
      operation: "add",
    });
  });

  it("reads the distance in the document unit (2 in → 50.8 mm)", () => {
    const preview = extrudePreviewState(
      { ...defaultExtrudeForm("sk"), distanceInput: "2" },
      "in",
    );
    expect(preview?.distanceMm).toBeCloseTo(50.8, 6);
  });

  it("is null while the form has no profile or no valid distance", () => {
    expect(
      extrudePreviewState(
        { ...defaultExtrudeForm(""), distanceInput: "10" },
        "mm",
      ),
    ).toBeNull();
    expect(
      extrudePreviewState(
        { ...defaultExtrudeForm("sk"), distanceInput: "" },
        "mm",
      ),
    ).toBeNull();
    expect(
      extrudePreviewState(
        { ...defaultExtrudeForm("sk"), distanceInput: "0" },
        "mm",
      ),
    ).toBeNull();
  });
});
