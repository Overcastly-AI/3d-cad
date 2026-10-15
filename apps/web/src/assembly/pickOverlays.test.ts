/**
 * BIKE2-FAILED-PART-KILLS-PICKS root cause: one part's overlay 422 rejected the
 * shared `Promise.all`, so no part in the assembly was pickable. Each part now
 * settles on its own, and a part that never answers times out with a message.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EvaluateTreeRequest, OverlayResult } from "../api/measure";
import { MeasureError } from "../api/measure";
import { fetchOverlaysSettled } from "./pickOverlays";

const tree = (partId: string) =>
  ({
    part_id: partId,
    tree_version: 0,
    features: [],
  }) as unknown as EvaluateTreeRequest;

const overlay = (n: number) =>
  ({ faces: [], edges: new Array(n).fill(null) }) as unknown as OverlayResult;

afterEach(() => {
  vi.useRealTimers();
});

describe("fetchOverlaysSettled", () => {
  it("delivers the good parts when one part's overlay is refused", async () => {
    const fetcher = vi.fn(async (request: EvaluateTreeRequest) => {
      if (request.part_id === "arm") {
        throw new MeasureError(
          "profile_unsupported",
          "The profile crosses the arm's end edge.",
        );
      }
      return overlay(request.part_id === "ring" ? 5 : 3);
    });
    const settled = await fetchOverlaysSettled(
      [
        ["ring", tree("ring")],
        ["arm", tree("arm")],
        ["frame", tree("frame")],
      ],
      fetcher,
    );
    expect([...settled.overlays.keys()]).toEqual(["ring", "frame"]);
    expect(settled.overlays.get("ring")?.edges).toHaveLength(5);
    expect(settled.failures).toEqual(
      new Map([["arm", "The profile crosses the arm's end edge."]]),
    );
  });

  it("times a part out with a message instead of waiting forever", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn((request: EvaluateTreeRequest) =>
      request.part_id === "slow"
        ? new Promise<OverlayResult>(() => {})
        : Promise.resolve(overlay(1)),
    );
    const pending = fetchOverlaysSettled(
      [
        ["slow", tree("slow")],
        ["fast", tree("fast")],
      ],
      fetcher,
      1_000,
    );
    await vi.advanceTimersByTimeAsync(1_000);
    const settled = await pending;
    expect([...settled.overlays.keys()]).toEqual(["fast"]);
    expect(settled.failures.get("slow")).toBe(
      "Its pick geometry did not arrive within 1 s.",
    );
  });
});
