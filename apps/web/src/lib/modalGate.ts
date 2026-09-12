/**
 * THE MODAL GATE — while a modal is open, it owns the keyboard. One thing,
 * consulted by nobody, forgettable by nobody.
 *
 * ## The defect this exists to delete
 *
 * W0 review, finding 1 (blocking): with the exit prompt open and the draw-
 * dimension strip armed behind it, Enter on the focused "Save sketch, then
 * leave" rung APPLIED THE DIMENSION instead of saving and leaving.
 * `SketchScene`'s session-wide window listener (FLOW-A1) guards only on
 * `isTypingTarget` — `INPUT | TEXTAREA | SELECT | contentEditable` — and a
 * `<button>` is none of those, so the listener ran while the dialog's own
 * button held focus and its `preventDefault()` cancelled the button's
 * activation. `Ctrl+Z` leaked the same way through `SketchStrip`, undoing in a
 * sketch the user had just been told they were leaving. The armed strip is
 * reached by the fix's OWN happy path: `drawFourEntities` ends with a placed
 * rectangle, and the committed FLOW-A2 screenshot shows the strip reading
 * *"Type a size · Tab switches · Enter applies"* behind the open dialog.
 *
 * ## Why this is not `stopPropagation()` in the modal
 *
 * A `stopPropagation()` in the panel's own `onKeyDown` closes the bubble-phase
 * leaks and nothing else: `FeatureTreePanel` already registers a window
 * listener with `capture: true`, which runs BEFORE the event ever reaches the
 * panel. And a per-listener guard is a rule every future listener has to
 * remember — this repo has paid five times for a check that could not observe
 * its subject.
 *
 * ## The mechanism
 *
 * One capture-phase `keydown`/`keypress` listener on `window`, installed when
 * this module is evaluated — which is before any component's effect can run,
 * because effects run after mount and module evaluation happens on import. It
 * does nothing at all until a layer is open. While one is:
 *
 *   1. `stopImmediatePropagation()`, unconditionally. `window` is the FIRST
 *      target in the capture path, so this is the earliest point the platform
 *      offers, and nothing downstream — other window listeners, document
 *      listeners, React's root-container delegation, the element's own
 *      handlers — is reachable. There is no gate for a future listener to
 *      consult and therefore nothing for it to forget.
 *   2. Hand the event to the top layer, which is the only thing still allowed
 *      to act on it. The layer is told whether the key landed inside its own
 *      panel, so it can distinguish its own Tab trap from a stray key arriving
 *      from somewhere focus should never have been.
 *
 * DEFAULT ACTIONS ARE UNTOUCHED, and that is the half that makes this safe:
 * stopping propagation does not cancel a default action, so Enter on a focused
 * button still fires its click, typing into a field inside the modal still
 * inserts characters, and only the modal decides whether to `preventDefault()`.
 *
 * `keyup` is deliberately NOT shielded. `SketchScene` keeps live modifier
 * state from keydown/keyup pairs; swallowing the release of a Shift that was
 * pressed before the modal opened would leave the sketcher believing a
 * modifier is held. A keyup runs no command anywhere in this app, so letting
 * it through costs nothing and keeps that bookkeeping truthful.
 *
 * ## How it fails loudly
 *
 * Consultation is automatic, so the failure this has to catch is not "a
 * listener forgot" but "the shield stopped being first, or stopped being
 * installed" — a module-eval-order change, a stray `removeEventListener`, a
 * future listener registered at module scope ahead of this one. So every time
 * a layer opens, {@link verifyGateOwnsTheKeyboard} dispatches ONE synthetic
 * keydown with three probe listeners attached at the places a leaked event
 * would have to pass — window capture, document capture, window bubble, all
 * registered after the shield and therefore last in their phases. If any of
 * them sees the probe, the shield did not stop it, and the gate throws in dev
 * (and `console.error`s in production) naming the leak instead of silently
 * handing the keyboard back to the workspace. A second, independently derived
 * reading is what turns a wrong answer into a legible one.
 *
 * What the probe CANNOT see, said out loud: a capture listener registered on
 * `window` before this module is evaluated would run ahead of the shield and
 * is invisible to any probe we can write. No component can be that listener —
 * they all register inside effects — so the residual is a future module-scope
 * registration, and the doc comment above is the only control for it.
 */
import { useEffect, useLayoutEffect, useRef } from "react";
import type { RefObject } from "react";

/** A key no user has and no handler acts on — the probe's own signature. */
const PROBE_KEY = "ModalGateProbe";

export interface ModalLayer {
  /** Who opened it — named in the failure message, not shown to the user. */
  name: string;
  /** The panel, read at event time: it does not exist when the layer opens. */
  element: () => HTMLElement | null;
  /**
   * Every shielded key, while this is the top layer. `insidePanel` is false
   * when focus has escaped the dialog — the modal, not the gate, decides what
   * that means.
   */
  onKeyDown: (event: KeyboardEvent, insidePanel: boolean) => void;
}

const layers: ModalLayer[] = [];
/** True only for the duration of the self-probe: deliver to nobody. */
let probing = false;
let installed = false;

/** Is a modal holding the keyboard right now? */
export function isModalOpen(): boolean {
  return layers.length > 0;
}

/** The layer that owns the keyboard — the most recently opened one. */
function topLayer(): ModalLayer | undefined {
  return layers[layers.length - 1];
}

function shield(event: Event): void {
  if (layers.length === 0) return;
  // THE GATE. Everything else in the app is downstream of this line.
  event.stopImmediatePropagation();
  if (probing) return;
  const layer = topLayer();
  if (layer === undefined) return;
  if (!(event instanceof KeyboardEvent)) return;
  const panel = layer.element();
  const target = event.target;
  const insidePanel =
    panel !== null && target instanceof Node && panel.contains(target);
  layer.onKeyDown(event, insidePanel);
}

/**
 * Install the shield. Idempotent, and called at module evaluation so it is
 * ahead of every listener any component registers in an effect.
 */
export function installModalGate(): void {
  if (installed) return;
  if (typeof window === "undefined") return;
  installed = true;
  window.addEventListener("keydown", shield, true);
  window.addEventListener("keypress", shield, true);
}

installModalGate();

/**
 * Take the shield off. THIS EXISTS FOR THE GATE'S OWN TEST AND NOTHING ELSE:
 * the only way to prove the self-probe below can actually fail is to break the
 * thing it watches. A gate whose alarm has never been heard is a gate nobody
 * knows the state of.
 */
export function uninstallModalGateForTest(): void {
  if (typeof window === "undefined") return;
  window.removeEventListener("keydown", shield, true);
  window.removeEventListener("keypress", shield, true);
  installed = false;
}

function verifyGateOwnsTheKeyboard(layer: ModalLayer): void {
  if (typeof window === "undefined") return;
  const leaks: string[] = [];
  const atWindowCapture = () => leaks.push("a window capture-phase listener");
  const atDocumentCapture = () =>
    leaks.push("a document capture-phase listener");
  const atWindowBubble = () => leaks.push("a window bubble-phase listener");
  window.addEventListener("keydown", atWindowCapture, true);
  document.addEventListener("keydown", atDocumentCapture, true);
  window.addEventListener("keydown", atWindowBubble);
  probing = true;
  try {
    const target = layer.element() ?? document.body;
    target.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: PROBE_KEY,
        bubbles: true,
        cancelable: true,
      }),
    );
  } finally {
    probing = false;
    window.removeEventListener("keydown", atWindowCapture, true);
    document.removeEventListener("keydown", atDocumentCapture, true);
    window.removeEventListener("keydown", atWindowBubble);
  }
  if (leaks.length === 0) return;
  const message =
    `modal gate: "${layer.name}" is open but a keystroke still reached ` +
    `${leaks.join(", ")}. The window-capture shield in lib/modalGate.ts is ` +
    `no longer first — every global shortcut in the app can fire behind this ` +
    `modal (W0 review finding 1). Check that modalGate is evaluated before ` +
    `any module-scope keyboard listener.`;
  if (import.meta.env.DEV) throw new Error(message);
  console.error(message);
}

/**
 * Open a layer. Returns the close — call it exactly once; a second call is a
 * no-op rather than a pop of somebody else's layer.
 */
export function openModalLayer(layer: ModalLayer): () => void {
  // NOT re-installed here on purpose: module evaluation is the one install
  // point, and re-adding the shield at open time would put it LAST in the
  // capture order behind every listener registered since — the exact failure
  // the probe below is watching for, introduced by the code meant to prevent
  // it. The probe verifies the one install instead.
  layers.push(layer);
  try {
    verifyGateOwnsTheKeyboard(layer);
  } catch (failure) {
    // A gate that has lost the keyboard must not also leave a layer holding it:
    // the caller is about to unwind, and a layer nobody can close would shield
    // every keystroke in the app for the rest of the page's life.
    const at = layers.indexOf(layer);
    if (at !== -1) layers.splice(at, 1);
    throw failure;
  }
  let closed = false;
  return () => {
    if (closed) return;
    closed = true;
    const at = layers.indexOf(layer);
    if (at !== -1) layers.splice(at, 1);
  };
}

/**
 * React's way in: a modal declares its panel and its key handling, and holds
 * the keyboard for as long as it is mounted.
 *
 * The handler is held in a ref so a modal re-rendering (a save starting, an
 * error arriving) never pops and re-pushes its own layer — which would reorder
 * the stack under any modal opened above it.
 */
export function useModalLayer(
  name: string,
  panelRef: RefObject<HTMLElement | null>,
  onKeyDown: (event: KeyboardEvent, insidePanel: boolean) => void,
): void {
  const latest = useRef(onKeyDown);
  useLayoutEffect(() => {
    latest.current = onKeyDown;
  });
  useEffect(
    () =>
      openModalLayer({
        name,
        element: () => panelRef.current,
        onKeyDown: (event, insidePanel) => latest.current(event, insidePanel),
      }),
    [name, panelRef],
  );
}
