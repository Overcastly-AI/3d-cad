/**
 * The part command band's EXPORT group — the fix for the defect the founder
 * named on 2026-08-17: *"the button to export should not be with all the mass
 * properties."*
 *
 * The band question these tests answer is placement, not plumbing (the group
 * itself is covered in `ExportToolGroup.test.tsx`): export must be a child of
 * the always-present command surface rather than of a collapsible readout
 * panel, it must carry the workspace's real gate reason, and — like every other
 * tool in this band — it must hold with the ONE honest lock reason while a
 * command is open, so no click can discard an in-progress selection.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { partVerbKey } from "../shortcuts/registry";
import { CreateStrip } from "./CreateStrip";

function renderStrip(props: Partial<Parameters<typeof CreateStrip>[0]> = {}) {
  return render(
    <CreateStrip
      treeReady
      onNewSketch={vi.fn()}
      canExtrude={false}
      onNewExtrude={vi.fn()}
      canRevolve={false}
      onNewRevolve={vi.fn()}
      canSweep={false}
      onNewSweep={vi.fn()}
      canLoft={false}
      onNewLoft={vi.fn()}
      {...props}
    />,
  );
}

const exporter = () =>
  Promise.resolve({ blob: new Blob(["x"]), filename: "part.step" });

describe("CreateStrip — export", () => {
  it("puts EXPORT in the band, not in a panel", () => {
    renderStrip({ onExport: exporter, exportState: "ready" });

    const group = screen.getByTestId("part-export-band-controls");
    expect(group).toBeVisible();
    expect(group).toHaveAttribute("data-export-state", "ready");
    // Inside the band's own tool-group container — i.e. it cannot be collapsed
    // away with the Inspector, which is the whole point of the ticket.
    expect(screen.getByTestId("tool-groups")).toContainElement(group);
    expect(screen.getByTestId("part-export-band-step")).toBeEnabled();
    expect(screen.getByTestId("part-export-band-stl")).toBeEnabled();
  });

  it("carries the workspace's export gate reason", () => {
    renderStrip({
      onExport: exporter,
      exportDisabledReason: "No body",
      exportState: "no-body",
    });

    const step = screen.getByTestId("part-export-band-step");
    // A gated band tool uses `aria-disabled`, never the native attribute, so
    // its reason stays hoverable and focusable (jest-dom's `toBeDisabled` reads
    // only the native one; Playwright's honours both).
    expect(step).toHaveAttribute("aria-disabled", "true");
    // The reason is the DESCRIPTION, not the name (A11Y-TOOLBTN-1): the cell is
    // called the same thing whether or not it is gated.
    expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    expect(step).toHaveAccessibleDescription(/No body/);
  });

  it("holds with the open command's reason, like every other band tool", () => {
    renderStrip({
      onExport: exporter,
      activeCommand: "Fillet",
      exportState: "ready",
    });

    const step = screen.getByTestId("part-export-band-step");
    // A gated band tool uses `aria-disabled`, never the native attribute, so
    // its reason stays hoverable and focusable (jest-dom's `toBeDisabled` reads
    // only the native one; Playwright's honours both).
    expect(step).toHaveAttribute("aria-disabled", "true");
    expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    expect(step).toHaveAccessibleDescription(/Finish Fillet first/);
  });

  it("renders no export group at all when the workspace supplies no exporter", () => {
    renderStrip();
    expect(screen.queryByTestId("part-export-band-controls")).toBeNull();
  });
});

/**
 * FLOW-B3 — the accented next verb.
 *
 * The table itself is tested without a DOM in `nextStep.test.ts`; what is
 * tested here is everything the BAND adds on top of it, which is the part that
 * can quietly stop working: the accent must land on exactly one tool, never on
 * a tool the user cannot press, and it must retire when the user answers it.
 */
describe("CreateStrip — the next-step accent", () => {
  const proposal = {
    featureId: "e1",
    tool: "new-hole" as const,
    caption: "Another hole on this body",
  };

  /** Every band tool currently wearing the dot. */
  const accented = () =>
    Array.from(document.querySelectorAll("[data-next-step='true']"));

  it("accents exactly ONE tool, and it is the proposed one", () => {
    renderStrip({ canModify: true, onHole: vi.fn(), nextStep: proposal });

    expect(accented()).toHaveLength(1);
    const hole = screen.getByTestId("new-hole");
    expect(hole).toHaveAttribute("data-next-step", "true");
    // Enabled — a proposal on a tool you cannot press is a dead end.
    expect(hole).not.toHaveAttribute("aria-disabled");
    // …and it is the DOT that marks it, not the active scribe: `aria-pressed`
    // and the bottom scribe already mean "this tool is on", and a proposal is
    // not a state.
    expect(hole).not.toHaveAttribute("aria-pressed", "true");
    expect(hole.querySelector("[data-scribe]")).toBeNull();
    expect(hole.querySelector("[data-testid='next-step-dot']")).not.toBeNull();
  });

  it("speaks the proposal to a screen reader through the caption", () => {
    renderStrip({ canModify: true, onHole: vi.fn(), nextStep: proposal });
    // The dot is aria-hidden; the WORDS are how a non-sighted user gets the
    // same proposal, and `ToolButton` routes the caption via aria-describedby.
    expect(screen.getByTestId("new-hole")).toHaveAccessibleDescription(
      "Another hole on this body",
    );
  });

  it("proposes nothing when the tree proposes nothing", () => {
    renderStrip({ canModify: true, onHole: vi.fn(), nextStep: null });
    expect(accented()).toHaveLength(0);
  });

  it("withholds the accent when the proposed tool is not usable", () => {
    // `onHole` absent => the Hole tool is gated, so there is nothing to propose.
    renderStrip({ canModify: true, nextStep: proposal });

    expect(screen.getByTestId("new-hole")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(accented()).toHaveLength(0);
  });

  it("withholds the accent when the part has no built body", () => {
    // The guard that catches a build which FAILED: extrude/revolve are gated on
    // a solved sketch, not on a body, so without this the band would propose
    // another extrude on a part that has nothing in it.
    renderStrip({
      canModify: false,
      canExtrude: true,
      onNewExtrude: vi.fn(),
      nextStep: { featureId: "e1", tool: "new-extrude", caption: "Another…" },
    });
    expect(accented()).toHaveLength(0);
  });

  it("retires the accent when a command opens, and does not re-arm it", () => {
    const { rerender } = renderStrip({
      canModify: true,
      onHole: vi.fn(),
      nextStep: proposal,
    });
    expect(accented()).toHaveLength(1);

    const props = {
      treeReady: true,
      onNewSketch: vi.fn(),
      canExtrude: false,
      onNewExtrude: vi.fn(),
      canRevolve: false,
      onNewRevolve: vi.fn(),
      canSweep: false,
      onNewSweep: vi.fn(),
      canLoft: false,
      onNewLoft: vi.fn(),
      canModify: true,
      onHole: vi.fn(),
      nextStep: proposal,
    };
    rerender(<CreateStrip {...props} activeCommand="Fillet" />);
    expect(accented()).toHaveLength(0);

    // Closing the command must NOT bring it back: the user has already said
    // what they were doing next, and a dot that returns is a nag.
    rerender(<CreateStrip {...props} activeCommand={null} />);
    expect(accented()).toHaveLength(0);

    // A DIFFERENT feature landing arms a fresh one — the dismissal is keyed on
    // the feature, so it cannot latch the accent off for the rest of the session.
    rerender(
      <CreateStrip
        {...props}
        activeCommand={null}
        nextStep={{ ...proposal, featureId: "e2" }}
      />,
    );
    expect(accented()).toHaveLength(1);
  });

  it("retires the accent on Esc with no command open", () => {
    renderStrip({ canModify: true, onHole: vi.fn(), nextStep: proposal });
    expect(accented()).toHaveLength(1);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(accented()).toHaveLength(0);
  });

  it("prints the five new letters the registry now owns", () => {
    // Read from the registry, never typed here: a band that hardcodes a key is
    // correct the day it is written and silently lying afterwards.
    renderStrip({
      canModify: true,
      canExtrude: true,
      canRevolve: true,
      onFillet: vi.fn(),
      onChamfer: vi.fn(),
    });
    for (const [testId, id] of [
      ["new-sketch", "sketch"],
      ["new-extrude", "extrude"],
      ["new-revolve", "revolve"],
      ["new-fillet", "fillet"],
      ["new-chamfer", "chamfer"],
    ] as const) {
      const key = partVerbKey(id);
      expect(key, id).toBeDefined();
      expect(
        within(screen.getByTestId(testId)).getByText(key!.toUpperCase()),
        testId,
      ).toBeVisible();
    }
  });
});
