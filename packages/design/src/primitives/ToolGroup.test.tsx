// @vitest-environment jsdom
/**
 * ToolGroup's "more" (▾) menu: the group's eyebrow becomes the trigger for
 * its low-frequency verbs (Fusion's "CREATE ▾"). The width it saves is
 * measured by `apps/web/e2e/toolbar-overflow.spec.ts`; this holds the
 * structure: a plain eyebrow without items, a trigger whose word no tier
 * sheds with them, and rows that open, act and say what they need.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToolGroup } from "./ToolGroup";

afterEach(cleanup);

describe("ToolGroup more menu", () => {
  it("keeps a plain eyebrow when the group has no more items", () => {
    render(<ToolGroup eyebrow="Inspect" />);
    expect(screen.getByRole("group", { name: "Inspect" })).toHaveTextContent(
      "Inspect",
    );
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("turns the eyebrow into a menu trigger for the group's quieter verbs", () => {
    const onPipe = vi.fn();
    render(
      <ToolGroup
        eyebrow="Create"
        moreTestId="create-more"
        more={[
          {
            key: "pipe",
            icon: <svg aria-hidden />,
            label: "Pipe",
            onSelect: onPipe,
            "data-testid": "new-pipe",
          },
          {
            key: "plane",
            icon: <svg aria-hidden />,
            label: "Plane along path",
            onSelect: () => undefined,
            available: false,
            requires: "a sketch curve",
            disabled: true,
          },
        ]}
      />,
    );
    const group = screen.getByRole("group", { name: "Create" });
    // The menu hangs from the group, below its tools.
    expect(group.className).toContain("relative");

    const trigger = screen.getByTestId("create-more");
    expect(trigger).toHaveAccessibleName("More Create tools");
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    // The group's name is the eyebrow every tier keeps: never shed.
    const word = Array.from(trigger.querySelectorAll("span")).find(
      (span) => span.textContent === "Create",
    );
    expect(word?.className ?? "").not.toContain("data-labels=off");

    fireEvent.click(trigger);
    expect(
      screen.getByRole("menu", { name: "More Create tools" }),
    ).toBeVisible();
    expect(
      screen.getByRole("menuitem", {
        name: "Plane along path — needs a sketch curve",
      }),
    ).toBeDisabled();
    fireEvent.click(screen.getByTestId("new-pipe"));
    expect(onPipe).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
