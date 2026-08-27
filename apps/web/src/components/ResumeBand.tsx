import { Link } from "@tanstack/react-router";
import { useMemo } from "react";

import { documentActivity } from "../lib/activity";
import type { PartResponse } from "../api/parts";

/**
 * THE RESUME BAND — what the parts register was missing, in one line.
 *
 * The founder's report on this surface was three words: *"The main file page
 * looks like an after thought."* It had no backlog entry, so this is the first
 * deliberate look at it, and the diagnosis is worth writing down because the
 * page is not badly made — it has been through a design pass and its internal
 * reasoning is careful. It fails one level up.
 *
 * IT ANSWERS "WHAT HAVE I FILED?" AND NOTHING ELSE. The question a returning
 * engineer actually arrives with is "where was I, and what do I do next?" — and
 * the design mandate's first flow test is that the next step must be visible
 * from the current state. Measured on a real five-part drawer at 1600x1000
 * before this change: the single most likely action, resume the thing you were
 * in the middle of, required reading a column, identifying the top row, and
 * clicking a name. The only control the page PROPOSED was a text field labelled
 * "Part name" at the bottom of ~490 px of blank ruled lines — i.e. it proposed
 * starting over. Tellingly, the EMPTY state was the better screen: it had a
 * headline, an invitation and a focused field, and the moment you had work the
 * page stopped speaking to you.
 *
 * So this band names the one document you are most likely to want and opens it.
 * Every word of it is derived from the list payload already on screen — the
 * name, the age, and which of the two things it says — so there is nothing here
 * that only decorates (mandate 3a). It is deliberately a RULED LINE and not a
 * card: the register is a log book, the drawer below is ruled, and a rounded
 * hero panel would be the one foreign object on the page.
 *
 * TWO STATES, because a drawer has two ways of being unhelpful:
 *
 *  - SOMETHING HAS BEEN WORKED ON. Name it, say when, offer Open. `updated_at`
 *    is bumped by every tree write, so "most recently worked" is a fact, not an
 *    inference (see `lib/activity.ts` for why the two stamps can carry this).
 *  - EVERYTHING IS A NAMED STUB. A drawer of parts nobody has drawn in is the
 *    common shape of a first evening with a new tool, and "resume" would be a
 *    lie there. It says so instead, and points at the same next step the empty
 *    part workspace already teaches — pick a plane and draw — so the two
 *    surfaces give one instruction rather than two.
 *
 * It renders NOTHING for an empty drawer: `EmptyRegister` owns that screen and
 * already does it well, and a second invitation beside it would be the "two
 * places saying the same word" defect this register keeps deleting.
 */

export interface ResumeTarget {
  part: PartResponse;
  /** True when nothing in the drawer has been edited since it was named. */
  unstarted: boolean;
  /** Relative age of the last edit; null in the unstarted case. */
  age: string | null;
}

/**
 * Which document the band points at, and which of the two things it says.
 *
 * Exported and pure so it can be unit-tested without a router: the branch here
 * decides what the landing surface tells a returning user, which is too
 * load-bearing to verify only by looking at it.
 */
export function resumeTarget(
  parts: readonly PartResponse[],
  now: number = Date.now(),
): ResumeTarget | null {
  if (parts.length === 0) return null;

  let best: { part: PartResponse; when: number; age: string } | null = null;
  let newestStub: { part: PartResponse; when: number } | null = null;

  for (const part of parts) {
    const activity = documentActivity(
      part.created_at,
      part.updated_at,
      "",
      now,
    );
    const when = Date.parse(part.updated_at);
    if (Number.isNaN(when)) continue;
    if (activity.kind === "worked") {
      if (best === null || when > best.when) {
        best = { part, when, age: activity.label };
      }
    } else if (newestStub === null || when > newestStub.when) {
      newestStub = { part, when };
    }
  }

  if (best !== null) {
    return { part: best.part, unstarted: false, age: best.age };
  }
  // Nothing worked. Point at the most recently NAMED one — the last thing the
  // user did, which is the closest honest equivalent of "where you were".
  if (newestStub !== null) {
    return { part: newestStub.part, unstarted: true, age: null };
  }
  return null;
}

export function ResumeBand({ parts }: { parts: readonly PartResponse[] }) {
  const target = useMemo(() => resumeTarget(parts), [parts]);
  if (target === null) return null;

  const { part, unstarted, age } = target;
  return (
    // Ruled and gutter-aligned to the register below, so the two read as one
    // instrument in two plates — direction, then contents — rather than as a
    // hero card sitting on top of a table.
    <div
      className="mt-4 flex items-stretch border border-hairline bg-anvil"
      data-testid="parts-resume"
    >
      {/* The register's own scribed margin, at the register's own width, so the
          left rule of the whole drawer is one straight line. It carries the
          BRASS SCRIBE the register already uses to mark the addressed row —
          this is the addressed row, before you have addressed it. */}
      <div
        className="w-[3.5rem] shrink-0 border-l-2 border-brass bg-carbide"
        aria-hidden="true"
      />
      <div className="min-w-0 grow px-3 py-3">
        <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
          {unstarted ? "Start here" : "Resume"}
        </p>
        {/*
          ONE CONTROL, and the verb is inside it.

          The obvious build was a name plus a solid brass "Open" button, and it
          is wrong twice. The `Button` primitive's own rule is "spend brass on at
          most one solid button per surface", and this page already spends it on
          the register's create control — so a second would break the rule at the
          exact moment it matters, where the eye is deciding what to do. And two
          links to the same part is two tab stops with one destination. Folding
          the verb into the name link keeps the next step VISIBLE (mandate: the
          tool proposes), while the accessible name stays the sentence a screen
          reader needs: "Open Bracket plate".
        */}
        <Link
          to="/parts/$partId"
          params={{ partId: part.id }}
          aria-label={`Open ${part.name}`}
          title={part.name}
          data-testid="parts-resume-open"
          className="group mt-1 flex max-w-full items-baseline gap-3 rounded-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          <span
            className="truncate font-body text-lg text-mist transition-colors duration-fast group-hover:text-brass group-focus-visible:text-brass"
            data-testid="parts-resume-name"
          >
            {part.name}
          </span>
          <span
            aria-hidden="true"
            className="shrink-0 font-display text-2xs uppercase tracking-[0.16em] text-brass"
          >
            Open &rsaquo;
          </span>
        </Link>
        <p
          className="mt-1 font-data text-xs text-gauge"
          data-testid="parts-resume-caption"
        >
          {unstarted
            ? "Named, not drawn yet — open it and pick a plane."
            : `Last edited ${age}`}
        </p>
      </div>
    </div>
  );
}
