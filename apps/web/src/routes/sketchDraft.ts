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
 * ## The sweep (W0REV-3)
 *
 * Dropping on read was the ONLY expiry, and it only ever looked at the one key
 * being read — so fifty parts touched once left fifty buffers on disk forever,
 * and a full origin quota then broke the one write that matters most: the
 * session token, which reads to the user as "logged out on reload" and would
 * never be traced back here. So drafts are now swept as a set
 * ({@link sweepSketchDrafts}): expired and unreadable ones go, and the
 * survivors are capped at {@link MAX_SKETCH_DRAFTS} drafts and
 * {@link MAX_SKETCH_DRAFT_BYTES}, oldest evicted first. It runs at app start
 * (the session store, before it reads anything) and on the draft write path,
 * throttled so a sketch session does not re-parse every other part's buffer on
 * every edit. And because the sweep keeps drafts WELL inside the quota rather
 * than guaranteeing room, any write that still hits "full" — a draft's own, or
 * the session's — evicts drafts oldest-first and retries
 * ({@link writeEvictingDrafts}): a stale buffer from another part is always
 * worth less than the write being attempted.
 *
 * Storage is `localStorage` — it has to survive the tab dying, which is the
 * case `sessionStorage` cannot cover and the whole reason this exists. Same
 * injectable-storage seam as `auth/session.ts` and `settings/preferences.ts`,
 * so the unit tests drive a fake and never touch the real thing.
 */
import {
  defaultStorage,
  isQuotaExceeded,
  storageKeys,
  type SessionStorageLike,
} from "../auth/storage";
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

/** How long a draft is worth restoring. Older ones are dropped on read and swept. */
export const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * How many drafts are kept at most. A draft is one part's UNSAVED sketch; the
 * live save loop persists work the whole time the token is valid, so more than
 * a handful at once is already unusual and twenty is a generous ceiling, not a
 * working set.
 */
export const MAX_SKETCH_DRAFTS = 20;

/**
 * The byte budget for all drafts together, measured the way browsers meter the
 * quota: UTF-16, so two bytes per code unit of key + value. Origins get about
 * 5 MiB; drafts may use two of it and leave the rest to everything else. The
 * LIVE draft is never evicted to meet this — a single huge sketch still keeps
 * its own copy; it just pushes every older draft out first.
 */
export const MAX_SKETCH_DRAFT_BYTES = 2 * 1024 * 1024;

/**
 * The write path re-sweeps at most this often for a part it has already seen.
 * A write for a part the last sweep did NOT see always sweeps, so the count
 * cap holds exactly; this interval only bounds how stale the byte total can
 * get while one sketch grows.
 */
export const DRAFT_SWEEP_INTERVAL_MS = 60 * 1000;

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
  const parsed = parseDraft(raw);
  if (parsed === null || now - parsed.savedAt > DRAFT_MAX_AGE_MS) {
    // Nothing will ever restore these bytes; do not leave them on the quota.
    removeQuietly(storage, draftKey(partId));
    return null;
  }
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
  const key = draftKey(partId);
  const payload: SketchDraft = {
    ...draft,
    version: DRAFT_VERSION,
    savedAt: now,
  };
  let serialized: string;
  try {
    serialized = JSON.stringify(payload);
  } catch {
    return false;
  }
  const written = writeEvictingDrafts(
    storage,
    () => storage.setItem(key, serialized),
    key,
  );
  if (written.ok) maybeSweep(storage, key, now);
  return written.ok;
}

/** What {@link writeEvictingDrafts} did, so no caller has to guess. */
export type EvictingWriteResult =
  | { ok: true; evicted: number }
  | { ok: false; evicted: number; error: unknown };

/**
 * Run *write*; if the storage is FULL, evict drafts oldest-first — one at a
 * time, retrying after each — until it fits or no draft is left to evict.
 *
 * Never throws. Only a quota error triggers eviction: a storage that refuses
 * writes for any other reason (switched off, private mode) is not cured by
 * deleting a user's work, so that failure is returned untouched. *keep* names
 * a draft that must survive (the one being written — evicting it to make room
 * for itself would be absurd).
 */
export function writeEvictingDrafts(
  storage: SessionStorageLike,
  write: () => void,
  keep: string | null = null,
): EvictingWriteResult {
  let evicted = 0;
  let queue: string[] | null = null;
  for (;;) {
    try {
      write();
      return { ok: true, evicted };
    } catch (error) {
      if (!isQuotaExceeded(error)) return { ok: false, evicted, error };
      queue ??= (listDrafts(storage) ?? [])
        .filter((entry) => entry.key !== keep)
        .map((entry) => entry.key);
      const victim = queue.shift();
      if (victim === undefined || !removeQuietly(storage, victim)) {
        return { ok: false, evicted, error };
      }
      evicted += 1;
    }
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
  const keys = storageKeys(storage);
  if (keys === null) return -1;
  let removed = 0;
  for (const name of keys) {
    // Same posture as every other write here: a storage that throws must not
    // take down the sign-out that called this.
    if (name.startsWith(KEY_PREFIX) && removeQuietly(storage, name)) {
      removed += 1;
    }
  }
  sweepState.delete(storage);
  return removed;
}

/**
 * Sweep the drafts as a SET: drop every one that is expired or unreadable,
 * then evict oldest-first until at most {@link MAX_SKETCH_DRAFTS} remain and
 * they total at most {@link MAX_SKETCH_DRAFT_BYTES}. Only keys under
 * {@link SKETCH_DRAFT_KEY_PREFIX} are ever touched — the storage is the whole
 * origin's, and the session, the preferences and anything else living there
 * are not ours to tidy.
 *
 * *keep* is exempt (the live draft, written moments ago — evicting it to meet
 * a budget it is the newest member of would delete the one buffer that
 * matters). Returns how many keys it removed, or -1 when the storage cannot be
 * enumerated, for the same reason {@link clearAllSketchDrafts} does. Never
 * throws.
 */
export function sweepSketchDrafts(
  storage: SessionStorageLike = defaultStorage(),
  now: number = Date.now(),
  keep: string | null = null,
): number {
  const entries = listDrafts(storage);
  if (entries === null) return -1;
  let removed = 0;
  const survivors: DraftEntry[] = [];
  for (const entry of entries) {
    const dead =
      entry.key !== keep &&
      (entry.savedAt === null || now - entry.savedAt > DRAFT_MAX_AGE_MS);
    if (!dead) survivors.push(entry);
    else if (removeQuietly(storage, entry.key)) removed += 1;
  }
  let count = survivors.length;
  let bytes = survivors.reduce((sum, entry) => sum + entry.bytes, 0);
  const kept = new Set(survivors.map((entry) => entry.key));
  // `listDrafts` is oldest-first, so this walk IS the eviction order.
  for (const entry of survivors) {
    if (count <= MAX_SKETCH_DRAFTS && bytes <= MAX_SKETCH_DRAFT_BYTES) break;
    if (entry.key === keep || !removeQuietly(storage, entry.key)) continue;
    removed += 1;
    count -= 1;
    bytes -= entry.bytes;
    kept.delete(entry.key);
  }
  sweepState.set(storage, { at: now, keys: kept });
  return removed;
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

/** A draft as the sweep sees it: enough to order, cap and evict it. */
interface DraftEntry {
  key: string;
  /** Null when the bytes are not a draft this build can restore. */
  savedAt: number | null;
  /** UTF-16 bytes of key + value, the unit browsers meter the quota in. */
  bytes: number;
}

/**
 * Every draft in *storage*, OLDEST FIRST — unreadable ones before all others,
 * since nothing will ever restore them. Null when the storage cannot be
 * enumerated ("could not look" is not "no drafts").
 */
function listDrafts(storage: SessionStorageLike): DraftEntry[] | null {
  const keys = storageKeys(storage);
  if (keys === null) return null;
  const entries: DraftEntry[] = [];
  for (const key of keys) {
    if (!key.startsWith(KEY_PREFIX)) continue;
    let raw: string | null;
    try {
      raw = storage.getItem(key);
    } catch {
      continue;
    }
    if (raw === null) continue;
    entries.push({
      key,
      savedAt: parseDraft(raw)?.savedAt ?? null,
      bytes: (key.length + raw.length) * 2,
    });
  }
  const age = (entry: DraftEntry) => entry.savedAt ?? Number.NEGATIVE_INFINITY;
  return entries.sort((a, b) => age(a) - age(b));
}

/** The draft in *raw*, or null for every shape this build cannot restore. */
function parseDraft(raw: string): SketchDraft | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isDraft(parsed)) return null;
  if (parsed.version !== DRAFT_VERSION) return null;
  if (parsed.entities.length === 0) return null;
  return parsed;
}

/** `removeItem` that reports instead of throwing. */
function removeQuietly(storage: SessionStorageLike, key: string): boolean {
  try {
    storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

/**
 * The last sweep per storage: when it ran and which drafts it left standing.
 * A WeakMap, so a test's throwaway fake takes its entry with it.
 */
const sweepState = new WeakMap<
  SessionStorageLike,
  { at: number; keys: Set<string> }
>();

/**
 * The write path's sweep, kept cheap: a write for a draft the last sweep did
 * not see (a NEW part — the only way the count grows) always sweeps; a write
 * to a known draft sweeps at most once per {@link DRAFT_SWEEP_INTERVAL_MS}.
 * A sketch session therefore costs one scan when it starts, not one per edit.
 */
function maybeSweep(storage: SessionStorageLike, key: string, now: number) {
  const last = sweepState.get(storage);
  if (
    last !== undefined &&
    last.keys.has(key) &&
    now - last.at < DRAFT_SWEEP_INTERVAL_MS
  ) {
    return;
  }
  sweepSketchDrafts(storage, now, key);
}
