/**
 * The Joint dialog's DOM contract: the motion picker offers all six, limits
 * and the drive appear per motion (the wire's rule), the Flip
 * hint shows only when the preview drives one body through the other, and a
 * server refusal is printed in the server's own words. The preview and the
 * writes live in `useJointDialog`; this renders the instrument.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EdgeSignature } from "../api/parts";
import { useJointDialogStore } from "../assembly/jointDialogStore";
import type { JointOriginPick } from "../assembly/joints";
import { DocumentUnitProvider } from "../units/documentUnit";
import { JointDialog } from "./JointDialog";

const rim: EdgeSignature = {
  subshape_type: "edge",
  curve: "circle",
  end_a: { x: 25, y: 12.5, z: 10 },
  end_b: { x: 25, y: 12.5, z: 10 },
  midpoint: { x: 15, y: 12.5, z: 10 },
  length_mm: 31.4,
};
const pick = (instanceId: string): JointOriginPick => ({
  instanceId,
  kind: "circle_centre",
  signature: rim,
  at: null,
  key: "circle-0",
});

function renderDialog(props: Partial<Parameters<typeof JointDialog>[0]> = {}) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(
    <DocumentUnitProvider unit="mm">
      <JointDialog
        instanceName={(id) => (id === "a" ? "Plate <1>" : "Plate <2>")}
        previewing={false}
        throughEachOther={false}
        previewProblem={null}
        onSubmit={onSubmit}
        onCancel={onCancel}
        {...props}
      />
    </DocumentUnitProvider>,
  );
  return { onSubmit, onCancel };
}

afterEach(() => useJointDialogStore.getState().close());

describe("JointDialog", () => {
  it("names both origins and opens on Rigid with no free axis to limit", () => {
    useJointDialogStore.getState().openCreate(pick("a"), pick("b"));
    renderDialog();
    expect(screen.getByTestId("joint-origin-A")).toHaveTextContent(
      "Hole centre · Plate <1>",
    );
    expect(screen.getByTestId("joint-motion-rigid")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.queryByTestId("joint-rotMax")).toBeNull();
  });

  it("offers every motion, with the fields the wire lets each one take", () => {
    useJointDialogStore.getState().openCreate(pick("a"), pick("b"));
    renderDialog();
    for (const motion of ["cylindrical", "planar", "ball"]) {
      const button = screen.getByTestId(`joint-motion-${motion}`);
      expect(button).toBeEnabled();
      expect(button).not.toHaveTextContent("coming soon");
    }
    fireEvent.click(screen.getByTestId("joint-motion-cylindrical"));
    for (const f of ["rotMin", "rotMax", "rotValue", "linMin", "linMax"]) {
      expect(screen.getByTestId(`joint-${f}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("joint-linValue")).toBeInTheDocument();
    expect(screen.getByLabelText("Max angle")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("joint-motion-planar"));
    expect(screen.getByTestId("joint-rotMax")).toBeInTheDocument();
    expect(screen.getByTestId("joint-rotValue")).toBeInTheDocument();
    expect(screen.queryByTestId("joint-linMax")).toBeNull();
    expect(screen.queryByTestId("joint-linValue")).toBeNull();
    fireEvent.click(screen.getByTestId("joint-motion-ball"));
    expect(screen.queryByTestId("joint-rotMax")).toBeNull();
    expect(screen.queryByTestId("joint-rotValue")).toBeNull();
    expect(screen.getByTestId("joint-ball-note")).toBeInTheDocument();
  });

  it("reveals the free axis's limits and drive per motion", () => {
    useJointDialogStore.getState().openCreate(pick("a"), pick("b"));
    renderDialog();
    fireEvent.click(screen.getByTestId("joint-motion-revolute"));
    expect(screen.getByTestId("joint-rotMax")).toBeInTheDocument();
    expect(screen.getByTestId("joint-rotValue")).toBeInTheDocument();
    expect(screen.queryByTestId("joint-linMax")).toBeNull();
    fireEvent.click(screen.getByTestId("joint-motion-slider"));
    expect(screen.getByTestId("joint-linMax")).toBeInTheDocument();
    expect(screen.queryByTestId("joint-rotMax")).toBeNull();
  });

  it("flips, turns a quarter, and commits on Enter / cancels on Escape", () => {
    useJointDialogStore.getState().openCreate(pick("a"), pick("b"));
    const { onSubmit, onCancel } = renderDialog();
    fireEvent.click(screen.getByTestId("joint-flip"));
    expect(screen.getByTestId("joint-flip")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByTestId("joint-rotate"));
    expect(screen.getByTestId("joint-rotate")).toHaveAccessibleName(
      "Rotate 90°, now 90°",
    );
    const offset = screen.getByTestId("joint-offset");
    fireEvent.keyDown(offset, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledOnce();
    fireEvent.keyDown(offset, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("holds OK while a cell does not parse", () => {
    useJointDialogStore.getState().openCreate(pick("a"), pick("b"));
    renderDialog();
    fireEvent.change(screen.getByTestId("joint-offset"), {
      target: { value: "twelve" },
    });
    expect(screen.getByTestId("joint-ok")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("shows the Flip hint only when the preview puts B through A", () => {
    useJointDialogStore.getState().openCreate(pick("a"), pick("b"));
    renderDialog({ throughEachOther: true });
    expect(screen.getByTestId("joint-flip-hint")).toHaveTextContent("Flip");
  });

  it("prints a refusal verbatim and locks the motion of a stored joint", () => {
    useJointDialogStore.getState().openEdit(
      "m1",
      "Revolute 1",
      {
        type: "joint",
        motion: "revolute",
        a: {
          instance_id: "a",
          kind: "circle_centre",
          signature: rim,
          flip: false,
          quarter_turns: 0,
        },
        b: {
          instance_id: "b",
          kind: "circle_centre",
          signature: rim,
          flip: false,
          quarter_turns: 0,
        },
        offset_mm: 0,
        angle_deg: 0,
        limits: { rot_max_deg: 180 },
        value: { rot_deg: 45 },
      },
      "mm",
    );
    useJointDialogStore
      .getState()
      .setError("Revolute 1: 200° exceeds max 180°");
    renderDialog();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Revolute 1: 200° exceeds max 180°",
    );
    expect(screen.getByTestId("joint-rotMax")).toHaveValue("180");
    expect(screen.getByTestId("joint-motion-slider")).toBeDisabled();
    expect(screen.getByTestId("joint-motion-revolute")).toBeEnabled();
  });
});
