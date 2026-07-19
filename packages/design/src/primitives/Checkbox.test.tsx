// @vitest-environment jsdom
/**
 * Checkbox primitive (MB-1b "Merge result" toggle): a role="checkbox" button
 * with an accurate aria-checked, that reports the NEXT state on toggle and
 * carries a legible accessible name.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Checkbox } from "./Checkbox";

afterEach(cleanup);

describe("Checkbox", () => {
  it("reflects checked state through aria-checked", () => {
    const { rerender } = render(
      <Checkbox label="Merge result" checked onChange={() => {}} />,
    );
    const box = screen.getByRole("checkbox", { name: "Merge result" });
    expect(box).toHaveAttribute("aria-checked", "true");

    rerender(
      <Checkbox label="Merge result" checked={false} onChange={() => {}} />,
    );
    expect(box).toHaveAttribute("aria-checked", "false");
  });

  it("reports the toggled next state on click", () => {
    const onChange = vi.fn();
    render(<Checkbox label="Merge result" checked onChange={onChange} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Merge result" }));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("does not fire while disabled", () => {
    const onChange = vi.fn();
    render(
      <Checkbox
        label="Merge result"
        checked={false}
        onChange={onChange}
        disabled
      />,
    );
    const box = screen.getByRole("checkbox", { name: "Merge result" });
    expect(box).toBeDisabled();
    fireEvent.click(box);
    expect(onChange).not.toHaveBeenCalled();
  });
});
