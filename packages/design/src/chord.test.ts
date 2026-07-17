import { describe, expect, it } from "vitest";

import { formatChord } from "./chord";

describe("formatChord", () => {
  it("keeps the authored Windows/Linux notation off mac", () => {
    expect(formatChord("Ctrl+Z", false)).toBe("Ctrl+Z");
    expect(formatChord("Ctrl+Shift+Z", false)).toBe("Ctrl+Shift+Z");
    expect(formatChord("Ctrl+Y", false)).toBe("Ctrl+Y");
  });

  it("re-teaches the chord in Apple notation on mac", () => {
    expect(formatChord("Ctrl+Z", true)).toBe("⌘Z");
    expect(formatChord("Ctrl+Shift+Z", true)).toBe("⇧⌘Z");
    expect(formatChord("Alt+Shift+A", true)).toBe("⌥⇧A");
  });

  it("orders mac modifiers canonically (⌥ ⇧ ⌘) regardless of authoring", () => {
    expect(formatChord("Shift+Ctrl+Z", true)).toBe("⇧⌘Z");
    expect(formatChord("Ctrl+Alt+Shift+K", true)).toBe("⌥⇧⌘K");
  });

  it("returns single-key chips verbatim on every platform", () => {
    expect(formatChord("M", true)).toBe("M");
    expect(formatChord("M", false)).toBe("M");
    expect(formatChord("Esc", true)).toBe("Esc");
  });

  it("defaults mac detection safely off in node (no navigator)", () => {
    expect(formatChord("Ctrl+Z")).toBe("Ctrl+Z");
  });
});
