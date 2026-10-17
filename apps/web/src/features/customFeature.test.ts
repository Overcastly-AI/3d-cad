/**
 * A custom feature as ONE tree row (PLUGIN-UI): geometry reports its members,
 * and the workspace reads one folded result per custom row.
 */
import { describe, expect, it } from "vitest";

import type { EvaluateTreeResult, FeatureResponse } from "../api/parts";
import { TWISTED_PRISM } from "../test/pluginFixture";
import {
  bracketedPluginCode,
  buildTools,
  foldCustomResults,
  foldMemberResults,
  pluginAvailability,
  pluginErrorSentence,
  roleTitle,
  withMemberIds,
} from "./customFeature";

const SKETCH = {
  type: "sketch",
  version: 1,
  params: {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [],
    constraints: [],
  },
};

function row(id: string, feature: unknown): FeatureResponse {
  return {
    id,
    part_id: "p",
    order_index: 0,
    name: id,
    feature,
    rolled_back: false,
    created_at: "",
    updated_at: "",
  } as FeatureResponse;
}

const CUSTOM = row("c", {
  type: "custom",
  version: 1,
  params: {
    plugin_id: "loft.twisted_prism",
    plugin_version: "1.0.0",
    inputs: {},
    expansion: [
      { role: "path", index: 0, id: "m-path", feature: SKETCH },
      { role: "sweep", index: 0, id: "m-sweep", feature: SKETCH },
    ],
  },
});
const TREE = [row("s", SKETCH), CUSTOM, row("f", SKETCH)];

function evaluation(
  features: EvaluateTreeResult["features"],
  lastGood: string | null,
): EvaluateTreeResult {
  return {
    features,
    last_good_feature_id: lastGood,
  } as unknown as EvaluateTreeResult;
}

describe("foldMemberResults", () => {
  it("is the first error, else suppressed, else skipped, else ok", () => {
    const error = { code: "x", message: "m" };
    expect(
      foldMemberResults("c", [
        { feature_id: "a", status: "ok" },
        { feature_id: "b", status: "error", error },
      ]),
    ).toEqual({ feature_id: "c", status: "error", error });
    expect(
      foldMemberResults("c", [
        { feature_id: "a", status: "suppressed" },
        { feature_id: "b", status: "suppressed" },
      ])?.status,
    ).toBe("suppressed");
    expect(
      foldMemberResults("c", [
        { feature_id: "a", status: "ok" },
        { feature_id: "b", status: "skipped" },
      ])?.status,
    ).toBe("skipped");
    expect(
      foldMemberResults("c", [{ feature_id: "a", status: "ok" }])?.status,
    ).toBe("ok");
    expect(foldMemberResults("c", [])).toBeUndefined();
  });
});

describe("foldCustomResults", () => {
  it("reads a memberless door as the wall it is hosted in", () => {
    const door = row("d", {
      type: "custom",
      version: 1,
      params: {
        plugin_id: "loft.door",
        plugin_version: "1.0.0",
        inputs: { host_wall: { kind: "feature", feature_id: "c" }, w: 1 },
        expansion: [],
      },
    });
    const error = { code: "parameter_value_invalid", message: "Door 1: ..." };
    const folded = foldCustomResults(
      evaluation(
        [
          { feature_id: "s", status: "ok" },
          { feature_id: "m-path", status: "ok" },
          { feature_id: "m-sweep", status: "error", error },
        ],
        "m-path",
      ),
      [...TREE, door],
    );
    expect(folded.features.find((f) => f.feature_id === "d")).toEqual({
      feature_id: "d",
      status: "error",
      error,
    });
  });

  it("adds one result per custom row after its members, keeping theirs", () => {
    const folded = foldCustomResults(
      evaluation(
        [
          { feature_id: "s", status: "ok" },
          { feature_id: "m-path", status: "ok" },
          { feature_id: "m-sweep", status: "ok" },
          { feature_id: "f", status: "ok" },
        ],
        "f",
      ),
      TREE,
    );
    expect(folded.features.map((f) => f.feature_id)).toEqual([
      "s",
      "m-path",
      "m-sweep",
      "c",
      "f",
    ]);
    expect(folded.last_good_feature_id).toBe("f");
  });

  it("reads a member as the last good ROW", () => {
    const built = evaluation(
      [
        { feature_id: "s", status: "ok" },
        { feature_id: "m-path", status: "ok" },
        { feature_id: "m-sweep", status: "ok" },
      ],
      "m-sweep",
    );
    expect(foldCustomResults(built, TREE).last_good_feature_id).toBe("c");
    // Built only partway through: the custom feature is not the last good.
    const partway = evaluation(
      [
        { feature_id: "s", status: "ok" },
        { feature_id: "m-path", status: "ok" },
        {
          feature_id: "m-sweep",
          status: "error",
          error: { code: "x", message: "" },
        },
      ],
      "m-path",
    );
    const folded = foldCustomResults(partway, TREE);
    expect(folded.last_good_feature_id).toBe("s");
    expect(folded.features.find((f) => f.feature_id === "c")?.status).toBe(
      "error",
    );
  });

  it("leaves a tree with no custom feature untouched", () => {
    const plain = evaluation([{ feature_id: "s", status: "ok" }], "s");
    expect(foldCustomResults(plain, [row("s", SKETCH)])).toBe(plain);
  });
});

describe("the catalog", () => {
  it("lists the latest Build version of each plugin as a tool", () => {
    const older = { ...TWISTED_PRISM, version: "0.9.0", latest: false };
    expect(buildTools([TWISTED_PRISM, older])).toEqual([TWISTED_PRISM]);
    expect(buildTools(undefined)).toEqual([]);
  });

  it("says a feature is read-only when its pinned version is not installed", () => {
    const pin = { plugin_id: "loft.twisted_prism", plugin_version: "1.0.0" };
    expect(pluginAvailability(undefined, pin).state).toBe("loading");
    expect(pluginAvailability([TWISTED_PRISM], pin)).toEqual({
      state: "ready",
      manifest: TWISTED_PRISM,
    });
    expect(
      pluginAvailability([{ ...TWISTED_PRISM, version: "2.0.0" }], pin),
    ).toEqual({
      state: "missing",
      pluginId: "loft.twisted_prism",
      version: "1.0.0",
    });
  });

  it("titles a member by its manifest role", () => {
    expect(roleTitle(TWISTED_PRISM, "sweep")).toBe("Twisted sweep");
    expect(roleTitle(undefined, "sweep")).toBe("sweep");
  });

  it("lights a custom feature's members with it", () => {
    expect(withMemberIds(["c"], TREE)).toEqual(["c", "m-path", "m-sweep"]);
    expect(withMemberIds(["s"], TREE)).toEqual(["s"]);
  });
});

describe("typed refusals", () => {
  it("heads a plugin or limit refusal, and passes anything else through", () => {
    expect(pluginErrorSentence("feature_limit_exceeded", "Over 1000.")).toBe(
      "Too many features: Over 1000.",
    );
    expect(pluginErrorSentence("plugin_read_only", "Cannot edit.")).toBe(
      "Read-only: Cannot edit.",
    );
    expect(pluginErrorSentence("parameter_unresolved", "No Q.")).toBe("No Q.");
    expect(pluginErrorSentence(null, "No Q.")).toBe("No Q.");
  });

  it("lifts the plugin code out of an evaluation's input_error", () => {
    expect(bracketedPluginCode("[plugin_expansion_too_large] the part")).toBe(
      "plugin_expansion_too_large",
    );
    expect(bracketedPluginCode("/inputs/x = 'q': not found")).toBeNull();
  });
});
