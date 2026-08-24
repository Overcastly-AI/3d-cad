// @vitest-environment jsdom
/**
 * ScrollRegion — the panel body that ADMITS it is clipped (AUDIT-PRODUCT T-18).
 *
 * jsdom has no layout, so `scrollHeight`/`clientHeight`/`scrollTop` are stubbed
 * on the viewport element to stage each state. That is the whole subject here:
 * the component's only job is to turn those three numbers into a break rule, a
 * keyboard seat and a `data-scroll-edges` readout, and it is the mapping — not
 * the browser's layout — that regressed for three audit passes.
 */
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ScrollRegion } from "./ScrollRegion";

afterEach(cleanup);

beforeEach(() => {
  // The component observes its own box; jsdom ships no ResizeObserver.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

/** The scrolling viewport — the element that carries the region semantics. */
function viewport(): HTMLElement {
  const el = screen.getByTestId("region").querySelector("div");
  if (el === null) throw new Error("no viewport");
  return el;
}

/** Stage a scroll geometry on the viewport and fire a scroll event. */
function stage(geometry: {
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
}): void {
  const el = viewport();
  for (const [key, value] of Object.entries(geometry)) {
    Object.defineProperty(el, key, { value, configurable: true });
  }
  act(() => {
    el.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
}

function renderRegion() {
  render(
    <ScrollRegion label="Inspector readouts" data-testid="region">
      <p>Min</p>
    </ScrollRegion>,
  );
}

describe("ScrollRegion — the break rule is a readout, not decoration", () => {
  it("marks NOTHING while everything fits, and adds no tab stop", () => {
    renderRegion();
    stage({ scrollTop: 0, clientHeight: 400, scrollHeight: 400 });
    expect(screen.getByTestId("region")).toHaveAttribute(
      "data-scroll-edges",
      "none",
    );
    expect(screen.queryByTestId("scroll-edge-top")).toBeNull();
    expect(screen.queryByTestId("scroll-edge-bottom")).toBeNull();
    // A region with nothing to scroll must not sit in the tab order.
    expect(viewport()).not.toHaveAttribute("tabindex");
    expect(viewport()).not.toHaveAttribute("role");
  });

  it("marks the BOTTOM edge when content is hidden below the fold", () => {
    renderRegion();
    // The measured 1280x800 case: 542px of title block in a 347px column.
    stage({ scrollTop: 0, clientHeight: 347, scrollHeight: 542 });
    expect(screen.getByTestId("region")).toHaveAttribute(
      "data-scroll-edges",
      "bottom",
    );
    expect(screen.getByTestId("scroll-edge-bottom")).toBeInTheDocument();
    expect(screen.queryByTestId("scroll-edge-top")).toBeNull();
  });

  it("marks BOTH edges mid-scroll and only the TOP at the end", () => {
    renderRegion();
    stage({ scrollTop: 100, clientHeight: 347, scrollHeight: 542 });
    expect(screen.getByTestId("region")).toHaveAttribute(
      "data-scroll-edges",
      "both",
    );
    expect(screen.getByTestId("scroll-edge-top")).toBeInTheDocument();
    expect(screen.getByTestId("scroll-edge-bottom")).toBeInTheDocument();

    stage({ scrollTop: 195, clientHeight: 347, scrollHeight: 542 });
    expect(screen.getByTestId("region")).toHaveAttribute(
      "data-scroll-edges",
      "top",
    );
    expect(screen.queryByTestId("scroll-edge-bottom")).toBeNull();
  });

  it("becomes a NAMED, FOCUSABLE region once there is something to reach", () => {
    renderRegion();
    stage({ scrollTop: 0, clientHeight: 347, scrollHeight: 542 });
    const region = screen.getByRole("region", { name: "Inspector readouts" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region).toBe(viewport());
  });

  it("keeps the break rules out of the a11y tree and out of the way", () => {
    renderRegion();
    stage({ scrollTop: 100, clientHeight: 347, scrollHeight: 542 });
    for (const id of ["scroll-edge-top", "scroll-edge-bottom"]) {
      const rule = screen.getByTestId(id);
      expect(rule).toHaveAttribute("aria-hidden", "true");
      // A mark that swallowed clicks would make the row beneath it unpickable.
      expect(rule.className).toContain("pointer-events-none");
    }
  });

  it("shows the TRAVEL mark only while there is travel, and moves it", () => {
    renderRegion();
    stage({ scrollTop: 0, clientHeight: 400, scrollHeight: 400 });
    expect(screen.queryByTestId("scroll-travel")).toBeNull();

    // 347 of 600 visible: a thumb just under 58 % of the track, at the top.
    stage({ scrollTop: 0, clientHeight: 347, scrollHeight: 600 });
    const thumb = screen.getByTestId("scroll-travel-thumb");
    expect(thumb.style.height).toBe("57.833333333333336%");
    expect(thumb.style.top).toBe("0%");

    // Scrolled to the end: the thumb sits at the bottom of the track.
    stage({ scrollTop: 253, clientHeight: 347, scrollHeight: 600 });
    expect(screen.getByTestId("scroll-travel-thumb").style.top).toBe(
      "42.166666666666664%",
    );
  });

  it("STANDS DOWN where the engine draws a classic scrollbar", () => {
    renderRegion();
    // A measurable gutter means the platform is already showing the position;
    // a second bar beside it would be decoration.
    Object.defineProperty(viewport(), "offsetWidth", {
      value: 320,
      configurable: true,
    });
    Object.defineProperty(viewport(), "clientWidth", {
      value: 305,
      configurable: true,
    });
    stage({ scrollTop: 0, clientHeight: 347, scrollHeight: 600 });
    expect(screen.queryByTestId("scroll-travel")).toBeNull();
    // The break rule still reports — it says a different thing.
    expect(screen.getByTestId("scroll-edge-bottom")).toBeInTheDocument();
  });

  it("ignores sub-pixel rounding — a 0.4px overflow is not a clipped edge", () => {
    renderRegion();
    stage({ scrollTop: 0.4, clientHeight: 347, scrollHeight: 347.4 });
    expect(screen.getByTestId("region")).toHaveAttribute(
      "data-scroll-edges",
      "none",
    );
  });
});
