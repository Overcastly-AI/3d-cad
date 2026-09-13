/**
 * WHO OWNS THIS KEYSTROKE — the one module that answers it, for every surface.
 *
 * It holds three answers, in descending strength, and nothing else in the app
 * may hold a fourth:
 *
 *   1. **A MODAL LAYER** ({@link useModalLayer}) — while one is open it owns
 *      every key, enforced by a window-capture shield that stops the event dead
 *      before any other listener exists. Consultation is automatic, so there is
 *      nothing for a future listener to forget.
 *   2. **THE FOCUSED CONTROL** ({@link activationKeyOwner}) — `Enter`/`Space`
 *      on a focused button, link or `[role=button]` belong to that control, not
 *      to a global shortcut. This one CANNOT be enforced by the shield (see the
 *      "why the second answer is a seam, not a shield" section below), so it is
 *      enforced at the registration seam instead.
 *   3. **THE WORKSPACE** — everything else, through {@link useGlobalKeys},
 *      which is how a window-level shortcut gets 1 and 2 for free.
 *
 * W2 review, blocking finding: `viewport/ProposalNote.tsx` bound `keydown` on
 * `window` with `{ capture: true }` and `preventDefault()`, guarded only by
 * `isTypingTarget`. Pressing `?` for the key card and then `E` — the row the
 * card itself teaches — opened the Extrude editor BEHIND the open sheet; and
 * `Enter` on a focused button (the sheet's own Close, the view rail's Fit, any
 * band tool) accepted the proposal and cancelled the button's activation, so
 * the control the user was standing on did nothing. Both are this file's
 * subject, and both had already been fixed here once for the exit prompt: the
 * gate worked, but `useModalLayer` had exactly ONE caller in app code, so the
 * general fix had generalised to one surface.
 *
 * ## Why the second answer is a seam, not a shield
 *
 * The obvious move is to extend the shield: claim `Enter`/`Space` for the
 * focused control and `stopImmediatePropagation()`. Measured, that trades a
 * keyboard theft for a keyboard BREAK. Stopping propagation at window capture
 * also stops React's root delegation, so it silences the control's OWN handlers
 * and those of every ancestor — and two real ones would go with it:
 * `packages/design`'s `Flyout` trigger implements `Enter`/`Space` in its React
 * `onKeyDown`, and every feature editor puts Enter-applies on the FORM, which a
 * focused button inside it (`Cut`, `Cancel`) legitimately fires through. Those
 * ancestors are in the control's own context and are exactly the code that
 * SHOULD run. A window-level listener that has never heard of the control is
 * not, and that is the distinction the shield cannot draw but a registration
 * seam can.
 *
 * So: forgetting is made loud rather than impossible here. `useGlobalKeys` is
 * the easy path (it is shorter than the raw listener it replaces), and
 * `modalGate.audit.test.ts` walks `apps/web/src` for raw `addEventListener
 * ("keydown")` calls and fails naming any file that is not on its list.
 *
 * ## The modal gate proper — the defect it exists to delete
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

import { isTypingTarget } from "./isTypingTarget";

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
  if (layers.length === 0) {
    if (event.type === "keydown") warnAboutUnheldModals();
    return;
  }
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
 * THE ALARM FOR THE FAILURE THE PROBE ABOVE CANNOT SEE: a surface that says it
 * is modal and never took the keyboard.
 *
 * `verifyGateOwnsTheKeyboard` watches the shield. It has nothing to say about a
 * dialog that simply never registered — which is the W2 blocking finding, and
 * which had been true of `ShortcutSheet` since the day it shipped: `role=
 * "dialog" aria-modal="true"` on screen, every workspace shortcut still live
 * behind it. Nothing in the DOM, the tests or the types objected.
 *
 * `aria-modal="true"` is the element's own promise that everything outside it
 * is inert. So the moment a keystroke is about to reach the workspace while
 * such an element is in the document, that promise is being broken, and this
 * says so by name. It runs only when NO layer is open (i.e. only when the
 * promise can be broken), and reports each offender once — a per-keystroke
 * console flood is a thing people mute.
 *
 * It does not throw: this runs inside a live event dispatch, where a throw is
 * swallowed by the browser's dispatch loop and reports nothing useful. It
 * `console.error`s and stamps `<html data-modal-gate-leak>` so a Playwright
 * spec, a screenshot and a developer's console all show the same fact.
 */
const reported = new Set<string>();

function warnAboutUnheldModals(): void {
  if (typeof document === "undefined") return;
  const claimant = document.querySelector('[aria-modal="true"]');
  if (claimant === null) {
    // The stamp tracks the CURRENT state, so a fixed (or merely closed) dialog
    // clears it — a stale marker is a false alarm a spec would have to learn to
    // ignore, which is how an alarm stops being one.
    document.documentElement.removeAttribute("data-modal-gate-leak");
    return;
  }
  const name =
    claimant.getAttribute("data-testid") ??
    claimant.getAttribute("aria-label") ??
    claimant.tagName.toLowerCase();
  document.documentElement.setAttribute("data-modal-gate-leak", name);
  if (reported.has(name)) return;
  reported.add(name);
  console.error(
    `modal gate: "${name}" is on screen with aria-modal="true" but holds no ` +
      `keyboard layer, so every workspace shortcut is still live behind it ` +
      `(W2 review, blocking finding). Call useModalLayer() in that component, ` +
      `or drop the aria-modal claim if it is not modal.`,
  );
}

/** The gate's own test seam: forget what has already been reported. */
export function resetModalGateAlarmForTest(): void {
  reported.clear();
  if (typeof document !== "undefined") {
    document.documentElement.removeAttribute("data-modal-gate-leak");
  }
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

// --- THE FOCUSED CONTROL, AND THE SEAM EVERY GLOBAL SHORTCUT REGISTERS THROUGH

/**
 * Controls the keyboard activates with `Enter` OR `Space`.
 *
 * Both the native elements and the ARIA ones, because the question this answers
 * is "would the user expect this keystroke to press the thing they are standing
 * on", and a `[role=button]` promises exactly that to a screen-reader user —
 * `components/DrawingSheet.tsx` draws several as SVG `<g>`s with their own key
 * handlers. Splitting native from ARIA here would answer differently for two
 * controls that look identical from the keyboard.
 */
const ACTIVATES_ON_ENTER_OR_SPACE = [
  "button",
  "summary",
  'input[type="button"]',
  'input[type="submit"]',
  'input[type="reset"]',
  'input[type="checkbox"]',
  'input[type="radio"]',
  '[role="button"]',
  '[role="menuitem"]',
  '[role="menuitemcheckbox"]',
  '[role="menuitemradio"]',
  '[role="tab"]',
  '[role="switch"]',
  '[role="checkbox"]',
  '[role="radio"]',
  '[role="option"]',
].join(",");

/** …and the ones only `Enter` presses. A link does nothing on `Space`. */
const ACTIVATES_ON_ENTER = ["a[href]", '[role="link"]'].join(",");

/** `Space` as the three spellings a browser or a test may send it in. */
const SPACE = new Set([" ", "Spacebar", "Space"]);

/**
 * The control this keystroke belongs to, or null when it belongs to nobody in
 * particular and a global shortcut may have it.
 *
 * ONLY the activation keys are claimed. A letter is not: pressing `E` with the
 * Fit button focused should still open Extrude, the way every keyboard-driven
 * tool behaves — `Enter` and `Space` are the two the focused control is
 * already promising to answer, and taking those is what makes a button look
 * broken.
 *
 * `closest` rather than an equality test, so a control whose inner span somehow
 * holds focus still answers for it; and `Element`, not `HTMLElement`, because
 * an SVG `<g role="button">` is a control too.
 */
export function activationKeyOwner(event: KeyboardEvent): Element | null {
  const target = event.target;
  if (!(target instanceof Element)) return null;
  if (event.key === "Enter" || SPACE.has(event.key)) {
    const control = target.closest(ACTIVATES_ON_ENTER_OR_SPACE);
    if (control !== null) return control;
  }
  if (event.key !== "Enter") return null;
  return target.closest(ACTIVATES_ON_ENTER);
}

/** Live global listeners, by name — diagnostics, and what the audit test reads. */
const globalListeners = new Map<string, number>();

/** Who is listening on the window right now. */
export function liveGlobalKeyListeners(): readonly string[] {
  return [...globalListeners.keys()].sort();
}

export interface GlobalKeysOptions {
  /**
   * Capture phase. Needed only where a listener must run BEFORE a bubble-phase
   * one that claims the same key — the proposal note does, because
   * `PartPage`'s create-shortcut opener reads `event.defaultPrevented`.
   */
  capture?: boolean;
  /**
   * Act even while a text control has focus. Off by default; `Escape` clearing
   * the register's own filter field is the case that needs it.
   */
  whileTyping?: boolean;
}

/**
 * REGISTER A WINDOW-LEVEL SHORTCUT — the only way this app should.
 *
 * Pass `null` as the handler to stand down: a listener that is registered while
 * its surface is not on screen is a listener that acts when its surface is not
 * on screen.
 *
 * What it refuses before your handler runs, so that no caller has to remember:
 *
 *  · a key another handler has already cancelled (`defaultPrevented`);
 *  · a key being typed into a text control, unless `whileTyping`;
 *  · `Enter`/`Space` aimed at a focused button, link or `[role=button]`
 *    ({@link activationKeyOwner}) — the W2 blocking finding.
 *
 * A modal layer needs no mention here: the shield at the top of this file has
 * already stopped the event, so this never runs behind one.
 */
export function useGlobalKeys(
  name: string,
  onKeyDown: ((event: KeyboardEvent) => void) | null,
  options: GlobalKeysOptions = {},
): void {
  const { capture = false, whileTyping = false } = options;
  // The handler is held in a ref so a re-render never re-registers the
  // listener: a listener that unregisters and re-registers as state moves is
  // how one ends up absent at the moment it is needed.
  const latest = useRef(onKeyDown);
  useLayoutEffect(() => {
    latest.current = onKeyDown;
  });
  const armed = onKeyDown !== null;
  useEffect(() => {
    if (!armed) return;
    globalListeners.set(name, (globalListeners.get(name) ?? 0) + 1);
    const handle = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (!whileTyping && isTypingTarget(event.target)) return;
      if (activationKeyOwner(event) !== null) return;
      latest.current?.(event);
    };
    window.addEventListener("keydown", handle, { capture });
    return () => {
      window.removeEventListener("keydown", handle, { capture });
      const live = (globalListeners.get(name) ?? 1) - 1;
      if (live <= 0) globalListeners.delete(name);
      else globalListeners.set(name, live);
    };
  }, [armed, capture, name, whileTyping]);
}
