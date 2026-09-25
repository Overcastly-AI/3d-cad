import { describe, expect, it } from "vitest";

import type { FeatureResponse, FeatureResult } from "../api/parts";
import { movedEdgeWarning } from "./subshapeResolution";

function row(
  id: string,
  name: string,
  type: string,
  updated = "2026-09-25T00:00:00Z",
): FeatureResponse {
  return {
    id,
    name,
    part_id: "p",
    order_index: 0,
    created_at: "2026-09-25T00:00:00Z",
    updated_at: updated,
    rolled_back: false,
    feature: { type, version: 1, params: {} },
  } as unknown as FeatureResponse;
}

function result(
  id: string,
  resolution: FeatureResult["subshape_resolution"],
  status: FeatureResult["status"] = "ok",
): FeatureResult {
  return {
    feature_id: id,
    status,
    subshape_resolution: resolution,
  } as FeatureResult;
}

const TREE = [
  row("sk", "Sketch1", "sketch"),
  row("x1", "Extrude1", "extrude"),
  row("f1", "Fillet1", "fillet"),
  row("d1", "Datum1", "datum"),
];
const FILLET = TREE[2] as FeatureResponse;

const tier = (
  worst_tier: "exact" | "durable" | "adjacent",
  exact: number,
  durable: number,
  adjacent: number,
) => ({ worst_tier, exact, durable, adjacent });

describe("movedEdgeWarning", () => {
  it("says nothing for an exact rebuild", () => {
    expect(
      movedEdgeWarning(FILLET, TREE, result("f1", tier("exact", 4, 0, 0))),
    ).toBeNull();
  });

  it("says nothing for a durable one: that tier fires on correct rebuilds", () => {
    // topological-naming.md §15: two tree goldens report `durable` with no
    // edit at all, so a notice here would fire on a fresh create.
    expect(
      movedEdgeWarning(FILLET, TREE, result("f1", tier("durable", 0, 4, 0))),
    ).toBeNull();
  });

  it("warns on adjacent, naming how many of the picks it concerns", () => {
    const warning = movedEdgeWarning(
      FILLET,
      TREE,
      result("f1", tier("adjacent", 2, 0, 2)),
    );
    expect(warning).not.toBeNull();
    expect(warning?.moved).toBe(2);
    expect(warning?.total).toBe(4);
    expect(warning?.sentence).toBe(
      "2 of 4 picked edges moved in an earlier edit and were re-found by " +
        "their neighbouring faces. Check Fillet1 is on the edges you meant, " +
        "or re-pick them.",
    );
  });

  it("words one edge in the singular", () => {
    expect(
      movedEdgeWarning(FILLET, TREE, result("f1", tier("adjacent", 0, 0, 1)))
        ?.sentence,
    ).toBe(
      "1 of 1 picked edges moved in an earlier edit and was re-found by its " +
        "neighbouring faces. Check Fillet1 is on the edge you meant, or " +
        "re-pick it.",
    );
  });

  it("says nothing when there is no result, no summary, or no build", () => {
    expect(movedEdgeWarning(FILLET, TREE, undefined)).toBeNull();
    expect(movedEdgeWarning(FILLET, TREE, result("f1", null))).toBeNull();
    expect(
      movedEdgeWarning(
        FILLET,
        TREE,
        result("f1", tier("adjacent", 0, 0, 1), "error"),
      ),
    ).toBeNull();
  });

  it("keys a dismissal to the edit that moved the edge", () => {
    const adjacent = result("f1", tier("adjacent", 0, 0, 1));
    const key = movedEdgeWarning(FILLET, TREE, adjacent)?.key;
    // A later feature changing does not bring the notice back...
    const downstream = TREE.map((f) =>
      f.id === "d1" ? row("d1", "Datum1", "datum", "2026-09-26T00:00:00Z") : f,
    );
    expect(movedEdgeWarning(FILLET, downstream, adjacent)?.key).toBe(key);
    // ...an EARLIER one changing does: it is a new re-match.
    const upstream = TREE.map((f) =>
      f.id === "sk"
        ? row("sk", "Sketch1", "sketch", "2026-09-26T00:00:00Z")
        : f,
    );
    expect(movedEdgeWarning(FILLET, upstream, adjacent)?.key).not.toBe(key);
  });
});
