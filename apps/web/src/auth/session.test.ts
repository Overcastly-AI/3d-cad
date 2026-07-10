import { describe, expect, it } from "vitest";

import {
  createSessionStore,
  SESSION_STORAGE_KEY,
  type SessionStorageLike,
  type SessionUser,
} from "./session";

const USER: SessionUser = {
  id: "6f2f0e6a-9c1e-4be5-9d3e-6a1c76a3c001",
  email: "alice@example.com",
  created_at: "2026-07-10T12:00:00Z",
};

function fakeStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial));
  const storage: SessionStorageLike = {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => void map.set(key, value),
    removeItem: (key) => void map.delete(key),
  };
  return { storage, map };
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
    store.getState().signOut(); // must not throw
    expect(store.getState().token).toBeNull();
  });
});
