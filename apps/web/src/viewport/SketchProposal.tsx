/**
 * THE SKETCH PROPOSAL — "you can sketch on this face", offered where the
 * pointer already is (FLOW-1, founder report 2026-08-14).
 *
 * The complaint it answers: starting a sketch made you name the VERB before the
 * NOUN. Click Sketch, then hunt for the face — the opposite order from the one
 * a modeller is thinking in, every single time. Fusion lets you rest on a face
 * and go. This is that, and it routes through the SAME `authorFacePlane` call
 * the toolbar's Sketch -> pick-a-face flow makes, so the two cannot drift into
 * producing different planes for the same face.
 *
 * Three decisions worth stating, because each one is a way this could have gone
 * wrong:
 *
 * 1. **The face's own hover tint carries the proposal; this only confirms it.**
 *    SEL-1 already lights the single face under the cursor. Adding a second
 *    highlight would have been the loud, viewport-fighting answer. All that was
 *    missing was somewhere to click, so that is all this adds.
 *
 * 2. **It is written on REST, not on hover.** The pointer must stop for
 *    `proposal.dwellMs` before the note appears, so sweeping the model proposes
 *    nothing at all and a note only ever arrives where attention already
 *    stopped. Once written it STAYS PUT while the face is held — a target that
 *    keeps moving as you reach for it is hostile, and re-arming on every twitch
 *    would make the chip flicker exactly when the user is trying to hit it.
 *
 * 3. **It proposes; it does not select.** Nothing is committed by hovering,
 *    nothing is remembered, and it disappears the moment the pointer moves on.
 *    The only state it can change is behind an explicit click or Enter.
 *
 * The KEYBOARD path is not this component: the Sketch command's face overlay
 * puts a focusable, named `PickNode` on every planar face, which is a better
 * keyboard affordance than aiming ever is. What this adds for the keyboard is
 * `Enter` to accept the showing proposal without travelling to the chip — and
 * the chip prints the glyph, so the mouse teaches the keyboard.
 */
import {
  color,
  Kbd,
  proposal as proposalTokens,
  SketchIcon,
} from "@loft/design";
import { useCallback, useEffect, useRef, useState } from "react";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel } from "../features/face";
import { KEY_ACCEPT_PROPOSAL } from "../shortcuts/registry";
import { placeProposal, type ProposalPlacement } from "./sketchProposal";

/** A face that can actually carry a sketch — planar, so it has a signature. */
export type ProposableFace = OverlayFace & { signature: PlanarFaceSignature };

export interface SketchProposalProps {
  /**
   * May a proposal be offered at all — no command open, nothing armed, a body
   * on screen. SEPARATE from `face` on purpose: `face === null` is ambiguous
   * between "the pointer is not on a face right now" (which must NOT withdraw
   * a written note — see the latch below) and "proposals are off entirely"
   * (which must withdraw it at once). One boolean makes the difference
   * explicit rather than inferred.
   */
  enabled: boolean;
  /**
   * The face the pointer is addressing, already resolved to a PICKABLE one, or
   * null when the pointer addresses nothing a sketch could sit on. Resolving it
   * upstream is deliberate: a note offered over a cylindrical face would be a
   * dead end, and this component should not be the thing that knows that.
   */
  face: ProposableFace | null;
  /** Accept — the same call the toolbar's face pick makes. */
  onAccept: (face: ProposableFace) => void;
}

/** A written note: the face it is about, where it sits, and in what frame. */
interface Note {
  face: ProposableFace;
  placement: ProposalPlacement;
  frame: { width: number; height: number };
}

export function SketchProposal({
  enabled,
  face,
  onAccept,
}: SketchProposalProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  /** Last pointer position in CLIENT coords — a ref, so moves never re-render. */
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  // The written note is read inside DOM listeners, which close over the render
  // that installed them; the ref is what keeps those listeners looking at the
  // CURRENT note instead of a stale one.
  const noteRef = useRef<Note | null>(null);
  const putNote = useCallback((next: Note | null) => {
    noteRef.current = next;
    setNote(next);
  }, []);

  const faceIndex = face?.index ?? null;
  /** The live face prop, for listeners installed before it changed. */
  const faceRef = useRef<ProposableFace | null>(face);
  faceRef.current = face;

  /** The viewport container — the box every coordinate here is relative to. */
  const containerOf = useCallback((): HTMLElement | null => {
    const root = rootRef.current;
    if (root === null) return null;
    return root.closest<HTMLElement>('[data-testid="viewport"]');
  }, []);

  /**
   * THE LEASH — is the pointer still with the note?
   *
   * This is the whole reason a written note LATCHES. The chip is DOM sitting
   * over the canvas, so the moment the pointer travels onto it, it leaves the
   * mesh and r3f fires `pointerout`: the addressed face goes null and a naive
   * implementation withdraws the note in the instant the user reaches for it.
   * Measured, not theorised — the first version did exactly that, and the e2e
   * click landed on empty space while every earlier assertion passed.
   *
   * So the note survives `face === null` while the pointer is on (or a whisker
   * from) the chip, and is withdrawn as soon as it is not.
   */
  const withinLeash = useCallback((at: { x: number; y: number } | null) => {
    const chip = chipRef.current;
    if (chip === null || at === null) return false;
    const box = chip.getBoundingClientRect();
    const slack = proposalTokens.offset;
    return (
      at.x >= box.left - slack &&
      at.x <= box.right + slack &&
      at.y >= box.top - slack &&
      at.y <= box.bottom + slack
    );
  }, []);

  // Always-on position recorder. Mounted independently of the dwell so that a
  // pointer which enters a face and STOPS DEAD still has a known position —
  // the dwell's own listener is installed after the face is known and would
  // miss the move that caused the hover.
  useEffect(() => {
    const container = containerOf();
    if (container === null) return;
    const record = (event: PointerEvent) => {
      pointer.current = { x: event.clientX, y: event.clientY };
    };
    container.addEventListener("pointermove", record, { capture: true });
    return () =>
      container.removeEventListener("pointermove", record, { capture: true });
  }, [containerOf]);

  // The dwell, and the latch. Re-runs when the addressed face changes or the
  // context opens/closes — never per pointer move.
  useEffect(() => {
    if (!enabled) {
      putNote(null);
      return;
    }
    const container = containerOf();
    if (container === null) return;

    const current = noteRef.current;
    if (current !== null) {
      if (faceIndex === current.face.index) {
        // Still resting on the note's own face: hold it exactly where it is. A
        // note that re-placed itself under a moving pointer would be a target
        // that runs away from the hand reaching for it.
      } else if (faceIndex !== null) {
        // A DIFFERENT face is addressed — the old note is about the wrong face.
        putNote(null);
      } else if (!withinLeash(pointer.current)) {
        // Off the body and not with the note: withdraw.
        putNote(null);
      }
    }

    let timer = 0;

    const write = () => {
      const at = pointer.current;
      const target = faceRef.current;
      if (at === null || target === null) return;
      const rect = container.getBoundingClientRect();
      putNote({
        face: target,
        frame: { width: rect.width, height: rect.height },
        placement: placeProposal(
          { x: at.x - rect.left, y: at.y - rect.top },
          { width: rect.width, height: rect.height },
        ),
      });
    };

    const onMove = () => {
      if (noteRef.current !== null) {
        // Written. Hold it while the pointer is on its face or on the note;
        // otherwise withdraw and let the next rest write a new one.
        if (
          faceRef.current?.index === noteRef.current.face.index ||
          withinLeash(pointer.current)
        ) {
          return;
        }
        putNote(null);
        return;
      }
      if (faceRef.current === null) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(write, proposalTokens.dwellMs);
    };

    // Any camera gesture invalidates a note anchored to a point on screen: the
    // face it describes is about to move out from under it.
    const dismiss = (event: Event) => {
      if (chipRef.current?.contains(event.target as Node) === true) return;
      window.clearTimeout(timer);
      putNote(null);
    };

    container.addEventListener("pointermove", onMove);
    container.addEventListener("pointerdown", dismiss);
    container.addEventListener("wheel", dismiss, { passive: true });
    if (noteRef.current === null && faceIndex !== null) {
      timer = window.setTimeout(write, proposalTokens.dwellMs);
    }
    return () => {
      window.clearTimeout(timer);
      container.removeEventListener("pointermove", onMove);
      container.removeEventListener("pointerdown", dismiss);
      container.removeEventListener("wheel", dismiss);
    };
  }, [enabled, faceIndex, containerOf, putNote, withinLeash]);

  const accept = useCallback(() => {
    const target = noteRef.current?.face ?? faceRef.current;
    if (target !== null && target !== undefined) onAccept(target);
  }, [onAccept]);

  // `Enter` accepts the SHOWING note. Gated on the placement rather than on the
  // hover, so the key is live exactly when the glyph on the chip is on screen —
  // one fact, not a second derivation that could disagree with the pixels.
  useEffect(() => {
    if (note === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== KEY_ACCEPT_PROPOSAL) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      event.preventDefault();
      accept();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [note, accept]);

  const placement = note?.placement ?? null;
  const frame = note?.frame ?? null;

  return (
    <div
      ref={rootRef}
      data-testid="sketch-proposal-layer"
      className="absolute left-0 top-0 h-0 w-0"
      // Inline rather than a class: this element is a DIRECT child of the HUD
      // layer, whose `[&>*]:pointer-events-auto` rule has the same specificity
      // as a plain utility would. An inline declaration is unambiguous, and
      // getting it wrong makes the whole viewport un-orbitable.
      style={{ pointerEvents: "none" }}
    >
      {note !== null && placement !== null && frame !== null ? (
        <>
          {/*
            THE LEADER — a drafting leader note, which is the one place this
            affordance spends any boldness. The dot marks the exact point the
            note is about; the stub ties the chip to it, so the chip reads as an
            annotation ON the face rather than chrome floating over the scene.
            Frame-sized so its coordinates ARE frame coordinates, and inert.

            There is no entry animation, deliberately. The dwell already gives
            the note its deliberate arrival; a fade on top would be motion for
            its own sake, and the one thing worse than an affordance that shouts
            is one that shouts twice.
          */}
          <svg
            aria-hidden
            width={frame.width}
            height={frame.height}
            className="absolute left-0 top-0 text-brass"
            style={{ pointerEvents: "none" }}
          >
            {/*
              TWO-TONE, exactly as `PickNode`'s reticle — and for the leader
              this is load-bearing, not styling. A single brass hairline reads
              on the dark bench and all but vanishes on a lit aluminium face,
              which is precisely where a note about a FACE spends its life.
              Measured on the 1280x800 founder capture: at one tone the stub
              was invisible over the top face, and a leader nobody can see is
              the "chrome that only decorates" defect rather than the structure
              it is supposed to be. The dark casing goes down first, the brass
              core on top, so the line survives either ground.
            */}
            <line
              x1={placement.leader.x1}
              y1={placement.leader.y1}
              x2={placement.leader.x2}
              y2={placement.leader.y2}
              stroke={color.carbide}
              strokeWidth={3}
              strokeLinecap="round"
              opacity={0.55}
            />
            <line
              x1={placement.leader.x1}
              y1={placement.leader.y1}
              x2={placement.leader.x2}
              y2={placement.leader.y2}
              stroke="currentColor"
              strokeWidth={1.25}
              strokeLinecap="round"
            />
            {/* The anchor: the exact point on the face the note is about. */}
            <circle
              cx={placement.leader.x1}
              cy={placement.leader.y1}
              r={3.5}
              fill={color.carbide}
              opacity={0.7}
            />
            <circle
              cx={placement.leader.x1}
              cy={placement.leader.y1}
              r={2}
              fill="currentColor"
            />
          </svg>
          <button
            ref={chipRef}
            type="button"
            data-testid="sketch-proposal"
            // The NOTE's face, not whatever the pointer happens to address now:
            // once written, the note is a statement about one specific face and
            // must keep naming it while the pointer travels onto the chip.
            data-face-index={note.face.index}
            aria-label={`Sketch on ${faceLabel(note.face.index, note.face.signature)}`}
            onClick={accept}
            className={[
              // Sized from the token the placement maths flips against, so the
              // box on screen and the arithmetic are the same number.
              "absolute flex h-proposal w-proposal min-h-target-dense items-center gap-1.5",
              "border border-hairline bg-anvil/90 px-2 shadow-float backdrop-blur-sm",
              "text-brass transition-colors duration-fast",
              "hover:border-brass hover:bg-anvil hover:text-brass-hover",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
            ].join(" ")}
            style={{
              pointerEvents: "auto",
              left: placement.chip.left,
              top: placement.chip.top,
            }}
          >
            <SketchIcon size={13} />
            <span className="font-display text-2xs uppercase tracking-[0.16em]">
              Sketch
            </span>
            <Kbd className="ml-auto">↵</Kbd>
          </button>
        </>
      ) : null}
    </div>
  );
}
