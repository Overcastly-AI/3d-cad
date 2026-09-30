import { describe, expect, it } from "vitest";

import type { FeatureResponse, FeatureTreeResponse } from "../api/parts";
import {
  editPreviewStop,
  PREVIEW_BEFORE_KINDS,
  previewTree,
} from "./editPreview";

function feature(id: string, rolledBack = false): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-09-30T00:00:00Z",
    updated_at: "2026-09-30T00:00:00Z",
    rolled_back: rolledBack,
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

function tree(ids: string[], bar: string | null = null): FeatureTreeResponse {
  const at = bar === null ? ids.length - 1 : ids.indexOf(bar);
  return {
    part_id: "p",
    tree_version: 7,
    rollback_feature_id: bar,
    can_undo: true,
    can_redo: false,
    features: ids.map((id, index) => feature(id, index > at)),
  };
}

describe("editPreviewStop", () => {
  const features = tree(["s", "e", "sh", "f", "c"]).features;

  it("is the feature right before the one edited", () => {
    expect(editPreviewStop(features, "f")).toBe("sh");
    expect(editPreviewStop(features, "c")).toBe("f");
  });

  it("is undefined for the first feature or an unknown id", () => {
    expect(editPreviewStop(features, "s")).toBeUndefined();
    expect(editPreviewStop(features, "nope")).toBeUndefined();
  });

  it("covers the four pick-on-the-input-body editors", () => {
    expect([...PREVIEW_BEFORE_KINDS].sort()).toEqual([
      "chamfer",
      "draft",
      "fillet",
      "shell",
    ]);
  });
});

describe("previewTree", () => {
  it("shows the stop before the edited feature and marks the rest", () => {
    const shown = previewTree(tree(["s", "e", "sh", "f", "c"]), "sh");
    expect(shown.rollback_feature_id).toBe("sh");
    expect(shown.features.map((f) => f.rolled_back)).toEqual([
      false,
      false,
      false,
      true,
      true,
    ]);
    // Display only: the version is the stored one, nothing else changes.
    expect(shown.tree_version).toBe(7);
  });

  it("does not touch the tree it was given", () => {
    const stored = tree(["s", "e", "sh", "f", "c"]);
    previewTree(stored, "sh");
    expect(stored.rollback_feature_id).toBeNull();
    expect(stored.features.every((f) => !f.rolled_back)).toBe(true);
  });

  it("moves a stored stop FORWARD to the feature being edited", () => {
    const shown = previewTree(tree(["s", "e", "sh", "f", "c"], "e"), "f");
    expect(shown.features.map((f) => f.rolled_back)).toEqual([
      false,
      false,
      false,
      false,
      true,
    ]);
  });

  it("is the same tree for an unknown stop", () => {
    const stored = tree(["s", "e"]);
    expect(previewTree(stored, "nope")).toBe(stored);
  });
});
