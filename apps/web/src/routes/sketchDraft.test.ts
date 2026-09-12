import { describe, expect, it } from "vitest";

import type { SessionStorageLike } from "../auth/session";
import type { SketchEntity } from "../sketch/tools";
import {
  clearSketchDraft,
  DRAFT_MAX_AGE_MS,
  draftAge,
  draftKey,
  readSketchDraft,
  writeSketchDraft,
  type SketchDraftInput,
} from "./sketchDraft";

/** An in-memory stand-in for localStorage, plus a throwing variant. */
function fakeStorage(): SessionStorageLike & { map: Map<string, string> } {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => void map.set(key, value),
    removeItem: (key) => void map.delete(key),
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
