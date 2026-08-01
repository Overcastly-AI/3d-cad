/**
 * The feature-delete confirmation (UI-REVIEW F3) — what it may say, and what it
 * must refuse to offer.
 *
 * Two assertions carry the finding. When something depends on the feature, the
 * dependents are NAMED (not counted) and the Delete button is ABSENT — the
 * server would refuse the delete, and a button that cannot work is worse than
 * no button. When nothing does, the confirmation says what recovery exists,
 * because a confirmation that only says "are you sure?" is one people click
 * through.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FeatureDeleteConfirm } from "./FeatureDeleteConfirm";

describe("nothing depends on it", () => {
  it("offers the delete and names the way back", () => {
    render(
      <FeatureDeleteConfirm
        featureName="Extrude1"
        dependents={[]}
        pending={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const panel = screen.getByTestId("feature-delete-confirm");
    expect(panel).toHaveAttribute("data-blocked", "false");
    expect(panel).toHaveTextContent("Nothing else depends on it");
    expect(panel).toHaveTextContent("Undo brings it back");
    expect(
      screen.getByTestId("feature-delete-confirm-action"),
    ).toBeInTheDocument();
  });

  it("fires the delete only on the explicit confirm", () => {
    const onConfirm = vi.fn();
    render(
      <FeatureDeleteConfirm
        featureName="Extrude1"
        dependents={[]}
        pending={false}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("feature-delete-confirm-action"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("something does", () => {
  const dependents = [
    { id: "f1", name: "Extrude1", kind: "feature" as const },
    { id: "d1", name: "Assembly sheet", kind: "drawing" as const },
  ];

  it("NAMES what breaks, with what each one is", () => {
    render(
      <FeatureDeleteConfirm
        featureName="Sketch1"
        dependents={dependents}
        pending={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const named = screen
      .getAllByTestId("feature-dependent")
      .map((node) => node.textContent);
    expect(named).toEqual(["Extrude1", "Assembly sheet"]);
    expect(screen.getAllByTestId("feature-dependent")[1]).toHaveAttribute(
      "data-dependent-kind",
      "drawing",
    );
    // Never a bare count in place of the names.
    expect(screen.getByTestId("feature-delete-confirm")).not.toHaveTextContent(
      /referenced by \d+ other document/,
    );
  });

  it("does NOT offer a delete the server would refuse", () => {
    render(
      <FeatureDeleteConfirm
        featureName="Sketch1"
        dependents={dependents}
        pending={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("feature-delete-confirm")).toHaveAttribute(
      "data-blocked",
      "true",
    );
    expect(
      screen.queryByTestId("feature-delete-confirm-action"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("feature-delete-cancel")).toHaveTextContent(
      "Close",
    );
  });

  it("Escape backs out, like every other cancel in the product", () => {
    const onCancel = vi.fn();
    render(
      <FeatureDeleteConfirm
        featureName="Sketch1"
        dependents={dependents}
        pending={false}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.keyDown(screen.getByTestId("feature-delete-confirm"), {
      key: "Escape",
    });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
