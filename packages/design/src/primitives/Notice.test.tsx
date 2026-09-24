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
});
