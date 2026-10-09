import { describe, expect, it } from "vitest";

import type { FeatureResponse, FeatureResult } from "../api/parts";
import { PROJECTION_LOST_LABEL, projectionWarning } from "./subshapeResolution";

const SKETCH = {
  id: "sk2",
  name: "Sketch2",
  part_id: "p",
  order_index: 5,
  created_at: "2026-10-08T00:00:00Z",
  updated_at: "2026-10-08T00:00:00Z",
  rolled_back: false,
  feature: { type: "sketch", version: 1, params: {} },
} as unknown as FeatureResponse;

function solved(
  projections: { entity: string; state: "ok" | "sick"; reason?: string }[],
  status: FeatureResult["status"] = "ok",
): FeatureResult {
  return {
    feature_id: "sk2",
    status,
    data: {
      kind: "solved_sketch",
      entities: [],
      status: "converged",
      projections,
    },
  } as unknown as FeatureResult;
}

describe("projectionWarning — the tree's 'Projection lost'", () => {
  it("says nothing for a sketch whose projections all followed their edges", () => {
    expect(
      projectionWarning(
        SKETCH,
        solved([
          { entity: "e1", state: "ok" },
          { entity: "e2", state: "ok" },
        ]),
      ),
    ).toBeNull();
    expect(projectionWarning(SKETCH, solved([]))).toBeNull();
  });

  it("says nothing without a solved result (a failed build speaks for itself)", () => {
    expect(projectionWarning(SKETCH, undefined)).toBeNull();
    expect(
      projectionWarning(
        SKETCH,
        solved(
          [{ entity: "e1", state: "sick", reason: "unresolved" }],
          "error",
        ),
      ),
    ).toBeNull();
  });

  it("counts the sick projections, in the plan's own sentence", () => {
    const warning = projectionWarning(
      SKETCH,
      solved([
        { entity: "e1", state: "sick", reason: "unresolved" },
        { entity: "e2", state: "ok" },
        { entity: "e3", state: "sick", reason: "unresolved" },
      ]),
    );
    expect(warning).toMatchObject({ sick: 2, total: 3 });
    expect(warning?.sentence).toBe(
      "2 projected edges no longer exist; the sketch keeps their last position.",
    );
    expect(PROJECTION_LOST_LABEL).toBe("Projection lost");
  });

  it("speaks of one edge in the singular", () => {
    expect(
      projectionWarning(
        SKETCH,
        solved([{ entity: "e1", state: "sick", reason: "unresolved" }]),
      )?.sentence,
    ).toBe(
      "1 projected edge no longer exists; the sketch keeps its last position.",
    );
  });

  it("keys a dismissal to WHICH entities went sick", () => {
    const one = projectionWarning(
      SKETCH,
      solved([{ entity: "e1", state: "sick", reason: "unresolved" }]),
    );
    const other = projectionWarning(
      SKETCH,
      solved([{ entity: "e2", state: "sick", reason: "unresolved" }]),
    );
    expect(one?.key).not.toBe(other?.key);
  });
});
