import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  type BarState,
  EditRollback,
  editRollbackBarId,
  ROLLBACK_EDIT_KINDS,
} from "./editRollback";

function feature(id: string): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-09-30T00:00:00Z",
    updated_at: "2026-09-30T00:00:00Z",
    rolled_back: false,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [],
        constraints: [],
      },
    },
  };
}

/** A fake server: the bar, its version, and every move it was asked for. */
function server(initial: string | null = null) {
  const state = { bar: initial, version: 10 };
  const moves: { bar: string | null; quiet: boolean }[] = [];
  let cacheLags = false;
  let cached: BarState = { ...state };
  let fail = false;
  const rollback = new EditRollback({
    cachedBar: () => cached,
    moveBar: async (bar, expected, quiet) => {
      await Promise.resolve();
      if (fail) throw new Error("rollback refused");
      expect(expected).toBe(state.version);
      state.bar = bar;
      state.version += 1;
      moves.push({ bar, quiet });
      if (!quiet && !cacheLags) cached = { ...state };
      return state.version;
    },
  });
  return {
    rollback,
    state,
    moves,
    lagCache: () => {
      cacheLags = true;
    },
    failNext: (value: boolean) => {
      fail = value;
    },
  };
}

describe("editRollbackBarId", () => {
  const features = ["s", "e", "sh", "f", "c"].map(feature);

  it("is the feature right before the one edited", () => {
    expect(editRollbackBarId(features, "f")).toBe("sh");
    expect(editRollbackBarId(features, "c")).toBe("f");
  });

  it("is undefined for the first feature or an unknown id", () => {
    expect(editRollbackBarId(features, "s")).toBeUndefined();
    expect(editRollbackBarId(features, "nope")).toBeUndefined();
  });

  it("covers the four pick-on-the-input-body editors", () => {
    expect([...ROLLBACK_EDIT_KINDS].sort()).toEqual([
      "chamfer",
      "draft",
      "fillet",
      "shell",
    ]);
  });
});

describe("EditRollback", () => {
  it("rolls back on hold and restores the bar it found on release", async () => {
    const s = server(null);
    await s.rollback.hold("sh");
    expect(s.state.bar).toBe("sh");
    expect(s.rollback.held).toBe(true);
    await s.rollback.release();
    expect(s.state.bar).toBeNull();
    expect(s.rollback.held).toBe(false);
    expect(s.moves).toEqual([
      { bar: "sh", quiet: false },
      { bar: null, quiet: false },
    ]);
  });

  it("restores a bar the user had already rolled back", async () => {
    const s = server("e");
    await s.rollback.hold("f");
    await s.rollback.release();
    expect(s.state.bar).toBe("e");
  });

  it("does not move a bar that is already where it should be", async () => {
    const s = server("sh");
    expect(await s.rollback.hold("sh")).toBeNull();
    expect(await s.rollback.release()).toBeNull();
    expect(s.moves).toEqual([]);
  });

  it("switching edits keeps the bar the FIRST edit found", async () => {
    const s = server(null);
    void s.rollback.hold("sh");
    void s.rollback.hold("f");
    await s.rollback.release();
    expect(s.state.bar).toBeNull();
  });

  it("a Cancel and an immediate Edit, both queued, still restore the tip", async () => {
    const s = server(null);
    void s.rollback.hold("sh");
    void s.rollback.release();
    // The cache still says `sh` or null depending on timing; the queue knows.
    void s.rollback.hold("f");
    await s.rollback.release();
    expect(s.state.bar).toBeNull();
    expect(s.moves.map((m) => m.bar)).toEqual(["sh", null, "f", null]);
  });

  it("a quiet release before a save can be taken back after a failed save", async () => {
    const s = server(null);
    s.lagCache();
    await s.rollback.hold("sh");
    // The cache lags (no refetch yet); the controller trusts its own move.
    expect(await s.rollback.release(true)).toBe(12);
    expect(s.state.bar).toBeNull();
    await s.rollback.reacquire();
    expect(s.state.bar).toBe("sh");
    await s.rollback.release();
    expect(s.state.bar).toBeNull();
  });

  it("forget leaves the bar where the user put it", async () => {
    const s = server(null);
    await s.rollback.hold("sh");
    s.rollback.forget();
    expect(await s.rollback.release()).toBeNull();
    expect(s.state.bar).toBe("sh");
  });

  it("a failed move rejects its caller but does not strand the queue", async () => {
    const s = server(null);
    s.failNext(true);
    await expect(s.rollback.hold("sh")).rejects.toThrow("rollback refused");
    s.failNext(false);
    await s.rollback.hold("f");
    expect(s.state.bar).toBe("f");
  });
});
