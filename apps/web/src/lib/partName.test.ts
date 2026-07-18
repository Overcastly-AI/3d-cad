import { describe, expect, it } from "vitest";

import { MAX_PART_NAME_LENGTH, validatePartName } from "./partName";

describe("validatePartName", () => {
  it("accepts an ordinary name", () => {
    expect(validatePartName("Bracket plate")).toBeNull();
  });

  it("rejects an empty name", () => {
    expect(validatePartName("")).toBe("Name the part to create it.");
  });

  it("treats a whitespace-only name as empty (server trims too)", () => {
    expect(validatePartName("   ")).toBe("Name the part to create it.");
  });

  it("accepts a name at the length bound", () => {
    expect(validatePartName("a".repeat(MAX_PART_NAME_LENGTH))).toBeNull();
  });

  it("rejects a name past the length bound", () => {
    expect(validatePartName("a".repeat(MAX_PART_NAME_LENGTH + 1))).toBe(
      `Keep the name under ${MAX_PART_NAME_LENGTH} characters.`,
    );
  });
});
