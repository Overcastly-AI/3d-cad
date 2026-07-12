/**
 * The datum-plane editor — the pattern/revolve editor's twin in the same
 * title-block seat top-left of the viewport. A datum plane is a construction
 * plane parallel to an origin datum, offset a signed distance along its normal
 * (docs/design/datum-planes.md §3); it produces no body, only a plane that
 * later sketches sit on. Its structural choice is the base datum (a
 * SegmentedControl of the three origin datums); OFFSET is the parametric handle
 * and wears brass focus. Keyboard-first: offset autofocuses, Enter commits,
 * Escape cancels — the sketcher's dimension grammar.
 */
import {
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { DatumParams } from "../api/parts";
import {
  buildDatumParams,
  canSubmitDatum,
  DATUM_BASES,
  type DatumForm,
  offsetError,
} from "../features/datum";
import type { DatumPlaneName } from "../sketch/plane";

export interface DatumEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-datum defaults, or an existing datum's params). */
  initial: DatumForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: DatumParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

const BASE_OPTIONS: ReadonlyArray<SegmentOption<DatumPlaneName>> =
  DATUM_BASES.map((b) => ({
    value: b.id,
    label: b.label,
    "data-testid": `datum-base-${b.id}`,
    "aria-label": `Parallel to the ${b.label} datum`,
  }));

const FLIP_OPTIONS: ReadonlyArray<SegmentOption<"keep" | "flip">> = [
  {
    value: "keep",
    label: "Normal",
    "data-testid": "datum-flip-keep",
    "aria-label": "Keep the plane normal",
  },
  {
    value: "flip",
    label: "Flipped",
    "data-testid": "datum-flip-flip",
    "aria-label": "Reverse the plane normal",
  },
];

export function DatumEditor({
  mode,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: DatumEditorProps) {
  const [form, setForm] = useState<DatumForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildDatumParams(form);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    },
    [saving, submit, onCancel],
  );

  const canSubmit = canSubmitDatum(form) && !saving;

  return (
    <div
      className="absolute left-3 top-3 w-72 max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Datum plane" data-testid="datum-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New datum plane" : "Edit datum plane"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SegmentedControl
              label="Parallel to"
              value={form.base}
              options={BASE_OPTIONS}
              onChange={(base) => setForm((f) => ({ ...f, base }))}
            />
            <NumberField
              label="Offset"
              unit="mm"
              data-testid="datum-offset"
              autoFocus
              value={form.offsetInput}
              error={offsetError(form.offsetInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, offsetInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
              aria-label="Offset distance (mm, signed)"
            />
            <p className="-mt-1 font-body text-xs text-gauge">
              Distance along the {form.base} normal. 0 sits on the datum;
              negative offsets the other side.
            </p>
            <SegmentedControl
              label="Normal"
              value={form.flip ? "flip" : "keep"}
              options={FLIP_OPTIONS}
              onChange={(v) => setForm((f) => ({ ...f, flip: v === "flip" }))}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="datum-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="datum-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="datum-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
