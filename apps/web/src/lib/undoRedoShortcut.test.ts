import { describe, expect, it } from "vitest";

import { type HistoryKeyEvent, undoRedoStep } from "./undoRedoShortcut";

/** A chord with every modifier defaulted off. */
function chord(overrides: Partial<HistoryKeyEvent> & { key: string }) {
  return {
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    altKey: false,
    ...overrides,
  };
}

describe("undoRedoStep — modifier matrix", () => {
  it("Ctrl+Z → undo (Windows/Linux)", () => {
    expect(undoRedoStep(chord({ key: "z", ctrlKey: true }), false)).toBe(
      "undo",
    );
  });

  it("⌘+Z → undo (mac)", () => {
    expect(undoRedoStep(chord({ key: "z", metaKey: true }), false)).toBe(
      "undo",
    );
  });

  it("Ctrl+Shift+Z → redo", () => {
    // A shifted chord reports "Z"; the grammar lowercases before matching.
    expect(
      undoRedoStep(chord({ key: "Z", ctrlKey: true, shiftKey: true }), false),
    ).toBe("redo");
  });

  it("⌘+Shift+Z → redo", () => {
    expect(
      undoRedoStep(chord({ key: "Z", metaKey: true, shiftKey: true }), false),
    ).toBe("redo");
  });

  it("Ctrl+Y → redo (the Windows convention)", () => {
    expect(undoRedoStep(chord({ key: "y", ctrlKey: true }), false)).toBe(
      "redo",
    );
  });

  it("⌘+Y is NOT bound — it belongs to the platform", () => {
    expect(undoRedoStep(chord({ key: "y", metaKey: true }), false)).toBeNull();
  });

  it("Ctrl+Shift+Y is not bound", () => {
    expect(
      undoRedoStep(chord({ key: "y", ctrlKey: true, shiftKey: true }), false),
    ).toBeNull();
  });

  it("a plain Z (no primary modifier) is not ours", () => {
    expect(undoRedoStep(chord({ key: "z" }), false)).toBeNull();
    expect(undoRedoStep(chord({ key: "z", shiftKey: true }), false)).toBeNull();
  });

  it("an Alt chord is never ours (browser/OS shortcuts)", () => {
    expect(
      undoRedoStep(chord({ key: "z", ctrlKey: true, altKey: true }), false),
    ).toBeNull();
    expect(
      undoRedoStep(chord({ key: "y", ctrlKey: true, altKey: true }), false),
    ).toBeNull();
  });

  it("other keys under the primary modifier pass through", () => {
    expect(undoRedoStep(chord({ key: "s", ctrlKey: true }), false)).toBeNull();
    expect(undoRedoStep(chord({ key: "c", metaKey: true }), false)).toBeNull();
  });
});

describe("undoRedoStep — typing-target guard", () => {
  it("never hijacks a focused text control's native undo", () => {
    expect(undoRedoStep(chord({ key: "z", ctrlKey: true }), true)).toBeNull();
    expect(undoRedoStep(chord({ key: "z", metaKey: true }), true)).toBeNull();
    expect(
      undoRedoStep(chord({ key: "Z", ctrlKey: true, shiftKey: true }), true),
    ).toBeNull();
    expect(undoRedoStep(chord({ key: "y", ctrlKey: true }), true)).toBeNull();
  });
});
