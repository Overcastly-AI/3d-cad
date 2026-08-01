import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  barSlotIndex,
  isRolledBack,
  nearestSlotIndex,
  rollbackIdForSlot,
} from "./rollback";

function feature(id: string): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
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

const tree = [feature("a"), feature("b"), feature("c")];

describe("barSlotIndex", () => {
  it("maps the tip (null) to the last slot", () => {
    expect(barSlotIndex(tree, null)).toBe(2);
  });
  it("maps a named last-included feature to its slot", () => {
    expect(barSlotIndex(tree, "a")).toBe(0);
    expect(barSlotIndex(tree, "b")).toBe(1);
  });
  it("falls through to the tip for an unknown id", () => {
    expect(barSlotIndex(tree, "zzz")).toBe(2);
  });
});

describe("rollbackIdForSlot", () => {
  it("returns the feature id for an interior slot", () => {
    expect(rollbackIdForSlot(tree, 0)).toBe("a");
    expect(rollbackIdForSlot(tree, 1)).toBe("b");
  });
  it("returns null (tip = all included) for the last slot", () => {
    expect(rollbackIdForSlot(tree, 2)).toBeNull();
  });
});

describe("nearestSlotIndex", () => {
  // Three slots on the way, centred at 100 / 200 / 300 client px.
  const anchors = [100, 200, 300];

  it("lands in the slot whose anchor is nearest the pointer", () => {
    expect(nearestSlotIndex(anchors, 104)).toBe(0);
    expect(nearestSlotIndex(anchors, 189)).toBe(1);
    expect(nearestSlotIndex(anchors, 260)).toBe(2);
  });

  it("clamps past either end of the way instead of falling off it", () => {
    expect(nearestSlotIndex(anchors, -400)).toBe(0);
    expect(nearestSlotIndex(anchors, 9000)).toBe(2);
  });

  it("takes the EARLIER slot on an exact midpoint (never overshoots)", () => {
    expect(nearestSlotIndex(anchors, 150)).toBe(0);
    expect(nearestSlotIndex(anchors, 250)).toBe(1);
  });

  it("has no slot to land in on an empty way", () => {
    expect(nearestSlotIndex([], 120)).toBe(-1);
  });
});

describe("isRolledBack", () => {
  it("marks only features below the bar", () => {
    // Bar after "a" (last included = a): b and c are rolled back.
    expect(isRolledBack(tree, "a", 0)).toBe(false);
    expect(isRolledBack(tree, "a", 1)).toBe(true);
    expect(isRolledBack(tree, "a", 2)).toBe(true);
    // Bar at the tip: nothing is rolled back.
    expect(isRolledBack(tree, null, 2)).toBe(false);
  });
});
