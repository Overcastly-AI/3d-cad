import { describe, expect, it } from "vitest";

import { CONTEXT_MENU_DRAG_SLOP_PX, isDragGesture } from "./contextMenuGesture";

/**
 * FINDINGS burn-down 2026-07-25 #4: the right button PANS the camera, so a
 * right-drag must never end with the context menu popping at the release
 * point — only a right CLICK opens it.
 */
describe("isDragGesture", () => {
  it("treats a still right-click as a click (the menu opens)", () => {
    expect(isDragGesture({ x: 400, y: 300 }, { x: 400, y: 300 })).toBe(false);
  });

  it("tolerates hand tremor inside the slop", () => {
    expect(isDragGesture({ x: 400, y: 300 }, { x: 402, y: 302 })).toBe(false);
    expect(
      isDragGesture(
        { x: 400, y: 300 },
        { x: 400 + CONTEXT_MENU_DRAG_SLOP_PX, y: 300 },
      ),
    ).toBe(false);
  });

  it("calls a real pan a drag (the menu stays shut)", () => {
    expect(isDragGesture({ x: 400, y: 300 }, { x: 460, y: 300 })).toBe(true);
    expect(isDragGesture({ x: 400, y: 300 }, { x: 400, y: 220 })).toBe(true);
    // Diagonal travel counts by distance, not by axis.
    expect(isDragGesture({ x: 400, y: 300 }, { x: 404, y: 304 })).toBe(true);
  });

  it("opens the menu when the gesture has no known origin", () => {
    // Context-menu key, or a button that went down outside the viewport.
    expect(isDragGesture(null, { x: 400, y: 300 })).toBe(false);
  });

  it("honors a caller-supplied slop", () => {
    expect(isDragGesture({ x: 0, y: 0 }, { x: 10, y: 0 }, 20)).toBe(false);
    expect(isDragGesture({ x: 0, y: 0 }, { x: 30, y: 0 }, 20)).toBe(true);
  });
});
