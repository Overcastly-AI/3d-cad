/**
 * STEP-import view logic — the pure guards the Import affordance and PartPage
 * share, kept out of the components so they can be unit-tested without a DOM.
 * The server (§6 of docs/design/step-import.md) is the source of truth for
 * rejection; these client-side checks only give instant feedback before the
 * bytes ever leave the browser, and derive the feature name from the filename.
 */

/**
 * The hard size cap the gateway enforces as it streams the body (oversize →
 * 422 `import_too_large` before the whole file is read). Mirrored here only to
 * fail fast on the client; 16 MiB, the same constant the server uses.
 */
export const IMPORT_MAX_BYTES = 16 * 1024 * 1024;

/** Filename extensions the native picker accepts and this guard recognises. */
export const STEP_EXTENSIONS = [".step", ".stp"] as const;

/** True when a filename ends in a STEP extension (case-insensitive). */
export function isStepFilename(name: string): boolean {
  const lower = name.toLowerCase();
  return STEP_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/**
 * The user-facing feature name for an imported file: its base name without the
 * directory or extension. Empty/edge names fall back to the server default so
 * the tree row is never blank.
 */
export function stepFeatureName(filename: string): string {
  const base = filename.replace(/^.*[\\/]/, ""); // drop any path prefix
  const dot = base.lastIndexOf(".");
  const stem = dot > 0 ? base.slice(0, dot) : base;
  const trimmed = stem.trim();
  return trimmed === "" ? "Imported STEP" : trimmed;
}

/**
 * Client-side pre-check → a legible message, or null when the file may be sent.
 * Instant feedback only: the same conditions are re-checked server-side (the
 * source of truth), whose envelope message is surfaced on a real rejection.
 */
export function precheckStepFile(file: {
  name: string;
  size: number;
}): string | null {
  if (!isStepFilename(file.name)) {
    return "That is not a STEP file. Choose a .step or .stp file.";
  }
  if (file.size === 0) {
    return "That file is empty. Choose a STEP file that contains a solid.";
  }
  if (file.size > IMPORT_MAX_BYTES) {
    return "That STEP file is over the 16 MB limit. Simplify or split the model first.";
  }
  return null;
}
