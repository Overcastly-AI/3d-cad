/**
 * `.loft` import view logic (docs/FILE-FORMAT.md): the client-side pre-check
 * and the one piece of state that has to outlive a navigation.
 *
 * An import creates a NEW part, so the workspace navigates to it — and the
 * warnings the server returned (a hand-edited tree, a volume that differs from
 * the file's, features that failed to rebuild) belong on the page the user
 * lands on, not the one they left. They ride across in this store, keyed by
 * the part they describe, until dismissed.
 */
import { create } from "zustand";

import type { LoftWarning } from "../api/importLoft";

/** The gateway's streamed upload cap (64 MiB), mirrored only to fail fast. */
export const LOFT_IMPORT_MAX_BYTES = 64 * 1024 * 1024;

/** The one suffix a `.loft` has. */
export const LOFT_EXTENSION = ".loft";

/**
 * A legible message, or null when the file may be sent. Instant feedback
 * only: the server re-checks everything and its envelope message is shown on
 * a real refusal.
 */
export function precheckLoftFile(file: {
  name: string;
  size: number;
}): string | null {
  if (!file.name.toLowerCase().endsWith(LOFT_EXTENSION)) {
    return "That is not a Loft file. Choose a .loft file.";
  }
  if (file.size === 0) {
    return "That file is empty. Choose a .loft file exported from Loft.";
  }
  if (file.size > LOFT_IMPORT_MAX_BYTES) {
    return "That .loft file is over the 64 MB limit.";
  }
  return null;
}

interface LoftImportNoticeState {
  /** The part the warnings describe, or null when there is nothing to say. */
  partId: string | null;
  warnings: readonly LoftWarning[];
  show: (partId: string, warnings: readonly LoftWarning[]) => void;
  dismiss: () => void;
}

export const useLoftImportNotice = create<LoftImportNoticeState>((set) => ({
  partId: null,
  warnings: [],
  show: (partId, warnings) => set({ partId, warnings }),
  dismiss: () => set({ partId: null, warnings: [] }),
}));
