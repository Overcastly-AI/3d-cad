// @vitest-environment jsdom
/**
 * SegmentedControl — the density options added for FB-19 must not cost the
 * control its NAME. `hideLabel` drops a caption from the screen; if it dropped
 * it from the accessibility tree, two toggles sharing a row would be two
 * unlabelled pairs of buttons, which is a worse defect than the tall form.
 *
 * The 24px target floor of a dense segment is measured in the browser
 * (`e2e/fb19-chrome-density.spec.ts`) — jsdom has no layout, so asserting it
 * here would be an assertion that cannot fail.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SegmentedControl, type SegmentOption } from "./SegmentedControl";

afterEach(cleanup);

const OPTIONS: ReadonlyArray<SegmentOption<"add" | "cut">> = [
  { value: "add", label: "Add", "aria-label": "Operation: Add" },
  { value: "cut", label: "Cut", "aria-label": "Operation: Cut" },
];

describe("SegmentedControl hideLabel", () => {
  it("keeps the group's name while dropping the caption line", () => {
    render(
      <SegmentedControl
        label="Operation"
        hideLabel
        value="add"
        options={OPTIONS}
        onChange={() => {}}
      />,
    );
    // The group is still named …
    expect(
      screen.getByRole("group", { name: "Operation" }),
    ).toBeInTheDocument();
    // … and no visible caption text remains to spend a line on.
    expect(screen.queryByText("Operation")).toBeNull();
  });

  it("puts the group name in reach of a POINTER too, via the segment tooltip", () => {
    render(
      <SegmentedControl
        label="Operation"
        hideLabel
        value="add"
        options={OPTIONS}
        onChange={() => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Operation: Add" }),
    ).toHaveAttribute("title", "Operation: Add");
  });

  it("leaves the caption on screen — and untitled — in the default layout", () => {
    render(
      <SegmentedControl
        label="Operation"
        value="add"
        options={OPTIONS}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("Operation")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Operation: Add" }),
    ).not.toHaveAttribute("title");
  });
});
