// @vitest-environment jsdom
/**
 * ContextMenu — the reusable right-click menu. jsdom has no layout, so the
 * clamp math is exercised only insofar as it doesn't crash; the behaviour that
 * matters (renders sections/items, selecting fires the action AND closes,
 * disabled rows are inert, Escape closes) is asserted here. The real pointer
 * positioning is covered by the Playwright specs in apps/web/e2e.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContextMenu, type ContextMenuSection } from "./ContextMenu";

afterEach(cleanup);

function sections(
  onFit: () => void,
  onDelete: () => void,
): ContextMenuSection[] {
  return [
    {
      key: "view",
      label: "View",
      items: [
        { key: "fit", label: "Fit", onSelect: onFit, "data-testid": "fit" },
        {
          key: "top",
          label: "Top",
          onSelect: () => {},
          disabled: true,
          "data-testid": "top",
        },
      ],
    },
    {
      key: "edit",
      items: [
        {
          key: "delete",
          label: "Delete",
          danger: true,
          onSelect: onDelete,
          "data-testid": "delete",
        },
      ],
    },
  ];
}

describe("ContextMenu", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <ContextMenu
        open={false}
        x={0}
        y={0}
        aria-label="Menu"
        sections={sections(
          () => {},
          () => {},
        )}
        onClose={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders section labels + items with a menu role", () => {
    render(
      <ContextMenu
        open
        x={10}
        y={10}
        aria-label="Viewport actions"
        sections={sections(
          () => {},
          () => {},
        )}
        onClose={() => {}}
      />,
    );
    expect(
      screen.getByRole("menu", { name: "Viewport actions" }),
    ).toBeInTheDocument();
    expect(screen.getByText("View")).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
  });

  it("fires the action and closes on select", () => {
    const onFit = vi.fn();
    const onClose = vi.fn();
    render(
      <ContextMenu
        open
        x={0}
        y={0}
        aria-label="Menu"
        sections={sections(onFit, () => {})}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId("fit"));
    expect(onFit).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("leaves a disabled row inert", () => {
    const onClose = vi.fn();
    render(
      <ContextMenu
        open
        x={0}
        y={0}
        aria-label="Menu"
        sections={sections(
          () => {},
          () => {},
        )}
        onClose={onClose}
      />,
    );
    expect(screen.getByTestId("top")).toBeDisabled();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <ContextMenu
        open
        x={0}
        y={0}
        aria-label="Menu"
        sections={sections(
          () => {},
          () => {},
        )}
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  /**
   * FINDINGS burn-down 2026-07-25 #9: the docstring promised focus return; it
   * now happens. Closing the menu hands focus back to whatever opened it (the
   * feature row), so a keyboard user never lands on <body>.
   */
  it("returns focus to the trigger when it closes", () => {
    function Harness({ open }: { open: boolean }) {
      return (
        <>
          <button type="button" data-testid="trigger">
            Feature row
          </button>
          <ContextMenu
            open={open}
            x={0}
            y={0}
            aria-label="Menu"
            sections={sections(
              () => {},
              () => {},
            )}
            onClose={() => {}}
          />
        </>
      );
    }
    const { rerender } = render(<Harness open={false} />);
    const trigger = screen.getByTestId("trigger");
    trigger.focus();
    expect(trigger).toHaveFocus();

    rerender(<Harness open />);
    expect(screen.getByTestId("fit")).toHaveFocus();

    // Escape → closed → focus is back where the user left it.
    rerender(<Harness open={false} />);
    expect(trigger).toHaveFocus();
  });

  it("defers to a focus move the picked action made", () => {
    function Harness({ open }: { open: boolean }) {
      return (
        <>
          <button type="button" data-testid="trigger">
            Feature row
          </button>
          <input data-testid="rename" />
          <ContextMenu
            open={open}
            x={0}
            y={0}
            aria-label="Menu"
            sections={sections(
              () => {},
              () => {},
            )}
            onClose={() => {}}
          />
        </>
      );
    }
    const { rerender } = render(<Harness open={false} />);
    screen.getByTestId("trigger").focus();
    rerender(<Harness open />);

    // The action focused its own field (Rename → inline editor); closing the
    // menu must NOT snatch that focus back to the trigger.
    screen.getByTestId("rename").focus();
    rerender(<Harness open={false} />);
    expect(screen.getByTestId("rename")).toHaveFocus();
  });
});
