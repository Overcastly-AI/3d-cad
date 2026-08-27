// @vitest-environment jsdom
/**
 * OverflowMenu — the trigger that holds a row's verbs. The menu card is
 * `ContextMenu` (tested next door), so what is asserted here is the seam: the
 * verbs are absent until asked for, the trigger states its own expanded state,
 * picking a verb fires it AND closes, and the accessible name names the ROW —
 * a table of identical "More" buttons is the a11y defect this must not ship.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverflowMenu } from "./OverflowMenu";
import type { ContextMenuSection } from "./ContextMenu";

afterEach(cleanup);

function sections(onRename: () => void, onDelete: () => void) {
  const built: ContextMenuSection[] = [
    {
      key: "edit",
      items: [
        {
          key: "rename",
          label: "Rename",
          onSelect: onRename,
          "data-testid": "part-rename",
        },
      ],
    },
    {
      key: "destroy",
      items: [
        {
          key: "delete",
          label: "Delete",
          danger: true,
          onSelect: onDelete,
          "data-testid": "part-delete",
        },
      ],
    },
  ];
  return built;
}

describe("OverflowMenu", () => {
  it("holds the verbs closed until asked", () => {
    render(
      <OverflowMenu
        label="Actions for Bracket plate"
        data-testid="part-actions"
        sections={sections(vi.fn(), vi.fn())}
      />,
    );
    expect(screen.queryByTestId("part-rename")).toBeNull();
    const trigger = screen.getByTestId("part-actions");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  });

  it("names the row it acts on, on the trigger AND on the menu", () => {
    render(
      <OverflowMenu
        label="Actions for Bracket plate"
        data-testid="part-actions"
        sections={sections(vi.fn(), vi.fn())}
      />,
    );
    expect(screen.getByTestId("part-actions")).toHaveAccessibleName(
      "Actions for Bracket plate",
    );
    fireEvent.click(screen.getByTestId("part-actions"));
    expect(screen.getByRole("menu")).toHaveAccessibleName(
      "Actions for Bracket plate",
    );
  });

  it("opens, fires the verb, and closes behind it", () => {
    const onRename = vi.fn();
    render(
      <OverflowMenu
        label="Actions for Bracket plate"
        data-testid="part-actions"
        sections={sections(onRename, vi.fn())}
      />,
    );
    fireEvent.click(screen.getByTestId("part-actions"));
    expect(screen.getByTestId("part-actions")).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    fireEvent.click(screen.getByTestId("part-rename"));
    expect(onRename).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("part-rename")).toBeNull();
    expect(screen.getByTestId("part-actions")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("closes on a second click of the trigger, firing nothing", () => {
    const onDelete = vi.fn();
    render(
      <OverflowMenu
        label="Actions for Bracket plate"
        data-testid="part-actions"
        sections={sections(vi.fn(), onDelete)}
      />,
    );
    const trigger = screen.getByTestId("part-actions");
    fireEvent.click(trigger);
    fireEvent.click(trigger);
    expect(screen.queryByTestId("part-delete")).toBeNull();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("closes on Escape and hands focus back to the trigger", () => {
    render(
      <OverflowMenu
        label="Actions for Bracket plate"
        data-testid="part-actions"
        sections={sections(vi.fn(), vi.fn())}
      />,
    );
    const trigger = screen.getByTestId("part-actions");
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveFocus();
  });
});
