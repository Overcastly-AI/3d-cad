/**
 * The Save version dialog (LOFT-VERSIONS): a name, an optional description,
 * Enter submits, Escape cancels, and a refusal reads as a sentence.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  SaveVersionDialog,
  type SaveVersionDialogProps,
} from "./SaveVersionDialog";

function renderDialog(props: Partial<SaveVersionDialogProps> = {}) {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <SaveVersionDialog
      partName="Bracket"
      defaultName="V3"
      pending={false}
      error={null}
      onSave={onSave}
      onCancel={onCancel}
      {...props}
    />,
  );
  return { onSave, onCancel, ...view };
}

describe("SaveVersionDialog", () => {
  it("is a labelled modal dialog with the default name focused", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Save version" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const name = screen.getByLabelText("Name");
    expect(name).toHaveValue("V3");
    expect(name).toHaveFocus();
    expect(screen.getByText("Bracket")).toBeInTheDocument();
  });

  it("Enter in the name field submits the trimmed name and description", () => {
    const { onSave } = renderDialog();
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "  Rev B  " },
    });
    fireEvent.change(screen.getByLabelText("Description (optional)"), {
      target: { value: "Thicker web " },
    });
    // Implicit submission: Enter in a form field submits the form.
    fireEvent.submit(screen.getByTestId("save-version-dialog"));
    expect(onSave).toHaveBeenCalledWith({
      name: "Rev B",
      message: "Thicker web",
    });
  });

  it("Ctrl+S in the dialog saves what is typed", () => {
    const { onSave } = renderDialog();
    fireEvent.keyDown(screen.getByLabelText("Name"), {
      key: "s",
      ctrlKey: true,
    });
    expect(onSave).toHaveBeenCalledWith({ name: "V3", message: "" });
  });

  it("the Save version button submits too", () => {
    const { onSave } = renderDialog();
    fireEvent.click(screen.getByTestId("save-version-submit"));
    expect(onSave).toHaveBeenCalledWith({ name: "V3", message: "" });
  });

  it("refuses an empty name in place, without calling onSave", () => {
    const { onSave } = renderDialog();
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "  " },
    });
    fireEvent.submit(screen.getByTestId("save-version-dialog"));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Name the version.");
    expect(screen.getByLabelText("Name")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("Escape cancels, and holds the keyboard from listeners behind it", () => {
    const behind = vi.fn();
    window.addEventListener("keydown", behind);
    try {
      const { onCancel } = renderDialog();
      fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Escape" });
      expect(onCancel).toHaveBeenCalledTimes(1);
      fireEvent.keyDown(screen.getByLabelText("Name"), { key: "e" });
      expect(behind).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("keydown", behind);
    }
  });

  it("Cancel and the backdrop cancel; a click inside does not", () => {
    const { onCancel } = renderDialog();
    fireEvent.click(screen.getByTestId("save-version-dialog"));
    expect(onCancel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("save-version-cancel"));
    fireEvent.click(screen.getByTestId("save-version-backdrop"));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("shows the refusal and holds while a save is in flight", () => {
    const { onSave } = renderDialog({
      pending: true,
      error: "This part already has 100 versions, the limit for one part.",
    });
    expect(screen.getByTestId("save-version-error")).toHaveTextContent(
      "100 versions",
    );
    const submit = screen.getByTestId("save-version-submit");
    expect(submit).toBeDisabled();
    expect(submit).toHaveTextContent("Saving…");
    fireEvent.submit(screen.getByTestId("save-version-dialog"));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("takes a late default name until the user types", () => {
    const { rerender, onSave, onCancel } = renderDialog({ defaultName: "V1" });
    const props = {
      partName: "Bracket",
      pending: false,
      error: null,
      onSave,
      onCancel,
    };
    rerender(<SaveVersionDialog {...props} defaultName="V4" />);
    expect(screen.getByLabelText("Name")).toHaveValue("V4");
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Mine" },
    });
    rerender(<SaveVersionDialog {...props} defaultName="V5" />);
    expect(screen.getByLabelText("Name")).toHaveValue("Mine");
  });
});
