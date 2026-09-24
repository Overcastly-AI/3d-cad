/**
 * THE STORAGE SEAM — the one shape every localStorage consumer here is written
 * against (`auth/session.ts`, `routes/sketchDraft.ts`,
 * `settings/preferences.ts`), so unit tests drive an in-memory fake and never
 * touch the real thing.
 *
 * A leaf module ON PURPOSE: it imports nothing. `session.ts` imports
 * `sketchDraft.ts` at runtime (sign-out purges drafts; a full quota evicts
 * them), so the helpers both of them need cannot live in either one without
 * an import cycle — and a cycle here would be the bad kind, because
 * `session.ts` builds its store at module evaluation.
 *
 * Every helper below is TOTAL: it never throws. A storage can be absent (SSR),
 * switched off (private mode, enterprise policy — `SecurityError` on access),
 * or full (`QuotaExceededError` on write), and none of those may take down the
 * render or the sign-in that happened to touch it.
 */

/** The subset of the Storage API the app needs (injectable for tests). */
export interface SessionStorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
  /**
   * Enumeration — the key scan. A real `Storage` supplies both. They are
   * optional because most consumers address keys by name and their no-op
   * fallbacks do not bother; the draft sweep and the sign-out purge need them
   * to find keys whose names they do not know (one draft per part id), and
   * {@link storageKeys} reports a storage without them as "could not look"
   * rather than as "empty".
   */
  readonly length?: number;
  key?(index: number): string | null;
}

/**
 * Every key in *storage*, or null when it cannot be enumerated.
 *
 * Null and `[]` are different answers — "I could not look" versus "there was
 * nothing there" — and callers that report a count keep them apart. The key
 * list is snapshotted before the caller mutates anything: removing keys while
 * walking `key(i)` shifts every later index and skips entries.
 */
export function storageKeys(storage: SessionStorageLike): string[] | null {
  try {
    const { length } = storage;
    if (typeof storage.key !== "function" || typeof length !== "number") {
      return null;
    }
    const keys: string[] = [];
    for (let index = 0; index < length; index += 1) {
      const name = storage.key(index);
      if (name !== null) keys.push(name);
    }
    return keys;
  } catch {
    return null;
  }
}

/**
 * Whether *error* is the storage saying "full".
 *
 * By NAME, not `instanceof DOMException`: jsdom, Node and each browser build
 * their own exception objects, and the name is the part every engine agrees
 * on. Firefox historically used its own name for the same condition. Only this
 * condition is worth evicting for — a `SecurityError` (storage switched off)
 * will not be cured by deleting anything.
 */
export function isQuotaExceeded(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  const name = (error as { name?: unknown }).name;
  return name === "QuotaExceededError" || name === "NS_ERROR_DOM_QUOTA_REACHED";
}

/** No-op storage for environments without localStorage (SSR, unit tests). */
export const nullStorage: SessionStorageLike = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

/**
 * The browser's localStorage, or {@link nullStorage} when there is none or
 * merely touching it throws (a blocked-storage `SecurityError`).
 */
export function defaultStorage(): SessionStorageLike {
  try {
    return globalThis.localStorage ?? nullStorage;
  } catch {
    return nullStorage;
  }
}
