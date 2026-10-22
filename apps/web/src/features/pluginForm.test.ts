/**
 * The form generator (PLUGIN-UI): a custom feature's fields, seeds, checks
 * and write are derived from the served manifest alone. The fixture is the
 * twisted prism's real manifest shape (packages/loft-plugins), plus a count,
 * an optional feature reference and a material to cover every input kind.
 */
import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import type { CustomParams, PluginManifest } from "../api/plugins";
import { TWISTED_PRISM } from "../test/pluginFixture";
import {
  boundsPhrase,
  defaultPluginForm,
  fieldKind,
  firstPluginBlocker,
  formFromCustomParams,
  inputPointer,
  inputUnit,
  isNumericInput,
  type NumericInput,
  pickedIds,
  type PluginForm,
  pluginInputsFromForm,
  referenceOptions,
  togglePick,
  validatePluginForm,
} from "./pluginForm";

const EVERY_KIND: PluginManifest = {
  ...TWISTED_PRISM,
  id: "loft.every_kind",
  inputs: [
    ...TWISTED_PRISM.inputs,
    {
      kind: "count",
      name: "rungs",
      label: "Rungs",
      default: 3,
      minimum: 1,
      maximum: 50,
    },
    {
      kind: "feature",
      name: "host",
      label: "Host",
      feature_types: ["datum"],
      optional: true,
      host: false,
    },
    { kind: "material", name: "material", label: "Material", default: null },
  ],
};

function row(id: string, name: string, type: string): FeatureResponse {
  return {
    id,
    part_id: "p",
    order_index: 0,
    name,
    feature: { type, version: 1, params: {} },
    rolled_back: false,
    created_at: "",
    updated_at: "",
  } as unknown as FeatureResponse;
}

const TREE = [
  row("s1", "Sketch1", "sketch"),
  row("d1", "Plane1", "datum"),
  row("s2", "Sketch2", "sketch"),
  row("c1", "Twisted prism 1", "custom"),
  row("s3", "Sketch3", "sketch"),
];

function numeric(name: string, manifest = EVERY_KIND): NumericInput {
  const input = manifest.inputs.find((i) => i.name === name);
  if (input === undefined || !isNumericInput(input)) throw new Error(name);
  return input;
}

function withValues(form: PluginForm, values: Record<string, string>) {
  return { ...form, values: { ...form.values, ...values } };
}

describe("the generated fields", () => {
  it("map each numeric kind to its ValueField kind, unit and pointer", () => {
    expect(fieldKind(numeric("distance_mm"))).toBe("length");
    expect(fieldKind(numeric("twist_angle_deg"))).toBe("angle");
    expect(fieldKind(numeric("rungs"))).toBe("int");
    expect(inputUnit(numeric("distance_mm"), "in")).toBe("in");
    expect(inputUnit(numeric("twist_angle_deg"), "in")).toBe("°");
    expect(inputUnit(numeric("rungs"), "mm")).toBe("");
    // The pointer documents resolves a formula at (`/inputs/<name>`).
    expect(inputPointer("twist_angle_deg")).toBe("/inputs/twist_angle_deg");
  });

  it("state the manifest's bounds in the document unit", () => {
    expect(boundsPhrase(numeric("distance_mm"), "mm")).toBe("more than 0 mm");
    expect(boundsPhrase(numeric("twist_angle_deg"), "mm")).toBe(
      "-3600° to 3600°",
    );
    expect(boundsPhrase(numeric("rungs"), "mm")).toBe("1 to 50");
  });
});

describe("defaultPluginForm", () => {
  it("seeds every input at its manifest default, lengths in the document unit", () => {
    const form = defaultPluginForm(EVERY_KIND, "mm", TREE);
    expect(form.values).toEqual({
      profile: "s3", // the latest sketch, as Extrude proposes
      distance_mm: "10",
      twist_angle_deg: "30",
      operation: "add",
      rungs: "3",
      host: "", // optional: left empty
      material: "",
    });
    // In an inch part the 10 mm default is shown in inches, with the digits
    // that write back exactly 10 mm on an untouched Create.
    const inch = defaultPluginForm(TWISTED_PRISM, "in", TREE);
    expect(inch.values.distance_mm).toMatch(/^0\.3937/);
    expect(
      pluginInputsFromForm(TWISTED_PRISM, inch, "in", TREE, null)?.distance_mm,
    ).toBe(10);
  });
});

describe("referenceOptions", () => {
  it("offers only EARLIER features of the input's types", () => {
    const profile = TWISTED_PRISM.inputs[0]!;
    if (profile.kind !== "profile") throw new Error("fixture");
    expect(referenceOptions(profile, TREE, null).map((o) => o.value)).toEqual([
      "s1",
      "s2",
      "s3",
    ]);
    expect(referenceOptions(profile, TREE, "c1").map((o) => o.label)).toEqual([
      "Sketch1",
      "Sketch2",
    ]);
    const host = EVERY_KIND.inputs.find((i) => i.name === "host")!;
    if (host.kind !== "feature") throw new Error("fixture");
    expect(referenceOptions(host, TREE, null)).toEqual([
      { value: "d1", label: "Plane1" },
    ]);
  });

  it("offers a host input only custom features of its plugins (a window's walls)", () => {
    const custom = (id: string, name: string, pluginId: string) =>
      ({
        ...row(id, name, "custom"),
        feature: {
          type: "custom",
          version: 1,
          params: { plugin_id: pluginId, plugin_version: "1.0.0", inputs: {} },
        },
      }) as unknown as FeatureResponse;
    const tree = [
      custom("w1", "Wall 1", "loft.wall"),
      custom("k1", "Deck 1", "loft.deck"),
      row("d1", "Plane1", "datum"),
      custom("w2", "Wall 2", "loft.wall"),
      custom("o1", "Door 1", "loft.door"),
    ];
    const wall = {
      kind: "feature" as const,
      name: "host_wall",
      label: "Host wall",
      feature_types: ["custom"],
      plugin_ids: ["loft.wall"],
      optional: false,
      host: true,
    };
    expect(referenceOptions(wall, tree, null).map((o) => o.value)).toEqual([
      "w1",
      "w2",
    ]);
    // Nothing to host it: the form says what to add.
    const manifest = { ...EVERY_KIND, inputs: [wall] };
    const form = defaultPluginForm(manifest, "mm", [tree[1]!]);
    expect(form.values.host_wall).toBe("");
    expect(
      validatePluginForm(manifest, form, "mm", [tree[1]!], null).host_wall,
    ).toBe("Add a host wall first.");
  });
});

describe("validatePluginForm", () => {
  const base = defaultPluginForm(EVERY_KIND, "mm", TREE);
  const check = (values: Record<string, string>, unit: "mm" | "in" = "mm") =>
    validatePluginForm(EVERY_KIND, withValues(base, values), unit, TREE, null);

  it("passes the defaults", () => {
    expect(check({})).toEqual({});
  });

  it("refuses a value on or past a bound, saying the bound", () => {
    expect(check({ distance_mm: "0" }).distance_mm).toBe(
      "Must be more than 0 mm.",
    );
    expect(check({ twist_angle_deg: "3601" }).twist_angle_deg).toBe(
      "Must be -3600° to 3600°.",
    );
    expect(check({ twist_angle_deg: "-3600" })).toEqual({});
    expect(check({ rungs: "0" }).rungs).toBe("Must be 1 to 50.");
  });

  it("refuses an empty, unparseable or fractional count", () => {
    expect(check({ distance_mm: "" }).distance_mm).toBe("Enter distance.");
    // A formula that does not resolve leaves its text in the form.
    expect(check({ twist_angle_deg: "twist*2" }).twist_angle_deg).toBe(
      "Enter a number or a formula.",
    );
    expect(check({ rungs: "2.5" }).rungs).toBe("Must be a whole number.");
  });

  it("checks references and choices against what the tree and manifest offer", () => {
    expect(check({ profile: "" }).profile).toBe("Pick profile.");
    expect(check({ profile: "d1" }).profile).toBe(
      "Profile must be an earlier feature.",
    );
    expect(check({ operation: "fuse" }).operation).toBe("Choose operation.");
    expect(
      validatePluginForm(
        EVERY_KIND,
        withValues(base, { profile: "" }),
        "mm",
        [],
        null,
      ).profile,
    ).toBe("Draw a sketch first.");
  });

  it("names the first failing field as the Create gate's reason", () => {
    const errors = check({ distance_mm: "0", rungs: "0" });
    expect(firstPluginBlocker(EVERY_KIND, errors)).toBe(
      "Distance: Must be more than 0 mm.",
    );
    expect(firstPluginBlocker(EVERY_KIND, {})).toBeNull();
  });
});

describe("pluginInputsFromForm", () => {
  it("writes numbers in the input's own unit and leaves empty optionals out", () => {
    const form = withValues(defaultPluginForm(EVERY_KIND, "in", TREE), {
      distance_mm: "2",
      twist_angle_deg: "90",
      rungs: "4",
    });
    expect(pluginInputsFromForm(EVERY_KIND, form, "in", TREE, null)).toEqual({
      profile: { kind: "feature", feature_id: "s3" },
      distance_mm: 50.8,
      twist_angle_deg: 90,
      operation: "add",
      rungs: 4,
    });
  });

  it("is null while any field is invalid", () => {
    const form = withValues(defaultPluginForm(EVERY_KIND, "mm", TREE), {
      distance_mm: "-1",
    });
    expect(pluginInputsFromForm(EVERY_KIND, form, "mm", TREE, null)).toBeNull();
  });

  it("round-trips stored inputs exactly through an unchanged edit", () => {
    const stored: CustomParams = {
      plugin_id: "loft.twisted_prism",
      plugin_version: "1.0.0",
      inputs: {
        profile: { kind: "feature", feature_id: "s1" },
        distance_mm: 12.345678901234,
        twist_angle_deg: 33.333333333333336,
        operation: "cut",
      },
    };
    const form = formFromCustomParams(TWISTED_PRISM, stored, "in");
    expect(form.values.profile).toBe("s1");
    expect(form.values.operation).toBe("cut");
    expect(pluginInputsFromForm(TWISTED_PRISM, form, "in", TREE, "c1")).toEqual(
      stored.inputs,
    );
  });

  it("reads 11-15/32 as a mixed number, and a no-op save keeps it (B7-MIXED-FRACTION)", () => {
    const form = defaultPluginForm(TWISTED_PRISM, "in", TREE);
    const typedForm = {
      ...form,
      values: { ...form.values, distance_mm: "11-15/32" },
    };
    const typed = pluginInputsFromForm(
      TWISTED_PRISM,
      typedForm,
      "in",
      TREE,
      null,
    );
    expect(typed?.distance_mm).toBeCloseTo(11.46875 * 25.4, 12);
    // Stored, reopened in inches and in mm, saved untouched: byte for byte.
    const stored: CustomParams = {
      plugin_id: "loft.twisted_prism",
      plugin_version: "1.0.0",
      inputs: { ...(typed ?? {}) },
    };
    for (const unit of ["in", "mm"] as const) {
      const reopened = formFromCustomParams(TWISTED_PRISM, stored, unit);
      expect(
        pluginInputsFromForm(TWISTED_PRISM, reopened, unit, TREE, null),
      ).toEqual(stored.inputs);
    }
  });
});

describe("a feature list (a roof's picked walls, ROOF-VALLEY)", () => {
  const custom = (id: string, name: string, pluginId: string) =>
    ({
      ...row(id, name, "custom"),
      feature: {
        type: "custom",
        version: 1,
        params: { plugin_id: pluginId, plugin_version: "1.0.0", inputs: {} },
      },
    }) as unknown as FeatureResponse;
  const tree = [
    custom("w1", "Wall 1", "loft.wall"),
    custom("k1", "Deck 1", "loft.deck"),
    custom("w2", "Wall 2", "loft.wall"),
    custom("w3", "Wall 3", "loft.wall"),
  ];
  const walls = {
    kind: "features" as const,
    name: "walls",
    label: "Walls",
    feature_types: ["custom"],
    plugin_ids: ["loft.wall"],
    min_items: 0,
    max_items: 2,
  };
  const manifest: PluginManifest = { ...EVERY_KIND, inputs: [walls] };

  it("offers the earlier walls, starts empty and toggles picks in order", () => {
    expect(referenceOptions(walls, tree, null).map((o) => o.value)).toEqual([
      "w1",
      "w2",
      "w3",
    ]);
    const form = defaultPluginForm(manifest, "mm", tree);
    expect(form.values.walls).toBe("");
    expect(pluginInputsFromForm(manifest, form, "mm", tree, null)).toEqual({});
    const picked = togglePick(togglePick("", "w3"), "w1");
    expect(pickedIds(picked)).toEqual(["w3", "w1"]);
    expect(togglePick(picked, "w3")).toBe("w1");
    expect(
      pluginInputsFromForm(
        manifest,
        withValues(form, { walls: picked }),
        "mm",
        tree,
        null,
      ),
    ).toEqual({
      walls: [
        { kind: "feature", feature_id: "w3" },
        { kind: "feature", feature_id: "w1" },
      ],
    });
  });

  it("refuses a pick that is not an earlier wall, or too many", () => {
    const form = defaultPluginForm(manifest, "mm", tree);
    const check = (text: string) =>
      validatePluginForm(
        manifest,
        withValues(form, { walls: text }),
        "mm",
        tree,
        null,
      ).walls;
    expect(check("w1,k1")).toBe("Walls must be earlier features.");
    expect(check("w1,w2,w3")).toBe("Pick at most 2.");
    expect(check("w1,w2")).toBeUndefined();
  });

  it("seeds an edit from the stored picks", () => {
    const stored: CustomParams = {
      plugin_id: manifest.id,
      plugin_version: manifest.version,
      inputs: {
        walls: [
          { kind: "feature", feature_id: "w2" },
          { kind: "feature", feature_id: "w1" },
        ],
      },
    };
    expect(formFromCustomParams(manifest, stored, "mm").values.walls).toBe(
      "w2,w1",
    );
  });
});
