/**
 * Tab containment for a modal panel that holds a `lib/modalGate` layer. The
 * gate hands every key to the layer; this keeps Tab and Shift+Tab cycling
 * inside the panel and pulls a key that arrived from outside back in.
 *
 * Returns true when it handled the key.
 */
const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

export function containFocus(
  panel: HTMLElement | null,
  event: KeyboardEvent,
  insidePanel: boolean,
): boolean {
  if (panel === null) return false;
  const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
  if (!insidePanel) {
    event.preventDefault();
    (focusable[0] ?? panel).focus();
    return true;
  }
  if (event.key !== "Tab" || focusable.length === 0) return false;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (active === first || active === panel)) {
    event.preventDefault();
    last?.focus();
    return true;
  }
  if (!event.shiftKey && active === last) {
    event.preventDefault();
    first?.focus();
    return true;
  }
  return false;
}

/** Ctrl+S (Cmd+S on a Mac), no other modifier: Save version. */
export function isSaveChord(event: KeyboardEvent): boolean {
  return (
    (event.ctrlKey || event.metaKey) &&
    !event.shiftKey &&
    !event.altKey &&
    event.key.toLowerCase() === "s"
  );
}
