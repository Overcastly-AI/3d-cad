/**
 * The corner-relief editor — cuts a rectangular notch at the shared corner of
 * TWO adjacent edge flanges so that corner develops into a single, flat,
 * non-overlapping blank (sheet-metal parity §4.4). Same title-block strip the
 * other sheet-metal editors use, keyboard-first (Enter commits, Escape cancels).
 *
 * Unlike a hem this is NOT an edge pick — it references two existing edge-flange
 * FEATURES by id. With today's pick infrastructure the cleanest, fully
 * keyboard-reachable affordance is two ruled selects (Bend A / Bend B) listing
 * the part's edge flanges by name; the current selection is mirrored up
 * (`onBendsChange`) so the workspace highlights + tags those bends in the
 * viewport (`BendHighlightOverlay`), and a direct viewport bend-face pick is a
 * follow-up (docs/design/sheet-metal-parity.md). The corner/perpendicular check
 * is the kernel's — a parallel or non-touching pair comes back as the typed
 * `corner_relief_failed` / `reference_unresolved`, surfaced verbatim below.
 *
 * The notch is sized `relief_ratio × gauge` by default (1.0 = one thickness, the
 * tear-safe default); an absolute size override wins when its toggle is on. When
 * inheriting, the resolved size is previewed from the base-flange gauge so the
 * ratio is never an opaque number.
 */
import {
  Checkbox,
  NumberField,
  Panel,
  PanelActionCell,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { SheetMetalCornerReliefParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import {
  buildCornerReliefParams,
  cornerReliefSubmitBlocker,
  type CornerReliefForm,
  parseReliefRatio,
  reliefRatioError,
  reliefSizeError,
  type SheetMetalDefaults,
  unresolvedBendRef,
} from "../features/sheetMetal";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface CornerReliefEditorProps {
  mode: "create" | "edit";
  initial: CornerReliefForm;
  /** The part's edge-flange features (id + name) offered as the two bends. */
  edgeFlanges: readonly { id: string; name: string }[];
  /** The part's base-flange defaults — the gauge previews the ratio-sized notch. */
  defaults: SheetMetalDefaults | null;
  onSubmit: (params: SheetMetalCornerReliefParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
  /**
   * Reports the CURRENT Bend A / Bend B selection (on open and on every
   * change) so the workspace can highlight those flanges' bends in the
   * viewport — the in-scene answer to which option is which corner.
   */
  onBendsChange?: (bendAId: string, bendBId: string) => void;
}

export function CornerReliefEditor({
  mode,
  initial,
  edgeFlanges,
  defaults,
  onSubmit,
  onCancel,
  saving,
  error,
  onBendsChange,
}: CornerReliefEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<CornerReliefForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  // Mirror the live bend selection up for the viewport highlight.
  useEffect(() => {
    onBendsChange?.(form.bendAId, form.bendBId);
  }, [form.bendAId, form.bendBId, onBendsChange]);

  const submit = useCallback(() => {
    const params = buildCornerReliefParams(form, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit, unit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  // Edit-mode guard: a stored bend whose flange was rolled back or removed no
  // longer resolves — the select shows an explicit (disabled) guard entry
  // instead of silently displaying the wrong flange, and submit stays off
  // until a live flange is picked.
  const unresolvedA = unresolvedBendRef(edgeFlanges, form.bendAId);
  const unresolvedB = unresolvedBendRef(edgeFlanges, form.bendBId);

  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Save with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already. The unresolved-bend guard is composed HERE rather than in
  // `cornerReliefSubmitBlocker` because it is a fact about the live tree, not
  // about the form, and the form module has no view of the tree.
  const blocker = saving
    ? null
    : unresolvedA
      ? "Bend A is gone — pick a live edge flange."
      : unresolvedB
        ? "Bend B is gone — pick a live edge flange."
        : cornerReliefSubmitBlocker(form, unit);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);

  const options = edgeFlanges.map((f) => ({ value: f.id, label: f.name }));
  const guardOptions = (unresolved: boolean, value: string) =>
    unresolved
      ? [{ value, label: "Missing edge flange", disabled: true }, ...options]
      : options;
  const guardError = (unresolved: boolean) =>
    unresolved ? "This bend no longer exists. Pick an edge flange." : null;
  const sameBend =
    form.bendAId !== "" && form.bendAId === form.bendBId
      ? "Pick two different edge flanges — the two bends that meet at the corner."
      : null;

  // The resolved notch size when inheriting the ratio: relief_ratio × gauge.
  const ratio = parseReliefRatio(form.reliefRatioInput);
  const notchPreview =
    !form.overrideSize && ratio !== null && defaults !== null
      ? `≈ ${Math.round(ratio * defaults.thicknessMm * 100) / 100} mm (${ratio} × ${defaults.thicknessMm} mm gauge)`
      : null;

  return (
    <EditorCard
      onKeyDown={onKeyDown}
      // THE ACTION ROW IS PINNED, not scrolled (REASON-GATE-1, the shape
      // `HoleEditor` has used since UI-REVIEW 2026-07-30 P1 and `HemEditor`
      // since HEM-1B). It used to ride inside the scrolling body, so at the
      // 1280x800 floor a tall form could put the commit action — and the
      // sentence explaining why it is grey — below the fold of its own card.
      // An explanation the stuck user has to scroll for is the defect wearing
      // a longer sentence.
      footer={
        <>
          {error ? (
            <p
              role="alert"
              data-testid="corner-relief-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="corner-relief-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="corner-relief-submit"
              aria-busy={saving}
              disabled={!canSubmit}
              // The reason takes the caption's line while gated and is wired as
              // the cell's `aria-describedby` — eye, pointer and screen reader
              // get the same sentence. `blocker` is null while SAVING: the
              // label already says so, and a second sentence saying it again
              // would be the one accessory to remove.
              disabledReason={blocker ?? undefined}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel aria-label="Corner relief" data-testid="corner-relief-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New corner relief" : "Edit corner relief"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SelectField
              label="Bend A"
              data-testid="corner-relief-bend-a"
              autoFocus
              value={form.bendAId}
              error={guardError(unresolvedA)}
              options={guardOptions(unresolvedA, form.bendAId)}
              onChange={(e) =>
                setForm((f) => ({ ...f, bendAId: e.target.value }))
              }
            />
            <SelectField
              label="Bend B"
              data-testid="corner-relief-bend-b"
              value={form.bendBId}
              error={guardError(unresolvedB) ?? sameBend}
              options={guardOptions(unresolvedB, form.bendBId)}
              onChange={(e) =>
                setForm((f) => ({ ...f, bendBId: e.target.value }))
              }
            />
            <p className="font-body text-xs text-gauge">
              The two edge flanges whose bends meet at the corner to relieve.
              Each pick is tagged on its bend in the viewport.
            </p>

            <NumberField
              label="Relief ratio"
              unit="× gauge"
              data-testid="corner-relief-ratio"
              value={form.reliefRatioInput}
              error={reliefRatioError(form.reliefRatioInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, reliefRatioInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />
            {notchPreview ? (
              <p
                data-testid="corner-relief-size-preview"
                aria-live="polite"
                className="font-data text-2xs text-gauge"
              >
                Notch {notchPreview}
              </p>
            ) : null}

            {/* Absolute size override — wins over the ratio when on. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override notch size"
                data-testid="corner-relief-override-size"
                checked={form.overrideSize}
                onChange={(overrideSize) =>
                  setForm((f) => ({ ...f, overrideSize }))
                }
                description={
                  form.overrideSize
                    ? "An absolute notch size, ignoring the ratio."
                    : "Sizes the notch from the ratio × the part gauge."
                }
              />
              {form.overrideSize ? (
                <NumberField
                  label="Notch size"
                  unit={unit}
                  data-testid="corner-relief-size"
                  value={form.sizeInput}
                  error={reliefSizeError(form.sizeInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, sizeInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
            </div>
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}
