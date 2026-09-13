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
  activationKeyOwner,
  installModalGate,
  isModalOpen,
  liveGlobalKeyListeners,
  openModalLayer,
  resetModalGateAlarmForTest,
  uninstallModalGateForTest,
  useGlobalKeys,
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
  resetModalGateAlarmForTest();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
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

/**
 * THE W2 BLOCKING FINDING, in the shape a user meets it.
 *
 * The proposal note bound `window` in the capture phase with `preventDefault()`
 * and guarded only on `isTypingTarget`, so `Enter` on a focused BUTTON — the
 * key card's Close, the view rail's Fit, any band tool — accepted the offer and
 * cancelled the button's own activation.
 *
 * Every case below puts focus on a real `<button>` and dispatches a real key
 * event AT IT. A probe that dispatches on `document.body` passes against the
 * defect and proves nothing: `body` is not a control, so the claim never
 * applies and the old code looks correct.
 */
describe("the focused control's claim", () => {
  /** A window listener registered the way a feature would now register one. */
  function mountGlobal(
    handler: (event: KeyboardEvent) => void,
    options?: { capture?: boolean; whileTyping?: boolean },
  ) {
    function Listener() {
      useGlobalKeys("a workspace shortcut", handler, options);
      return null;
    }
    return render(<Listener />);
  }

  function focusedButton(): HTMLButtonElement {
    const button = document.body.appendChild(document.createElement("button"));
    button.textContent = "Fit";
    button.focus();
    return button;
  }

  function press(target: HTMLElement, key: string): KeyboardEvent {
    const event = new KeyboardEvent("keydown", {
      key,
      bubbles: true,
      cancelable: true,
    });
    target.dispatchEvent(event);
    return event;
  }

  it("keeps Enter for the button the user is standing on", () => {
    const accept = vi.fn();
    mountGlobal(
      (event) => {
        event.preventDefault();
        accept();
      },
      { capture: true },
    );
    const button = focusedButton();
    const clicked = vi.fn();
    button.addEventListener("click", clicked);

    const event = press(button, "Enter");

    expect(
      accept,
      "the global shortcut took Enter from a focused button",
    ).not.toHaveBeenCalled();
    // …and nothing cancelled the button's activation, which is the half the
    // user actually sees: jsdom does not synthesise the click, so the assertion
    // is on the cancellation rather than on the click itself.
    expect(event.defaultPrevented).toBe(false);
    expect(clicked).not.toHaveBeenCalled();
  });

  it("keeps Space too, and Enter on a link", () => {
    const fired = vi.fn();
    mountGlobal(fired);
    const button = focusedButton();
    press(button, " ");
    const link = document.body.appendChild(document.createElement("a"));
    link.href = "#somewhere";
    link.focus();
    press(link, "Enter");
    expect(fired).not.toHaveBeenCalled();
    // A link does NOT activate on Space, so the workspace may have that one.
    press(link, " ");
    expect(fired).toHaveBeenCalledTimes(1);
  });

  it("claims a role=button that is not a <button> at all", () => {
    // `components/DrawingSheet.tsx` draws several as SVG `<g>`s. From the
    // keyboard they are buttons, so they answer for Enter the same way.
    const fired = vi.fn();
    mountGlobal(fired);
    const control = document.body.appendChild(document.createElement("div"));
    control.setAttribute("role", "button");
    control.tabIndex = 0;
    control.focus();
    press(control, "Enter");
    expect(fired).not.toHaveBeenCalled();
  });

  it("does NOT claim a letter, so tool shortcuts still work from a button", () => {
    // The negative control, and the reason the cases above can fail: if the
    // seam swallowed everything while a button had focus, "the handler did not
    // run" would be true of a seam that had simply stopped working. It is also
    // the behaviour we want — `E` opens Extrude wherever focus happens to be.
    const fired = vi.fn();
    mountGlobal(fired);
    press(focusedButton(), "e");
    expect(fired).toHaveBeenCalledTimes(1);
  });

  it("stands down when its surface is not on screen", () => {
    const fired = vi.fn();
    function Listener({ armed }: { armed: boolean }) {
      useGlobalKeys("an ambient note", armed ? fired : null);
      return null;
    }
    const view = render(<Listener armed={false} />);
    press(document.body, "e");
    expect(fired).not.toHaveBeenCalled();
    expect(liveGlobalKeyListeners()).not.toContain("an ambient note");

    view.rerender(<Listener armed />);
    expect(liveGlobalKeyListeners()).toContain("an ambient note");
    press(document.body, "e");
    expect(fired).toHaveBeenCalledTimes(1);

    view.unmount();
    press(document.body, "e");
    expect(fired).toHaveBeenCalledTimes(1);
    expect(liveGlobalKeyListeners()).not.toContain("an ambient note");
  });

  it("bails on a typing target and on an already-handled key", () => {
    const fired = vi.fn();
    mountGlobal(fired);
    const field = document.body.appendChild(document.createElement("input"));
    field.focus();
    press(field, "e");
    expect(fired).not.toHaveBeenCalled();

    const handled = new KeyboardEvent("keydown", {
      key: "e",
      bubbles: true,
      cancelable: true,
    });
    handled.preventDefault();
    document.body.dispatchEvent(handled);
    expect(fired).not.toHaveBeenCalled();
  });

  it("answers with the control itself, so a caller can say which one", () => {
    const button = focusedButton();
    const event = new KeyboardEvent("keydown", { key: "Enter" });
    Object.defineProperty(event, "target", { value: button });
    expect(activationKeyOwner(event)).toBe(button);
  });
});

describe("the unheld-modal alarm", () => {
  function keyDownOnTheWorkspace(): void {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "e", bubbles: true }),
    );
  }

  function openDialog(testid: string): HTMLElement {
    const dialog = document.body.appendChild(document.createElement("div"));
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("data-testid", testid);
    return dialog;
  }

  it("names a dialog that claims aria-modal and holds no layer", () => {
    const complaint = vi.spyOn(console, "error").mockImplementation(() => {});
    openDialog("shortcut-sheet");

    keyDownOnTheWorkspace();

    expect(complaint).toHaveBeenCalledTimes(1);
    expect(complaint.mock.calls[0]?.[0]).toContain("shortcut-sheet");
    expect(document.documentElement.getAttribute("data-modal-gate-leak")).toBe(
      "shortcut-sheet",
    );
    // Once per offender: a per-keystroke flood is a thing people mute.
    keyDownOnTheWorkspace();
    expect(complaint).toHaveBeenCalledTimes(1);
  });

  it("is silent once that dialog holds the keyboard", () => {
    const complaint = vi.spyOn(console, "error").mockImplementation(() => {});
    const dialog = openDialog("shortcut-sheet");
    open(dialog);
    keyDownOnTheWorkspace();
    expect(complaint).not.toHaveBeenCalled();
    expect(document.documentElement.hasAttribute("data-modal-gate-leak")).toBe(
      false,
    );
  });

  it("is silent when nothing claims to be modal", () => {
    const complaint = vi.spyOn(console, "error").mockImplementation(() => {});
    document.body.appendChild(document.createElement("div"));
    keyDownOnTheWorkspace();
    expect(complaint).not.toHaveBeenCalled();
  });
});
