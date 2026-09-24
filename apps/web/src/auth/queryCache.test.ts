import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";

import { clearQueriesOnUserChange } from "./queryCache";
import { createSessionStore, type SessionUser } from "./session";
import { nullStorage } from "./storage";

const ALICE: SessionUser = {
  id: "6f2f0e6a-9c1e-4be5-9d3e-6a1c76a3c001",
  email: "alice@example.com",
  created_at: "2026-07-10T12:00:00Z",
};
const BOB: SessionUser = {
  id: "0b0b0b0b-9c1e-4be5-9d3e-6a1c76a3c002",
  email: "bob@example.com",
  created_at: "2026-07-11T12:00:00Z",
};

const ALICES_PARTS = [{ id: "p-1", name: "Alice's bracket" }];

describe("clearQueriesOnUserChange", () => {
  let store: ReturnType<typeof createSessionStore>;
  let queryClient: QueryClient;

  beforeEach(() => {
    store = createSessionStore(nullStorage);
    queryClient = new QueryClient();
    clearQueriesOnUserChange(store, queryClient);
    store.getState().signIn("token-a", ALICE);
    queryClient.setQueryData(["parts"], ALICES_PARTS);
  });

  /** Nothing Alice's session put in the cache can be read any more. */
  function expectEmpty() {
    expect(queryClient.getQueryData(["parts"])).toBeUndefined();
    expect(queryClient.getQueryCache().getAll()).toEqual([]);
  }

  it("keeps the cache across a renewal (same user, new token)", () => {
    store.getState().signIn("token-a2", ALICE);
    expect(queryClient.getQueryData(["parts"])).toEqual(ALICES_PARTS);
  });

  it("clears it when Alice signs in as Bob without signing out first", () => {
    store.getState().signIn("token-b", BOB);
    expectEmpty();
  });

  it("clears it on sign-out, before Bob signs in", () => {
    store.getState().signOut();
    expectEmpty();
    store.getState().signIn("token-b", BOB);
    expectEmpty();
  });

  it("clears it when the session expires", () => {
    store.getState().expire("/parts/p-1");
    expectEmpty();
  });

  it("clears it on the session_mismatch drop (abandon)", () => {
    store.getState().abandon();
    expectEmpty();
  });

  it("stops once unsubscribed", () => {
    const own = new QueryClient();
    const unsubscribe = clearQueriesOnUserChange(store, own);
    own.setQueryData(["parts"], ALICES_PARTS);
    unsubscribe();
    store.getState().signOut();
    expect(own.getQueryData(["parts"])).toEqual(ALICES_PARTS);
  });
});
