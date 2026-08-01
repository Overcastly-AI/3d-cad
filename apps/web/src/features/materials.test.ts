import { describe, expect, it } from "vitest";

import type { BodyLumpInfo, MaterialAssignment } from "../api/materials";
import type { BodyInfo } from "./bodies";
import {
  bodyMaterialRows,
  isUnassigned,
  massState,
  materialName,
  overrideFor,
  propertiesEyebrow,
  soleMaterial,
  unassignedBodies,
  unassignedNotice,
  withBodyMaterial,
  withDefaultMaterial,
} from "./materials";

function body(id: string, name: string, ordinal: number): BodyInfo {
  return { baseFeatureId: id, name, featureType: "extrude", ordinal };
}

function lump(
  id: string,
  material: BodyLumpInfo["material"] = null,
  mass_g: number | null = null,
): BodyLumpInfo {
  return { base_feature_id: id, lumps: 1, material, mass_g };
}

const TWO_BODIES = [body("b1", "Extrude1", 1), body("b2", "Boss", 2)];
const EMPTY: MaterialAssignment = { default_material: null, bodies: [] };

describe("bodyMaterialRows", () => {
  it("joins the tree's names to the evaluation's RESOLVED material + mass", () => {
    const rows = bodyMaterialRows(
      TWO_BODIES,
      [lump("b1", "aluminium_6061", 27), lump("b2", "steel_1018", 57.56)],
      {
        default_material: "aluminium_6061",
        bodies: [{ base_feature_id: "b2", material: "steel_1018" }],
      },
    );
    expect(rows.map((r) => r.name)).toEqual(["Extrude1", "Boss"]);
    expect(rows[0]?.material).toBe("aluminium_6061");
    expect(rows[1]?.massG).toBe(57.56);
    // The OVERRIDE is what the picker shows; the RESOLVED material is what the
    // server decided. Body 1 inherits the default, so it has no override.
    expect(rows[0]?.override).toBeNull();
    expect(rows[1]?.override).toBe("steel_1018");
  });

  it("marks a body the evaluation never mentioned as UNEVALUATED", () => {
    const rows = bodyMaterialRows(TWO_BODIES, [lump("b1")], EMPTY);
    expect(rows[0]?.evaluated).toBe(true);
    expect(rows[1]?.evaluated).toBe(false);
    // ...and it is therefore never named as the body missing a material: an
    // edited/rolled-back tree is not evidence about what anything is made of.
    expect(unassignedBodies(rows).map((r) => r.name)).toEqual(["Extrude1"]);
  });
});

describe("overrideFor", () => {
  it("finds the override for a body and nothing for the others", () => {
    const assignment: MaterialAssignment = {
      default_material: null,
      bodies: [{ base_feature_id: "b2", material: "brass_c360" }],
    };
    expect(overrideFor(assignment, "b2")).toBe("brass_c360");
    expect(overrideFor(assignment, "b1")).toBeNull();
    expect(overrideFor(null, "b2")).toBeNull();
  });
});

describe("massState — absence is a STATE, never a zero", () => {
  const assigned = bodyMaterialRows(
    TWO_BODIES,
    [lump("b1", "aluminium_6061", 27), lump("b2", "steel_1018", 57.56)],
    EMPTY,
  );
  const halfAssigned = bodyMaterialRows(
    TWO_BODIES,
    [lump("b1", "aluminium_6061", 27), lump("b2")],
    EMPTY,
  );
  const none = bodyMaterialRows(TWO_BODIES, [lump("b1"), lump("b2")], EMPTY);

  it("reports a real mass as known", () => {
    expect(massState(84.56, assigned)).toEqual({ kind: "known", massG: 84.56 });
  });

  it("reports a genuinely massless body as known 0 — not as absence", () => {
    // The whole reason `mass_g` is nullable: `0` is a claim, `null` is not.
    expect(massState(0, assigned)).toEqual({ kind: "known", massG: 0 });
  });

  it("calls a null total with SOME materials partial, and names the gap", () => {
    const state = massState(null, halfAssigned);
    expect(state.kind).toBe("partial");
    expect(
      state.kind === "partial" ? state.missing.map((r) => r.name) : [],
    ).toEqual(["Boss"]);
  });

  it("calls a part with nothing assigned unassigned", () => {
    expect(massState(null, none).kind).toBe("unassigned");
    expect(massState(undefined, none).kind).toBe("unassigned");
    expect(massState(null, []).kind).toBe("unassigned");
  });
});

describe("propertiesEyebrow — a title is a CLAIM", () => {
  it("says MASS PROPERTIES only when there is a mass", () => {
    expect(propertiesEyebrow({ kind: "known", massG: 27 })).toBe(
      "Mass properties",
    );
    expect(propertiesEyebrow({ kind: "unassigned" })).toBe("Properties");
    expect(propertiesEyebrow({ kind: "partial", missing: [] })).toBe(
      "Properties",
    );
  });
});

describe("unassignedNotice", () => {
  const rowsMissing = (names: string[]) =>
    bodyMaterialRows(
      names.map((n, i) => body(`b${i}`, n, i + 1)),
      names.map((_, i) => lump(`b${i}`)),
      EMPTY,
    );

  it("names one body in the singular", () => {
    expect(unassignedNotice(rowsMissing(["Boss"]))).toBe(
      "Boss has no material, so the part has no total mass.",
    );
  });

  it("names two or three bodies in the plural", () => {
    expect(unassignedNotice(rowsMissing(["Boss", "Pin"]))).toBe(
      "Boss and Pin have no material, so the part has no total mass.",
    );
    expect(unassignedNotice(rowsMissing(["A", "B", "C"]))).toBe(
      "A, B and C have no material, so the part has no total mass.",
    );
  });

  it("truncates a long list instead of filling the panel", () => {
    expect(unassignedNotice(rowsMissing(["A", "B", "C", "D", "E"]))).toBe(
      "A, B and C (+2 more) have no material, so the part has no total mass.",
    );
  });

  it("has nothing to say when every evaluated body has a material", () => {
    const rows = bodyMaterialRows(
      TWO_BODIES,
      [lump("b1", "abs", 4), lump("b2", "abs", 5)],
      EMPTY,
    );
    expect(unassignedNotice(rows)).toBeNull();
  });
});

describe("soleMaterial — the density headline is quoted only when it is true", () => {
  it("is the one material every evaluated body resolves to", () => {
    const rows = bodyMaterialRows(
      TWO_BODIES,
      [lump("b1", "pla", 4), lump("b2", "pla", 5)],
      EMPTY,
    );
    expect(soleMaterial(EMPTY, rows)).toBe("pla");
  });

  it("is null for a MIXED part (two densities, no single headline)", () => {
    const rows = bodyMaterialRows(
      TWO_BODIES,
      [lump("b1", "pla", 4), lump("b2", "steel_1018", 5)],
      EMPTY,
    );
    expect(soleMaterial(EMPTY, rows)).toBeNull();
  });

  it("falls back to the document default before anything is evaluated", () => {
    expect(soleMaterial({ default_material: "abs", bodies: [] }, [])).toBe(
      "abs",
    );
    // ...but not when a body overrides it: the default no longer speaks for all.
    expect(
      soleMaterial(
        {
          default_material: "abs",
          bodies: [{ base_feature_id: "b1", material: "pla" }],
        },
        [],
      ),
    ).toBeNull();
  });
});

describe("withDefaultMaterial / withBodyMaterial — WHOLESALE replacement", () => {
  it("sets and clears the document default, keeping overrides", () => {
    const start: MaterialAssignment = {
      default_material: null,
      bodies: [{ base_feature_id: "b2", material: "steel_1018" }],
    };
    const set = withDefaultMaterial(start, "aluminium_6061");
    expect(set.default_material).toBe("aluminium_6061");
    expect(set.bodies).toEqual(start.bodies);
    expect(withDefaultMaterial(set, null).default_material).toBeNull();
  });

  it("adds, replaces and removes ONE body's override without duplicating it", () => {
    const one = withBodyMaterial(EMPTY, "b2", "steel_1018");
    expect(one.bodies).toEqual([
      { base_feature_id: "b2", material: "steel_1018" },
    ]);
    // Re-assigning the same body REPLACES: a duplicate would make that body's
    // mass depend on array order, which the boundary rejects outright.
    const replaced = withBodyMaterial(one, "b2", "brass_c360");
    expect(replaced.bodies).toEqual([
      { base_feature_id: "b2", material: "brass_c360" },
    ]);
    expect(withBodyMaterial(replaced, "b2", null).bodies).toEqual([]);
  });

  it("never mutates the assignment it was given", () => {
    const start: MaterialAssignment = { default_material: null, bodies: [] };
    withBodyMaterial(start, "b1", "pla");
    withDefaultMaterial(start, "pla");
    expect(start).toEqual({ default_material: null, bodies: [] });
  });
});

describe("isUnassigned / materialName", () => {
  it("recognises the honest empty state", () => {
    expect(isUnassigned(EMPTY)).toBe(true);
    expect(isUnassigned(undefined)).toBe(true);
    expect(isUnassigned({ default_material: "abs", bodies: [] })).toBe(false);
    expect(
      isUnassigned({
        default_material: null,
        bodies: [{ base_feature_id: "b1", material: "abs" }],
      }),
    ).toBe(false);
  });

  it("names a key from the SERVED library, falling back to the key itself", () => {
    const library = [{ key: "abs" as const, name: "ABS", density_kg_m3: 1040 }];
    expect(materialName(library, "abs")).toBe("ABS");
    expect(materialName(library, "pla")).toBe("pla");
    expect(materialName(library, null)).toBeNull();
  });
});
