import { describe, expect, it, vi } from "vitest";

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
