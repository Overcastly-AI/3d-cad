/**
 * The loft editor — the sweep editor's twin, in the same title-block seat
 * top-left of the viewport (you author one feature at a time). Its distinctive
 * field is the ORDERED SECTION STACK: where sweep names two fixed slots
 * (profile + path), a loft skins a solid through a reorderable LIST of ≥2
 * section sketches, blended in list ORDER. Each row is a ruled SelectField over
 * the tree's earlier sketch features; rows add / remove / reorder, and the
 * two-digit ordinals renumber live so the sequence on screen is always the
 * blend sequence sent to the kernel.
 *
 * Signature: a quiet "blend spine" — a hairline threading a punch-mark node on
 * each numbered section — echoes the icon set's scribe nodes and the feature
 * tree's title-block numbering (order is truth here, so numbering encodes it).
 * Keyboard-first: the first section select autofocuses, Enter commits, Escape
 * cancels — the sketcher's dimension grammar. The scope note carries the honest
 * v1 limits (ruled loft, apex only first/last, no guide rails/tangency).
 */
import {
  AddIcon,
  CaretDownIcon,
  CloseIcon,
  CutIcon,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useState,
} from "react";

import type { LoftParams } from "../api/parts";
import {
  addSection,
  buildLoftParams,
  canSubmitLoft,
  type LoftForm,
  type LoftOperation,
  MIN_LOFT_SECTIONS,
  moveSection,
  type ProfileOption,
  removeSectionAt,
  setSectionAt,
} from "../features/loft";

export interface LoftEditorProps {
  mode: "create" | "edit";
  /** Every sketch feature in the tree, in build order (the section choices). */
  sections: readonly ProfileOption[];
  /** The seed form (new-loft defaults, or an existing loft's params). */
  initial: LoftForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: LoftParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

const OPERATIONS: ReadonlyArray<SegmentOption<LoftOperation>> = [
  {
    value: "add",
    label: "Add",
    icon: <AddIcon />,
    "data-testid": "loft-op-add",
    "aria-label": "Operation: Add",
  },
  {
    value: "cut",
    label: "Cut",
    icon: <CutIcon />,
    "data-testid": "loft-op-cut",
    "aria-label": "Operation: Cut",
  },
];

export function LoftEditor({
  mode,
  sections,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: LoftEditorProps) {
  const [form, setForm] = useState<LoftForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildLoftParams(form);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit]);

  // Enter commits, Escape cancels — except when a row control (a button) has
  // focus: Enter must fire that button's own action (reorder/remove/add), not
  // the whole-form submit.
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

  const canSubmit = canSubmitLoft(form) && !saving;
  const canRemove = form.sections.length > MIN_LOFT_SECTIONS;

  return (
    <div
      className="absolute left-editor top-3 w-80 max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Loft" data-testid="loft-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New loft" : "Edit loft"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* The section stack: each ordinal is threaded on a blend spine —
                a hairline down the left with a punch-mark node per section. The
                numbers ARE the blend order (reordering renumbers live). */}
            <ol
              data-testid="loft-sections"
              className="ml-1 flex flex-col gap-1.5 border-l border-etch pl-3"
            >
              {form.sections.map((sectionId, index) => {
                const ordinal = String(index + 1).padStart(2, "0");
                return (
                  <li
                    // Order can change but position is the stable identity: the
                    // SelectField is controlled by `value`, so index-keying is
                    // correct (the slot stays, its chosen sketch moves).
                    key={index}
                    data-testid="loft-section-row"
                    className="relative flex items-end gap-1.5"
                  >
                    <span
                      aria-hidden
                      className="absolute bottom-[9px] -left-[15px] h-1.5 w-1.5 rounded-full bg-gauge"
                    />
                    <SelectField
                      className="grow"
                      label={`Section ${ordinal}`}
                      data-testid={`loft-section-${index}`}
                      autoFocus={index === 0}
                      value={sectionId}
                      options={sectionSelectOptions(sections, sectionId)}
                      onChange={(e) =>
                        setForm((f) => setSectionAt(f, index, e.target.value))
                      }
                    />
                    <div className="flex shrink-0 items-center pb-1">
                      <RowButton
                        label={`Move section ${ordinal} up`}
                        data-testid={`loft-section-up-${index}`}
                        disabled={index === 0}
                        onClick={() =>
                          setForm((f) => moveSection(f, index, -1))
                        }
                      >
                        <CaretDownIcon className="rotate-180" />
                      </RowButton>
                      <RowButton
                        label={`Move section ${ordinal} down`}
                        data-testid={`loft-section-down-${index}`}
                        disabled={index === form.sections.length - 1}
                        onClick={() => setForm((f) => moveSection(f, index, 1))}
                      >
                        <CaretDownIcon />
                      </RowButton>
                      <RowButton
                        label={`Remove section ${ordinal}`}
                        data-testid={`loft-section-remove-${index}`}
                        disabled={!canRemove}
                        onClick={() =>
                          setForm((f) => removeSectionAt(f, index))
                        }
                      >
                        <CloseIcon />
                      </RowButton>
                    </div>
                  </li>
                );
              })}
            </ol>

            <button
              type="button"
              data-testid="loft-add-section"
              onClick={() => setForm((f) => addSection(f))}
              className="flex items-center gap-1.5 self-start rounded-sm px-1 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-brass transition-colors duration-fast hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
            >
              <AddIcon size={14} aria-hidden />
              Add section
            </button>

            <SegmentedControl
              label="Operation"
              value={form.operation}
              options={OPERATIONS}
              onChange={(operation) => setForm((f) => ({ ...f, operation }))}
            />

            <p
              className="-mt-0.5 font-body text-xs text-gauge"
              data-testid="loft-note"
            >
              A ruled loft skins a solid through the sections in this order.
              Each section is an earlier sketch — a closed profile, or a single
              point as an apex (first or last only). No guide rails or tangency
              yet.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="loft-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="loft-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="loft-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** A compact scribe-node control for a section row (reorder / remove). */
function RowButton({
  label,
  disabled,
  onClick,
  children,
  ...rest
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
  "data-testid": string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-gauge transition-colors duration-fast hover:bg-carbide hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-30"
      {...rest}
    >
      {children}
    </button>
  );
}

/**
 * The section-select options for one row: an unchosen placeholder ("") followed
 * by every eligible earlier sketch. The placeholder keeps an added-but-unpicked
 * row honestly blank (blocking submit) instead of silently defaulting.
 */
function sectionSelectOptions(
  sections: readonly ProfileOption[],
  currentValue: string,
): { value: string; label: string }[] {
  const options = sections.map((s) => ({ value: s.id, label: s.name }));
  if (currentValue === "") {
    return [{ value: "", label: "Choose a section…" }, ...options];
  }
  return options;
}
