import { describe, expect, it } from "vitest";

import type { FeatureResponse, LoftParams } from "../api/parts";
import {
  addSection,
  buildLoftParams,
  canSubmitLoft,
  defaultLoftForm,
  defaultLoftSections,
  formFromLoftParams,
  loftEligibleSketchCount,
  moveSection,
  removeSectionAt,
  setSectionAt,
} from "./loft";

function sketch(id: string, name: string): FeatureResponse {
  return {
    id,
    name,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
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
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
  };
}

const threeSketchesAndABody = [
  sketch("s1", "Sketch1"),
  sketch("s2", "Sketch2"),
  sketch("s3", "Sketch3"),
  extrude("x1", "s1"),
];

describe("defaultLoftSections / defaultLoftForm", () => {
  it("seeds the first two sketches in build order as the section stack", () => {
    expect(defaultLoftSections(threeSketchesAndABody)).toEqual(["s1", "s2"]);
    expect(defaultLoftForm(["s1", "s2"])).toEqual({
      sections: ["s1", "s2"],
      operation: "add",
      merge: true,
    });
  });

  it("only counts sketches (the extrude is never a section candidate)", () => {
    expect(loftEligibleSketchCount(threeSketchesAndABody)).toBe(3);
    expect(loftEligibleSketchCount([extrude("x1", "s1")])).toBe(0);
  });
});

describe("formFromLoftParams", () => {
  it("round-trips an existing loft's ordered profiles into form state", () => {
    const params: LoftParams = {
      profiles: [
        { kind: "feature", feature_id: "s1" },
        { kind: "feature", feature_id: "s3" },
        { kind: "feature", feature_id: "s2" },
      ],
      operation: "cut",
      merge: true,
    };
    expect(formFromLoftParams(params)).toEqual({
      sections: ["s1", "s3", "s2"],
      operation: "cut",
      merge: true,
    });
  });
});

describe("ordered-section list ops", () => {
  it("adds an empty slot the user must then fill", () => {
    expect(addSection(defaultLoftForm(["s1", "s2"]))).toEqual({
      sections: ["s1", "s2", ""],
      operation: "add",
      merge: true,
    });
  });

  it("removes the slot at an index", () => {
    expect(
      removeSectionAt(defaultLoftForm(["s1", "s2", "s3"]), 1).sections,
    ).toEqual(["s1", "s3"]);
  });

  it("sets the sketch id of a slot", () => {
    expect(setSectionAt(defaultLoftForm(["s1", ""]), 1, "s3").sections).toEqual(
      ["s1", "s3"],
    );
  });

  it("reorders by swapping with the neighbour (order is the blend sequence)", () => {
    const form = defaultLoftForm(["s1", "s2", "s3"]);
    expect(moveSection(form, 0, 1).sections).toEqual(["s2", "s1", "s3"]);
    expect(moveSection(form, 2, -1).sections).toEqual(["s1", "s3", "s2"]);
    // Out-of-range moves are no-ops (the ends can't move past the stack).
    expect(moveSection(form, 0, -1).sections).toEqual(["s1", "s2", "s3"]);
    expect(moveSection(form, 2, 1).sections).toEqual(["s1", "s2", "s3"]);
  });
});

describe("canSubmitLoft", () => {
  it("needs ≥2 sections with every slot chosen", () => {
    expect(canSubmitLoft(defaultLoftForm(["s1", "s2"]))).toBe(true);
    expect(canSubmitLoft(defaultLoftForm(["s1", "s2", "s3"]))).toBe(true);
    // Fewer than two sections can't skin a solid.
    expect(canSubmitLoft(defaultLoftForm(["s1"]))).toBe(false);
    expect(canSubmitLoft(defaultLoftForm([]))).toBe(false);
    // An unchosen slot blocks submit — no silent default section.
    expect(canSubmitLoft(defaultLoftForm(["s1", ""]))).toBe(false);
  });
});

describe("buildLoftParams", () => {
  it("builds the ordered FeatureRef list from a valid form", () => {
    expect(buildLoftParams(defaultLoftForm(["s1", "s2", "s3"]))).toEqual({
      profiles: [
        { kind: "feature", feature_id: "s1" },
        { kind: "feature", feature_id: "s2" },
        { kind: "feature", feature_id: "s3" },
      ],
      operation: "add",
      merge: true,
    });
  });

  it("is null when the form is incomplete", () => {
    expect(buildLoftParams(defaultLoftForm(["s1"]))).toBeNull();
    expect(buildLoftParams(defaultLoftForm(["s1", ""]))).toBeNull();
  });
});
