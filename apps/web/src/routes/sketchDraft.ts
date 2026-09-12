/**
 * THE PER-PART SKETCH DRAFT — the half of FLOW-A2 that makes the product feel
 * safe rather than merely careful.
 *
 * AUDIT-FLOW-2026-09 A2: with four entities drawn and nine constraints solved,
 * the browser Back button, the in-app breadcrumb and a page reload each
 * destroyed the lot, silently, and landed the user on "EMPTY PART — Start with
 * a Sketch". There was no navigation guard of any kind in `apps/web/src`.
 *
 * A guard alone would have been the wrong fix. A dialog that appears at every
 * exit is a tax on a flow the user did nothing wrong in, and it cannot help the
 * one case that hurts most — the tab that dies without asking anybody. So the
 * guard is only half: this module is the other half, and it changes what the
 * guard has to SAY. The prompt does not warn that work is about to be
 * destroyed, because with a draft on disk it is not; it explains the difference
 * between work that is in the PART (saved, shared, versioned, on the server)
 * and work that is in this BROWSER (a draft, private, and only here).
 *
 * ## What is stored, and why exactly this
 *
 * The buffer a sketch session can lose, and nothing else: `plane`, `entities`,
 * `constraints`, the binding (`featureId`), and the two counters that make the
 * restored buffer continuous with the one that was lost — `nextIdIndex` (mint
 * `e5`, never `e1` again, or every id-keyed consumer addresses two entities at
 * once) and `revision` (so the live save loop treats the restored buffer as the
 * edit it already was, not as a fresh one).
 *
 * `nextIdIndex` is CARRIED rather than recomputed on restore. The store derives
 * it from the entity ids when it re-opens a saved feature, and a second copy of
 * that derivation here would be a rule that can drift from the one the store
 * actually uses. The live value is already correct at write time; write it down.
 *
 * Deliberately NOT stored: selection, tool, cursor, hover, history (`past` /
 * `future`), solve readouts. The same line `SketchSnapshot` draws for undo, for
 * the same reason — restoring where the user's hands were is not restoring
 * their geometry, and a solve readout describing a buffer the server has never
 * seen would be a stale number wearing a fresh one's clothes.
 *
 * ## Lifetime
 *
 * Written whenever the live buffer holds work that is not in the part; cleared
 * the moment that stops being true (saved, or discarded) — see `PartPage`,
 * which owns both edges. Keyed per part, so two parts' drafts cannot collide.
 * A draft older than {@link DRAFT_MAX_AGE_MS} is dropped on read: an entity
 * buffer from a fortnight ago is not a session anyone is resuming, and silently
 * re-opening the sketcher on it would be a surprise rather than a rescue.
 *
 * Storage is `localStorage` — it has to survive the tab dying, which is the
 * case `sessionStorage` cannot cover and the whole reason this exists. Same
 * injectable-storage seam as `auth/session.ts` and `settings/preferences.ts`,
 * so the unit tests drive a fake and never touch the real thing.
 */
import type { SessionStorageLike } from "../auth/session";
import type { SketchConstraint } from "../sketch/constraints";
import type { SketchPlaneSpec } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";

/**
 * Bumped whenever the payload shape changes. A draft written by an older build
 * is DROPPED, never migrated: the cost of getting a migration subtly wrong is a
 * buffer that restores into a sketcher that cannot solve it, and the cost of
 * dropping one is that a single in-progress sketch does not come back across a
 * deploy. The second is much cheaper and much easier to explain.
 */
const DRAFT_VERSION = 1;

/**
 * Every draft key starts here, which is what makes the sign-out purge possible
 * without an index of part ids: one prefix scan over the storage.
 * `auth/session.ts` imports it through {@link clearAllSketchDrafts} rather than
 * writing the string down a second time.
 */
export const SKETCH_DRAFT_KEY_PREFIX = "loft.sketch-draft.v1.";

const KEY_PREFIX = SKETCH_DRAFT_KEY_PREFIX;

/** How long a draft is worth restoring. Older ones are dropped on read. */
export const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/** The sketch buffer, as it survives a navigation or a dead tab. */
export interface SketchDraft {
  version: number;
  /** `Date.now()` at the last write — the age check and the restore note. */
  savedAt: number;
  plane: SketchPlaneSpec;
  entities: SketchEntity[];
  constraints: SketchConstraint[];
  /** The persisted feature this buffer was bound to; null = never saved. */
  featureId: string | null;
  /** Resume the id counter here — never re-mint an id already in `entities`. */
  nextIdIndex: number;
  /** The store's edit counter, carried so the save loop sees one timeline. */
  revision: number;
  /** Whether the USER had constrained anything (gates the live save loop). */
  userConstrained: boolean;
}

/** Everything a caller supplies; the envelope fields are added here. */
export type SketchDraftInput = Omit<SketchDraft, "version" | "savedAt">;

export function draftKey(partId: string): string {
  return `${KEY_PREFIX}${partId}`;
}

/**
 * Read this part's draft, or null.
 *
 * Returns null for every way a read can go wrong — absent, unparseable, a
 * foreign shape, a version we do not speak, or too old — because a caller that
 * has to distinguish those is a caller that will get one of them wrong. The
 * only thing a reader can do with a draft it cannot trust is ignore it.
 */
export function readSketchDraft(
  partId: string,
  storage: SessionStorageLike = defaultStorage(),
  now: number = Date.now(),
): SketchDraft | null {
  let raw: string | null;
  try {
    raw = storage.getItem(draftKey(partId));
  } catch {
    return null;
  }
  if (raw === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isDraft(parsed)) return null;
  if (parsed.version !== DRAFT_VERSION) return null;
  if (parsed.entities.length === 0) return null;
  if (now - parsed.savedAt > DRAFT_MAX_AGE_MS) return null;
  return parsed;
}

/**
 * Mirror the live buffer to storage. Returns whether the copy is actually held.
 *
 * A failed write (quota, private mode, storage switched off) never throws:
 * these run inside a render effect, and an exception here would take down the
 * live sketch the draft exists to protect. But it must not be SILENT either —
 * the exit prompt promises the user that leaving keeps their entities, and a
 * promise the storage layer quietly declined to keep is the ambiguous exit this
 * whole item exists to delete. So the caller is told, and says something else.
 */
export function writeSketchDraft(
  partId: string,
  draft: SketchDraftInput,
  storage: SessionStorageLike = defaultStorage(),
  now: number = Date.now(),
): boolean {
  const payload: SketchDraft = {
    ...draft,
    version: DRAFT_VERSION,
    savedAt: now,
  };
  try {
    storage.setItem(draftKey(partId), JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

export function clearSketchDraft(
  partId: string,
  storage: SessionStorageLike = defaultStorage(),
): void {
  try {
    storage.removeItem(draftKey(partId));
  } catch {
    /* nothing to do and nothing worth failing a render over */
  }
}

/**
 * Drop EVERY part's draft — the identity that wrote them has gone (W0 review
 * finding 4; see `auth/session.ts` for why the bytes are deleted rather than
 * re-keyed per user).
 *
 * Returns how many keys it removed, and that return is the point: the call
 * site's test asserts a NUMBER, so a purge that walked a storage it could not
 * enumerate — and therefore found nothing to do — cannot pass for a purge that
 * worked. A storage with no `key()` is exactly that case, and it is reported as
 * -1 rather than 0 so "could not look" never reads as "nothing there".
 */
export function clearAllSketchDrafts(
  storage: SessionStorageLike = defaultStorage(),
): number {
  const { key, length } = storage;
  if (typeof key !== "function" || typeof length !== "number") return -1;
  const doomed: string[] = [];
  try {
    for (let index = 0; index < length; index += 1) {
      const name = key.call(storage, index);
      if (name !== null && name.startsWith(KEY_PREFIX)) doomed.push(name);
    }
    for (const name of doomed) storage.removeItem(name);
  } catch {
    // Same posture as every other write here: a storage that throws must not
    // take down the sign-out that called this.
    return doomed.length;
  }
  return doomed.length;
}

/** How long ago the draft was written, in the workshop's plain words. */
export function draftAge(savedAt: number, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - savedAt) / 1000));
  if (seconds < 60) return "moments ago";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "an hour ago" : `${hours} hours ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

function isDraft(value: unknown): value is SketchDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Partial<SketchDraft>;
  return (
    typeof draft.version === "number" &&
    typeof draft.savedAt === "number" &&
    typeof draft.nextIdIndex === "number" &&
    typeof draft.revision === "number" &&
    typeof draft.userConstrained === "boolean" &&
    (draft.featureId === null || typeof draft.featureId === "string") &&
    typeof draft.plane === "object" &&
    draft.plane !== null &&
    Array.isArray(draft.entities) &&
    Array.isArray(draft.constraints)
  );
}

/** No-op storage for environments without localStorage (SSR, unit tests). */
const nullStorage: SessionStorageLike = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

function defaultStorage(): SessionStorageLike {
  try {
    return globalThis.localStorage ?? nullStorage;
  } catch {
    return nullStorage;
  }
}
