/**
 * The datum-plane editor — the pattern/revolve editor's twin in the same
 * title-block seat top-left of the viewport. A datum plane is a construction
 * plane that produces no body, only a plane later sketches sit on
 * (docs/design/datum-planes.md §3/§7). Its structural choice is the KIND
 * (a ruled Type select): an OFFSET from an origin datum, an offset FROM another
 * datum (chaining), or a MIDPLANE midway between two references. Each kind wears
 * one parametric handle in brass focus — the offset distance for the offset
 * kinds, the first reference for a midplane. Keyboard-first: the handle
 * autofocuses, Enter commits, Escape cancels — the sketcher's dimension grammar.
 */
import {
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import { useCommandBridge } from "../features/commandActions";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { DatumParams } from "../api/parts";
import {
  buildDatumParams,
  canSubmitDatum,
  DATUM_BASES,
  type DatumForm,
  type DatumKind,
  type DatumRef,
  datumRefOptions,
  defaultFormForKind,
  midplaneSideOptions,
  offsetError,
} from "../features/datum";
import type { DatumPlaneName } from "../sketch/plane";

export interface DatumEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-datum defaults, or an existing datum's params). */
  initial: DatumForm;
  /** Earlier datum features — the references offset-from + midplane draw on. */
  datumRefs: readonly DatumRef[];
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: DatumParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

const KIND_OPTIONS: ReadonlyArray<{ value: DatumKind; label: string }> = [
  { value: "offset", label: "Offset from origin plane" },
  { value: "offset_from", label: "Offset from a datum" },
  { value: "midplane", label: "Midplane between two references" },
];

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

/** The Normal / Flipped toggle every kind shares. */
function FlipControl({
  flip,
  onChange,
}: {
  flip: boolean;
  onChange: (flip: boolean) => void;
}) {
  return (
    <SegmentedControl
      label="Normal"
      value={flip ? "flip" : "keep"}
      options={FLIP_OPTIONS}
      onChange={(v) => onChange(v === "flip")}
    />
  );
}

export function DatumEditor({
  mode,
  initial,
  datumRefs,
  onSubmit,
  onCancel,
  saving,
  error,
}: DatumEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<DatumForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildDatumParams(form, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit, unit]);

  // Enter commits, Escape cancels — except when a button (the footer / a
  // segment) has focus: Enter must fire that control's own action.
  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        if (event.target instanceof HTMLButtonElement) return;
        event.preventDefault();
        if (!saving) submit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    },
    [saving, submit, onCancel],
  );

  const canSubmit = canSubmitDatum(form, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  const noDatums = datumRefs.length === 0;

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Datum plane" data-testid="datum-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New datum plane" : "Edit datum plane"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SelectField
              label="Type"
              data-testid="datum-kind"
              value={form.kind}
              options={KIND_OPTIONS}
              onChange={(e) =>
                setForm((f) =>
                  defaultFormForKind(e.target.value as DatumKind, f.flip),
                )
              }
              aria-label="Datum plane type"
            />

            {form.kind === "offset" ? (
              <>
                <SegmentedControl
                  label="Parallel to"
                  value={form.base}
                  options={BASE_OPTIONS}
                  onChange={(base) => setForm((f) => ({ ...f, base }))}
                />
                <NumberField
                  label="Offset"
                  unit={unit}
                  data-testid="datum-offset"
                  autoFocus
                  value={form.offsetInput}
                  error={offsetError(form.offsetInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, offsetInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Offset distance (signed)"
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  Distance along the {form.base} normal. 0 sits on the datum;
                  negative offsets the other side.
                </p>
                <FlipControl
                  flip={form.flip}
                  onChange={(flip) => setForm((f) => ({ ...f, flip }))}
                />
              </>
            ) : null}

            {form.kind === "offset_from" ? (
              <>
                <SelectField
                  label="Base plane"
                  data-testid="datum-base-plane"
                  autoFocus
                  value={form.baseFeatureId}
                  options={datumRefOptions(datumRefs)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, baseFeatureId: e.target.value }))
                  }
                  aria-label="Datum plane to offset from"
                />
                <NumberField
                  label="Offset"
                  unit={unit}
                  data-testid="datum-offset"
                  value={form.offsetInput}
                  error={offsetError(form.offsetInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, offsetInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Offset distance (signed)"
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  {noDatums
                    ? "Create a datum plane first — this offsets from one."
                    : "Distance along the base datum's normal. 0 sits on it."}
                </p>
                <FlipControl
                  flip={form.flip}
                  onChange={(flip) => setForm((f) => ({ ...f, flip }))}
                />
              </>
            ) : null}

            {form.kind === "midplane" ? (
              <>
                <SelectField
                  label="First reference"
                  data-testid="datum-side-a"
                  autoFocus
                  value={form.a}
                  options={midplaneSideOptions(datumRefs)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, a: e.target.value }))
                  }
                  aria-label="First midplane reference"
                />
                <SelectField
                  label="Second reference"
                  data-testid="datum-side-b"
                  value={form.b}
                  options={midplaneSideOptions(datumRefs)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, b: e.target.value }))
                  }
                  aria-label="Second midplane reference"
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  The plane midway between the two references. Parallel
                  references give a plane halfway between them; angled ones give
                  their bisector. Pick a face for a reference from the sketch
                  plane picker.
                </p>
                <FlipControl
                  flip={form.flip}
                  onChange={(flip) => setForm((f) => ({ ...f, flip }))}
                />
              </>
            ) : null}
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
