import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  addsList,
  featureUpdate,
  outOfDateFeatures,
  outOfDateSentence,
  updateBadgeTitle,
  updateToLabel,
} from "./pluginUpdate";

interface Offer {
  to_version: string;
  summary: string;
  adds?: string[];
  quiet: boolean;
}

function row(id: string, update?: Offer): FeatureResponse {
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

describe("out-of-date Build features (OPENING-UPDATE, PLUGIN-UPDATE-ALL)", () => {
  const spacers: Offer = {
    to_version: "1.5.0",
    summary: "Adds 2 header spacers and 1 header ply. Draws the spacers.",
    adds: ["2 header spacers", "1 header ply"],
    quiet: false,
  };
  const floor: Offer = {
    to_version: "1.3.0",
    summary: "Joists bear on replaces Joist direction.",
    adds: [],
    quiet: true,
  };

  it("reads a row's update, or null for a current one", () => {
    expect(featureUpdate(row("a", spacers))).toEqual({
      toVersion: "1.5.0",
      summary: "Adds 2 header spacers and 1 header ply. Draws the spacers.",
      adds: ["2 header spacers", "1 header ply"],
      quiet: false,
    });
    expect(featureUpdate(row("b"))).toBeNull();
    // An offer from before PLUGIN-UPDATE-ALL names nothing it adds.
    const bare: Offer = {
      to_version: spacers.to_version,
      summary: spacers.summary,
      quiet: false,
    };
    expect(featureUpdate(row("c", bare))?.adds).toEqual([]);
  });

  it("lists the rows whose update changes something, in tree order", () => {
    const rows = [
      row("a", spacers),
      row("b"),
      row("f", floor),
      row("c", spacers),
    ];
    expect(outOfDateFeatures(rows).map((o) => o.feature.id)).toEqual([
      "a",
      "c",
    ]);
  });

  it("names what an update adds", () => {
    expect(addsList([])).toBe("");
    expect(addsList(["11 ceiling joists"])).toBe("11 ceiling joists");
    expect(addsList(["3 pier footings", "3 post bases"])).toBe(
      "3 pier footings and 3 post bases",
    );
    expect(addsList(["a", "b", "c"])).toBe("a, b and c");
    const spacersUpdate = featureUpdate(row("a", spacers));
    const floorUpdate = featureUpdate(row("f", floor));
    if (spacersUpdate === null || floorUpdate === null) throw new Error();
    expect(updateBadgeTitle(spacersUpdate)).toBe(
      "Update to 1.5.0: adds 2 header spacers and 1 header ply",
    );
    expect(updateBadgeTitle(floorUpdate)).toBe(
      "Update to 1.3.0: Joists bear on replaces Joist direction.",
    );
  });

  it("names the actions as the user reads them", () => {
    expect(updateToLabel("1.5.0")).toBe("Update to 1.5.0");
    expect(outOfDateSentence(1)).toBe("1 Build feature out of date");
    expect(outOfDateSentence(8)).toBe("8 Build features out of date");
  });
});
