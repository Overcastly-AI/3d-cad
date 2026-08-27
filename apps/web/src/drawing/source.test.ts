import { describe, expect, it } from "vitest";

import {
  drawingSourceKind,
  drawingSourceName,
  drawingSourceOptions,
} from "./source";

const PARTS = [
  { id: "p1", name: "Bracket plate" },
  { id: "p2", name: "Cover plate" },
];
const ASSEMBLIES = [{ id: "a1", name: "Gearbox" }];

describe("drawingSourceOptions", () => {
  it("lists parts first, then assemblies, each tagged with its kind", () => {
    expect(drawingSourceOptions(PARTS, ASSEMBLIES)).toEqual([
      { id: "p1", name: "Bracket plate", kind: "part" },
      { id: "p2", name: "Cover plate", kind: "part" },
      { id: "a1", name: "Gearbox", kind: "assembly" },
    ]);
  });

  it("is empty when neither register has anything", () => {
    expect(drawingSourceOptions([], [])).toEqual([]);
  });
});

describe("drawingSourceKind", () => {
  const sources = drawingSourceOptions(PARTS, ASSEMBLIES);

  it("recovers the kind from the bare id — the picker never encodes it", () => {
    expect(drawingSourceKind(sources, "p2")).toBe("part");
    expect(drawingSourceKind(sources, "a1")).toBe("assembly");
  });

  it("falls back to part for an unknown or absent id", () => {
    expect(drawingSourceKind(sources, "nope")).toBe("part");
    expect(drawingSourceKind(sources, null)).toBe("part");
  });
});

describe("drawingSourceName", () => {
  const sources = drawingSourceOptions(PARTS, ASSEMBLIES);

  it("resolves the display name for either kind", () => {
    expect(drawingSourceName(sources, "p1")).toBe("Bracket plate");
    expect(drawingSourceName(sources, "a1")).toBe("Gearbox");
  });

  it("is null when the id is unknown — never a fabricated caption", () => {
    expect(drawingSourceName(sources, "gone")).toBeNull();
    expect(drawingSourceName(sources, null)).toBeNull();
  });
});
