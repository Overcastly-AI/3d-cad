/**
 * The Parameters panel (PART-PARAMETERS): the table reads in the document
 * unit, a cell commits on Enter or blur and reverts on Escape, and a refusal
 * sits on its row with the user's text still in the cell.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { rowsFromServer, type RowError } from "../features/parameters";
import { ParametersPanel, type ParametersPanelProps } from "./ParametersPanel";

const W_ID = "00000000-0000-4000-8000-000000000001";
const H_ID = "00000000-0000-4000-8000-000000000002";

const ROWS = rowsFromServer([
  {
    id: W_ID,
    name: "W",
    expression: "40",
    unit: "length",
    value: 40,
    comment: "width",
  },
  {
    id: H_ID,
    name: "H",
    expression: "W - 15",
    unit: "length",
    value: 25,
    comment: "",
  },
]);

function renderPanel(props: Partial<ParametersPanelProps> = {}) {
  const handlers = {
    onCommitCell: vi.fn(),
    onUnitChange: vi.fn(),
    onAdd: vi.fn(),
    onDelete: vi.fn(),
    onRetry: vi.fn(),
    onClose: vi.fn(),
  };
  render(
    <ParametersPanel
      rows={ROWS}
      stored={new Map(ROWS.map((row) => [row.id, row]))}
      documentUnit="mm"
      loadError={null}
      error={null}
      stale={false}
      saving={false}
      focusRowId={null}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

describe("ParametersPanel", () => {
  it("shows each row's value in the document unit", () => {
    renderPanel({ documentUnit: "in" });
    const values = screen.getAllByTestId("parameter-value");
    expect(values.map((cell) => cell.textContent)).toEqual([
      "1.5748 in",
      "0.9843 in",
    ]);
  });

  it("commits a changed cell on Enter, and an unchanged one too (retry)", () => {
    const { onCommitCell } = renderPanel();
    const cell = screen.getByLabelText("H expression");
    fireEvent.focus(cell);
    fireEvent.change(cell, { target: { value: "W - 20" } });
    fireEvent.keyDown(cell, { key: "Enter" });
    expect(onCommitCell).toHaveBeenCalledWith(H_ID, "expression", "W - 20");
    fireEvent.blur(cell);
    expect(onCommitCell).toHaveBeenCalledTimes(1);
  });

  it("commits on blur only when the text changed", () => {
    const { onCommitCell } = renderPanel();
    const cell = screen.getByLabelText("W comment");
    fireEvent.focus(cell);
    fireEvent.blur(cell);
    expect(onCommitCell).not.toHaveBeenCalled();
    fireEvent.focus(cell);
    fireEvent.change(cell, { target: { value: "overall width" } });
    fireEvent.blur(cell);
    expect(onCommitCell).toHaveBeenCalledWith(W_ID, "comment", "overall width");
  });

  it("puts the cell back on Escape and commits nothing", () => {
    const { onCommitCell } = renderPanel();
    const cell = screen.getByLabelText<HTMLInputElement>("W expression");
    fireEvent.focus(cell);
    fireEvent.change(cell, { target: { value: "99" } });
    fireEvent.keyDown(cell, { key: "Escape" });
    fireEvent.blur(cell);
    expect(cell.value).toBe("40");
    expect(onCommitCell).not.toHaveBeenCalled();
  });

  it("prints a refusal on its row and marks the offending cell", () => {
    const error: RowError = {
      rowId: H_ID,
      field: "expression",
      message: "Circular reference: H → W → H.",
      code: "expression_cycle",
    };
    renderPanel({ error });
    const message = screen.getByTestId("parameter-row-error");
    expect(message).toHaveTextContent("H → W → H");
    const cell = screen.getByLabelText("H expression");
    expect(cell).toHaveAttribute("aria-invalid", "true");
    expect(cell).toHaveAccessibleDescription("Circular reference: H → W → H.");
    expect(screen.getByLabelText("W expression")).not.toHaveAttribute(
      "aria-invalid",
    );
  });

  it("marks an unevaluated value pending rather than showing a stale number", () => {
    const edited = ROWS.map((row) =>
      row.id === H_ID
        ? { ...row, expression: "W - 20", bareUnit: "mm" as const }
        : row,
    );
    renderPanel({ rows: edited });
    const values = screen.getAllByTestId("parameter-value");
    expect(values[1]).toHaveTextContent("—");
  });

  it("explains what parameters are for when there are none, with Add", () => {
    const { onAdd } = renderPanel({ rows: [] });
    const empty = screen.getByTestId("parameters-empty");
    expect(empty).toHaveTextContent(/every feature that uses it follows/);
    fireEvent.click(within(empty).getByRole("button", { name: "Add" }));
    expect(onAdd).toHaveBeenCalledOnce();
  });

  it("offers a retry after a lost race", () => {
    const { onRetry } = renderPanel({ stale: true });
    expect(screen.getByTestId("parameters-stale")).toHaveTextContent(
      /part changed/,
    );
    fireEvent.click(screen.getByTestId("parameters-retry"));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("is read-only, and says why, while a command is open", () => {
    const { onDelete } = renderPanel({
      blockedReason: "Close the open command to change parameters.",
    });
    expect(screen.getByTestId("parameters-blocked")).toBeVisible();
    expect(screen.getByLabelText("W expression")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Delete W" }));
    expect(onDelete).not.toHaveBeenCalled();
  });
});
