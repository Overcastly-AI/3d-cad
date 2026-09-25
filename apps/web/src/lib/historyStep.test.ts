import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { clearQueriesOnUserChange } from "../auth/queryCache";
import { createSessionStore, type SessionUser } from "../auth/session";
import { nullStorage } from "../auth/storage";

import {
  executeHistoryStep,
  HISTORY_STEP_FALLBACK,
  type HistoryStepPorts,
} from "./historyStep";

interface Doc {
  version: number;
}

/** Ports whose every seam is a spy; override per test. */
function ports(overrides: Partial<HistoryStepPorts<Doc>> = {}) {
  const base: HistoryStepPorts<Doc> = {
    version: () => 4,
    run: vi.fn(() => Promise.resolve({ version: 5 })),
    versionOf: (doc) => doc.version,
    adoptNoOp: vi.fn(),
    onRestored: vi.fn(),
    isStale: () => false,
    resync: vi.fn(),
    owner: () => "alice",
  };
  return { ...base, ...overrides };
}

describe("executeHistoryStep", () => {
  it("passes the step and the awaited fresh version to run", async () => {
    const run = vi.fn(() => Promise.resolve({ version: 8 }));
    // Async version source (the part page refetches when the cache is cold).
    const p = ports({ version: () => Promise.resolve(7), run });
    await expect(executeHistoryStep("redo", p)).resolves.toEqual({
      kind: "restored",
    });
    expect(run).toHaveBeenCalledWith("redo", 7);
  });

  it("a version-changed response is a real restore: hygiene, never adopt", async () => {
    const p = ports();
    await expect(executeHistoryStep("undo", p)).resolves.toEqual({
      kind: "restored",
    });
    expect(p.onRestored).toHaveBeenCalledWith({ version: 5 });
    expect(p.adoptNoOp).not.toHaveBeenCalled();
    expect(p.resync).not.toHaveBeenCalled();
  });

  it("boundary no-op (version unchanged): adopt the echo, no restore hygiene", async () => {
    const p = ports({ run: vi.fn(() => Promise.resolve({ version: 4 })) });
    await expect(executeHistoryStep("undo", p)).resolves.toEqual({
      kind: "noop",
    });
    expect(p.adoptNoOp).toHaveBeenCalledWith({ version: 4 });
    expect(p.onRestored).not.toHaveBeenCalled();
  });

  it("a typed stale error resyncs quietly", async () => {
    const stale = new Error("moved on");
    const p = ports({
      run: vi.fn(() => Promise.reject(stale)),
      isStale: (error) => error === stale,
    });
    await expect(executeHistoryStep("undo", p)).resolves.toEqual({
      kind: "stale",
    });
    expect(p.resync).toHaveBeenCalledTimes(1);
    expect(p.onRestored).not.toHaveBeenCalled();
    expect(p.adoptNoOp).not.toHaveBeenCalled();
  });

  it("a non-stale failure surfaces its own message", async () => {
    const p = ports({
      run: vi.fn(() => Promise.reject(new Error("gateway exploded"))),
    });
    await expect(executeHistoryStep("redo", p)).resolves.toEqual({
      kind: "failed",
      message: "gateway exploded",
    });
    expect(p.resync).not.toHaveBeenCalled();
  });

  it("a messageless / non-Error failure falls back per step", async () => {
    await expect(
      executeHistoryStep(
        "undo",
        ports({ run: vi.fn(() => Promise.reject(new Error(""))) }),
      ),
    ).resolves.toEqual({ kind: "failed", message: HISTORY_STEP_FALLBACK.undo });
    await expect(
      executeHistoryStep(
        "redo",
        // A non-Error rejection is the case under test.
        ports({ run: vi.fn(() => Promise.reject("boom" as unknown as Error)) }),
      ),
    ).resolves.toEqual({ kind: "failed", message: HISTORY_STEP_FALLBACK.redo });
  });

  it("a restore-hygiene failure is reported, not swallowed", async () => {
    const p = ports({
      onRestored: vi.fn(() => Promise.reject(new Error("refresh failed"))),
    });
    await expect(executeHistoryStep("undo", p)).resolves.toEqual({
      kind: "failed",
      message: "refresh failed",
    });
  });
});

/**
 * A STEP THAT RESOLVES FOR SOMEONE ELSE WRITES NOTHING
 * (UNDO-REDO-USER-SWITCH-RACE-1).
 *
 * `clearQueriesOnUserChange` empties the cache the moment the signed-in user
 * changes (`f0c2bbc`). An undo that was already in flight resolved after that,
 * and its no-op path put the PREVIOUS user's tree back into the cache the next
 * user now reads from. The step belongs to whoever started it; when that is no
 * longer who is signed in, its result is dropped: no adopt, no restore, no
 * resync.
 */
describe("a step that outlives its user", () => {
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
  const KEY = ["features", "p-1"];

  /** The real session store and cache, wired as the app wires them. */
  function signedInAsAlice() {
    const store = createSessionStore(nullStorage);
    const queryClient = new QueryClient();
    clearQueriesOnUserChange(store, queryClient);
    store.getState().signIn("token-a", ALICE);
    let resolve: (doc: Doc) => void = () => {};
    const run = vi.fn(
      () =>
        new Promise<Doc>((r) => {
          resolve = r;
        }),
    );
    const p = ports({
      run,
      owner: () => store.getState().user?.id ?? null,
      adoptNoOp: vi.fn((doc: Doc) => queryClient.setQueryData(KEY, doc)),
    });
    return { store, queryClient, p, resolve: (doc: Doc) => resolve(doc) };
  }

  it("drops a no-op that resolves after the user changed", async () => {
    const { store, queryClient, p, resolve } = signedInAsAlice();
    const pending = executeHistoryStep("undo", p);
    await vi.waitFor(() => expect(p.run).toHaveBeenCalled());
    store.getState().signIn("token-b", BOB);
    resolve({ version: 4 });
    await expect(pending).resolves.toEqual({ kind: "abandoned" });
    expect(p.adoptNoOp).not.toHaveBeenCalled();
    expect(queryClient.getQueryData(KEY)).toBeUndefined();
  });

  it("drops a restore, and its resync, the same way", async () => {
    const { store, p, resolve } = signedInAsAlice();
    const pending = executeHistoryStep("redo", p);
    await vi.waitFor(() => expect(p.run).toHaveBeenCalled());
    store.getState().signOut();
    resolve({ version: 5 });
    await expect(pending).resolves.toEqual({ kind: "abandoned" });
    expect(p.onRestored).not.toHaveBeenCalled();
    expect(p.resync).not.toHaveBeenCalled();
  });

  it("adopts as before while the same user is signed in", async () => {
    // The negative control: a renewal keeps the id, and so keeps the step.
    const { store, queryClient, p, resolve } = signedInAsAlice();
    const pending = executeHistoryStep("undo", p);
    await vi.waitFor(() => expect(p.run).toHaveBeenCalled());
    store.getState().signIn("token-a2", ALICE);
    resolve({ version: 4 });
    await expect(pending).resolves.toEqual({ kind: "noop" });
    expect(queryClient.getQueryData(KEY)).toEqual({ version: 4 });
  });
});
