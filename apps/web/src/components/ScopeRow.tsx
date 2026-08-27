/**
 * The scope row — the one line in the pattern / mirror editor that says WHAT the
 * feature acts on: `This body` or the feature the tree named (`Hole1`).
 *
 * It is deliberately a two-state ruled toggle in the existing SegmentedControl
 * idiom rather than a new chip-list widget: this editor authors exactly one
 * subject, and a control that can hold a set implies a set is expected. The
 * second segment carries the feature's OWN NAME, so the control reads as a
 * sentence with the note beneath it — "REPEATS · THIS BODY | HOLE1", then
 * "Repeats Hole1's cut at every placement" — instead of a caption plus an
 * abstract enum.
 *
 * Shared by both editors on its SECOND real use (the DRY rule), because a
 * pattern and a mirror ask the user the identical question and must not ask it
 * two different ways (docs/design/pattern-scope.md §2).
 */
import { SegmentedControl, type SegmentOption } from "@loft/design";

import {
  type ScopeFeature,
  type ScopeMode,
  type ScopeVerb,
  scopeNote,
  scopeRefusal,
  scopeSubject,
} from "../features/patternScope";

export interface ScopeRowProps {
  /** Which verb is asking — only the copy differs. */
  verb: ScopeVerb;
  /** The current reading. */
  mode: ScopeMode;
  /**
   * The named subject the `features` reading acts on. Kept populated while the
   * row sits on `body` so flipping back restores the same subject rather than
   * making the user re-state it — the pick is a suggestion, never a commitment.
   */
  features: readonly ScopeFeature[];
  onChange: (mode: ScopeMode) => void;
}

export function ScopeRow({ verb, mode, features, onChange }: ScopeRowProps) {
  // Nothing in this tree can be repeated on its own (a body of nothing but
  // modifiers): the body reading is the only honest one, so the control holds
  // there and the note says why rather than offering a dead segment.
  const nameable = features.length > 0;
  const subject = nameable ? scopeSubject(features) : "A feature";
  const verbWord = verb === "pattern" ? "Repeats" : "Reflects";
  const options: ReadonlyArray<SegmentOption<ScopeMode>> = [
    {
      value: "body",
      label: "This body",
      "data-testid": `${verb}-scope-body`,
      "aria-label": `${verbWord} the whole body`,
    },
    {
      value: "features",
      label: subject,
      "data-testid": `${verb}-scope-features`,
      "aria-label": `${verbWord} ${subject}`,
    },
  ];

  return (
    <div className="flex flex-col gap-1" data-testid={`${verb}-scope`}>
      {/* Default size, not `dense`: this control sits directly above the
          linear/circular one and a shorter twin would read as a lesser
          question, when it is the more important of the two. */}
      <SegmentedControl
        label={verbWord}
        value={mode}
        options={options}
        disabled={!nameable}
        onChange={onChange}
      />
      <p
        className="font-body text-xs text-gauge"
        data-testid={`${verb}-scope-note`}
      >
        {nameable ? scopeNote(verb, mode, features) : scopeRefusal()}
      </p>
    </div>
  );
}
