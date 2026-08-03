import { describe, expect, it } from "vitest";

import type { ExtrudeParams, FeatureResponse } from "../api/parts";
import {
  canSubmitExtrude,
  defaultExtrudeDirection,
  defaultExtrudeForm,
  defaultProfileId,
  describeExtrudeDirection,
  distanceError,
  extrudePreviewState,
  formFromParams,
  optionProvenance,
  parseDistanceMm,
  planeProvenance,
  profileOptions,
  withDirection,
  withOperation,
  withProfile,
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

/** A sketch seated on datum feature `datumId` (an on-face or offset datum). */
function sketchOnDatum(
  id: string,
  name: string,
  datumId: string,
): FeatureResponse {
  const base = sketch(id, name);
  return {
    ...base,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "feature", feature_id: datumId },
        entities: [],
        constraints: [],
      },
    },
  };
}

/** An `on_face` datum — the seat whose normal is the OUTWARD face normal. */
function onFaceDatum(id: string): FeatureResponse {
  return {
    ...sketch(id, "Datum1"),
    feature: {
      type: "datum",
      version: 1,
      params: {
        kind: "on_face",
        face: {
          kind: "subshape",
          feature_id: "x1",
          subshape_type: "face",
          selector: {
            selector_version: 1,
            signature: {
              subshape_type: "face",
              surface: "plane",
              normal: { x: 0, y: 0, z: 1 },
              centroid: { x: 0, y: 0, z: 10 },
              area_mm2: 100,
            },
          },
        },
        offset_mm: 0,
      },
    },
  };
}

/** An offset datum — a free-standing plane with no material side. */
function offsetDatum(id: string): FeatureResponse {
  return {
    ...sketch(id, "Datum2"),
    feature: {
      type: "datum",
      version: 1,
      params: { kind: "offset", base: "XY", offset_mm: 30, flip: false },
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
      directionTouched: false,
      merge: true,
    });
  });

  it("adds outward off a face-seated sketch (metal belongs outside)", () => {
    expect(defaultExtrudeForm("sk", "face").direction).toBe("normal");
  });
});

// FB-4: "I select a sketch do a cut it somehow misses everything going a
// different way." An on_face datum's z_dir IS the outward face normal, so the
// old hardcoded `direction: "normal"` swept a cut straight out of the solid.
describe("defaultExtrudeDirection", () => {
  it("cuts INTO the material from a face-seated sketch", () => {
    expect(defaultExtrudeDirection("cut", "face")).toBe("reverse");
  });

  it("adds OUT of the material from a face-seated sketch", () => {
    expect(defaultExtrudeDirection("add", "face")).toBe("normal");
  });

  it("leaves a base/datum plane alone — it has no material side", () => {
    expect(defaultExtrudeDirection("cut", "base")).toBe("normal");
    expect(defaultExtrudeDirection("add", "base")).toBe("normal");
  });
});

describe("planeProvenance / optionProvenance", () => {
  it("reads a sketch on an on_face datum as face-seated", () => {
    const features = [
      onFaceDatum("d1"),
      sketchOnDatum("s1", "Sketch1", "d1"),
      sketch("s2", "Sketch2"),
      offsetDatum("d2"),
      sketchOnDatum("s3", "Sketch3", "d2"),
    ];
    expect(planeProvenance(features, "s1")).toBe("face");
    // An origin datum and a constructed (offset) datum are both free-standing.
    expect(planeProvenance(features, "s2")).toBe("base");
    expect(planeProvenance(features, "s3")).toBe("base");
    // An unknown sketch cannot be face-seated on the evidence available.
    expect(planeProvenance(features, "nope")).toBe("base");
    expect(profileOptions(features).map((p) => p.provenance)).toEqual([
      "face",
      "base",
      "base",
    ]);
    expect(optionProvenance(profileOptions(features), "s1")).toBe("face");
    expect(optionProvenance(profileOptions(features), "gone")).toBe("base");
  });
});

describe("withOperation / withProfile / withDirection", () => {
  const faceForm = defaultExtrudeForm("s1", "face");

  it("re-defaults the direction when the operation switches to cut", () => {
    const cut = withOperation(faceForm, "cut", "face");
    expect(cut).toMatchObject({
      operation: "cut",
      direction: "reverse",
      directionTouched: false,
    });
    // …and back again when the user returns to an add.
    expect(withOperation(cut, "add", "face").direction).toBe("normal");
  });

  it("never re-defaults a direction the user chose", () => {
    const chosen = withDirection(faceForm, "normal");
    expect(chosen.directionTouched).toBe(true);
    expect(withOperation(chosen, "cut", "face")).toMatchObject({
      operation: "cut",
      direction: "normal",
    });
  });

  it("tracks the override by touch, not by value", () => {
    // The user picks the value that HAPPENS to be the current default, then
    // switches operation: their choice must still stand. Inferring "overridden"
    // from `direction !== default` would silently flip this one.
    const chosen = withDirection(defaultExtrudeForm("s1", "face"), "normal");
    expect(withOperation(chosen, "cut", "face").direction).toBe("normal");
  });

  it("re-reads the seat when the profile is retargeted", () => {
    const cutOnDatum = withOperation(defaultExtrudeForm("s2"), "cut", "base");
    expect(cutOnDatum.direction).toBe("normal");
    expect(withProfile(cutOnDatum, "s1", "face").direction).toBe("reverse");
    // A user-chosen direction survives a profile switch too.
    const touched = withDirection(cutOnDatum, "normal");
    expect(withProfile(touched, "s1", "face")).toMatchObject({
      profileFeatureId: "s1",
      direction: "normal",
    });
  });
});

describe("describeExtrudeDirection", () => {
  it("says where the material goes on a face-seated sketch", () => {
    expect(describeExtrudeDirection("cut", "reverse", "face")).toBe(
      "Cuts into the part, behind the face.",
    );
    expect(describeExtrudeDirection("cut", "normal", "face")).toContain(
      "nothing to remove",
    );
    expect(describeExtrudeDirection("add", "normal", "face")).toBe(
      "Builds out from the face.",
    );
  });

  it("names the axis on a free-standing plane rather than claiming a side", () => {
    expect(describeExtrudeDirection("cut", "normal", "base")).toBe(
      "Along the plane normal.",
    );
    expect(describeExtrudeDirection("cut", "reverse", "base")).toBe(
      "Against the plane normal.",
    );
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
      // Session-scoped: the stored direction shows as authored, but an
      // operation switch in this session re-defaults it (FB-4).
      directionTouched: false,
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
