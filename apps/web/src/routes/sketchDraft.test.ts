import { describe, expect, it } from "vitest";

import type { SessionStorageLike } from "../auth/session";
import type { SketchEntity } from "../sketch/tools";
import {
  clearAllSketchDrafts,
  clearSketchDraft,
  DRAFT_MAX_AGE_MS,
  DRAFT_SWEEP_INTERVAL_MS,
  draftAge,
  draftKey,
  MAX_SKETCH_DRAFT_BYTES,
  MAX_SKETCH_DRAFTS,
  readSketchDraft,
  SKETCH_DRAFT_KEY_PREFIX,
  sweepSketchDrafts,
  writeEvictingDrafts,
  writeSketchDraft,
  type SketchDraftInput,
} from "./sketchDraft";

/**
 * An in-memory stand-in for localStorage, plus a throwing variant.
 *
 * It ENUMERATES, like the real thing: the sign-out purge finds keys it does not
 * know the names of (one per part id), so a fake without `key()`/`length` would
 * let a purge that walked nothing pass for a purge that worked.
 */
function fakeStorage(
  quotaChars = Number.POSITIVE_INFINITY,
): SessionStorageLike & { map: Map<string, string>; reads: number } {
  const map = new Map<string, string>();
  const used = () =>
    [...map].reduce((sum, [key, value]) => sum + key.length + value.length, 0);
  return {
    map,
    reads: 0,
    getItem(key) {
      this.reads += 1;
      return map.get(key) ?? null;
    },
    // Metered like the real thing: key + value code units against a quota,
    // and a write that would cross it throws the browser's own error NAME.
    setItem: (key, value) => {
      const after =
        used() - (map.get(key)?.length ?? -key.length) + value.length;
      if (after > quotaChars) {
        throw new DOMException("quota", "QuotaExceededError");
      }
      map.set(key, value);
    },
    removeItem: (key) => void map.delete(key),
    get length() {
      return map.size;
    },
    key: (index) => [...map.keys()][index] ?? null,
  };
}

const throwingStorage: SessionStorageLike = {
  getItem: () => {
    throw new Error("storage disabled");
  },
  setItem: () => {
    throw new Error("quota exceeded");
  },
  removeItem: () => {
    throw new Error("storage disabled");
  },
};

const LINE: SketchEntity = {
  kind: "line",
  id: "e1",
  construction: false,
  start: { x: 0, y: 0 },
  end: { x: 10, y: 0 },
};

function input(overrides: Partial<SketchDraftInput> = {}): SketchDraftInput {
  return {
    plane: { kind: "origin", base: "XY" },
    entities: [LINE],
    constraints: [],
    featureId: null,
    nextIdIndex: 2,
    revision: 3,
    userConstrained: false,
    ...overrides,
  };
}

describe("sketchDraft", () => {
  it("round-trips a draft and keys it per part", () => {
    const storage = fakeStorage();
    writeSketchDraft("part-a", input(), storage, 1_000);
    writeSketchDraft(
      "part-b",
      input({ entities: [LINE, { ...LINE, id: "e2" }], nextIdIndex: 3 }),
      storage,
      1_000,
    );

    const a = readSketchDraft("part-a", storage, 2_000);
    const b = readSketchDraft("part-b", storage, 2_000);
    expect(a?.entities).toHaveLength(1);
    expect(b?.entities).toHaveLength(2);
    expect(a?.savedAt).toBe(1_000);
    expect(storage.map.has(draftKey("part-a"))).toBe(true);
    expect(readSketchDraft("part-c", storage, 2_000)).toBeNull();
  });

  it("carries the id counter rather than making the reader re-derive it", () => {
    // The store resumes minting above this number; a second derivation of it
    // here is a rule that can drift from the store's own.
    const storage = fakeStorage();
    writeSketchDraft("p", input({ nextIdIndex: 17, revision: 42 }), storage);
    const draft = readSketchDraft("p", storage);
    expect(draft?.nextIdIndex).toBe(17);
    expect(draft?.revision).toBe(42);
  });

  it("clears", () => {
    const storage = fakeStorage();
    writeSketchDraft("p", input(), storage);
    clearSketchDraft("p", storage);
    expect(readSketchDraft("p", storage)).toBeNull();
  });

  it("drops a draft past the age ceiling", () => {
    const storage = fakeStorage();
    writeSketchDraft("p", input(), storage, 0);
    expect(readSketchDraft("p", storage, DRAFT_MAX_AGE_MS - 1)).not.toBeNull();
    expect(readSketchDraft("p", storage, DRAFT_MAX_AGE_MS + 1)).toBeNull();
    // Dropped from the quota too, not merely ignored (W0REV-3).
    expect(storage.map.has(draftKey("p"))).toBe(false);
  });

  it("refuses every shape it cannot trust", () => {
    const storage = fakeStorage();
    const cases: Record<string, string> = {
      "not json": "{oops",
      "not an object": '"a string"',
      null: "null",
      "missing plane": JSON.stringify({
        version: 1,
        savedAt: Date.now(),
        entities: [LINE],
        constraints: [],
        featureId: null,
        nextIdIndex: 2,
        revision: 1,
        userConstrained: false,
      }),
      "wrong version": JSON.stringify({
        ...input(),
        version: 99,
        savedAt: Date.now(),
      }),
      "empty buffer": JSON.stringify({
        ...input({ entities: [] }),
        version: 1,
        savedAt: Date.now(),
      }),
    };
    for (const [name, raw] of Object.entries(cases)) {
      storage.map.set(draftKey("p"), raw);
      expect(readSketchDraft("p", storage), name).toBeNull();
    }
  });

  it("never throws out of a storage failure", () => {
    // These run inside a render effect; an exception here would take down the
    // live sketch the draft exists to protect.
    expect(() => writeSketchDraft("p", input(), throwingStorage)).not.toThrow();
    expect(() => clearSketchDraft("p", throwingStorage)).not.toThrow();
    expect(readSketchDraft("p", throwingStorage)).toBeNull();
  });

  it("says how old a draft is in plain words", () => {
    const now = 1_000_000_000;
    const ago = (ms: number) => draftAge(now - ms, now);
    expect(ago(5_000)).toBe("moments ago");
    expect(ago(5 * 60_000)).toBe("5 min ago");
    expect(ago(60 * 60_000)).toBe("an hour ago");
    expect(ago(5 * 60 * 60_000)).toBe("5 hours ago");
    expect(ago(24 * 60 * 60_000)).toBe("yesterday");
    expect(ago(3 * 24 * 60 * 60_000)).toBe("3 days ago");
  });
});

/**
 * W0 review finding 4 — a draft outlived the session that made it.
 *
 * `signOut` removed the token and nothing else, so a user's in-progress
 * geometry stayed on the disk of a shared browser for seven days, under a key
 * that names the PART and not the person.
 */
describe("clearAllSketchDrafts", () => {
  it("removes every part's draft and leaves everything else alone", () => {
    const storage = fakeStorage();
    writeSketchDraft("part-a", input(), storage, 1_000);
    writeSketchDraft("part-b", input(), storage, 1_000);
    storage.setItem("loft.session.v1", "{}");
    storage.setItem("loft.preferences.v1", "{}");

    // By COUNT, not by "it did not throw": a purge that found nothing to do
    // reports 0 here and cannot pass for one that worked.
    expect(clearAllSketchDrafts(storage)).toBe(2);
    expect(readSketchDraft("part-a", storage, 2_000)).toBeNull();
    expect(readSketchDraft("part-b", storage, 2_000)).toBeNull();
    expect(storage.map.has("loft.session.v1")).toBe(true);
    expect(storage.map.has("loft.preferences.v1")).toBe(true);
  });

  it("reports -1 for a storage it cannot walk, never 0", () => {
    // "I could not look" and "there was nothing there" are different answers,
    // and a purge that returns the second for the first is a gate that cannot
    // fail. `SessionStorageLike` makes enumeration optional, so this is a real
    // shape a caller can pass.
    const blind: SessionStorageLike = {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    };
    expect(clearAllSketchDrafts(blind)).toBe(-1);
  });

  it("survives a storage that throws", () => {
    expect(() => clearAllSketchDrafts(throwingStorage)).not.toThrow();
  });
});

/**
 * W0REV-3 — drafts were never swept. Expiry was checked only when that one
 * part's key was read, so fifty parts touched once left fifty buffers on disk
 * for good, and a full quota then broke the session write ("logged out on
 * reload"). These drive the PUBLIC write path wherever they can, so they
 * describe what the app does rather than what one helper does when asked.
 */
describe("the draft sweep (W0REV-3)", () => {
  const DAY = 24 * 60 * 60 * 1000;
  const draftKeys = (storage: { map: Map<string, string> }) =>
    [...storage.map.keys()].filter((key) =>
      key.startsWith(SKETCH_DRAFT_KEY_PREFIX),
    );
  /** A line entity with a long id: bulk for the byte-budget cases. */
  const bulky = (chars: number): SketchDraftInput =>
    input({ entities: [{ ...LINE, id: "x".repeat(chars) }] });
  const FOREIGN: Record<string, string> = {
    "loft.session.v1": '{"token":"t"}',
    "loft.preferences.v1": '{"unit":"mm"}',
    // Look like ours and are not: another version's prefix, and a key that
    // merely CONTAINS our prefix. Neither may be touched.
    "loft.sketch-draft.v2.part-a": "{}",
    "other-app.loft.sketch-draft.v1.part-a": "{}",
    "someone-else": "x".repeat(4096),
  };
  const seedForeign = (storage: SessionStorageLike) => {
    for (const [key, value] of Object.entries(FOREIGN)) {
      storage.setItem(key, value);
    }
  };
  const expectForeignIntact = (storage: { map: Map<string, string> }) => {
    for (const [key, value] of Object.entries(FOREIGN)) {
      expect(storage.map.get(key), key).toBe(value);
    }
  };

  it("a write removes OTHER parts' expired drafts, not only its own on read", () => {
    const storage = fakeStorage();
    writeSketchDraft("stale-a", input(), storage, 0);
    writeSketchDraft("stale-b", input(), storage, 0);
    writeSketchDraft("fresh", input(), storage, DRAFT_MAX_AGE_MS - DAY);

    writeSketchDraft("today", input(), storage, DRAFT_MAX_AGE_MS + DAY);

    expect(draftKeys(storage).sort()).toEqual(
      [draftKey("fresh"), draftKey("today")].sort(),
    );
  });

  it("caps the count, evicting the OLDEST first", () => {
    const storage = fakeStorage();
    const parts = 50; // the finding's own number
    for (let index = 0; index < parts; index += 1) {
      writeSketchDraft(`part-${index}`, input(), storage, 1_000 + index);
    }
    const kept = draftKeys(storage);
    expect(kept.length).toBeLessThan(parts);
    expect(kept).toHaveLength(MAX_SKETCH_DRAFTS);
    // The newest MAX survive; the ones written first are the ones gone.
    for (let index = 0; index < parts; index += 1) {
      expect(kept.includes(draftKey(`part-${index}`)), `part-${index}`).toBe(
        index >= parts - MAX_SKETCH_DRAFTS,
      );
    }
  });

  it("caps the bytes, oldest first, measured as the quota is (UTF-16)", () => {
    const storage = fakeStorage();
    // Each draft ~0.4 MiB of UTF-16: five of them overrun the 2 MiB budget.
    const chars = Math.floor(MAX_SKETCH_DRAFT_BYTES / 2 / 5) + 1000;
    for (let index = 0; index < 5; index += 1) {
      writeSketchDraft(`big-${index}`, bulky(chars), storage, 1_000 + index);
    }
    const kept = draftKeys(storage);
    const bytes = kept.reduce(
      (sum, key) =>
        sum + (key.length + (storage.map.get(key)?.length ?? 0)) * 2,
      0,
    );
    expect(bytes).toBeLessThanOrEqual(MAX_SKETCH_DRAFT_BYTES);
    expect(kept).not.toContain(draftKey("big-0"));
    expect(kept).toContain(draftKey("big-4"));
    expect(kept.length).toBeGreaterThan(1);
  });

  it("never evicts the live draft to meet a budget it alone exceeds", () => {
    const storage = fakeStorage();
    writeSketchDraft("older", input(), storage, 1_000);
    const huge = bulky(MAX_SKETCH_DRAFT_BYTES); // 2x the budget on its own
    expect(writeSketchDraft("live", huge, storage, 2_000)).toBe(true);
    expect(draftKeys(storage)).toEqual([draftKey("live")]);
  });

  it("sweeps only our prefix: every other key in the origin is untouched", () => {
    const storage = fakeStorage();
    seedForeign(storage);
    writeSketchDraft("stale", input(), storage, 0);
    storage.map.set(draftKey("garbage"), "{not json");
    for (let index = 0; index < MAX_SKETCH_DRAFTS + 3; index += 1) {
      storage.map.set(
        draftKey(`p-${index}`),
        JSON.stringify({ ...input(), version: 1, savedAt: DAY + index }),
      );
    }
    // garbage + stale (expired) + 3 over the count cap.
    expect(sweepSketchDrafts(storage, DRAFT_MAX_AGE_MS + DAY / 2)).toBe(5);
    expectForeignIntact(storage);
    expect(draftKeys(storage)).toHaveLength(MAX_SKETCH_DRAFTS);
  });

  it("app-start sweep: expired and unreadable drafts go, counted", () => {
    const storage = fakeStorage();
    writeSketchDraft("stale", input(), storage, 0);
    writeSketchDraft("fresh", input(), storage, DRAFT_MAX_AGE_MS);
    storage.map.set(draftKey("garbage"), "{not json");
    storage.map.set(draftKey("old-build"), JSON.stringify({ version: 0 }));
    expect(sweepSketchDrafts(storage, DRAFT_MAX_AGE_MS + DAY)).toBe(3);
    expect(draftKeys(storage)).toEqual([draftKey("fresh")]);
  });

  it("is cheap on the write path: one scan per new part, not one per edit", () => {
    const storage = fakeStorage();
    for (let index = 0; index < 10; index += 1) {
      writeSketchDraft(`other-${index}`, input(), storage, 1_000);
    }
    writeSketchDraft("live", input(), storage, 1_000);
    storage.reads = 0;
    for (let edit = 0; edit < 50; edit += 1) {
      writeSketchDraft(
        "live",
        input({ revision: edit }),
        storage,
        1_000 + edit,
      );
    }
    expect(storage.reads).toBe(0);
    // ...but a part the last sweep never saw is a new draft, and is counted.
    writeSketchDraft("another", input(), storage, 1_100);
    expect(storage.reads).toBeGreaterThan(0);
    // ...and a long-lived session re-checks the budget on the interval.
    storage.reads = 0;
    writeSketchDraft("live", input(), storage, 1_100 + DRAFT_SWEEP_INTERVAL_MS);
    expect(storage.reads).toBeGreaterThan(0);
  });

  it("a FULL storage evicts older drafts, oldest first, to keep the live one", () => {
    const storage = fakeStorage(30_000);
    seedForeign(storage);
    for (let index = 0; index < 5; index += 1) {
      expect(
        writeSketchDraft(`old-${index}`, bulky(4_000), storage, index),
      ).toBe(true);
    }
    // Full now: this one only fits if older drafts make way.
    expect(writeSketchDraft("live", bulky(9_000), storage, 100)).toBe(true);
    const kept = draftKeys(storage);
    expect(kept).toContain(draftKey("live"));
    expect(kept).not.toContain(draftKey("old-0"));
    expect(kept).toContain(draftKey("old-4"));
    expectForeignIntact(storage);
  });

  it("reports a write the quota refuses even after evicting every draft", () => {
    const storage = fakeStorage(10_000);
    seedForeign(storage);
    writeSketchDraft("old", input(), storage, 0);
    expect(writeSketchDraft("live", bulky(9_000), storage, 1)).toBe(false);
    expectForeignIntact(storage);
  });

  it("a storage that refuses for any OTHER reason evicts nothing", () => {
    // Switched off (SecurityError) is not cured by deleting someone's work.
    const storage = fakeStorage();
    writeSketchDraft("keep-me", input(), storage, 0);
    const result = writeEvictingDrafts(storage, () => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(result).toMatchObject({ ok: false, evicted: 0 });
    expect(storage.map.has(draftKey("keep-me"))).toBe(true);
  });

  it("reports -1 for a storage it cannot walk, and never throws", () => {
    const blind: SessionStorageLike = {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    };
    expect(sweepSketchDrafts(blind)).toBe(-1);
    expect(() => sweepSketchDrafts(throwingStorage)).not.toThrow();
    const walkThrows: SessionStorageLike = {
      ...throwingStorage,
      get length(): number {
        throw new Error("storage disabled");
      },
      key: () => {
        throw new Error("storage disabled");
      },
    };
    expect(sweepSketchDrafts(walkThrows)).toBe(-1);
    expect(clearAllSketchDrafts(walkThrows)).toBe(-1);
    expect(writeSketchDraft("p", input(), walkThrows)).toBe(false);
  });
});
