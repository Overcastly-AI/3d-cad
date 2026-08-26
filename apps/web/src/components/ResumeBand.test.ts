import { describe, expect, it } from "vitest";

import { resumeTarget } from "./ResumeBand";
import type { PartResponse } from "../api/parts";

/**
 * The branch that decides what the landing surface TELLS a returning user is
 * too load-bearing to verify only by looking at a screenshot: a wrong branch
 * would greet a first-run user with "resume" pointing at a part they have never
 * opened, which is worse than the silence it replaced. `resumeTarget` is pure
 * precisely so it can be pinned here.
 */

const NOW = Date.parse("2026-08-26T12:00:00.000Z");

/** Only the fields `resumeTarget` reads are meaningful; the rest is scaffolding. */
function part(
  name: string,
  createdIso: string,
  updatedIso: string,
): PartResponse {
  return {
    id: `id-${name}`,
    name,
    created_at: createdIso,
    updated_at: updatedIso,
  } as PartResponse;
}

/**
 * A never-edited document's two stamps are written by separate `datetime.now()`
 * calls in one INSERT, so they differ by microseconds rather than being equal —
 * `lib/activity.ts` allows 250 ms for that. A fixture that made them EXACTLY
 * equal would test a case the server never produces, and would pass even if the
 * skew window were deleted.
 */
function stub(name: string, createdIso: string): PartResponse {
  const created = Date.parse(createdIso);
  return part(name, createdIso, new Date(created + 3).toISOString());
}

describe("resumeTarget", () => {
  it("draws nothing for an empty drawer — the empty register owns that screen", () => {
    expect(resumeTarget([], NOW)).toBeNull();
  });

  it("names the most recently EDITED part, not the most recently created", () => {
    const target = resumeTarget(
      [
        // Created last, never touched since: the naive "newest" answer, and the
        // wrong one — you were not working on it.
        stub("Cover panel", "2026-08-26T11:50:00.000Z"),
        part(
          "Spindle housing",
          "2026-08-20T09:00:00.000Z",
          "2026-08-26T11:40:00.000Z",
        ),
        part(
          "Bracket plate",
          "2026-08-19T09:00:00.000Z",
          "2026-08-26T09:00:00.000Z",
        ),
      ],
      NOW,
    );
    expect(target?.part.name).toBe("Spindle housing");
    expect(target?.unstarted).toBe(false);
    expect(target?.age).toBe("20 min ago");
  });

  it("says START HERE, not RESUME, when every part is a named stub", () => {
    const target = resumeTarget(
      [
        stub("Bracket plate", "2026-08-26T10:00:00.000Z"),
        stub("Shim 0.8", "2026-08-26T11:00:00.000Z"),
      ],
      NOW,
    );
    // Falls back to the most recently NAMED one — the last thing the user
    // actually did, which is the closest honest equivalent of "where you were".
    expect(target?.part.name).toBe("Shim 0.8");
    expect(target?.unstarted).toBe(true);
    expect(target?.age).toBeNull();
  });

  it("prefers ONE worked part over any number of newer stubs", () => {
    const target = resumeTarget(
      [
        stub("Shim 0.8", "2026-08-26T11:58:00.000Z"),
        stub("Cover panel", "2026-08-26T11:59:00.000Z"),
        part(
          "Motor mount",
          "2026-08-01T09:00:00.000Z",
          "2026-08-25T12:00:00.000Z",
        ),
      ],
      NOW,
    );
    expect(target?.part.name).toBe("Motor mount");
    expect(target?.unstarted).toBe(false);
    expect(target?.age).toBe("Yesterday");
  });

  it("skips a row whose stamp cannot be read rather than pointing at it", () => {
    const target = resumeTarget(
      [
        part("Corrupt", "not-a-date", "not-a-date"),
        part(
          "Bracket plate",
          "2026-08-20T09:00:00.000Z",
          "2026-08-26T11:00:00.000Z",
        ),
      ],
      NOW,
    );
    expect(target?.part.name).toBe("Bracket plate");
  });

  it("returns null when NO row has a readable stamp — it never guesses", () => {
    expect(
      resumeTarget([part("Corrupt", "not-a-date", "not-a-date")], NOW),
    ).toBeNull();
  });
});
