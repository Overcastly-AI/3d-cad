import { describe, expect, it } from "vitest";

import type { EdgeSignature } from "../api/parts";
import {
  edgeSignatureKey,
  edgeSubshapeRef,
  isEdgePicked,
  pickedEdgesSelector,
  toggleEdge,
} from "./edge";

const SIG_A: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 20 },
  end_b: { x: 20, y: 0, z: 20 },
  midpoint: { x: 10, y: 0, z: 20 },
  length_mm: 20,
  subshape_type: "edge",
};
const SIG_B: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 20, z: 20 },
  end_b: { x: 20, y: 20, z: 20 },
  midpoint: { x: 10, y: 20, z: 20 },
  length_mm: 20,
  subshape_type: "edge",
};

describe("edgeSubshapeRef", () => {
  it("echoes the signature into a stage-1 edge reference", () => {
    expect(edgeSubshapeRef("feat-1", SIG_A)).toEqual({
      kind: "subshape",
      feature_id: "feat-1",
      subshape_type: "edge",
      selector: { selector_version: 1, signature: SIG_A },
    });
  });

  it("passes the signature through unchanged (full precision)", () => {
    expect(edgeSubshapeRef("feat-1", SIG_A).selector.signature).toBe(SIG_A);
  });
});

describe("pickedEdgesSelector", () => {
  it("builds a {kind:'edges'} selector from the anchor + signatures", () => {
    expect(pickedEdgesSelector("feat-1", [SIG_A, SIG_B])).toEqual({
      kind: "edges",
      refs: [
        edgeSubshapeRef("feat-1", SIG_A),
        edgeSubshapeRef("feat-1", SIG_B),
      ],
    });
  });

  it("is null with no anchor or no picks (never an empty ref list)", () => {
    expect(pickedEdgesSelector(null, [SIG_A])).toBeNull();
    expect(pickedEdgesSelector("feat-1", [])).toBeNull();
  });
});

describe("edgeSignatureKey", () => {
  it("distinguishes two distinct edges", () => {
    expect(edgeSignatureKey(SIG_A)).not.toBe(edgeSignatureKey(SIG_B));
  });

  it("is stable for an equal signature (a fresh object)", () => {
    expect(edgeSignatureKey({ ...SIG_A })).toBe(edgeSignatureKey(SIG_A));
  });
});

describe("toggleEdge", () => {
  it("adds an unpicked edge, preserving order", () => {
    expect(toggleEdge([SIG_A], SIG_B)).toEqual([SIG_A, SIG_B]);
  });

  it("removes an already-picked edge (a repeat click)", () => {
    expect(toggleEdge([SIG_A, SIG_B], SIG_A)).toEqual([SIG_B]);
  });

  it("matches by identity, not reference (an equal fresh object toggles off)", () => {
    expect(toggleEdge([SIG_A], { ...SIG_A })).toEqual([]);
  });

  it("round-trips: add then remove returns to empty", () => {
    expect(toggleEdge(toggleEdge([], SIG_A), SIG_A)).toEqual([]);
  });
});

describe("isEdgePicked", () => {
  it("reports membership by signature identity", () => {
    expect(isEdgePicked([SIG_A], { ...SIG_A })).toBe(true);
    expect(isEdgePicked([SIG_A], SIG_B)).toBe(false);
  });
});
