/**
 * The Bodies panel's names (BODY-NAMES): a member body reads its own name,
 * not "Body n", and a double-click renames a body in place, as Fusion's
 * browser does.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BodyInfo } from "../features/bodies";
import { BodiesPanel } from "./BodiesPanel";

const BODIES: BodyInfo[] = [
  {
    baseFeatureId: "x1",
    name: "Extrude1",
    featureType: "extrude",
    ordinal: 1,
    label: "Body 1",
    named: false,
    unrenamed: "Body 1",
  },
  {
    baseFeatureId: "s3",
    name: "Front wall",
    featureType: "custom",
    ordinal: 2,
    label: "Front wall · Stud 3",
    named: true,
    unrenamed: "Front wall · Stud 3",
  },
];

function panel(onRenameBody = vi.fn()) {
  render(
    <BodiesPanel
      bodies={BODIES}
      selectedFeatureId={null}
      onSelectBody={vi.fn()}
      onRenameBody={onRenameBody}
    />,
  );
  return onRenameBody;
}

describe("BodiesPanel names", () => {
  it("shows a member body's own name, without its feature twice", () => {
    panel();
    expect(screen.getByTestId("body-name-1")).toHaveTextContent(
      "Front wall · Stud 3",
    );
    expect(screen.getByTestId("body-select-1")).not.toHaveTextContent(
      "Stud 3Front wall",
    );
    expect(screen.getByTestId("body-select-0")).toHaveTextContent(
      "Body 1Extrude1",
    );
  });

  it("renames on double-click and Enter", () => {
    const onRename = panel();
    fireEvent.doubleClick(screen.getByTestId("body-select-1"));
    const field = screen.getByTestId("body-rename-1");
    fireEvent.change(field, { target: { value: "King stud" } });
    fireEvent.keyDown(field, { key: "Enter" });
    expect(onRename).toHaveBeenCalledWith(BODIES[1], "King stud");
    expect(screen.queryByTestId("body-rename-1")).toBeNull();
  });

  it("keeps the name on Escape or an unchanged name", () => {
    const onRename = panel();
    fireEvent.doubleClick(screen.getByTestId("body-select-0"));
    fireEvent.keyDown(screen.getByTestId("body-rename-0"), { key: "Escape" });
    fireEvent.doubleClick(screen.getByTestId("body-select-0"));
    fireEvent.blur(screen.getByTestId("body-rename-0"));
    expect(onRename).not.toHaveBeenCalled();
  });
});
