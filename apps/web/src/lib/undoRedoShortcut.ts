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
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
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
  const key = event.key.toLowerCase();
  if (key === "z") return event.shiftKey ? "redo" : "undo";
  if (key === "y" && event.ctrlKey && !event.metaKey && !event.shiftKey) {
    return "redo";
  }
  return null;
}
