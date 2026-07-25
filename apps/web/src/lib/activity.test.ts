import { describe, expect, it } from "vitest";

import { documentActivity, relativeAge } from "./activity";

const T0 = Date.parse("2026-07-25T12:00:00.000Z");
const iso = (offsetMs: number) => new Date(T0 + offsetMs).toISOString();

describe("relativeAge", () => {
  it("uses coarse buckets a person reads at a glance", () => {
    expect(relativeAge(0)).toBe("just now");
    expect(relativeAge(44_000)).toBe("just now");
    expect(relativeAge(46_000)).toBe("1 min ago");
    expect(relativeAge(20 * 60_000)).toBe("20 min ago");
    expect(relativeAge(90 * 60_000)).toBe("1 h ago");
    expect(relativeAge(23 * 3_600_000)).toBe("23 h ago");
    expect(relativeAge(30 * 3_600_000)).toBe("Yesterday");
    expect(relativeAge(3 * 86_400_000)).toBe("3 d ago");
  });

  it("gives up past a week — a date names it better than a day count", () => {
    expect(relativeAge(8 * 86_400_000)).toBeNull();
  });
});

describe("documentActivity", () => {
  it("reads a never-edited document as unstarted", () => {
    // Both stamps are written by separate now() calls in one INSERT, so they
    // differ by microseconds — that must NOT read as an edit.
    expect(documentActivity(iso(0), iso(3), "2026-07-25", T0)).toEqual({
      kind: "never",
    });
    expect(documentActivity(iso(0), iso(0), "2026-07-25", T0)).toEqual({
      kind: "never",
    });
  });

  it("reads an edit just past the insert-skew window as a real edit", () => {
    expect(
      documentActivity(iso(-60_000), iso(-59_000), "2026-07-25", T0),
    ).toMatchObject({ kind: "worked" });
  });

  it("reads a real edit as worked, with its relative age", () => {
    const created = iso(-5 * 86_400_000);
    expect(
      documentActivity(created, iso(-20 * 60_000), "2026-07-25", T0),
    ).toEqual({ kind: "worked", label: "20 min ago" });
  });

  it("falls back to the absolute date for an edit older than a week", () => {
    const created = iso(-60 * 86_400_000);
    expect(
      documentActivity(created, iso(-30 * 86_400_000), "2026-06-25", T0),
    ).toEqual({ kind: "worked", label: "2026-06-25" });
  });

  it("clamps a future stamp instead of printing a negative age", () => {
    const created = iso(-86_400_000);
    expect(documentActivity(created, iso(5_000), "2026-07-25", T0)).toEqual({
      kind: "worked",
      label: "just now",
    });
  });

  it("says nothing for an unreadable stamp rather than guessing", () => {
    expect(documentActivity("nonsense", iso(0), "—", T0)).toEqual({
      kind: "unknown",
    });
    expect(documentActivity(iso(0), "nonsense", "—", T0)).toEqual({
      kind: "unknown",
    });
  });
});
