/**
 * FloatingPanel's sash (CUT-LIST-PANEL): a resizable panel says how far it
 * can go (`aria-valuemin`/`aria-valuemax`), and a frame too narrow for its
 * 640 px floor beside the 320 px tree shrinks the panel instead of letting it
 * run over the tree or out of the frame.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FloatingPanel, resizeBounds } from "./FloatingPanel";

const initialWidth = window.innerWidth;

function setFrame(width: number) {
  act(() => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: width,
    });
    window.dispatchEvent(new Event("resize"));
  });
}

afterEach(() => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: initialWidth,
  });
});

describe("resizeBounds", () => {
  it("floors at the token and ceils at the frame less the tree", () => {
    expect(resizeBounds(640, 1280)).toEqual({ floor: 640, ceiling: 936 });
    expect(resizeBounds(640, 984)).toEqual({ floor: 640, ceiling: 640 });
  });

  it("shrinks the floor in a frame too narrow for the panel and the tree", () => {
    expect(resizeBounds(640, 900)).toEqual({ floor: 556, ceiling: 556 });
    // Never below the inspector's 320, nor wider than the frame.
    expect(resizeBounds(640, 500)).toEqual({ floor: 320, ceiling: 320 });
    expect(resizeBounds(640, 300)).toEqual({ floor: 276, ceiling: 276 });
  });
});

describe("FloatingPanel resizable", () => {
  function renderPanel() {
    render(
      <FloatingPanel
        side="right"
        title="Cut list"
        id="cut-list"
        width="cut-list"
        resizable
      >
        <span>rows</span>
      </FloatingPanel>,
    );
    return screen.getByRole("separator", { name: "Resize Cut list" });
  }

  it("names its range and moves within it", () => {
    setFrame(1280);
    const sash = renderPanel();
    expect(sash).toHaveAttribute("aria-valuemin", "640");
    expect(sash).toHaveAttribute("aria-valuemax", "936");
    expect(sash).toHaveAttribute("aria-valuenow", "640");
    fireEvent.keyDown(sash, { key: "End" });
    expect(sash).toHaveAttribute("aria-valuenow", "936");
    const panel = sash.parentElement!;
    expect(panel.style.width).toBe("936px");
    fireEvent.keyDown(sash, { key: "Home" });
    expect(sash).toHaveAttribute("aria-valuenow", "640");
    expect(panel.style.width).toBe("");
  });

  it("narrows with a frame under 984 px, and a drag follows it", () => {
    setFrame(1280);
    const sash = renderPanel();
    fireEvent.keyDown(sash, { key: "End" });
    setFrame(900);
    expect(sash).toHaveAttribute("aria-valuemin", "556");
    expect(sash).toHaveAttribute("aria-valuemax", "556");
    expect(sash).toHaveAttribute("aria-valuenow", "556");
    expect(sash.parentElement!.style.width).toBe("556px");
    setFrame(1280);
    // The drag is remembered while the frame is wide enough for it.
    expect(sash).toHaveAttribute("aria-valuenow", "936");
  });
});
