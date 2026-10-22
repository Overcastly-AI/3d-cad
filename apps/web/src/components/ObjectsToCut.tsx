/**
 * The cut dialogs' OBJECTS TO CUT list (CUT-OBJECTS-TO-CUT): Fusion 360's
 * list of the bodies a cut meets, each ticked by default, untick one to leave
 * it whole. Shared by the extrude, revolve, sweep, loft and pipe editors.
 *
 * Shown only on a part with more than one body: with one there is nothing to
 * choose. The rows are the bodies the cut met on its last rebuild, so a NEW cut
 * (not yet built) says what it will do instead of listing guesses; once it is
 * built, Edit lists them. Unticking narrows the cut to a list, which stays a
 * list; "Cut every body it meets" is the one way back to every body, and the
 * one action a cut saved before Objects To Cut (its active body only) has.
 */
import { Button, Checkbox, FieldRow } from "@loft/design";

import type { BodyInfo } from "../features/bodies";
import {
  cutBodyRows,
  type CutBodiesChoice,
  toggleCutBody,
} from "../features/cutBodies";

/** What the seat knows about the part's bodies, for a cut editor. */
export interface CutBodiesContext {
  /** The part's bodies, in tree order. */
  bodies: readonly BodyInfo[];
  /** The bodies this cut met on its last rebuild, or null (not built yet). */
  met: readonly string[] | null;
}

export function ObjectsToCut({
  choice,
  context,
  onChange,
}: {
  choice: CutBodiesChoice;
  context: CutBodiesContext | undefined;
  onChange: (choice: CutBodiesChoice) => void;
}) {
  if (context === undefined || context.bodies.length < 2) return null;
  const rows = cutBodyRows(choice, context.met, context.bodies);
  return (
    <FieldRow label="Objects To Cut">
      <div className="flex min-w-0 flex-col" data-testid="objects-to-cut">
        {choice === undefined ? (
          <span className="font-body text-xs text-gauge" role="note">
            Its active body only (saved before Objects To Cut).
          </span>
        ) : rows.length === 0 && choice === "all" ? (
          <span
            className="font-body text-xs text-mist"
            data-testid="objects-to-cut-every"
          >
            Every body the cut meets.
          </span>
        ) : (
          <ul aria-label="Objects To Cut" className="flex flex-col">
            {rows.map((row) => (
              <li key={row.id}>
                <Checkbox
                  label={row.label}
                  data-testid={`objects-to-cut-${row.id}`}
                  checked={row.checked}
                  onChange={(checked) =>
                    onChange(toggleCutBody(choice, rows, row.id, checked))
                  }
                />
              </li>
            ))}
          </ul>
        )}
        {choice !== "all" ? (
          // A narrowed (or pre-list) cut returns to every body only by asking:
          // re-ticking rows never does it (`toggleCutBody`).
          <Button
            className="mt-1 self-start"
            data-testid="objects-to-cut-all"
            onClick={() => onChange("all")}
          >
            Cut every body it meets
          </Button>
        ) : null}
      </div>
    </FieldRow>
  );
}
