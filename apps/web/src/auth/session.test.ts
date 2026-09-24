import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createSessionStore,
  probeSessionPersistence,
  SESSION_NOT_PERSISTED_MESSAGE,
  SESSION_STORAGE_KEY,
  SIGN_IN_WILL_NOT_PERSIST_MESSAGE,
  type SessionStorageLike,
  type SessionUser,
} from "./session";
import {
  DRAFT_MAX_AGE_MS,
  SKETCH_DRAFT_KEY_PREFIX,
} from "../routes/sketchDraft";

const USER: SessionUser = {
  id: "6f2f0e6a-9c1e-4be5-9d3e-6a1c76a3c001",
  email: "alice@example.com",
  created_at: "2026-07-10T12:00:00Z",
};

function fakeStorage(
  initial: Record<string, string> = {},
  quotaChars = Number.POSITIVE_INFINITY,
) {
  const map = new Map(Object.entries(initial));
  const used = () =>
    [...map].reduce((sum, [key, value]) => sum + key.length + value.length, 0);
  const storage: SessionStorageLike = {
    getItem: (key) => map.get(key) ?? null,
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
    // Enumerable, like the real `Storage`: the sign-out purge below has to find
    // keys whose names it does not know.
    get length() {
      return map.size;
    },
    key: (index) => [...map.keys()][index] ?? null,
  };
  return { storage, map };
}

/** A draft key for *partId*, spelled as `sketchDraft.ts` spells it. */
function draftKeyFor(partId: string): string {
  return `${SKETCH_DRAFT_KEY_PREFIX}${partId}`;
}

describe("createSessionStore", () => {
  it("starts signed out with empty storage", () => {
    const { storage } = fakeStorage();
    const store = createSessionStore(storage);
    expect(store.getState().token).toBeNull();
    expect(store.getState().user).toBeNull();
    expect(store.getState().expired).toBe(false);
  });

  it("hydrates a persisted session on creation", () => {
    const { storage } = fakeStorage({
      [SESSION_STORAGE_KEY]: JSON.stringify({ token: "tok-1", user: USER }),
    });
    const store = createSessionStore(storage);
    expect(store.getState().token).toBe("tok-1");
    expect(store.getState().user).toEqual(USER);
  });

  it.each([
    ["corrupt JSON", "{not json"],
    ["missing token", JSON.stringify({ user: USER })],
    ["malformed user", JSON.stringify({ token: "t", user: { id: 7 } })],
    ["non-object", JSON.stringify("nope")],
  ])("treats %s in storage as signed out", (_name, raw) => {
    const { storage } = fakeStorage({ [SESSION_STORAGE_KEY]: raw });
    const store = createSessionStore(storage);
    expect(store.getState().token).toBeNull();
    expect(store.getState().user).toBeNull();
  });

  it("signIn stores the session and persists it", () => {
    const { storage, map } = fakeStorage();
    const store = createSessionStore(storage);
    store.getState().signIn("tok-2", USER);
    expect(store.getState().token).toBe("tok-2");
    expect(store.getState().user).toEqual(USER);
    expect(JSON.parse(map.get(SESSION_STORAGE_KEY) ?? "")).toEqual({
      token: "tok-2",
      user: USER,
    });
  });

  it("signOut clears the session and storage without the expired notice", () => {
    const { storage, map } = fakeStorage();
    const store = createSessionStore(storage);
    store.getState().signIn("tok-3", USER);
    store.getState().signOut();
    expect(store.getState().token).toBeNull();
    expect(store.getState().expired).toBe(false);
    expect(map.has(SESSION_STORAGE_KEY)).toBe(false);
  });

  it("expire clears the session and flags the quiet notice", () => {
    const { storage, map } = fakeStorage();
    const store = createSessionStore(storage);
    store.getState().signIn("tok-4", USER);
    store.getState().expire();
    expect(store.getState().token).toBeNull();
    expect(store.getState().user).toBeNull();
    expect(store.getState().expired).toBe(true);
    expect(map.has(SESSION_STORAGE_KEY)).toBe(false);
  });

  it("signOut takes the session's unsaved sketches with it (W0 finding 4)", () => {
    // Before: `signOut` removed the token alone, so on a shared browser the
    // next person to open that part id had the previous user's geometry
    // restored into their session — and could save it into the part under their
    // own name. The drafts are keyed on the PART, never on the person, so
    // deleting them is what ends the exposure.
    const { storage, map } = fakeStorage();
    const store = createSessionStore(storage);
    store.getState().signIn("tok-7", USER);
    map.set(draftKeyFor("part-a"), '{"version":1}');
    map.set(draftKeyFor("part-b"), '{"version":1}');
    map.set("loft.preferences.v1", '{"unit":"mm"}');

    store.getState().signOut();

    expect(map.has(draftKeyFor("part-a"))).toBe(false);
    expect(map.has(draftKeyFor("part-b"))).toBe(false);
    // Scoped: a purge that emptied storage would pass the two lines above.
    expect(map.get("loft.preferences.v1")).toBe('{"unit":"mm"}');
  });

  it("an expired token takes them too — the other way a browser changes hands", () => {
    const { storage, map } = fakeStorage();
    const store = createSessionStore(storage);
    store.getState().signIn("tok-8", USER);
    map.set(draftKeyFor("part-c"), '{"version":1}');
    store.getState().expire();
    expect(map.has(draftKeyFor("part-c"))).toBe(false);
  });

  it("a later signIn clears the expired notice", () => {
    const { storage } = fakeStorage();
    const store = createSessionStore(storage);
    store.getState().expire();
    expect(store.getState().expired).toBe(true);
    store.getState().signIn("tok-5", USER);
    expect(store.getState().expired).toBe(false);
  });

  it("survives a storage that throws (private mode, quota)", () => {
    const throwing: SessionStorageLike = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    };
    const store = createSessionStore(throwing);
    expect(store.getState().token).toBeNull();
    store.getState().signIn("tok-6", USER); // must not throw
    expect(store.getState().token).toBe("tok-6");
    // ...but not silently: the reload that loses it is announced now.
    expect(store.getState().persistError).toBe(SESSION_NOT_PERSISTED_MESSAGE);
    store.getState().signOut(); // must not throw
    expect(store.getState().token).toBeNull();
    expect(store.getState().persistError).toBeNull();
  });
});

/**
 * W0REV-3 — a quota full of sketch drafts made the session write fail, the
 * failure was swallowed, and the user met it as "logged out on reload" with
 * nothing pointing here.
 */
describe("session persistence under a full storage (W0REV-3)", () => {
  const NOW = 1_800_000_000_000;
  /** A readable draft, *chars* long, written *ageMs* before NOW. */
  const draft = (chars: number, ageMs: number) =>
    JSON.stringify({
      version: 1,
      savedAt: NOW - ageMs,
      plane: { kind: "origin", base: "XY" },
      entities: [{ kind: "point", id: "x".repeat(chars) }],
      constraints: [],
      featureId: null,
      nextIdIndex: 2,
      revision: 1,
      userConstrained: false,
    });

  let errorSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    errorSpy.mockRestore();
  });

  it("QuotaExceededError on the session write evicts drafts, oldest first, and the session survives a reload", () => {
    const { storage, map } = fakeStorage({}, 12_000);
    const store = createSessionStore(storage, NOW);
    // The storage fills AFTER app start (the start-up sweep only trims to the
    // budget; it never guarantees room) — three fresh drafts and a neighbour.
    map.set(draftKeyFor("oldest"), draft(3_900, 3_000));
    map.set(draftKeyFor("middle"), draft(3_900, 2_000));
    map.set(draftKeyFor("newest"), draft(3_900, 1_000));
    map.set("loft.preferences.v1", '{"unit":"mm"}');

    store.getState().signIn("tok-q", USER);

    // The reload: a fresh store over the same storage is still signed in.
    const reloaded = createSessionStore(storage, NOW);
    expect(reloaded.getState().token).toBe("tok-q");
    expect(reloaded.getState().user).toEqual(USER);
    expect(store.getState().persistError).toBeNull();
    // Only as much as it needed, and oldest first.
    expect(map.has(draftKeyFor("oldest"))).toBe(false);
    expect(map.has(draftKeyFor("newest"))).toBe(true);
    expect(map.get("loft.preferences.v1")).toBe('{"unit":"mm"}');
  });

  it("a write that STILL fails is surfaced, never swallowed, and touches nothing it does not own", () => {
    // Full of someone else's data: evicting every draft cannot make room.
    const { storage, map } = fakeStorage(
      { "another-app": "y".repeat(9_900) },
      10_000,
    );
    const store = createSessionStore(storage, NOW);
    store.getState().signIn("tok-r", USER);

    expect(store.getState().token).toBe("tok-r"); // works until reload
    expect(store.getState().persistError).toBe(SESSION_NOT_PERSISTED_MESSAGE);
    expect(errorSpy).toHaveBeenCalled();
    expect(map.has(SESSION_STORAGE_KEY)).toBe(false);
    expect(map.get("another-app")).toBe("y".repeat(9_900));
  });

  it("the notice is dismissible, and a later successful sign-in clears it too", () => {
    const { storage, map } = fakeStorage(
      { "another-app": "y".repeat(9_900) },
      10_000,
    );
    const store = createSessionStore(storage, NOW);
    store.getState().signIn("tok-d", USER);
    expect(store.getState().persistError).toBe(SESSION_NOT_PERSISTED_MESSAGE);
    store.getState().dismissPersistError();
    expect(store.getState().persistError).toBeNull();
    expect(store.getState().token).toBe("tok-d"); // dismissing is not signing out

    store.getState().signIn("tok-e", USER);
    expect(store.getState().persistError).toBe(SESSION_NOT_PERSISTED_MESSAGE);
    map.delete("another-app"); // the user freed some storage
    store.getState().signIn("tok-f", USER);
    expect(store.getState().persistError).toBeNull();
  });

  it("the sign-in probe answers the way sign-in will, and leaves no trace", () => {
    // Full of someone else's data: no amount of draft eviction helps.
    const full = fakeStorage({ "another-app": "y".repeat(9_900) }, 10_000);
    expect(probeSessionPersistence(full.storage)).toBe(
      SIGN_IN_WILL_NOT_PERSIST_MESSAGE,
    );
    expect([...full.map.keys()]).toEqual(["another-app"]);

    // Full of drafts: the probe makes the room sign-in would have made.
    const drafts = fakeStorage({}, 9_000);
    drafts.map.set(draftKeyFor("old"), draft(4_000, 2_000));
    drafts.map.set(draftKeyFor("new"), draft(4_000, 1_000));
    expect(probeSessionPersistence(drafts.storage)).toBeNull();
    expect(drafts.map.has(draftKeyFor("old"))).toBe(false);
    expect(drafts.map.has(draftKeyFor("new"))).toBe(true);
    expect([...drafts.map.keys()].some((key) => key.endsWith(".probe"))).toBe(
      false,
    );

    // Private mode / blocked storage: a warning, never an exception.
    const blocked: SessionStorageLike = {
      getItem: () => null,
      setItem: () => {
        throw new DOMException("denied", "SecurityError");
      },
      removeItem: () => {
        throw new DOMException("denied", "SecurityError");
      },
    };
    expect(probeSessionPersistence(blocked)).toBe(
      SIGN_IN_WILL_NOT_PERSIST_MESSAGE,
    );
  });

  it("a non-quota refusal (storage switched off) evicts no drafts", () => {
    const { storage, map } = fakeStorage();
    map.set(draftKeyFor("keep-me"), draft(10, 0));
    const blocked: SessionStorageLike = {
      ...storage,
      get length() {
        return storage.length;
      },
      key: storage.key,
      setItem: () => {
        throw new DOMException("denied", "SecurityError");
      },
    };
    const store = createSessionStore(blocked, NOW);
    store.getState().signIn("tok-s", USER);
    expect(store.getState().persistError).toBe(SESSION_NOT_PERSISTED_MESSAGE);
    expect(map.has(draftKeyFor("keep-me"))).toBe(true);
  });

  it("app start sweeps expired drafts before anything needs the room", () => {
    const { storage, map } = fakeStorage({
      [draftKeyFor("stale")]: draft(10, DRAFT_MAX_AGE_MS + 1),
      [draftKeyFor("fresh")]: draft(10, 1_000),
      "loft.preferences.v1": '{"unit":"mm"}',
    });
    createSessionStore(storage, NOW);
    expect(map.has(draftKeyFor("stale"))).toBe(false);
    expect(map.has(draftKeyFor("fresh"))).toBe(true);
    expect(map.get("loft.preferences.v1")).toBe('{"unit":"mm"}');
  });
});
