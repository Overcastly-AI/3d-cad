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
  label: `Body ${i + 1}`,
  named: false,
  unrenamed: `Body ${i + 1}`,
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
    expect(toggleCutBody("all", rows, "b2", false)).toEqual([
      { kind: "feature", feature_id: "b1" },
      { kind: "feature", feature_id: "b4" },
    ]);
  });

  it("re-ticking a body never widens a narrowed cut to every body", () => {
    // The review's repro: bodies b1, b2, b3; the cut lists [b1, b2] (b3 was
    // excluded earlier and is no longer met, so it is not a row). Unticking
    // b2 and ticking it back must restore [b1, b2], not "all", which would
    // cut b3, the body the modeller left out.
    const three = BODIES.slice(0, 3);
    const listed = [
      { kind: "feature" as const, feature_id: "b1" },
      { kind: "feature" as const, feature_id: "b2" },
    ];
    const rows = cutBodyRows(listed, ["b1", "b2"], three);
    expect(rows.map((r) => [r.id, r.checked])).toEqual([
      ["b1", true],
      ["b2", true],
    ]);
    const unticked = toggleCutBody(listed, rows, "b2", false);
    expect(unticked).toEqual([{ kind: "feature", feature_id: "b1" }]);
    const again = toggleCutBody(
      unticked,
      cutBodyRows(unticked, ["b1", "b2"], three),
      "b2",
      true,
    );
    expect(again).toEqual(listed);
  });

  it("every body met stays every body until a row is unticked", () => {
    const rows = cutBodyRows("all", ["b1", "b2"], BODIES);
    const narrowed = toggleCutBody("all", rows, "b1", false);
    expect(narrowed).toEqual([{ kind: "feature", feature_id: "b2" }]);
    // Ticking b1 back is the explicit list of both, not "all".
    const both = cutBodyRows(narrowed, ["b1", "b2"], BODIES);
    expect(toggleCutBody(narrowed, both, "b1", true)).toEqual([
      { kind: "feature", feature_id: "b1" },
      { kind: "feature", feature_id: "b2" },
    ]);
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
