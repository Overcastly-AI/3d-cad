import { describe, expect, it } from "vitest";

import { evaluatedFeatures } from "./evaluatedFeatures";
import type { FeatureResponse } from "./partTypes";

const sketch = {
  type: "sketch",
  version: 1,
  params: {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [],
    constraints: [],
  },
} as const;

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

describe("evaluatedFeatures", () => {
  it("sends base features as they are", () => {
    expect(evaluatedFeatures([row("a", sketch)])).toEqual([
      { id: "a", feature: sketch },
    ]);
  });

  it("sends a custom feature's stored members, under their ids", () => {
    const custom = {
      type: "custom",
      version: 1,
      suppressed: true,
      params: {
        plugin_id: "loft.twisted_prism",
        plugin_version: "1.0.0",
        inputs: {},
        expansion: [{ role: "path", index: 0, id: "m0", feature: sketch }],
      },
    };
    expect(evaluatedFeatures([row("c", custom)])).toEqual([
      { id: "m0", feature: { ...sketch, suppressed: true } },
    ]);
  });
});
