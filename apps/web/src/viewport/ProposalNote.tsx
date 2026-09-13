/**
 * THE PROPOSAL NOTE — the one object this product uses to say "here is a verb
 * you can take right now, on this thing".
 *
 * THE LAW OF THE IDIOM (W2 direction §1), which this file is the keeper of:
 *
 *   · **brass + leader + `Kbd` = an offer you can take right now.** (this)
 *   · **mist + no leader + no `Kbd` = a name for what is under the pointer.**
 *     (`CursorMark`, the snap marks)
 *   · **band cell + eyebrow + `×` = a held state that renames verbs.** (SCOPE)
 *
 * Never mix them. A mist chip with a `Kbd` is a lie; a brass chip that only
 * names a thing is the decorative-chrome defect mandate 3c calls out by name.
 * A FOURTH vocabulary for "what next" is the failure this whole wave exists to
 * prevent — so when the next moment needs an offer, it gets a `verb` here, not
 * a component of its own.
 *
 * ## Two moments, one note
 *
 * 1. **Pointer-addressed** (FLOW-1): rest on a face and it offers the SKETCH
 *    that face affords. The complaint it answered was that starting a sketch
 *    made you name the VERB before the NOUN — click Sketch, then hunt for the
 *    face, the opposite order from the one a modeller thinks in. It routes
 *    through the SAME `authorFacePlane` call the toolbar's pick flow makes, so
 *    the two cannot drift into different planes for one face.
 *
 * 2. **State-triggered** (FLOW-B1): a sketch SOLVES and it offers the EXTRUDE
 *    that profile affords. Measured in `AUDIT-FLOW-2026-09`: across three parts
 *    modelled end to end, **8 of 15 recorded hunts were this one transition** —
 *    the hand leaving for the toolbar to fetch a verb the app already knew it
 *    wanted. There is no pointer in this path, so the note's anchor is derived
 *    from the profile itself (`SolveProposalAnchor` → `proposalAnchor.ts`).
 *
 * Three decisions from the first moment carry over unchanged, and are the
 * reason this affordance does not fight the viewport:
 *
 *  · **The face's own hover tint carries the proposal; the chip confirms it.**
 *    SEL-1 already lights the face under the cursor. All that was missing was
 *    somewhere to click, so that is all this adds.
 *  · **It is written on REST, not on hover** (pointer moment only — the dwell
 *    exists to stop a pointer SWEEP proposing things, and a solve is not a
 *    sweep, which is why the solve offer has no dwell at all).
 *  · **It proposes; it does not select.** Nothing is committed by hovering or
 *    by solving, and accepting opens the editor — one more `Enter` commits.
 *
 * ## At most one note, and the pointer wins
 *
 * Both moments are reachable at once (a sketch solves while the pointer rests
 * on an existing body's face). Two chips would be the "three dialects" failure
 * drawn on screen, so the pointer-addressed note — the user actively pointing
 * at something — displaces the ambient one, which **withdraws and does not
 * come back**. Never stack, never queue, never shrink one to fit both.
 *
 * ## One offer per subject, for the AMBIENT note only
 *
 * A proposal that cannot be ignored cheaply is worse than none. Dismiss the
 * extrude offer for `Sketch1` and `Sketch1` never offers again this session
 * (the seen-set below). The pointer note is deliberately NOT one-shot: it is
 * summoned by an explicit gesture every time, and suppressing it would make
 * resting on a face do nothing — which is the exact defect FLOW-1 fixed.
 *
 * There is no timeout dismissal. A chip that vanishes on a timer while you are
 * reading it is the nag's evil twin; the note persists until it is acted on,
 * dismissed, or invalidated by a camera gesture.
 *
 * ## No motion, deliberately
 *
 * No fade, no slide, no pulse, on either note. The dwell already gives the
 * pointer note a deliberate arrival, and the solve note arrives at a moment the
 * user caused. `prefers-reduced-motion` therefore needs no new code here, which
 * is the best available outcome rather than an omission.
 */
import {
  color,
  Kbd,
  proposal as proposalTokens,
  VerbGlyph,
} from "@loft/design";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel } from "../features/face";
import { useGlobalKeys } from "../lib/modalGate";
import { KEY_ACCEPT_PROPOSAL, partVerbKey } from "../shortcuts/registry";
import { useSketchStore } from "../sketch/store";
import { useProposalAnchorStore } from "./proposalAnchor";
import { placeProposal, type ProposalPlacement } from "./sketchProposal";

/** A face that can actually carry a sketch — planar, so it has a signature. */
export type ProposableFace = OverlayFace & { signature: PlanarFaceSignature };

/** A sketch feature an extrude could consume, as the tree names it. */
export interface ProfileSubject {
  id: string;
  name: string;
}

export interface ProposalNoteProps {
  /**
   * May a POINTER-ADDRESSED proposal be offered at all — no command open,
   * nothing armed, a body on screen. SEPARATE from `face` on purpose:
   * `face === null` is ambiguous between "the pointer is not on a face right
   * now" (which must NOT withdraw a written note — see the latch below) and
   * "proposals are off entirely" (which must withdraw it at once). One boolean
   * makes the difference explicit rather than inferred.
   */
  enabled: boolean;
  /**
   * The face the pointer is addressing, already resolved to a PICKABLE one, or
   * null when the pointer addresses nothing a sketch could sit on. Resolving it
   * upstream is deliberate: a note offered over a cylindrical face would be a
   * dead end, and this component should not be the thing that knows that.
   */
  face: ProposableFace | null;
  /** Accept the sketch offer — the same call the toolbar's face pick makes. */
  onAccept: (face: ProposableFace) => void;
  /**
   * May a STATE-TRIGGERED proposal be offered — the model is idle, no command
   * is open, no measurement is armed. Deliberately NOT `enabled`: that one also
   * demands a body, and the first sketch on an empty part is precisely the case
   * this offer exists for.
   */
  extrudeEnabled: boolean;
  /** The sketches the tree offers as extrude profiles, in build order. */
  profiles: readonly ProfileSubject[];
  /** Accept the extrude offer — the same call the band's Extrude button makes. */
  onAcceptExtrude: (profileFeatureId: string) => void;
}

/** Which verb a note carries. Both are `PartVerbId`s — one vocabulary. */
type ProposalVerb = "sketch" | "extrude";

/** A written pointer note: the face it is about, where it sits, in what frame. */
interface FaceNote {
  face: ProposableFace;
  placement: ProposalPlacement;
  frame: { width: number; height: number };
}

/** Everything the chip needs, whichever moment wrote it. */
interface Written {
  verb: ProposalVerb;
  /** The noun, in words — carried in the accessible name, never in the chip. */
  subject: string;
  label: string;
  placement: ProposalPlacement;
  frame: { width: number; height: number };
  testId: string;
  /** Announce its arrival to a screen reader (the ambient note only). */
  announce: boolean;
}

export function ProposalNote({
  enabled,
  face,
  onAccept,
  extrudeEnabled,
  profiles,
  onAcceptExtrude,
}: ProposalNoteProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  /** Last pointer position in CLIENT coords — a ref, so moves never re-render. */
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const [note, setNote] = useState<FaceNote | null>(null);
  // The written note is read inside DOM listeners, which close over the render
  // that installed them; the ref is what keeps those listeners looking at the
  // CURRENT note instead of a stale one.
  const noteRef = useRef<FaceNote | null>(null);

  // --- the ambient (solve-triggered) offer ---------------------------------
  //
  // `offered` is the sketch feature an EXTRUDE is being proposed for. It is set
  // once, by the solve transition, and cleared by any withdrawal. `seen` is the
  // one-shot: local to this module, keyed on the subject's id, and it needs no
  // store slice because nothing outside this component has an opinion about it.
  const [offered, setOffered] = useState<string | null>(null);
  const seen = useRef(new Set<string>());
  const requestAnchor = useProposalAnchorStore((state) => state.requestAnchor);
  const anchor = useProposalAnchorStore((state) => state.anchor);

  const withdrawOffer = useCallback(() => {
    setOffered((current) => {
      if (current !== null) seen.current.add(current);
      return null;
    });
  }, []);

  const putNote = useCallback(
    (next: FaceNote | null) => {
      noteRef.current = next;
      setNote(next);
      // THE PRIORITY RULE, in the one place both notes are known: a
      // pointer-addressed note displaces the ambient one permanently.
      if (next !== null) withdrawOffer();
    },
    [withdrawOffer],
  );

  /**
   * THE TRIGGER: a sketch session ending, read from the store's own
   * transitions rather than from a render.
   *
   * A subscription, not an effect on `mode`, because the two facts this needs
   * arrive in two separate `set` calls inside one promise callback —
   * `bind(featureId)` then `exit()` — and React batches them into a SINGLE
   * render in which the bound id is already gone. An effect would see only the
   * end state and could never name the sketch that just closed. The store
   * notifies per `set`, so this sees both.
   */
  const bound = useRef<string | null>(null);
  useEffect(
    () =>
      useSketchStore.subscribe((state, previous) => {
        if (state.mode !== "off" && state.featureId !== null) {
          bound.current = state.featureId;
        }
        if (state.mode === "off" && previous.mode !== "off") {
          const subject = bound.current;
          bound.current = null;
          // One offer per subject, per session — checked HERE, at the offer,
          // not at the render. A note that is pending an anchor (the solve
          // round-trip takes a moment) must stay pending, not be suppressed by
          // the record of its own offer.
          if (subject !== null && !seen.current.has(subject)) {
            setOffered(subject);
          }
        }
      }),
    [],
  );

  // Opening a command (or arming a measurement) withdraws the offer — §4's
  // "dismiss by doing anything else". Written as a TRANSITION rather than a
  // steady state so that an offer landing in the same batch as the context
  // re-enabling cannot be withdrawn by its own arrival.
  const wasEnabled = useRef(extrudeEnabled);
  useEffect(() => {
    if (wasEnabled.current && !extrudeEnabled) withdrawOffer();
    wasEnabled.current = extrudeEnabled;
  }, [extrudeEnabled, withdrawOffer]);

  // Ask the scene for this subject's anchor, and stop asking when there is no
  // subject — the projection then costs nothing at all.
  useEffect(() => {
    requestAnchor(offered);
  }, [offered, requestAnchor]);
  useEffect(
    () => () => useProposalAnchorStore.getState().requestAnchor(null),
    [],
  );

  const profile = useMemo(
    () =>
      offered === null
        ? null
        : (profiles.find((candidate) => candidate.id === offered) ?? null),
    [offered, profiles],
  );

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

  // Camera gestures withdraw the AMBIENT offer, and this listener is mounted
  // unconditionally — unlike the pointer note's, which lives inside the dwell
  // effect and is therefore absent exactly when `enabled` is false. An empty
  // part has no body and so no pointer proposals, and it is the commonest place
  // for a solve offer to be written: the cheapest dismissal ("I just start
  // orbiting") has to work there too.
  useEffect(() => {
    const container = containerOf();
    if (container === null) return;
    const dismiss = (event: Event) => {
      if (chipRef.current?.contains(event.target as Node) === true) return;
      withdrawOffer();
    };
    container.addEventListener("pointerdown", dismiss);
    container.addEventListener("wheel", dismiss, { passive: true });
    return () => {
      container.removeEventListener("pointerdown", dismiss);
      container.removeEventListener("wheel", dismiss);
    };
  }, [containerOf, withdrawOffer]);

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

  /**
   * THE ONE NOTE ON SCREEN. The pointer-addressed note wins outright; the
   * ambient one is only ever consulted when there is no pointer note, which is
   * the §1.1 priority rule expressed as a `??` rather than as a state machine
   * that could disagree with the pixels.
   */
  const written = useMemo<Written | null>(() => {
    if (note !== null) {
      const name = faceLabel(note.face.index, note.face.signature);
      return {
        verb: "sketch",
        subject: name,
        label: `Sketch on ${name}`,
        placement: note.placement,
        frame: note.frame,
        testId: "sketch-proposal",
        announce: false,
      };
    }
    if (!extrudeEnabled || profile === null || anchor === null) return null;
    return {
      verb: "extrude",
      subject: profile.name,
      // The noun is carried in WORDS only here. On the chip it would cost ~60 %
      // more width for something the leader already says in space.
      label: `Extrude ${profile.name}`,
      placement: placeProposal({ x: anchor.x, y: anchor.y }, anchor.frame),
      frame: anchor.frame,
      testId: "extrude-proposal",
      announce: true,
    };
  }, [note, extrudeEnabled, profile, anchor]);

  // The ambient note is WRITTEN at most once per subject: record it the moment
  // it reaches the screen, so a later re-solve of the same sketch does not
  // offer again.
  useEffect(() => {
    if (written?.verb === "extrude" && offered !== null) {
      seen.current.add(offered);
    }
  }, [written, offered]);

  const writtenRef = useRef<Written | null>(written);
  writtenRef.current = written;

  const accept = useCallback(() => {
    const showing = writtenRef.current;
    if (showing === null) return;
    if (showing.verb === "extrude") {
      const target = profile;
      if (target === null) return;
      withdrawOffer();
      onAcceptExtrude(target.id);
      return;
    }
    const target = noteRef.current?.face ?? faceRef.current;
    if (target !== null && target !== undefined) onAccept(target);
  }, [onAccept, onAcceptExtrude, profile, withdrawOffer]);

  const withdraw = useCallback(() => {
    if (writtenRef.current?.verb === "extrude") {
      withdrawOffer();
      return;
    }
    putNote(null);
  }, [putNote, withdrawOffer]);

  /**
   * THE KEYS, and the half of a cross-agent contract that lives here.
   *
   * Bound on `window` in the CAPTURE phase with `preventDefault()`, which is
   * not a style choice: `PartPage`'s create-shortcut table is a BUBBLE-phase
   * `window` listener claiming the same letters, and its first statement is
   * `if (event.defaultPrevented) return;`. Capture on `window` runs before any
   * bubble-phase `window` listener, so the order is deterministic rather than
   * registration-order luck. Without this half, `E` on a showing offer runs
   * BOTH handlers — the note's accept, then the generic opener, which
   * `setEditor(...)`s over the top with the DEFAULT profile. The editor is open
   * either way and looks right; only the profile is wrong, which is the
   * silent-wrong-result class rather than a visible break.
   *
   * Three keys, one meaning each:
   *  · the verb's own LETTER, read from the registry — the thing a user can
   *    carry away, which is why the chip prints it;
   *  · `Enter`, which means accept everywhere in this product and stays
   *    unprinted because it stops working the moment the note is gone;
   *  · `Escape`, which withdraws the note and STOPS THERE. It is still "back
   *    out one step" — the note is simply the frontmost step now.
   *
   * Gated on the WRITTEN note rather than on the hover, so the keys are live
   * exactly when the glyph on the chip is on screen: one fact, not a second
   * derivation that could disagree with the pixels.
   *
   * REGISTERED THROUGH `lib/modalGate.ts`, not with a raw listener, and that is
   * the W2 blocking finding rather than tidiness. `isTypingTarget` — the only
   * target guard this had — covers `INPUT | TEXTAREA | SELECT | contentEditable`
   * and a `<button>` is none of those, so `Enter` on ANY focused button in the
   * app accepted this offer and `preventDefault()`ed the button's own
   * activation: the control the user was standing on did nothing, and an editor
   * opened instead. The seam refuses an activation key that belongs to a focused
   * control before this handler is reached, so the note can keep `Enter`
   * (meaning accept, everywhere in this product) without taking it from a
   * button that also means accept.
   *
   * While a modal layer is open — the exit ticket, the key card — the gate's
   * window-capture shield calls `stopImmediatePropagation()` and this never
   * runs. That is correct and deliberate, and it is not this binding failing.
   */
  const verbKey = written === null ? undefined : partVerbKey(written.verb);
  const onProposalKey = useCallback(
    (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Escape") {
        event.preventDefault();
        withdraw();
        return;
      }
      const letter = verbKey;
      if (
        event.key !== KEY_ACCEPT_PROPOSAL &&
        (letter === undefined || event.key.toLowerCase() !== letter)
      ) {
        return;
      }
      event.preventDefault();
      accept();
    },
    [verbKey, accept, withdraw],
  );
  // Null while nothing is written: the keys are live exactly when the glyph is
  // on screen, which is one fact rather than a second derivation of it.
  useGlobalKeys("the proposal note", written === null ? null : onProposalKey, {
    capture: true,
  });

  const placement = written?.placement ?? null;
  const frame = written?.frame ?? null;

  return (
    <div
      ref={rootRef}
      data-testid="sketch-proposal-layer"
      // WHY THE LAYER STAMPS ITS OWN STATE: the ambient offer can decline to
      // appear for two entirely different reasons — no solve transition was
      // seen, or the profile projected somewhere a leader would lie about
      // (`loopAnchor`) — and both look identical from outside, as an absent
      // chip. The same posture as `data-edge-mark-seats` next door: a refusal
      // that cannot be read is a refusal nobody can tell from a bug.
      data-proposal-pending={offered ?? undefined}
      data-proposal-anchored={
        offered === null ? undefined : anchor === null ? "no" : "yes"
      }
      className="absolute left-0 top-0 h-0 w-0"
      // Inline rather than a class: this element is a DIRECT child of the HUD
      // layer, whose `[&>*]:pointer-events-auto` rule has the same specificity
      // as a plain utility would. An inline declaration is unambiguous, and
      // getting it wrong makes the whole viewport un-orbitable.
      style={{ pointerEvents: "none" }}
    >
      {/*
        THE ANNOUNCEMENT. A live region that is always MOUNTED (an empty one
        added at the same time as its text is announced unreliably), carrying
        the ambient note's accessible name only: the pointer-addressed note is
        silent because that user is already looking at it, and announcing every
        dwell would be chatter.

        It is a region beside the chip rather than `role="status"` ON the chip,
        because that role would REPLACE the button role and cost a screen-reader
        user the one thing the element actually is.
      */}
      <span
        data-testid="proposal-announcement"
        role="status"
        aria-live="polite"
        className="sr-only"
      >
        {written?.announce === true ? written.label : ""}
      </span>
      {written !== null && placement !== null && frame !== null ? (
        <>
          {/*
            THE LEADER — a drafting leader note, which is the one place this
            affordance spends any boldness. The dot marks the exact point the
            note is about; the stub ties the chip to it, so the chip reads as an
            annotation ON the model rather than chrome floating over the scene.
            Frame-sized so its coordinates ARE frame coordinates, and inert.

            It is also what lets the chip carry the verb ALONE: the noun is said
            in SPACE, by the line, which is the whole idea of a leader note.
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
            {/* The anchor: the exact point the note is about. */}
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
            data-testid={written.testId}
            // The WRITTEN note's subject, not whatever the pointer happens to
            // address now: once written, the note is a statement about one
            // specific thing and must keep naming it while the pointer travels
            // onto the chip. Both notes answer the same two questions, so one
            // assertion can ask "what is the app proposing right now?" without
            // knowing which moment wrote it.
            data-proposal-verb={written.verb}
            data-proposal-subject={written.subject}
            data-face-index={note?.face.index}
            aria-label={written.label}
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
            {/* One glyph source for every surface that draws a verb. */}
            <VerbGlyph verb={written.verb} size={13} />
            <span className="font-display text-2xs uppercase tracking-[0.16em]">
              {written.verb}
            </span>
            {/*
              THE KEY, READ FROM THE REGISTRY — never a literal. A chip printing
              a hardcoded letter is the "gate that cannot fail" defect wearing a
              `Kbd`: correct the day it is written and silently lying the day
              somebody re-keys the verb. `↵` is the honest fallback for a verb
              with no letter, and `PartVerbId` deliberately covers the keyless
              verbs so that branch is reachable rather than dead.
            */}
            <Kbd className="ml-auto">{verbKey?.toUpperCase() ?? "↵"}</Kbd>
          </button>
        </>
      ) : null}
    </div>
  );
}
