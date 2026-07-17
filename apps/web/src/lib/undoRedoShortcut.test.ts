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

describe("undoRedoStep — non-Latin / remapped layouts", () => {
  it("Cyrillic layout: key 'я' with physical KeyZ still undoes/redoes", () => {
    expect(
      undoRedoStep(chord({ key: "я", code: "KeyZ", ctrlKey: true }), false),
    ).toBe("undo");
    expect(
      undoRedoStep(
        chord({ key: "Я", code: "KeyZ", ctrlKey: true, shiftKey: true }),
        false,
      ),
    ).toBe("redo");
  });

  it("Cyrillic layout: key 'н' with physical KeyY fires Ctrl+Y redo", () => {
    expect(
      undoRedoStep(chord({ key: "н", code: "KeyY", ctrlKey: true }), false),
    ).toBe("redo");
  });

  it("non-Latin keys on OTHER physical keys stay unbound", () => {
    expect(
      undoRedoStep(chord({ key: "ф", code: "KeyA", ctrlKey: true }), false),
    ).toBeNull();
  });

  it("QWERTZ: the layout's label wins over the physical code", () => {
    // Physical KeyY types "z" — the user's Ctrl+Z must undo…
    expect(
      undoRedoStep(chord({ key: "z", code: "KeyY", ctrlKey: true }), false),
    ).toBe("undo");
    // …and physical KeyZ types "y" — their Ctrl+Y redoes, never undoes.
    expect(
      undoRedoStep(chord({ key: "y", code: "KeyZ", ctrlKey: true }), false),
    ).toBe("redo");
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
