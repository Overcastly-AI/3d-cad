import type { Locator } from "@playwright/test";

import type { Page } from "./fixtures";
import { waitForFrames } from "./support";

/**
 * The viewport's hover stamps (`data-*-pick-hover`) and the two ways to read
 * one honestly: wait for a goal on animation frames, or settle until two reads
 * agree across a rendered frame. Shared by the pick-affordance oracles.
 */

export type StampGoal =
  | { kind: "absent" }
  | { kind: "present" }
  | { kind: "is"; value: string }
  | { kind: "not"; value: string };

/**
 * How long a parked oracle waits for the transition it parked for.
 *
 * Not a frame budget — a settle-tolerant ceiling, so a slower runner cannot
 * re-break it. Measured transition time with rAF polling on this build: p50
 * 206 ms, p90 229 ms, max 279 ms (the floor is the ~5 fps software-GL frame,
 * not React). 5 s is ~18x the p90 and matches the timeout every other wait in
 * this file already uses. It is only ever SPENT when a claim is about to fail.
 */
export const ORACLE_TIMEOUT_MS = 5_000;

/** Wait, polling on animation frames, for the viewport stamp to reach `goal`. */
export async function stampSettles(
  page: Page,
  attribute: string,
  goal: StampGoal,
  timeout = ORACLE_TIMEOUT_MS,
): Promise<boolean> {
  return page
    .waitForFunction(
      (input: { attribute: string; goal: StampGoal }) => {
        const value =
          document
            .querySelector('[data-testid="viewport"]')
            ?.getAttribute(input.attribute) ?? null;
        if (input.goal.kind === "absent") return value === null;
        if (input.goal.kind === "present") return value !== null;
        if (input.goal.kind === "is") return value === input.goal.value;
        return value !== input.goal.value;
      },
      { attribute, goal },
      { timeout, polling: "raf" },
    )
    .then(
      () => true,
      () => false,
    );
}

/**
 * The stamp once the pointer's last move has landed: two reads that agree
 * across a rendered frame, up to 5 rounds. The stamp is written by a passive
 * effect a commit after the r3f handler sets hover, so a bare read straight
 * after `page.mouse.move` can still hold the PREVIOUS position's answer.
 */
export async function settledStamp(
  page: Page,
  viewport: Locator,
  attribute: string,
): Promise<string | null> {
  let last = await viewport.getAttribute(attribute);
  for (let round = 0; round < 5; round += 1) {
    await waitForFrames(page, 1);
    const next = await viewport.getAttribute(attribute);
    if (next === last) return next;
    last = next;
  }
  return last;
}
