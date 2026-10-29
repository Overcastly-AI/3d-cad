import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  featureUpdate,
  outOfDateFeatures,
  outOfDateSentence,
  updateToLabel,
} from "./pluginUpdate";

function row(
  id: string,
  update?: { to_version: string; summary: string },
): FeatureResponse {
  return {
    id,
    part_id: "p",
    order_index: 0,
    name: id,
    rolled_back: false,
    created_at: "2026-10-28T00:00:00Z",
    updated_at: "2026-10-28T00:00:00Z",
    feature: {
      type: "custom",
      version: 1,
      params: {
        plugin_id: "loft.window",
        plugin_version: "1.1.0",
        inputs: {},
      },
    },
    ...(update === undefined ? {} : { plugin_update: update }),
  } as FeatureResponse;
}

describe("out-of-date Build features (OPENING-UPDATE)", () => {
  const spacers = { to_version: "1.5.0", summary: "Draws the spacers." };

  it("reads a row's update, or null for a current one", () => {
    expect(featureUpdate(row("a", spacers))).toEqual({
      toVersion: "1.5.0",
      summary: "Draws the spacers.",
    });
    expect(featureUpdate(row("b"))).toBeNull();
  });

  it("lists the updatable rows in tree order", () => {
    const rows = [row("a", spacers), row("b"), row("c", spacers)];
    expect(outOfDateFeatures(rows).map((o) => o.feature.id)).toEqual([
      "a",
      "c",
    ]);
  });

  it("names the actions as the user reads them", () => {
    expect(updateToLabel("1.5.0")).toBe("Update to 1.5.0");
    expect(outOfDateSentence(1)).toBe("1 Build feature out of date");
    expect(outOfDateSentence(8)).toBe("8 Build features out of date");
  });
});
