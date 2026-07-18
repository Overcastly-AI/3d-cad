/**
 * Undo/redo keyboard grammar (docs/design/undo-redo.md §UR2):
 *
 *   Ctrl/⌘+Z        → undo
 *   Ctrl/⌘+Shift+Z  → redo
 *   Ctrl+Y          → redo   (the Windows convention; ⌘Y is NOT bound — it
 *                             belongs to the platform)
 *
 * Pure and node-testable: the caller passes whether the keystroke belongs to a
 * focused text control (`isTypingTarget`) — a text field's NATIVE undo stack is
 * never hijacked, matching every other PartPage keyboard effect.
 */

export type HistoryStep = "undo" | "redo";

/** The keydown fields the grammar reads (a structural subset of KeyboardEvent). */
export interface HistoryKeyEvent {
  key: string;
  /** Physical key (e.g. "KeyZ") — the non-Latin-layout fallback. */
  code?: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

/**
 * Layout-proof letter match. The layout's OWN label wins where it produces a
 * Latin letter (QWERTZ's physical KeyY types "z" — that user's Ctrl+Z must
 * undo, and their physical KeyZ types "y" — Ctrl+Y must redo, not undo). A
 * non-Latin layout (Cyrillic Ctrl+Z reports key "я") falls back to the
 * physical `event.code`, so the chord still fires.
 */
function matchesLetter(event: HistoryKeyEvent, letter: "z" | "y"): boolean {
  const key = event.key.toLowerCase();
  if (/^[a-z]$/.test(key)) return key === letter;
  return event.code === (letter === "z" ? "KeyZ" : "KeyY");
}

/**
 * Resolve a keydown to a history step, or null when the keystroke isn't ours:
 * no primary modifier, an Alt chord (browser/OS shortcuts), an unbound key, or
 * a focused text control (`typing` — its own undo stays native).
 */
export function undoRedoStep(
  event: HistoryKeyEvent,
  typing: boolean,
): HistoryStep | null {
  if (typing) return null;
  if (event.altKey) return null;
  if (!event.ctrlKey && !event.metaKey) return null;
  if (matchesLetter(event, "z")) return event.shiftKey ? "redo" : "undo";
  if (
    matchesLetter(event, "y") &&
    event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey
  ) {
    return "redo";
  }
  return null;
}
