import { describe, expect, it } from "vitest";

import { sanitizeDrawingFilename } from "./exportSvg";

describe("sanitizeDrawingFilename", () => {
  it("slugifies a drawing name into a safe lower-case basename", () => {
    expect(sanitizeDrawingFilename("Plate — dimensions")).toBe(
      "plate-dimensions",
    );
    expect(sanitizeDrawingFilename("Bracket v2")).toBe("bracket-v2");
    expect(sanitizeDrawingFilename("  Housing  ")).toBe("housing");
  });

  it("collapses runs of punctuation/whitespace and trims edge hyphens", () => {
    expect(sanitizeDrawingFilename("A / B \\ C")).toBe("a-b-c");
    expect(sanitizeDrawingFilename("--weird--name--")).toBe("weird-name");
    expect(sanitizeDrawingFilename("Ø10 hole")).toBe("10-hole");
  });

  it("falls back to 'drawing' when nothing usable remains", () => {
    expect(sanitizeDrawingFilename("")).toBe("drawing");
    expect(sanitizeDrawingFilename("   ")).toBe("drawing");
    expect(sanitizeDrawingFilename("———")).toBe("drawing");
  });
});
