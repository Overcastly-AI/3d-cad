import { beforeEach, describe, expect, it } from "vitest";

import {
  beginHand,
  handUnderway,
  instrumentsMounted,
  mountInstrument,
  releaseHand,
  resetInstruments,
  unmountInstrument,
} from "./instruments";

/**
 * The two ways a boolean would have been wrong, for each counter. Neither
 * failure has a symptom of its own in the running app — the consequence is that
 * the preview re-fit silently stops happening, or happens under a live hand,
 * i.e. the ABSENCE or the MIS-TIMING of a behaviour rather than an error.
 * That is the hardest kind of defect to notice, which is why it is pinned here.
 */
describe("instruments", () => {
  beforeEach(() => resetInstruments());

  it("reports nothing mounted and no hand at rest", () => {
    expect(instrumentsMounted()).toBe(false);
    expect(handUnderway()).toBe(false);
  });

  it("stays mounted while a SECOND instrument is still on screen", () => {
    // The hole verb mounts depth and Ø together; the pattern layer mounts a
    // count and a spacing. A flag lets the first to leave speak for both.
    mountInstrument();
    mountInstrument();
    unmountInstrument();
    expect(instrumentsMounted()).toBe(true);
    unmountInstrument();
    expect(instrumentsMounted()).toBe(false);
  });

  it("stays held while a SECOND instrument is still under the pointer", () => {
    beginHand();
    beginHand();
    releaseHand();
    expect(handUnderway()).toBe(true);
    releaseHand();
    expect(handUnderway()).toBe(false);
  });

  it("cannot be driven negative by an unbalanced release", () => {
    // A cancel path can fire the no-button backstop AND the real pointerup. At
    // -1 the NEXT grab would read as no grab at all, and the camera would be
    // free to move under a live hand — the one thing the flag exists to stop.
    releaseHand();
    releaseHand();
    unmountInstrument();
    expect(handUnderway()).toBe(false);
    expect(instrumentsMounted()).toBe(false);
    beginHand();
    mountInstrument();
    expect(handUnderway()).toBe(true);
    expect(instrumentsMounted()).toBe(true);
  });

  it("keeps the two counters independent", () => {
    // An instrument on screen with nobody touching it is the resting state of
    // every open command, and it must not read as a drag.
    mountInstrument();
    expect(instrumentsMounted()).toBe(true);
    expect(handUnderway()).toBe(false);
  });
});
