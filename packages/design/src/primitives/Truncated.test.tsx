// @vitest-environment jsdom
/**
 * Truncated — jsdom has no layout, so what is asserted here is the CONTRACT that
 * makes truncation possible and recoverable: the text lives in a BLOCK box that
 * clips with an ellipsis, and the full string is on `title`. The defect this
 * closes was the opposite pair (an atomic `inline-flex` box, `title: null`), and
 * both halves are visible without a layout engine.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Truncated, truncatedProps, TRUNCATED_CLASS } from "./Truncated";

afterEach(cleanup);

const LONG = "Motor mount adapter plate rev C";

describe("Truncated", () => {
  it("renders the full text and keeps it on title", () => {
    render(<Truncated text={LONG} data-testid="name" />);
    const node = screen.getByTestId("name");
    expect(node).toHaveTextContent(LONG);
    expect(node).toHaveAttribute("title", LONG);
  });

  it("clips in a BLOCK box — the inline-flex that defeated the ellipsis is gone", () => {
    render(<Truncated text={LONG} data-testid="name" />);
    const cls = screen.getByTestId("name").className;
    expect(cls).toContain("block");
    expect(cls).toContain("truncate");
    // `min-w-0`, or a flex parent gives the item its content width and the text
    // pushes the column wide instead of ellipsising.
    expect(cls).toContain("min-w-0");
    expect(cls).not.toContain("inline-flex");
  });

  it("keeps the caller's ink alongside the truncation", () => {
    render(<Truncated text={LONG} className="text-brass" data-testid="name" />);
    const cls = screen.getByTestId("name").className;
    expect(cls).toContain("text-brass");
    expect(cls).toContain("truncate");
  });

  it("hands the same contract to an element the caller renders", () => {
    const props = truncatedProps(LONG, "font-body");
    expect(props.title).toBe(LONG);
    expect(props.className).toContain("font-body");
    for (const token of TRUNCATED_CLASS.split(" ")) {
      expect(props.className).toContain(token);
    }
    render(
      <a href="/parts/1" data-testid="link" {...props}>
        {LONG}
      </a>,
    );
    expect(screen.getByTestId("link")).toHaveAttribute("title", LONG);
  });

  it("keeps the 24px tap target the old inline-flex was reaching for", () => {
    render(<Truncated text={LONG} data-testid="name" />);
    expect(screen.getByTestId("name").className).toContain(
      "min-h-target-dense",
    );
  });
});
