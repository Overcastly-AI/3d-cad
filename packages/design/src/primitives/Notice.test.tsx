import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Notice } from "./Notice";

describe("Notice", () => {
  it("announces with the role it is given and carries its sentence", () => {
    render(
      <Notice role="alert" label="Not saved" data-testid="n">
        Reloading will sign you out.
      </Notice>,
    );
    const notice = screen.getByRole("alert");
    expect(notice).toHaveAttribute("data-testid", "n");
    expect(notice).toHaveTextContent("Not saved");
    expect(notice).toHaveTextContent("Reloading will sign you out.");
    expect(notice.className).toContain("border-l-flag");
  });

  it("dismisses through its own control, and offers none without a handler", () => {
    const onDismiss = vi.fn();
    const { rerender } = render(
      <Notice role="status" label="Note" tone="gauge" onDismiss={onDismiss}>
        Text
      </Notice>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    rerender(
      <Notice role="status" label="Note" tone="gauge">
        Text
      </Notice>,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("stacks for a narrow panel without changing what is announced, or in what order", () => {
    render(
      <Notice role="status" label="Lead" layout="stacked" onDismiss={() => {}}>
        Sentence.
      </Notice>,
    );
    const notice = screen.getByRole("status");
    expect(notice).toHaveAttribute("data-layout", "stacked");
    expect(notice.className).toContain("grid");
    // Visual placement is by grid lines; the DOM (reading) order is fixed.
    expect(notice.textContent).toBe("LeadSentence.Dismiss");
    const [, sentence, dismiss] = Array.from(notice.children);
    expect(sentence?.className).toContain("col-span-2");
    expect(dismiss?.className).toContain("row-start-1");
  });

  it("offers the ONE action that answers it, before Dismiss", () => {
    // A notice that names a fix and makes the reader hunt for it is half a
    // notice (EDGE-RESOLVE-WARN-1: "re-pick them").
    const onAction = vi.fn();
    render(
      <Notice
        role="status"
        label="Edge moved"
        layout="stacked"
        action={{ label: "Re-pick edges", onClick: onAction, testId: "act" }}
        onDismiss={() => {}}
      >
        Sentence.
      </Notice>,
    );
    const notice = screen.getByRole("status");
    expect(notice.textContent).toBe("Edge movedSentence.Re-pick edgesDismiss");
    // Stacked, the action is the line under the sentence (a narrow tree row
    // cannot hold stamp, action and Dismiss on one line); Dismiss keeps the
    // top-right corner.
    const [, , act, dismiss] = Array.from(notice.children);
    expect(act?.className).toContain("row-start-3");
    expect(dismiss?.className).toContain("row-start-1");
    fireEvent.click(screen.getByRole("button", { name: "Re-pick edges" }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("act")).toHaveAccessibleName("Re-pick edges");
  });
});
