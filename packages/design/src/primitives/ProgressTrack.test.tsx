import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { carriageTravelPercent, progress } from "../tokens";
import { ProgressTrack } from "./ProgressTrack";

/**
 * The contract of an indeterminate wait, asserted where a screenshot cannot
 * see it (UI-REVIEW 2026-08-27 P1-B).
 *
 * Every case here is a property the finding measured as ABSENT: a progressbar
 * role, an accessible name, a liveness signal that does not depend on watching
 * pixels, and a reduced-motion path that still says "working". A test that
 * merely rendered the component and asserted it existed would have passed
 * against the broken version too — the busy line existed, it just said nothing.
 */
describe("ProgressTrack", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("is a NAMED progressbar, and deliberately has no value", () => {
    render(<ProgressTrack label="Importing bracket.step" />);
    const bar = screen.getByRole("progressbar", {
      name: "Importing bracket.step",
    });
    // The omission IS the semantics: no `aria-valuenow` is how ARIA spells
    // indeterminate. A number here would be a prediction the client cannot
    // make, which is the same lie as a bar that fills.
    expect(bar.getAttribute("aria-valuenow")).toBeNull();
    expect(bar.getAttribute("aria-valuetext")).toBeNull();
  });

  it("counts elapsed seconds, in the accessibility tree and not just in pixels", () => {
    render(<ProgressTrack label="Importing bracket.step" />);
    expect(screen.getByText(/^0s$/)).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    // The readout is a SIBLING of the bar, not a child: `progressbar` is a leaf
    // role, so a child would be pixels only. This assertion is the proof.
    const elapsed = screen.getByText(/^3s$/);
    expect(elapsed.closest('[role="progressbar"]')).toBeNull();
    expect(elapsed.textContent).toBe("3s elapsed");
  });

  it("stops counting when it unmounts, so the number cannot outlive the work", () => {
    const { unmount } = render(<ProgressTrack label="Importing" />);
    unmount();
    // A leaked interval would keep setting state on a dead component; React
    // would warn and, worse, the next mount would inherit a running clock.
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(5_000);
      });
    }).not.toThrow();
  });

  it("moves only under motion-safe, and fills the bed under motion-reduce", () => {
    const { container } = render(<ProgressTrack label="Importing" />);
    const carriage = container.querySelector<HTMLElement>(
      '[role="progressbar"] > span',
    );
    expect(carriage).not.toBeNull();
    const classes = carriage?.className ?? "";
    // Never bare `animate-travel`: an unconditional animation is the quality
    // floor broken.
    expect(classes).toContain("motion-safe:animate-travel");
    expect(classes).not.toMatch(/(^|\s)animate-travel/);
    // A STATIONARY 28 % segment would read as "28 % done" — the exact claim
    // this component must never make — so reduced motion fills the bed.
    expect(classes).toContain("w-carriage");
    expect(classes).toContain("motion-reduce:w-full");
  });

  it("forwards its test hook to the bar, the bed and the readout", () => {
    render(<ProgressTrack label="Importing" data-testid="import-progress" />);
    expect(screen.getByTestId("import-progress")).toBeTruthy();
    expect(screen.getByTestId("import-progress-bed").getAttribute("role")).toBe(
      "progressbar",
    );
    expect(screen.getByTestId("import-progress-elapsed").textContent).toBe(
      "0s elapsed",
    );
  });
});

/**
 * The travel distance is DERIVED, and this is the guard that keeps it derived.
 *
 * `translateX` is a percentage of the moving element's OWN width, so the number
 * that lands the carriage flush with the end of its bed is not 100 and is not
 * obvious. Transcribing it (357.14…) would be exactly the copy-waiting-to-drift
 * this repo rejects for palettes and API types, and the symptom would be a
 * carriage that overshoots or stops short — visible only to whoever happened to
 * look at the right frame.
 */
describe("carriage geometry", () => {
  it("lands the carriage flush with the far end of its bed", () => {
    const bed = 1000;
    const carriage = (progress.carriage / 100) * bed;
    const travelled = (carriageTravelPercent / 100) * carriage;
    expect(carriage + travelled).toBeCloseTo(bed, 6);
  });
});
