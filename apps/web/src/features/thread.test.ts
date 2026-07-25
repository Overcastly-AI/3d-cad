import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  boreFitsThread,
  coarsePitchFor,
  formatDesignation,
  ISO_METRIC_PITCHES,
  isSupportedDesignation,
  minorDiameterMm,
  pitchesFor,
  tapDrillMm,
  THREAD_NOMINALS,
} from "./thread";

/**
 * The kernel module the client table mirrors. The path is deliberate: if the
 * kernel module moves, this test fails loudly rather than silently stopping
 * guarding anything.
 */
const KERNEL_THREADS = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../services/geometry/src/geometry/kernel/threads.py",
);

/** Parse `ISO_METRIC_PITCHES` out of the kernel module — the source of truth. */
function kernelTable(source: string): Record<string, number[]> {
  const start = source.indexOf("ISO_METRIC_PITCHES");
  expect(start, "kernel ISO_METRIC_PITCHES table not found").toBeGreaterThan(
    -1,
  );
  const open = source.indexOf("{", start);
  const close = source.indexOf("\n}", open);
  const body = source.slice(open + 1, close);
  const table: Record<string, number[]> = {};
  for (const line of body.split("\n")) {
    const match = /^\s*([\d.]+):\s*\(([^)]*)\),?\s*$/.exec(line);
    if (match === null) continue;
    const [, nominal, pitches] = match;
    table[String(Number(nominal))] = (pitches as string)
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p !== "")
      .map(Number);
  }
  return table;
}

describe("ISO_METRIC_PITCHES mirrors the kernel table", () => {
  const source = readFileSync(KERNEL_THREADS, "utf8");

  it("is identical to geometry.kernel.threads.ISO_METRIC_PITCHES", () => {
    const kernel = kernelTable(source);
    // A non-empty parse is part of the assertion: a regex that silently matched
    // nothing would make the equality below vacuously true.
    expect(Object.keys(kernel).length).toBeGreaterThan(20);
    expect(ISO_METRIC_PITCHES).toEqual(kernel);
  });

  it("derives the minor diameter from the kernel's own expression", () => {
    // The accepted-bore band's floor. If the kernel ever rounds this to 1.0825
    // (or changes it), the client band would silently disagree with the server.
    expect(source).toContain("1.25 * math.sqrt(3.0) / 2.0");
    expect(minorDiameterMm(10, 1.5)).toBeCloseTo(10 - 1.0825 * 1.5, 4);
  });

  it("uses the kernel's designation tolerance", () => {
    expect(source).toContain("_DESIGNATION_TOL = 1e-9");
  });
});

describe("THREAD_NOMINALS", () => {
  it("is the series ascending, M1.6 through M64", () => {
    expect(THREAD_NOMINALS[0]).toBe(1.6);
    expect(THREAD_NOMINALS[THREAD_NOMINALS.length - 1]).toBe(64);
    const sorted = [...THREAD_NOMINALS].sort((a, b) => a - b);
    expect(THREAD_NOMINALS).toEqual(sorted);
  });
});

describe("formatDesignation", () => {
  it("spells the pitch out with an ASCII x (the kernel's notation)", () => {
    expect(formatDesignation(10, 1.5)).toBe("M10x1.5");
    expect(formatDesignation(6, 1)).toBe("M6x1");
    expect(formatDesignation(3, 0.5)).toBe("M3x0.5");
    expect(formatDesignation(1.6, 0.35)).toBe("M1.6x0.35");
  });

  it("distinguishes a coarse from a fine thread of the same size", () => {
    expect(formatDesignation(10, 1.5)).not.toBe(formatDesignation(10, 1.25));
  });
});

describe("pitchesFor / coarsePitchFor / isSupportedDesignation", () => {
  it("offers a size's standard pitches, coarse first", () => {
    expect(pitchesFor(10)).toEqual([1.5, 1.25, 1, 0.75]);
    expect(coarsePitchFor(10)).toBe(1.5);
    expect(coarsePitchFor(8)).toBe(1.25);
  });

  it("has nothing for a size off the series", () => {
    expect(pitchesFor(7)).toEqual([]);
    expect(coarsePitchFor(7)).toBeNull();
    expect(isSupportedDesignation(7, 1)).toBe(false);
  });

  it("rejects a pitch that is not standard for that size", () => {
    expect(isSupportedDesignation(10, 1.5)).toBe(true);
    expect(isSupportedDesignation(10, 1.75)).toBe(false);
  });
});

describe("tapDrillMm", () => {
  it("matches the published metric tap-drill tables", () => {
    // The kernel cross-checks these same values (geometry test_hole.py).
    expect(tapDrillMm(3, 0.5)).toBeCloseTo(2.5, 10);
    expect(tapDrillMm(4, 0.7)).toBeCloseTo(3.3, 10);
    expect(tapDrillMm(5, 0.8)).toBeCloseTo(4.2, 10);
    expect(tapDrillMm(6, 1)).toBeCloseTo(5.0, 10);
    expect(tapDrillMm(8, 1.25)).toBeCloseTo(6.75, 10);
    expect(tapDrillMm(10, 1.5)).toBeCloseTo(8.5, 10);
    expect(tapDrillMm(12, 1.75)).toBeCloseTo(10.25, 10);
  });
});

describe("boreFitsThread", () => {
  it("accepts the ISO tap drill", () => {
    expect(boreFitsThread(10, 1.5, 8.5)).toBe(true);
    expect(boreFitsThread(6, 1, 5)).toBe(true);
  });

  it("accepts a shop table's rounded stock drill", () => {
    // 6.8 for M8x1.25, where D - P is 6.75 — the whole reason the bore stays
    // editable instead of being locked to the derived value.
    expect(boreFitsThread(8, 1.25, 6.8)).toBe(true);
  });

  it("rejects a bore below the minor diameter (the tap cannot enter)", () => {
    expect(minorDiameterMm(8, 1.25)).toBeCloseTo(6.6468, 3);
    expect(boreFitsThread(8, 1.25, 6.5)).toBe(false);
  });

  it("rejects a bore at or above the nominal (no material left to cut)", () => {
    expect(boreFitsThread(10, 1.5, 10)).toBe(false);
    expect(boreFitsThread(10, 1.5, 12)).toBe(false);
  });
});
