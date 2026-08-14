import { describe, expect, it } from "vitest";

import { BUILD_SHA, BUILD_TIME, buildLabel } from "./build";

/*
 * These run WITHOUT vite's `define`, so they exercise the fallback path — which
 * is the one that matters. A build stamp that silently reports a stale or empty
 * value is worse than none: the whole point (FB-11) is answering "which build
 * is this?" for a founder testing from a Codespace, and a confident wrong
 * answer sends both sides chasing a fix that is or is not present.
 */
describe("the build stamp degrades honestly", () => {
  it("says 'unknown' rather than undefined when nothing was injected", () => {
    expect(BUILD_SHA).toBe("unknown");
    expect(buildLabel()).toContain("unknown");
  });

  it("never renders the literal string undefined or null", () => {
    // The failure a user would actually see and report as a bug.
    expect(buildLabel()).not.toMatch(/undefined|null|NaN/);
  });

  it("falls back to the sha alone when the time is absent or unparseable", () => {
    expect(BUILD_TIME).toBe("");
    expect(buildLabel()).toBe(BUILD_SHA);
  });
});
