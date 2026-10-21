import { describe, expect, it } from "vitest";

import type { BodyInfo } from "./bodies";
import {
  cutBodiesBlocker,
  cutBodiesField,
  cutBodyRows,
  seedCutBodies,
  toggleCutBody,
} from "./cutBodies";
import { defaultExtrudeForm, extrudeParamsFromForm } from "./extrude";
import { buildPipeParams, defaultPipeForm } from "./pipe";

const BODIES: BodyInfo[] = ["b1", "b2", "b3", "b4"].map((id, i) => ({
  baseFeatureId: id,
  name: `Wall ${i + 1}`,
  featureType: "extrude",
  ordinal: i + 1,
}));

describe("Objects To Cut (CUT-OBJECTS-TO-CUT)", () => {
  it("a new cut cuts every body it meets; an add carries no list", () => {
    const form = { ...defaultExtrudeForm("sk"), operation: "cut" as const };
    expect(extrudeParamsFromForm(form, 5).cut_bodies).toBe("all");
    expect(
      extrudeParamsFromForm(defaultExtrudeForm("sk"), 5),
    ).not.toHaveProperty("cut_bodies");
    const pipe = buildPipeParams(
      {
        ...defaultPipeForm(),
        curves: ["s:l1"],
        hollow: false,
        operation: "cut",
      },
      "mm",
    );
    expect(pipe?.cut_bodies).toBe("all");
  });

  it("seeds a stored cut's choice verbatim, absent staying absent", () => {
    const listed = [{ kind: "feature" as const, feature_id: "b2" }];
    expect(seedCutBodies({ operation: "cut", cut_bodies: listed })).toBe(
      listed,
    );
    expect(seedCutBodies({ operation: "cut" })).toBeUndefined();
    // An add switched to Cut in its edit is a new cut.
    expect(seedCutBodies({ operation: "add" })).toBe("all");
    expect(cutBodiesField("cut", undefined)).toEqual({});
    expect(cutBodiesField("add", "all")).toEqual({});
  });

  it("lists the bodies met, ticked, and unticking one narrows to the rest", () => {
    const rows = cutBodyRows("all", ["b1", "b2", "b4"], BODIES);
    expect(rows.map((r) => [r.label, r.checked])).toEqual([
      ["Body 1 · Wall 1", true],
      ["Body 2 · Wall 2", true],
      ["Body 4 · Wall 4", true],
    ]);
    expect(toggleCutBody(rows, "b2", false)).toEqual([
      { kind: "feature", feature_id: "b1" },
      { kind: "feature", feature_id: "b4" },
    ]);
  });

  it("ticking every row again is every body met", () => {
    const narrowed = toggleCutBody(
      cutBodyRows("all", ["b1", "b2"], BODIES),
      "b1",
      false,
    );
    const rows = cutBodyRows(narrowed, ["b2"], BODIES);
    // The unticked body stays listed (it was met) only while it is listed;
    // the rows are the met bodies plus the listed ones.
    expect(rows.map((r) => r.id)).toEqual(["b2"]);
    const both = cutBodyRows(narrowed, ["b1", "b2"], BODIES);
    expect(toggleCutBody(both, "b1", true)).toBe("all");
  });

  it("refuses a Save with nothing ticked", () => {
    expect(cutBodiesBlocker("cut", [])).toBe(
      "Tick a body under Objects To Cut.",
    );
    expect(cutBodiesBlocker("cut", "all")).toBeNull();
    expect(cutBodiesBlocker("add", [])).toBeNull();
  });

  it("a new cut has no rows yet (it has not met anything)", () => {
    expect(cutBodyRows("all", null, BODIES)).toEqual([]);
  });
});
