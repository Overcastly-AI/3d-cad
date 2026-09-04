/**
 * The hem editor — folds ONE straight edge of the sheet body ~180° back over
 * itself (sheet-metal parity §2). Mechanically an edge flange at a fixed 180°
 * fold, so it is the EdgeFlangeEditor with a hem framing: the SAME title-block
 * strip + edge-pick overlay/store (single-select: one edge, one hem),
 * keyboard-first (the return-length field autofocuses, Enter commits, Escape
 * cancels), but NO fold-angle field — the angle is always 180°, stated as a
 * quiet caption so the fixed fold is legible rather than hidden.
 *
 * The return `length` is THE parametric handle: it leads the fields and takes
 * focus on open. (It is a plain cell, not `emphasis="primary"` — the same as its
 * EdgeFlangeEditor twin. Promoting one of the pair and not the other would buy a
 * brass numeral at the cost of the consistency the sheet-metal cards read by.)
 *
 * WHAT THE CARD SAYS ABOUT THE RADIUS (HEM-1C/D). The radius is NOT inherited
 * from the base flange: it comes from the hem TYPE and the part's GAUGE, and
 * the fold's cross-section puts the two layers exactly `2 × radius` apart. So
 * the card is built around that consequence rather than around the input:
 *
 *   - a `Type` segment (Closed / Open) — the shape IS the choice a modeller
 *     makes, and hardcoding `closed` made the open hem the API ships
 *     unauthorable by clicking (HEM-1D);
 *   - a live `Gap` readout — the one number a feeler gauge would find, tracking
 *     the type, the part's gauge and any override. It is the quantity HEM-1 got
 *     wrong (6.00 mm of air inside a "closed" hem) while every status read ok;
 *   - guidance derived from the SAME rule the evaluator applies. It used to
 *     read `≈0.5 × gauge` — the OPEN ratio — so the form suggested the exact
 *     value a closed hem is refused for, and kept suggesting it after the
 *     refusal. Every number the card now names is one the evaluator accepts.
 *
 * K-factor is still inherited and still says so: K is a material property, and
 * only the radius stopped being a part-level default.
 *
 * WHAT A GATED SAVE SAYS (HEM-1B). Every state that disables Save states its
 * reason in the Save cell itself — `hemSubmitBlocker` is the single source of
 * both the gate and the sentence, so a grey cell with nothing to read is
 * unreachable. And an override toggle SEEDS its field from the value it is
 * replacing, so "checked with no value" — the state the audit found holding a
 * repair hostage — cannot be produced by clicking in the first place.
 */
import {
  Checkbox,
  formatLength,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { SheetMetalHemParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  bendRadiusError,
  buildHemParams,
  derivedHemRadiusMm,
  type HemForm,
  hemGapInGauges,
  hemGapMm,
  hemLengthError,
  hemRadiusBoundaryMm,
  hemRadiusConflict,
  hemSubmitBlocker,
  type HemType,
  kFactorError,
  resolvedHemRadiusMm,
  type SheetMetalDefaults,
  withHemBendRadiusOverride,
  withHemKFactorOverride,
} from "../features/sheetMetal";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

/** The two hem shapes this fold can build, in the SegmentedControl's order. */
const HEM_TYPES: readonly {
  value: HemType;
  label: string;
  "data-testid": string;
}[] = [
  { value: "closed", label: "Closed", "data-testid": "hem-type-closed" },
  { value: "open", label: "Open", "data-testid": "hem-type-open" },
];

export interface HemEditorProps {
  mode: "create" | "edit";
  initial: HemForm;
  /** The anchor for the picked edge's ref — the current sheet body's feature. */
  bodyFeatureId: string | null;
  /**
   * The part's sheet-metal defaults. The GAUGE sizes the hem (its radius and
   * air gap are multiples of it) and the K-factor is the inherited value behind
   * that override; the part's own bend radius is deliberately unused here — a
   * hem does not inherit it (HEM-1).
   */
  defaults: SheetMetalDefaults | null;
  onSubmit: (params: SheetMetalHemParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}

export function HemEditor({
  mode,
  initial,
  bodyFeatureId,
  defaults,
  onSubmit,
  onCancel,
  saving,
  error,
}: HemEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<HemForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const picked = useEdgePickStore((s) => s.picked);
  const overlayError = useEdgePickStore((s) => s.overlayError);
  const clearPicks = useEdgePickStore((s) => s.clearPicks);

  const submit = useCallback(() => {
    const params = buildHemParams(form, picked, bodyFeatureId, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, picked, bodyFeatureId, onSubmit, unit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  // WHY Save is gated, in the cell that is gated — never an unexplained grey
  // control (HEM-1B). `canSubmitHem` IS "no blocker", so the two cannot disagree.
  const blocker = hemSubmitBlocker(form, picked, bodyFeatureId, unit, defaults);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);

  const inheritedK = defaults !== null ? String(defaults.kFactor) : "—";
  const closed = form.hemType === "closed";
  /** The part's gauge — every hem number below is a multiple of it (HEM-1). */
  const gauge = defaults?.thicknessMm ?? null;

  // Every hem number the card shows comes from this ONE resolution of the rule,
  // so the readout, the guidance and the conflict note cannot disagree.
  const radiusMm = resolvedHemRadiusMm(form, defaults, unit);
  const gapReadout =
    radiusMm === null || gauge === null
      ? "—"
      : `${formatLength(hemGapMm(radiusMm), unit)} (${Number(
          hemGapInGauges(radiusMm, gauge).toFixed(3),
        )} × gauge)`;

  // Guidance for the radius override, in the accepted band for THIS type: the
  // floor/ceiling the evaluator enforces, then the value the type derives. Both
  // numbers are radii it accepts — following this hint cannot produce a refusal.
  const derivedRadius =
    gauge === null
      ? null
      : formatLength(derivedHemRadiusMm(form.hemType, gauge), unit);
  const boundary =
    gauge === null ? null : formatLength(hemRadiusBoundaryMm(gauge), unit);
  const radiusHint =
    derivedRadius === null || boundary === null
      ? "The radius comes from the hem type and the part's gauge."
      : closed
        ? `Use at most ${boundary} for a closed hem; ${derivedRadius} presses it flat.`
        : `Use at least ${boundary} for an open hem; ${derivedRadius} is the standard opening.`;
  const derivedNote =
    derivedRadius === null || gauge === null
      ? "Set by the hem type and the part's gauge."
      : `Set by the hem type and the ${formatLength(gauge, unit)} gauge: ${derivedRadius}.`;

  // The refusal the evaluator would return, said BEFORE the rebuild — and it
  // names the switch that resolves it, which is now one click away. Advisory,
  // never blocking: the evaluator owns this rule (see `buildHemParams`).
  const conflict =
    gauge !== null && form.overrideBendRadius && radiusMm !== null
      ? hemRadiusConflict(form.hemType, radiusMm, gauge, unit)
      : null;

  return (
    <EditorCard
      onKeyDown={onKeyDown}
      // THE ACTION ROW IS PINNED, not scrolled (HEM-1B, the shape `HoleEditor`
      // has used since UI-REVIEW 2026-07-30 P1). It used to ride inside the
      // scrolling body, and at the 1280x800 floor the gated Save's REASON fell
      // out of the card entirely: measured before this change, the sentence's
      // own centre hit-tested to `feature-tree-section`, i.e. the explanation
      // for a grey button was underneath the panel below it. An explanation the
      // stuck user has to scroll for is the defect wearing a longer sentence.
      footer={
        <>
          {error ? (
            <p
              role="alert"
              data-testid="hem-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="hem-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="hem-submit"
              aria-busy={saving}
              disabled={!canSubmit}
              // The reason takes the caption's line while gated and is wired as
              // the cell's `aria-describedby` — eye, pointer and screen reader
              // get the same sentence. While SAVING the label already says so,
              // and a second sentence saying it again would be the one
              // accessory to remove.
              disabledReason={saving ? undefined : (blocker ?? undefined)}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      {/* The panel keeps its own bottom border: it is the rule the pinned
          footer sits under (the footer draws `border-t-0`, exactly as
          `HoleEditor`'s does), so the card still reads as one ruled block. */}
      <Panel aria-label="Hem" data-testid="hem-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New hem" : "Edit hem"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* The one hemmed edge — reuses the fillet/chamfer edge-pick overlay
                in single-select mode (a click replaces the pick). */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="font-body text-xs text-gauge">Edge</span>
                <button
                  type="button"
                  data-testid="hem-pick-clear"
                  disabled={picked.length === 0}
                  onClick={clearPicks}
                  className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:text-gauge disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
              <p
                data-testid="hem-pick-count"
                aria-live="polite"
                className="font-data text-base text-mist"
              >
                {picked.length === 1 ? "1 edge picked" : "No edge picked"}
              </p>
              <p className="font-body text-xs text-gauge">
                Click one straight edge of the sheet to fold it 180° back onto
                itself.
              </p>
              {overlayError ? (
                <p
                  role="alert"
                  data-testid="hem-pick-error"
                  className="font-body text-xs text-flag"
                >
                  {overlayError}
                </p>
              ) : null}
            </div>

            <NumberField
              label="Return length"
              unit={unit}
              data-testid="hem-length"
              autoFocus
              value={form.lengthInput}
              error={hemLengthError(form.lengthInput, unit)}
              onChange={(e) =>
                setForm((f) => ({ ...f, lengthInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            {/* The hem SHAPE — the choice that sets the fold's radius, and with
                it the air gap. Closed presses flat; open keeps a deliberate
                opening. (Teardrop and rolled wrap past 180°: this fold cannot
                build them, so they are not offered.) */}
            <SegmentedControl<HemType>
              label="Type"
              value={form.hemType}
              options={HEM_TYPES}
              onChange={(hemType) => setForm((f) => ({ ...f, hemType }))}
            />

            {/* The fold angle is fixed at 180° for a hem — stated, not a field.
                Keeps the strip honest (no editable no-op). */}
            <div className="flex items-baseline justify-between">
              <span className="font-body text-xs text-gauge">Fold</span>
              <span
                data-testid="hem-fold-readout"
                className="font-data text-base text-mist"
              >
                {closed ? "180° (closed)" : "180° (open)"}
              </span>
            </div>

            {/* THE AIR GAP — what the radius MEANS, and the number HEM-1 got
                wrong while every status read ok. Live: it tracks the type, the
                part's gauge and any override. */}
            <div className="flex items-baseline justify-between">
              <span className="font-body text-xs text-gauge">Gap</span>
              <span
                data-testid="hem-gap-readout"
                aria-live="polite"
                className="font-data text-base text-mist"
              >
                {gapReadout}
              </span>
            </div>

            {/* Bend radius — DERIVED from the type + gauge (never inherited from
                the base flange), overridable per-hem. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override bend radius"
                data-testid="hem-override-radius"
                checked={form.overrideBendRadius}
                // Ticking it SEEDS the field with the radius in force, so the
                // override opens on the number it replaces (HEM-1B) rather than
                // on a blank that silently gates Save.
                onChange={(on) =>
                  setForm((f) =>
                    withHemBendRadiusOverride(f, on, defaults, unit),
                  )
                }
                description={form.overrideBendRadius ? radiusHint : derivedNote}
              />
              {form.overrideBendRadius ? (
                <NumberField
                  label="Bend radius"
                  unit={unit}
                  data-testid="hem-bend-radius"
                  value={form.bendRadiusInput}
                  error={bendRadiusError(form.bendRadiusInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, bendRadiusInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
              {conflict !== null ? (
                <p
                  role="status"
                  data-testid="hem-radius-conflict"
                  className="font-body text-xs text-flag"
                >
                  {conflict}
                </p>
              ) : null}
            </div>

            {/* K-factor — inherited unless overridden per-hem. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override K-factor"
                data-testid="hem-override-k"
                checked={form.overrideKFactor}
                // Seeded from the inherited K the line below names, so the box
                // and the field always agree (HEM-1B).
                onChange={(on) =>
                  setForm((f) => withHemKFactorOverride(f, on, defaults))
                }
                description={
                  form.overrideKFactor
                    ? undefined
                    : `Inherits ${inheritedK} from the base flange.`
                }
              />
              {form.overrideKFactor ? (
                <NumberField
                  label="K-factor"
                  data-testid="hem-k-factor"
                  value={form.kFactorInput}
                  error={kFactorError(form.kFactorInput)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, kFactorInput: e.target.value }))
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
