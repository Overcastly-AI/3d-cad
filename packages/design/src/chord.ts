/**
 * Platform-aware keyboard-chord labels for `Kbd` chips.
 *
 * Chords are AUTHORED in the Windows/Linux vocabulary ("Ctrl+Shift+Z") with
 * `Ctrl` naming the PRIMARY modifier — the same convention the app's chord
 * grammar uses (`ctrlKey || metaKey`). On macOS the label re-teaches the same
 * chord in Apple notation: symbol glyphs, canonical modifier order
 * (⌃ ⌥ ⇧ ⌘), no separators — "Ctrl+Shift+Z" → "⇧⌘Z". One home for the
 * mapping so every future chord chip inherits it (single-letter chips are
 * unaffected: no "+" → returned verbatim).
 */

/** Apple-notation glyphs, in canonical display order. */
const MAC_MODIFIERS: Record<string, { glyph: string; order: number }> = {
  // The authored "Ctrl" means the primary modifier → ⌘ on a Mac.
  ctrl: { glyph: "⌘", order: 3 },
  cmd: { glyph: "⌘", order: 3 },
  meta: { glyph: "⌘", order: 3 },
  shift: { glyph: "⇧", order: 2 },
  alt: { glyph: "⌥", order: 1 },
  option: { glyph: "⌥", order: 1 },
};

/** True on Apple platforms (safe under SSR/node: defaults false). */
export function isMacPlatform(): boolean {
  if (typeof navigator === "undefined") return false;
  const signature = `${navigator.platform ?? ""} ${navigator.userAgent ?? ""}`;
  return /Mac|iPhone|iPad|iPod/i.test(signature);
}

/**
 * Format an authored chord for the running platform. Pass `mac` explicitly in
 * tests (or SSR); it defaults to runtime detection.
 */
export function formatChord(
  chord: string,
  mac: boolean = isMacPlatform(),
): string {
  if (!mac || !chord.includes("+")) return chord;
  const parts = chord.split("+").map((part) => part.trim());
  const key = parts[parts.length - 1] ?? "";
  const modifiers = parts
    .slice(0, -1)
    .map((part) => MAC_MODIFIERS[part.toLowerCase()])
    .filter((entry): entry is NonNullable<typeof entry> => entry !== undefined)
    .sort((a, b) => a.order - b.order)
    .map((entry) => entry.glyph)
    .join("");
  return `${modifiers}${key.toUpperCase()}`;
}
