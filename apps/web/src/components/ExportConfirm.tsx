import { useEffect, useRef } from "react";

import type { ExportFormat } from "../api/exportPart";
import { PARTIAL_POSE_CLAUSE } from "../features/assemblyExport";

/** The confirm's own words, on the button and as its accessible name. */
export const EXPORT_ANYWAY_LABEL = `Export anyway — ${PARTIAL_POSE_CLAUSE}`;

/**
 * THE ONE EXPLICIT CONFIRM before writing a file that misplaces parts
 * (QA 2026-10-10): the assembly's mates did not all solve, so the file would
 * hold components at their last solved or initial positions. Shared by the
 * Inspector's strip (in flow, under the cells) and the command band (hung
 * under the group), so both ask the same question in the same words.
 *
 * Not a modal, like `FeatureDeleteConfirm`: the user should be able to look at
 * the tree's "unresolved" rows while deciding. Focus lands on the confirm so
 * Enter answers it; Escape cancels.
 */
export function ExportConfirm({
  format,
  reason,
  testIdPrefix,
  onConfirm,
  onCancel,
  className,
}: {
  format: ExportFormat;
  /** What is wrong, in a sentence ("1 joint unresolved."). */
  reason: string;
  testIdPrefix: string;
  onConfirm: () => void;
  onCancel: () => void;
  className?: string;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    confirmRef.current?.focus();
  }, [format]);
  const titleId = `${testIdPrefix}-confirm-title`;
  return (
    <div
      role="alertdialog"
      aria-labelledby={titleId}
      data-testid={`${testIdPrefix}-confirm`}
      data-format={format}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          onCancel();
        }
      }}
      className={className}
    >
      <p id={titleId} className="font-body text-xs text-flag">
        {format.toUpperCase()} would be partial. {reason}
      </p>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <button
          ref={confirmRef}
          type="button"
          data-testid={`${testIdPrefix}-confirm-export`}
          onClick={onConfirm}
          className="min-h-target-dense text-left font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          {EXPORT_ANYWAY_LABEL}
        </button>
        <button
          type="button"
          data-testid={`${testIdPrefix}-confirm-cancel`}
          onClick={onCancel}
          className="min-h-target-dense font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
