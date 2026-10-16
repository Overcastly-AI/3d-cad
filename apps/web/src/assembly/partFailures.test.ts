/**
 * BIKE2-FAILED-PART-KILLS-PICKS: a part that failed to build is found at any
 * depth — directly, inside a sub-assembly, as a pattern copy — and named once.
 */
import { describe, expect, it } from "vitest";

import type {
  EvaluatedInstance,
  InstancePlacementResult,
} from "../api/assemblies";
import {
  failedDocumentIds,
  failedParts,
  failuresByComponent,
  partNameOf,
} from "./partFailures";

const ERROR = {
  code: "profile_unsupported",
  message: "The profile crosses the arm's end edge.",
};
const PLACEMENT = {
  translation: [0, 0, 0],
  rotation: { w: 1, x: 0, y: 0, z: 0 },
} as unknown as InstancePlacementResult["placement"];

function part(id: string, doc: string, name: string): EvaluatedInstance {
  return {
    instance_id: id,
    part_key: `${doc}@tip`,
    name,
    features: [],
  } as unknown as EvaluatedInstance;
}

function sub(id: string, name: string, inner: EvaluatedInstance[]) {
  return {
    instance_id: id,
    part_key: `sub-${id}@tip`,
    name,
    features: [],
    sub_assembly: { instances: inner },
  } as unknown as EvaluatedInstance;
}

function row(
  id: string,
  over: Partial<InstancePlacementResult> = {},
): InstancePlacementResult {
  return {
    instance_id: id,
    part_mesh_glb_id: null,
    placement: PLACEMENT,
    error: ERROR,
    ...over,
  } as InstancePlacementResult;
}

const FRAME = part("frame", "doc-frame", "Frame <1>");
const CRANKSET = sub("crankset", "Crankset <1>", [
  part("ring", "doc-ring", "Chainring <1>"),
  part("arm-l", "doc-arm", "Crank arm <1>"),
  part("arm-r", "doc-arm", "Crank arm <2>"),
]);
const REQUEST = { instances: [FRAME, CRANKSET] };

describe("partNameOf", () => {
  it("drops the instance ordinal", () => {
    expect(partNameOf("Crank arm <12>")).toBe("Crank arm");
    expect(partNameOf("Bracket")).toBe("Bracket");
  });
});

describe("failedParts", () => {
  it("is empty when every row has a body", () => {
    expect(
      failedParts(
        [row("frame", { part_mesh_glb_id: "sha256:a", error: null })],
        REQUEST,
      ),
    ).toEqual([]);
  });

  it("names a failed part inside a sub-assembly once, counting both occurrences", () => {
    const rows = [
      row("frame", { part_mesh_glb_id: "sha256:a", error: null }),
      row("occ-ring", {
        path: ["crankset", "ring"],
        part_mesh_glb_id: "sha256:b",
        error: null,
      }),
      row("occ-l", { path: ["crankset", "arm-l"] }),
      row("occ-r", { path: ["crankset", "arm-r"] }),
    ];
    const failed = failedParts(rows, REQUEST);
    expect(failed).toEqual([
      {
        partDocumentId: "doc-arm",
        name: "Crank arm",
        code: "profile_unsupported",
        message: ERROR.message,
        componentIds: ["crankset"],
        occurrences: 2,
      },
    ]);
    expect(failuresByComponent(failed).get("crankset")).toHaveLength(1);
    expect(failuresByComponent(failed).has("frame")).toBe(false);
    expect([...failedDocumentIds(failed)]).toEqual(["doc-arm"]);
  });

  it("counts a top-level part and its pattern copies against the seed", () => {
    const rows = [
      row("frame"),
      row("copy-1", {
        pattern: { pattern_id: "p", seed_instance_id: "frame", index: 1 },
      }),
    ];
    const [frame] = failedParts(rows, REQUEST);
    expect(frame?.name).toBe("Frame");
    expect(frame?.componentIds).toEqual(["frame"]);
    expect(frame?.occurrences).toBe(2);
  });

  it("follows a pattern copy of a sub-assembly back to the seed's part", () => {
    const rows = [
      row("occ-l", { path: ["crankset", "arm-l"] }),
      row("copy-occ", {
        path: ["copy-of-crankset", "arm-l"],
        pattern: { pattern_id: "p", seed_instance_id: "crankset", index: 1 },
      }),
    ];
    const failed = failedParts(rows, REQUEST);
    expect(failed).toHaveLength(1);
    expect(failed[0]?.occurrences).toBe(2);
  });

  it("folds a copy placed by a pattern inside a sub-assembly into its seed", () => {
    // Such a copy's path names a copy id the request does not hold.
    const rows = [
      row("occ-l", { path: ["crankset", "arm-l"] }),
      row("inner-copy", { path: ["crankset", "inner-copy-id"] }),
    ];
    const failed = failedParts(rows, REQUEST);
    expect(failed).toHaveLength(1);
    expect(failed[0]?.occurrences).toBe(2);
  });

  it("still reports a failure the request cannot name", () => {
    const failed = failedParts([row("ghost")], null);
    expect(failed).toHaveLength(1);
    expect(failed[0]?.name).toBe("A part");
    expect(failed[0]?.partDocumentId).toBeNull();
  });
});
