import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as parts from "../api/parts";
import type { FeatureResponse, FeatureTreeResponse } from "../api/parts";
import {
  editPreviewKey,
  type PreviewedEditor,
  useEditPreview,
} from "./editPreview";

function feature(id: string): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
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

const TREE: FeatureTreeResponse = {
  part_id: "p",
  tree_version: 9,
  rollback_feature_id: null,
  can_undo: true,
  can_redo: false,
  features: ["s", "e", "sh", "f"].map(feature),
};

const FULL = { mesh_glb_id: "tip-mesh" } as parts.EvaluateTreeResult;
const INPUT = { mesh_glb_id: "input-mesh" } as parts.EvaluateTreeResult;

afterEach(() => vi.restoreAllMocks());

describe("useEditPreview", () => {
  it("keys the partial body apart from the full evaluation, and lets go on close", async () => {
    const spy = vi
      .spyOn(parts, "evaluatePart")
      .mockImplementation(async (_id, _client, before) =>
        before === undefined ? FULL : INPUT,
      );
    const client = new QueryClient();
    client.setQueryData(["evaluate", "p", 9], FULL);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const editing: PreviewedEditor = {
      kind: "fillet",
      mode: "edit",
      featureId: "f",
    };
    const { result, rerender } = renderHook(
      ({ editor }: { editor: PreviewedEditor | null }) =>
        useEditPreview("p", TREE, editor),
      {
        wrapper,
        initialProps: { editor: editing as PreviewedEditor | null },
      },
    );

    await waitFor(() =>
      expect(result.current.inputMeshGlbId).toBe("input-mesh"),
    );
    expect(spy).toHaveBeenCalledWith("p", undefined, "f");
    expect(result.current.displayTree?.rollback_feature_id).toBe("sh");
    // The full evaluation's entry is untouched by the preview.
    expect(client.getQueryData(["evaluate", "p", 9])).toBe(FULL);
    expect(client.getQueryData(editPreviewKey("p", 9, "f"))).toBe(INPUT);

    // Cancel / Save closes the editor: the whole body, the stored tree.
    rerender({ editor: null });
    expect(result.current.inputMeshGlbId).toBeNull();
    expect(result.current.displayTree).toBe(TREE);
    expect(client.getQueryData(["evaluate", "p", 9])).toBe(FULL);
  });

  it("does not preview a create, another editor kind, or the first feature", () => {
    const spy = vi.spyOn(parts, "evaluatePart");
    const client = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    for (const editor of [
      { kind: "fillet", mode: "create" },
      { kind: "extrude", mode: "edit", featureId: "e" },
      { kind: "fillet", mode: "edit", featureId: "s" },
    ] as PreviewedEditor[]) {
      const { result } = renderHook(() => useEditPreview("p", TREE, editor), {
        wrapper,
      });
      expect(result.current.inputMeshGlbId).toBeNull();
      expect(result.current.displayTree).toBe(TREE);
    }
    expect(spy).not.toHaveBeenCalled();
  });
});
