import { describe, expect, it } from "vitest";

import { parsePropertiesHeader, PROPERTIES_HEADER } from "./tessellate";

/** A real header payload shape for the 10×20×30 first-light box. */
const validMeta = {
  properties: {
    volume: 6000,
    surface_area: 2200,
    centroid: { x: 5, y: 10, z: 15 },
    bounding_box: { min: { x: 0, y: 0, z: 0 }, max: { x: 10, y: 20, z: 30 } },
    topology: { faces: 6, edges: 12, shells: 1 },
  },
  mesh: { triangles: 12, vertices: 24, glb_bytes: 1804 },
};

describe("parsePropertiesHeader", () => {
  it("parses a valid X-Loft-Properties header", () => {
    const meta = parsePropertiesHeader(JSON.stringify(validMeta));
    expect(meta.properties.volume).toBe(6000);
    expect(meta.properties.centroid).toEqual({ x: 5, y: 10, z: 15 });
    expect(meta.mesh.triangles).toBe(12);
  });

  it("throws when the header is missing", () => {
    expect(() => parsePropertiesHeader(null)).toThrow(PROPERTIES_HEADER);
    expect(() => parsePropertiesHeader("  ")).toThrow(PROPERTIES_HEADER);
  });

  it("throws on malformed JSON", () => {
    expect(() => parsePropertiesHeader("{not json")).toThrow(/not valid JSON/);
  });

  it("throws when required fields are missing", () => {
    const missingVolume = structuredClone(validMeta) as Record<string, unknown>;
    delete (missingVolume.properties as Record<string, unknown>).volume;
    expect(() => parsePropertiesHeader(JSON.stringify(missingVolume))).toThrow(
      /does not match TessellationMetadata/,
    );
  });

  it("throws when numbers are not finite numbers", () => {
    const bad = structuredClone(validMeta) as {
      properties: { volume: unknown };
    };
    bad.properties.volume = "6000";
    expect(() => parsePropertiesHeader(JSON.stringify(bad))).toThrow(
      /does not match TessellationMetadata/,
    );
  });

  it("throws on non-object payloads", () => {
    expect(() => parsePropertiesHeader("42")).toThrow(/does not match/);
    expect(() => parsePropertiesHeader("null")).toThrow(/does not match/);
  });
});
