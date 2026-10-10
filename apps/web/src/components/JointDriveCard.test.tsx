/**
 * The drive card's DOM contract: both axes of a cylindrical joint, the one
 * drag scheme spelled out, and the "at limit" stamp from the solve or from a
 * drag that reaches a limit the user set.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { JointMate } from "../api/assemblies";
import type { DriveGesture, DriveTarget } from "../assembly/useJointDrive";
import { DocumentUnitProvider } from "../units/documentUnit";
import { JointDriveCard } from "./JointDriveCard";

const placement = {
  position: { x: 0, y: 0, z: 0 },
  orientation: { w: 1, x: 0, y: 0, z: 0 },
};

function target(over: Partial<DriveTarget> = {}): DriveTarget {
  return {
    mateId: "m1",
    label: "Cylindrical 1",
    instanceId: "b",
    motion: "cylindrical",
    joint: { motion: "cylindrical" } as JointMate,
    axis: { point: { x: 0, y: 0, z: 0 }, dir: { x: 0, y: 0, z: 1 } },
    base: placement,
    rot: { value: 30, min: -3600, max: 3600, limited: [false, false] },
    lin: { value: 12, min: -100_000, max: 40, limited: [false, true] },
    atLimit: false,
    ...over,
  };
}

function renderCard(t: DriveTarget, gesture: DriveGesture | null = null) {
  render(
    <DocumentUnitProvider unit="mm">
      <JointDriveCard
        target={t}
        gesture={gesture}
        committing={false}
        onEdit={vi.fn()}
        onDone={vi.fn()}
      />
    </DocumentUnitProvider>,
  );
}

describe("JointDriveCard", () => {
  it("reads both axes of a cylindrical joint and says how to drag each", () => {
    renderCard(target());
    expect(screen.getByTestId("joint-drive-value")).toHaveTextContent(
      "30° · 12 mm",
    );
    expect(screen.getByTestId("joint-drive")).toHaveTextContent(
      "Shift+drag (or the arrow) to slide along it",
    );
    expect(screen.queryByTestId("joint-drive-at-limit")).toBeNull();
  });

  it("stamps at limit when the solve has the joint on a limit", () => {
    renderCard(target({ atLimit: true }));
    expect(screen.getByTestId("joint-drive-at-limit")).toHaveTextContent(
      "at limit",
    );
  });

  it("stamps a drag that reaches a set limit, and only a set one", () => {
    renderCard(target(), { mode: "slide", value: 40 });
    expect(screen.getByTestId("joint-drive-value")).toHaveTextContent(
      "30° · 40 mm",
    );
    expect(screen.getByTestId("joint-drive-at-limit")).toBeInTheDocument();
  });
});
