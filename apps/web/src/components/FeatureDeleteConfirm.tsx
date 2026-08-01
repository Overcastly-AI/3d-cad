import { Button } from "@loft/design";
import { useEffect, useRef } from "react";

import type { FeatureDependent } from "../api/parts";

/**
 * "WHAT BREAKS IF I DELETE THIS?" — asked and answered BEFORE the delete fires
 * (UI-REVIEW 2026-07-30 F3).
 *
 * The finding: deleting a feature other features consume fired with no
 * confirmation and no dependency check, and the refusal a user eventually met
 * said "referenced by 2 other document(s)" — a sentence that ends the
 * conversation instead of starting the next action. Fusion names the dependents
 * before proceeding; so does this.
 *
 * TWO STATES, and which one you get is the SERVER'S answer, never a guess:
 *
 *  - NOTHING DEPENDS ON IT — a plain confirmation that says what recovery
 *    exists ("Undo brings it back"), because this delete is recoverable and
 *    saying so is the difference between a confirmation people read and one
 *    they click through.
 *  - SOMETHING DOES — the delete is not offered at all, because the server will
 *    refuse it (409 `feature_has_dependents`). Offering a button that cannot
 *    work is the "chrome that only decorates" defect with teeth. The dependents
 *    are LISTED BY NAME, with what each one is ("feature" / "drawing"), so the
 *    next action — go and delete or re-point those — is obvious.
 *
 * The list comes from `GET …/features/{id}/dependents`, which documents answers
 * with the SAME query that builds the delete's 409. That is what makes this
 * honest rather than merely helpful: a warning with its own copy of the rule is
 * a warning that can drift from the refusal it is warning about.
 *
 * FORM. The bottom-left HUD lane the tree's other transient chrome already
 * uses, in the same anvil-on-hairline panel; flag ink only on the name at risk.
 * It is not a modal: a modeler should still be able to look at the tree and the
 * body while deciding, which is the whole reason the names matter.
 */
export function FeatureDeleteConfirm({
  featureName,
  dependents,
  pending,
  onConfirm,
  onCancel,
}: {
  featureName: string;
  /** What the server says breaks. Empty = the delete will go through. */
  dependents: readonly FeatureDependent[];
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const blocked = dependents.length > 0;

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  return (
    <div
      ref={panelRef}
      role="alertdialog"
      aria-labelledby="feature-delete-title"
      tabIndex={-1}
      data-testid="feature-delete-confirm"
      data-blocked={blocked ? "true" : "false"}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onCancel();
        }
      }}
      className="absolute bottom-3 left-3 z-hud max-w-md rounded-sm border border-hairline bg-anvil px-3 py-2 outline-none"
    >
      <span
        id="feature-delete-title"
        className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge"
      >
        {blocked ? "Cannot delete yet" : "Delete feature"}
      </span>
      {blocked ? (
        <>
          <p className="mt-1 font-body text-xs text-mist">
            <span className="font-data text-flag">{featureName}</span> is used
            by{" "}
            {dependents.length === 1
              ? "one thing"
              : `${dependents.length} things`}
            . Delete or re-point {dependents.length === 1 ? "it" : "them"}{" "}
            first.
          </p>
          <ul className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            {dependents.map((dependent) => (
              <li key={dependent.id} className="flex items-baseline gap-1.5">
                <span
                  className="font-data text-xs text-mist"
                  data-testid="feature-dependent"
                  data-dependent-kind={dependent.kind}
                >
                  {dependent.name}
                </span>
                <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
                  {dependent.kind}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-1 font-body text-xs text-mist">
          Delete <span className="font-data text-flag">{featureName}</span>?
          Nothing else depends on it, and Undo brings it back.
        </p>
      )}
      <div className="mt-2 flex items-center gap-2">
        <Button onClick={onCancel} data-testid="feature-delete-cancel">
          {blocked ? "Close" : "Cancel"}
        </Button>
        {blocked ? null : (
          <Button
            variant="danger"
            onClick={onConfirm}
            disabled={pending}
            data-testid="feature-delete-confirm-action"
          >
            {pending ? "Deleting…" : "Delete"}
          </Button>
        )}
      </div>
    </div>
  );
}
