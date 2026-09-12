/**
 * THE GATE, AND THE PROOF THAT IT CAN FAIL.
 *
 * W0 review finding 1: with the exit prompt open, `SketchScene`'s session-wide
 * window listener still ran on Enter and applied the armed draw dimension
 * instead of letting the focused button fire. The listeners in question are
 * ordinary `window.addEventListener("keydown", …)` calls — one of them in the
 * CAPTURE phase — so every case here registers exactly that and asserts it is
 * never called, which is the shape of the real leak rather than a stand-in.
 *
 * The spies are attached AFTER this module imports the gate, i.e. after the
 * shield is installed, which is the position every listener in the app is in:
 * they all register inside effects.
 */
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  installModalGate,
  isModalOpen,
  openModalLayer,
  uninstallModalGateForTest,
  useModalLayer,
} from "./modalGate";

interface Spies {
  windowCapture: ReturnType<typeof vi.fn>;
  windowBubble: ReturnType<typeof vi.fn>;
  documentCapture: ReturnType<typeof vi.fn>;
  release: () => void;
}

/** The three positions a workspace shortcut is registered in, in this app. */
function spyOnTheWorkspace(): Spies {
  const windowCapture = vi.fn();
  const windowBubble = vi.fn();
  const documentCapture = vi.fn();
  window.addEventListener("keydown", windowCapture, true);
  window.addEventListener("keydown", windowBubble);
  document.addEventListener("keydown", documentCapture, true);
  return {
    windowCapture,
    windowBubble,
    documentCapture,
    release: () => {
      window.removeEventListener("keydown", windowCapture, true);
      window.removeEventListener("keydown", windowBubble);
      document.removeEventListener("keydown", documentCapture, true);
    },
  };
}

function pressEnterOn(target: HTMLElement): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key: "Enter",
    bubbles: true,
    cancelable: true,
  });
  target.dispatchEvent(event);
  return event;
}

const opened: Array<() => void> = [];

function open(panel: HTMLElement | null, onKeyDown = vi.fn()) {
  const close = openModalLayer({
    name: "test layer",
    element: () => panel,
    onKeyDown,
  });
  opened.push(close);
  return { close, onKeyDown };
}

afterEach(() => {
  for (const close of opened.splice(0)) close();
  installModalGate();
  document.body.innerHTML = "";
});

describe("the modal gate", () => {
  it("lets the workspace have its keys when no modal is open", () => {
    // THE NEGATIVE CONTROL, and the reason every other case here can fail: if
    // the spies could not see a keystroke at all, "the spies never fired" would
    // be true of a gate that does nothing.
    const spies = spyOnTheWorkspace();
    const button = document.body.appendChild(document.createElement("button"));
    pressEnterOn(button);
    spies.release();
    expect(spies.windowCapture).toHaveBeenCalledTimes(1);
    expect(spies.windowBubble).toHaveBeenCalledTimes(1);
    expect(spies.documentCapture).toHaveBeenCalledTimes(1);
    expect(isModalOpen()).toBe(false);
  });

  it("takes the keyboard away from every listener while a modal is open", () => {
    const spies = spyOnTheWorkspace();
    const panel = document.body.appendChild(document.createElement("div"));
    const button = panel.appendChild(document.createElement("button"));
    const { onKeyDown } = open(panel);

    pressEnterOn(button);

    spies.release();
    // Finding 1, in the three places the leak can live. The capture-phase spy
    // is the one a `stopPropagation()` inside the modal could never have
    // stopped — `FeatureTreePanel` registers exactly that.
    expect(spies.windowCapture).not.toHaveBeenCalled();
    expect(spies.windowBubble).not.toHaveBeenCalled();
    expect(spies.documentCapture).not.toHaveBeenCalled();
    // …and the modal did get it, with the key landing on its own panel.
    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onKeyDown.mock.calls[0]?.[1]).toBe(true);
  });

  it("leaves the button's own activation alone", () => {
    // The gate stops PROPAGATION, never the default action: Enter on a focused
    // button must still fire its click. A gate that called preventDefault()
    // would reproduce finding 1 from the other side.
    const panel = document.body.appendChild(document.createElement("div"));
    const button = panel.appendChild(document.createElement("button"));
    open(panel);
    expect(pressEnterOn(button).defaultPrevented).toBe(false);
  });

  it("tells the modal when a key arrived from outside its panel", () => {
    const panel = document.body.appendChild(document.createElement("div"));
    const stray = document.body.appendChild(document.createElement("input"));
    const { onKeyDown } = open(panel);
    pressEnterOn(stray);
    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onKeyDown.mock.calls[0]?.[1]).toBe(false);
  });

  it("hands the keyboard back when the modal closes", () => {
    const spies = spyOnTheWorkspace();
    const panel = document.body.appendChild(document.createElement("div"));
    const { close } = open(panel);
    close();
    pressEnterOn(panel);
    spies.release();
    expect(spies.windowCapture).toHaveBeenCalledTimes(1);
    expect(isModalOpen()).toBe(false);
  });

  it("does not swallow keyup, so modifier bookkeeping stays truthful", () => {
    // Deliberate exception, documented in the module: SketchScene tracks live
    // Shift/Ctrl state from keydown/keyup pairs, and eating the release would
    // leave the sketcher believing a modifier is still held.
    const seen = vi.fn();
    window.addEventListener("keyup", seen, true);
    const panel = document.body.appendChild(document.createElement("div"));
    open(panel);
    panel.dispatchEvent(
      new KeyboardEvent("keyup", { key: "Shift", bubbles: true }),
    );
    window.removeEventListener("keyup", seen, true);
    expect(seen).toHaveBeenCalledTimes(1);
  });

  it("the top layer owns the keyboard when two are open", () => {
    const first = vi.fn();
    const second = vi.fn();
    const panel = document.body.appendChild(document.createElement("div"));
    open(panel, first);
    open(panel, second);
    pressEnterOn(panel);
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
  });

  it("THROWS when the shield is no longer first — the loud failure", () => {
    // The alarm, proven by breaking the thing it watches. Without this case the
    // probe would be a gate that has never been heard: it would report a
    // healthy gate forever, including after someone deleted the shield.
    uninstallModalGateForTest();
    const panel = document.body.appendChild(document.createElement("div"));
    expect(() => open(panel)).toThrowError(/modal gate/);
    installModalGate();
  });

  it("holds the keyboard for as long as the component is mounted", () => {
    const spies = spyOnTheWorkspace();
    const seen: Array<[string, boolean]> = [];
    function Modal() {
      const ref = { current: null } as { current: HTMLDivElement | null };
      useModalLayer("component layer", ref, (event, inside) =>
        seen.push([event.key, inside]),
      );
      return <div ref={ref} data-testid="panel" />;
    }
    const view = render(<Modal />);
    pressEnterOn(view.getByTestId("panel"));
    expect(seen).toEqual([["Enter", true]]);
    view.unmount();
    pressEnterOn(document.body);
    spies.release();
    // One keystroke reached the workspace: the one after unmount.
    expect(spies.windowCapture).toHaveBeenCalledTimes(1);
    expect(seen).toHaveLength(1);
  });
});
