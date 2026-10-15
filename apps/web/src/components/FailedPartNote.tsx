/**
 * The component row's error line for a part that failed to build
 * (BIKE2-FAILED-PART-KILLS-PICKS): "Crank arm failed to build: <the kernel's
 * sentence> — Open part". SolidWorks flags such a component in the tree; before
 * this, Loft's row said nothing while the part was missing from the scene, the
 * picks and every exported file.
 *
 * One line per failed part the component holds (a sub-assembly can hold
 * several). The link opens the part, where the failing feature is marked.
 */
import { Link } from "@tanstack/react-router";

import type { FailedPart } from "../assembly/partFailures";

export function FailedPartNotes({
  componentId,
  failures,
}: {
  componentId: string;
  failures: readonly FailedPart[] | undefined;
}) {
  if (failures === undefined || failures.length === 0) return null;
  return (
    <ul
      data-testid={`instance-failed-${componentId}`}
      className="px-2 pb-1.5 pl-8"
    >
      {failures.map((failure) => (
        <li
          key={failure.partDocumentId ?? `${failure.code}:${failure.message}`}
          role="note"
          data-testid="instance-failed-part"
          data-part-document-id={failure.partDocumentId ?? undefined}
          data-error-code={failure.code}
          className="font-body text-xs text-flag"
        >
          <span aria-hidden>⚠ </span>
          {failure.name} failed to build: {failure.message}
          {failure.partDocumentId !== null ? (
            <>
              {" — "}
              <Link
                to="/parts/$partId"
                params={{ partId: failure.partDocumentId }}
                data-testid="instance-failed-open"
                className="text-brass underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
              >
                Open part
              </Link>
            </>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
