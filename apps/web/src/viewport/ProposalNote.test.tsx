/**
 * THE ONE-SHOT — what spends the solve offer, and what must not.
 *
 * W2 review, second finding: `withdrawOffer` recorded the subject as SEEN
 * unconditionally, while the chip only ever reaches the screen when an anchor
 * exists. So an offer nobody was ever shown was burned for the session. It is
 * not a corner: `extrudeEnabled` goes false whenever a command opens, measure
 * arms, or another sketch starts, and `loopAnchor` refuses an anchor at
 * perfectly ordinary poses — a profile whose screen bbox is shorter than the
 * chip, or a centroid inside the frame's keep-out.
 *
 * These drive the real seams the component listens to (`useSketchStore`'s
 * transitions and the anchor store the scene publishes through), not a
 * rewritten copy of them, because the trigger being a store SUBSCRIPTION
 * rather than a render is the whole reason the component is shaped this way.
 * The layer's own `data-proposal-pending` / `data-proposal-anchored` stamps are
 * what tell a pending offer from a refused one — they exist so a refusal can be
 * read without a debugger, and this reads them.
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSketchStore } from "../sketch/store";

import { ProposalNote, type ProfileSubject } from "./ProposalNote";
import { useProposalAnchorStore } from "./proposalAnchor";

const SKETCH1: ProfileSubject = { id: "s1", name: "Sketch1" };
const FRAME = { width: 1280, height: 800 };

function layer(): HTMLElement {
  return screen.getByTestId("sketch-proposal-layer");
}

/** A solve, through the store's own two sets — `bind` then `exit`. */
function solve(featureId: string): void {
  act(() => {
    useSketchStore.getState().begin();
    useSketchStore.getState().bind(featureId);
    useSketchStore.getState().exit();
  });
}

/** What the scene does when the profile projects somewhere honest. */
function publishAnchor(): void {
  act(() => {
    useProposalAnchorStore
      .getState()
      .publishAnchor({ x: 640, y: 400, frame: FRAME });
  });
}

function renderNote(extrudeEnabled: boolean) {
  const onAcceptExtrude = vi.fn();
  const view = render(
    <div data-testid="viewport">
      <ProposalNote
        enabled={false}
        face={null}
        onAccept={vi.fn()}
        extrudeEnabled={extrudeEnabled}
        profiles={[SKETCH1]}
        onAcceptExtrude={onAcceptExtrude}
      />
    </div>,
  );
  const show = (next: boolean) =>
    view.rerender(
      <div data-testid="viewport">
        <ProposalNote
          enabled={false}
          face={null}
          onAccept={vi.fn()}
          extrudeEnabled={next}
          profiles={[SKETCH1]}
          onAcceptExtrude={onAcceptExtrude}
        />
      </div>,
    );
  return { ...view, show, onAcceptExtrude };
}

beforeEach(() => {
  act(() => {
    useSketchStore.getState().exit();
    useProposalAnchorStore.getState().requestAnchor(null);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the solve offer's one-shot", () => {
  it("survives a withdrawal it was never drawn for", () => {
    const view = renderNote(true);
    solve("s1");
    // Pending, with no anchor yet — the state the scene leaves it in for a
    // beat on every solve, and permanently when `loopAnchor` refuses.
    expect(layer()).toHaveAttribute("data-proposal-pending", "s1");
    expect(layer()).toHaveAttribute("data-proposal-anchored", "no");
    expect(screen.queryByTestId("extrude-proposal")).not.toBeInTheDocument();

    // Anything else the user might do: open a command, arm measure, start
    // another sketch. All of them arrive here as `extrudeEnabled` going false.
    view.show(false);
    expect(layer()).not.toHaveAttribute("data-proposal-pending");
    view.show(true);

    // Solve the same sketch again, and this time the profile lands somewhere a
    // leader can point at. The offer the user never saw was not spent.
    solve("s1");
    expect(layer()).toHaveAttribute("data-proposal-pending", "s1");
    publishAnchor();
    const chip = screen.getByTestId("extrude-proposal");
    expect(chip).toHaveAttribute("data-proposal-subject", "Sketch1");
  });

  it("is spent by an offer the user DID see", () => {
    // The other half, and the reason the case above is not just "the one-shot
    // stopped working": a chip that reached the screen and was waved away must
    // not come back. Two notes never queue and a note that returns is a nag.
    const view = renderNote(true);
    solve("s1");
    publishAnchor();
    expect(screen.getByTestId("extrude-proposal")).toBeInTheDocument();

    view.show(false);
    view.show(true);
    expect(screen.queryByTestId("extrude-proposal")).not.toBeInTheDocument();

    solve("s1");
    expect(layer()).not.toHaveAttribute("data-proposal-pending");
    publishAnchor();
    expect(screen.queryByTestId("extrude-proposal")).not.toBeInTheDocument();
  });

  it("and a DIFFERENT sketch is a different subject either way", () => {
    const view = renderNote(true);
    solve("s1");
    publishAnchor();
    expect(screen.getByTestId("extrude-proposal")).toBeInTheDocument();
    view.show(false);
    view.show(true);

    solve("s2");
    expect(layer()).toHaveAttribute("data-proposal-pending", "s2");
  });
});

/**
 * THE SINGLE-WRITER INVARIANT, which was real and unasserted (W2 review, last
 * item). `putNote` is the only thing allowed to write the note, because a write
 * also updates the ref every DOM listener reads and withdraws the ambient
 * offer; a bare `setNote` would do neither, silently, with the chip still
 * looking correct on screen. The state setter is now named
 * `setNoteThroughPutNote`, so writing past it reads as wrong at the call site,
 * and a DEV layout-effect compares the ref against the state.
 *
 * WHAT THIS CASE IS AND IS NOT, said out loud rather than implied: it is the
 * check's NEGATIVE CONTROL — the ambient path writes no note, and the alarm
 * stays quiet, so the check does not cry wolf. It does NOT prove the alarm can
 * fire. Measured: reverting `putNote(null)` to a bare setter in the dwell's
 * withdraw branch leaves this file green, because every bare-write site is on
 * the POINTER path, and reaching that in jsdom needs a full `OverlayFace`
 * fixture, fake timers for the dwell, and a synthetic pointermove — a fixture
 * heavier than the thing it guards. The alarm's real theatre is the browser,
 * where any future bare write reddens the console on the next commit.
 */
describe("the note's single writer", () => {
  it("does not cry wolf while the ambient note is the one on screen", () => {
    const complaint = vi.spyOn(console, "error").mockImplementation(() => {});
    renderNote(true);
    solve("s1");
    publishAnchor();
    expect(screen.getByTestId("extrude-proposal")).toBeInTheDocument();
    expect(complaint).not.toHaveBeenCalled();
  });
});
