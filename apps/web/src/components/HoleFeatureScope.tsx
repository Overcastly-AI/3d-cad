/**
 * The Hole dialog's FEATURE SCOPE (HOLE-SCOPE-UI): SolidWorks' list of further
 * bodies a through-all hole also drills. By default a hole cuts the body that
 * owns its face only (HOLE-ACTIVE-BODY), so a hole on a stud never bores the
 * members behind it; ticking a body adds it.
 *
 * Shown only on a part with more than one body. While the depth is blind the
 * list is kept but not cut, and the note under it says so, so switching to
 * Blind never drops a scope without a word.
 */
import { Checkbox, FieldRow } from "@loft/design";

import type { BodyInfo } from "../features/bodies";
import {
  type HoleForm,
  holeScopeNote,
  toggleHoleScope,
} from "../features/hole";

export function HoleFeatureScope({
  form,
  bodies,
  onChange,
}: {
  form: HoleForm;
  bodies: readonly BodyInfo[] | undefined;
  onChange: (update: (form: HoleForm) => HoleForm) => void;
}) {
  if (bodies === undefined || bodies.length < 2) return null;
  const order = bodies.map((body) => body.baseFeatureId);
  const held = new Set(form.scopeBodies ?? []);
  const note = holeScopeNote(form);
  return (
    <FieldRow
      label="Feature Scope"
      note={note ?? "Further bodies a through-all hole drills."}
      noteTone={note === null ? "quiet" : "flag"}
      noteLabel="About the Feature Scope"
      noteTestId="hole-scope-note"
    >
      <ul
        aria-label="Feature Scope"
        data-testid="hole-scope"
        className="flex max-h-40 min-w-0 flex-col overflow-y-auto"
      >
        {bodies.map((body) => (
          <li key={body.baseFeatureId}>
            <Checkbox
              label={`Body ${body.ordinal} · ${body.name}`}
              data-testid={`hole-scope-${body.baseFeatureId}`}
              checked={held.has(body.baseFeatureId)}
              onChange={(checked) =>
                onChange((f) =>
                  toggleHoleScope(f, body.baseFeatureId, checked, order),
                )
              }
            />
          </li>
        ))}
      </ul>
    </FieldRow>
  );
}
