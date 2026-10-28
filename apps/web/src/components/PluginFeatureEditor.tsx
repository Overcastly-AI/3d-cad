/**
 * A custom feature's dialog (PLUGIN-UI, RESEARCH §23), GENERATED from the
 * plugin's served manifest, as Onshape builds a custom feature's dialog from
 * its precondition: no plugin has a hand-written form.
 *
 * Every numeric input is a `<ValueField>`, so it takes a number in the
 * document unit or a formula over the part's parameters (`twist*2`), kept by
 * pointer at `/inputs/<name>` for documents to resolve. The manifest's bounds
 * are checked on the field (`features/pluginForm`) before a round trip, and
 * the server's typed refusals (a feature limit, a plugin that cannot build
 * this) are stated in the card's alert slot with their heading.
 *
 * A feature whose plugin (or pinned version) this server lacks opens READ-
 * ONLY: it still rebuilds from its stored members, and the card says so and
 * shows what it was built from.
 */
import {
  Checkbox,
  Notice,
  Panel,
  PanelActionCell,
  SegmentedControl,
  SelectField,
  SelectionField,
  Stamp,
  formatLength,
} from "@loft/design";
import { useQuery } from "@tanstack/react-query";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { fetchMaterials } from "../api/materials";
import type { FeatureResponse } from "../api/parts";
import type {
  CustomFeatureWrite,
  CustomParams,
  PluginInput,
  PluginManifest,
} from "../api/plugins";
import { useCommandBridge } from "../features/commandActions";
import {
  bracketedPluginCode,
  pluginAvailability,
  pluginErrorSentence,
} from "../features/customFeature";
import {
  boundsPhrase,
  defaultPluginForm,
  fieldKind,
  firstPluginBlocker,
  formFromCustomParams,
  inputPointer,
  inputUnit,
  isNumericInput,
  pickedIds,
  type PluginForm,
  pluginInputsFromForm,
  referenceOptions,
  togglePick,
  validatePluginForm,
  withPluginValue,
} from "../features/pluginForm";
import {
  DISTANCE,
  distanceMm,
  endDistances,
  hasMeasureFrom,
  hostWallLine,
  MEASURE_FROM,
  nearerEnd,
  type WallEnd,
  withReference,
} from "../features/openingMeasure";
import { isOutlinePick, sideName } from "../features/outline";
import { featureUpdate, updateToLabel } from "../features/pluginUpdate";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { SolvedSketchLayer } from "../viewport/solvedSketchLayer";
import { EditorCard } from "./EditorCard";
import { PluginListField } from "./PluginListField";
import { toggleSide, useOutlinePick } from "./useOutlinePick";
import { ValueField } from "./ValueField";

export interface PluginFeatureEditorProps {
  mode: "create" | "edit";
  pluginId: string;
  pluginVersion: string;
  /** The feature being edited (edit mode), else undefined. */
  featureId?: string | undefined;
  /** Its stored params (edit mode): the inputs the form seeds from. */
  stored?: CustomParams | undefined;
  /** The installed plugins, or undefined while they load. */
  catalog: readonly PluginManifest[] | undefined;
  /** The part's tree, in build order (reference choices). */
  features: readonly FeatureResponse[];
  onSubmit: (write: CustomFeatureWrite) => void;
  onCancel: () => void;
  saving: boolean;
  /** A save's refusal or the feature's own rebuild error, or null. */
  error: string | null;
  /**
   * The part's solved sketches: where an Outline's lines are drawn for the
   * viewport pick (BUILDING-OUTLINE). Absent: the picks are the form's only.
   */
  sketchLayers?: readonly SolvedSketchLayer[] | undefined;
  /**
   * Update the stored feature to the newer release the server offers
   * (OPENING-UPDATE, `plugin_update`), its inputs carried by the plugin's
   * explicit map: one edit, one Undo. Absent: no update action.
   */
  onUpdate?: (() => void) | undefined;
}

const NO_LAYERS: readonly SolvedSketchLayer[] = [];

/** A stored feature's warning, headed by what it is about. */
const WARNING_LABELS: Record<string, string> = {
  roof_through_sheathing: "Through sheathing",
  crawl_height_low: "Crawl height",
};

/** A segmented control reads cleanly for a few short options, else a select. */
function segmented(input: Extract<PluginInput, { kind: "choice" }>): boolean {
  return (
    input.options.length <= 3 &&
    input.options.every((option) => option.label.length <= 10)
  );
}

/** `[plugin_x] message` (an evaluation's input_error) as a headed sentence. */
function shownError(error: string | null): string | null {
  if (error === null) return null;
  const code = bracketedPluginCode(error);
  if (code === null) return error;
  return pluginErrorSentence(code, error.replace(/^\[[a-z_]+\]\s*/, ""));
}

export function PluginFeatureEditor(props: PluginFeatureEditorProps) {
  const availability = pluginAvailability(props.catalog, {
    plugin_id: props.pluginId,
    plugin_version: props.pluginVersion,
  });
  if (availability.state === "ready") {
    return <GeneratedForm {...props} manifest={availability.manifest} />;
  }
  return <ReadOnlyCard {...props} loading={availability.state === "loading"} />;
}

function GeneratedForm({
  mode,
  manifest,
  featureId,
  stored,
  features,
  onSubmit,
  onCancel,
  saving,
  error,
  sketchLayers = NO_LAYERS,
  onUpdate,
}: PluginFeatureEditorProps & { manifest: PluginManifest }) {
  const unit = useDocumentLengthUnit();
  const selfId = featureId ?? null;
  // Seeded once per opened feature (the seat keys this card by plugin and
  // feature): a tree refetch mid-edit must not throw away what is typed.
  const [form, setForm] = useState<PluginForm>(() =>
    stored === undefined
      ? defaultPluginForm(manifest, unit, features)
      : formFromCustomParams(manifest, stored, unit),
  );

  // An opening measured from a wall end (OPENING-MEASURE-SWITCH): the host
  // wall's line, read from its stored members, so changing the reference
  // converts the distance and the opening stays put.
  const measured = hasMeasureFrom(manifest.inputs);
  const hostOf = useCallback(
    (values: Readonly<Record<string, string>>) =>
      measured
        ? hostWallLine(
            features,
            values.host_wall ?? "",
            values.wall_segment ?? "",
          )
        : null,
    [measured, features],
  );
  const host = useMemo(() => hostOf(form.values), [hostOf, form.values]);

  // A new outline drops the side picks made on the old one.
  const setValue = useCallback(
    (name: string, value: string) => {
      setForm((f) => ({
        ...f,
        values:
          measured && name === MEASURE_FROM
            ? withReference(
                f.values,
                value,
                hostOf(f.values),
                unit,
                f.stored?.[DISTANCE],
              )
            : withPluginValue(manifest, f.values, name, value, features),
      }));
    },
    [manifest, features, measured, hostOf, unit],
  );

  // A click on one end's read-out makes that end the reference and puts the
  // caret in the distance, as a Revit temporary dimension takes a click.
  const distanceInput = useRef<HTMLInputElement | null>(null);
  const focusDistance = useRef(false);
  const measureFromEnd = useCallback(
    (end: WallEnd) => {
      focusDistance.current = true;
      setValue(MEASURE_FROM, end);
    },
    [setValue],
  );
  useEffect(() => {
    if (!focusDistance.current) return;
    focusDistance.current = false;
    distanceInput.current?.focus();
    distanceInput.current?.select();
  }, [form]);

  const outlinePick = useOutlinePick({
    manifest,
    values: form.values,
    setValue,
    features,
    selfId,
    layers: sketchLayers,
  });

  const errors = validatePluginForm(manifest, form, unit, features, selfId);
  const blocker = saving ? null : firstPluginBlocker(manifest, errors);
  const canSubmit = blocker === null && !saving;

  // Save under a pin: this release (Save), or a newer one that fixes what
  // this one builds wrong (ROOF-THROUGH-SHEATHING-UPDATE). Either is one
  // ordinary edit of the feature, so Undo restores it.
  const saveAs = useCallback(
    (pluginVersion: string) => {
      const inputs = pluginInputsFromForm(
        manifest,
        form,
        unit,
        features,
        selfId,
      );
      if (inputs === null) return;
      onSubmit({ pluginId: manifest.id, pluginVersion, inputs });
    },
    [manifest, form, unit, features, selfId, onSubmit],
  );
  const submit = useCallback(
    () => saveAs(manifest.version),
    [saveAs, manifest.version],
  );
  useCommandBridge(submit, canSubmit);

  // What the stored feature's release builds wrong, read from the live tree
  // so an update clears it (a roof's tails through the wall sheathing).
  const row =
    mode === "edit" ? features.find((f) => f.id === featureId) : undefined;
  const warnings = row?.plugin_warnings ?? [];
  // A newer release that maps this feature's inputs (OPENING-UPDATE): the
  // server re-pins it, so the action is one edit whatever the form holds.
  const update = row === undefined ? null : featureUpdate(row);
  const serverUpdate =
    update !== null && onUpdate !== undefined && !saving ? onUpdate : null;

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter" && !event.defaultPrevented) {
        event.preventDefault();
        if (canSubmit) submit();
      }
    },
    [canSubmit, submit],
  );

  const materialsWanted = manifest.inputs.some((i) => i.kind === "material");
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: () => fetchMaterials(),
    staleTime: Infinity,
    enabled: materialsWanted,
  });

  const alert = shownError(error);
  return (
    <EditorCard
      onKeyDown={onKeyDown}
      footer={
        <>
          {alert !== null ? (
            <p
              role="alert"
              data-testid="plugin-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {alert}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="plugin-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="plugin-submit"
              aria-busy={saving}
              disabled={!canSubmit}
              disabledReason={blocker ?? undefined}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel
        aria-label={manifest.title}
        data-testid="plugin-editor"
        data-plugin={manifest.id}
      >
        <div className="flex items-baseline gap-2 px-3 pb-1 pt-3">
          <h2 className="grow font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New" : "Edit"} {manifest.title}
          </h2>
          <span
            className="font-data text-2xs text-gauge"
            data-testid="plugin-version"
          >
            v{manifest.version}
          </span>
        </div>
        {update !== null ? (
          <Notice
            role="status"
            tone="gauge"
            label="Update available"
            layout="stacked"
            data-testid="plugin-update-notice"
            action={
              serverUpdate === null
                ? undefined
                : {
                    label: updateToLabel(update.toVersion),
                    testId: "plugin-update",
                    onClick: serverUpdate,
                  }
            }
          >
            {`${manifest.title} ${update.toVersion}: ${update.summary} Undo restores this release.`}
          </Notice>
        ) : null}
        {warnings.map((warning) => {
          // The update notice above carries the action when the server
          // offers the same release; else the form re-saves under it.
          const target =
            update !== null && update.toVersion === warning.update_to
              ? null
              : warning.update_to;
          return (
            <Notice
              key={warning.code}
              role="status"
              label={WARNING_LABELS[warning.code] ?? "Warning"}
              layout="stacked"
              data-testid="plugin-warning"
              action={
                target === null || target === undefined
                  ? undefined
                  : {
                      label: `Update to ${target}`,
                      testId: "plugin-update",
                      onClick: () => {
                        if (canSubmit) saveAs(target);
                      },
                    }
              }
            >
              {warning.message}
            </Notice>
          );
        })}
        <p className="px-3 pb-1 font-body text-xs text-gauge">
          {manifest.description}
        </p>
        <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
          {manifest.inputs.map((input, index) => {
            // A field a pick has replaced is hidden (superseded_by): a
            // wall's typed line once its Outline is picked.
            if (outlinePick.hidden.has(input.name)) return null;
            const value = form.values[input.name] ?? "";
            const fieldError = errors[input.name] ?? null;
            const testId = `plugin-input-${input.name}`;
            let field;
            if (isNumericInput(input)) {
              const bounds = boundsPhrase(input, unit);
              field = (
                <ValueField
                  label={input.label}
                  unit={inputUnit(input, unit)}
                  kind={fieldKind(input)}
                  pointer={inputPointer(input.name)}
                  inputMode="text"
                  data-testid={testId}
                  value={value}
                  error={fieldError}
                  title={bounds === null ? undefined : `Allowed: ${bounds}`}
                  autoFocus={index === 0}
                  inputRef={
                    measured && input.name === DISTANCE
                      ? distanceInput
                      : undefined
                  }
                  onValueChange={(text) => setValue(input.name, text)}
                  onFocus={(e) => e.currentTarget.select()}
                />
              );
            } else if (input.kind === "features") {
              // Several picks (a roof's walls): a checklist of the earlier
              // features it may name, kept in pick order.
              const picked = pickedIds(value);
              field = (
                <fieldset
                  data-testid={testId}
                  className="flex flex-col gap-0.5"
                  aria-invalid={fieldError !== null}
                >
                  <legend className="font-body text-xs text-gauge">
                    {input.label}
                    {picked.length > 0 ? ` (${picked.length} picked)` : ""}
                  </legend>
                  {referenceOptions(input, features, selfId).map((option) => (
                    <Checkbox
                      key={option.value}
                      label={option.label}
                      checked={picked.includes(option.value)}
                      data-testid={`${testId}-pick`}
                      onChange={() =>
                        setValue(input.name, togglePick(value, option.value))
                      }
                    />
                  ))}
                  {fieldError !== null ? (
                    <p className="font-body text-2xs text-flag">{fieldError}</p>
                  ) : null}
                </fieldset>
              );
            } else if (input.kind === "segments") {
              // Lines of the outline, picked in the viewport or toggled here,
              // named by the way their walls face (BUILDING-OUTLINE).
              const sides = outlinePick.outlines.get(input.name)?.sides ?? null;
              const picked = pickedIds(value);
              field = (
                <SelectionField
                  label={input.label}
                  data-testid={testId}
                  armed={outlinePick.live === input.name}
                  onArm={() => outlinePick.arm(input.name)}
                  picked={picked.map((id) => sideName(sides, id))}
                  placeholder={sides === null ? "No outline" : "Select"}
                  onClear={() => setValue(input.name, "")}
                  options={(sides ?? []).map((side) => ({
                    value: side.lineId,
                    label: side.name,
                    selected: picked.includes(side.lineId),
                  }))}
                  onToggle={(lineId) => {
                    outlinePick.arm(input.name);
                    setValue(input.name, toggleSide(input, value, lineId));
                  }}
                  emptyHint={
                    sides === null
                      ? "Picks the walls of an outline: pick one above."
                      : undefined
                  }
                  error={fieldError}
                />
              );
            } else if (input.kind === "list") {
              // Rows of fields (a cabinet run's boxes), added and removed.
              field = (
                <PluginListField
                  input={input}
                  value={value}
                  unit={unit}
                  errors={errors}
                  data-testid={testId}
                  onChange={(text) => setValue(input.name, text)}
                />
              );
            } else if (input.kind === "choice" && segmented(input)) {
              field = (
                <SegmentedControl
                  label={input.label}
                  value={value}
                  options={input.options.map((option) => ({
                    value: option.value,
                    label: option.label,
                    "data-testid": `${testId}-${option.value}`,
                  }))}
                  onChange={(next) => setValue(input.name, next)}
                />
              );
            } else {
              const options =
                input.kind === "choice"
                  ? input.options.map((o) => ({
                      value: o.value,
                      label: o.label,
                    }))
                  : input.kind === "material"
                    ? (materials.data ?? []).map((m) => ({
                        value: m.key,
                        label: m.name,
                      }))
                    : referenceOptions(input, features, selfId);
              const optional =
                input.kind === "material" ||
                (input.kind === "feature" && input.optional);
              const outline = isOutlinePick(input);
              field = (
                <SelectField
                  label={input.label}
                  data-testid={testId}
                  data-armed={
                    outline
                      ? String(outlinePick.live === input.name)
                      : undefined
                  }
                  autoFocus={index === 0}
                  // An Outline field is live once touched: a click on a
                  // sketch in the viewport or the browser fills it.
                  onFocus={
                    outline ? () => outlinePick.arm(input.name) : undefined
                  }
                  value={value}
                  error={fieldError}
                  options={
                    optional || value === ""
                      ? [
                          { value: "", label: optional ? "None" : "—" },
                          ...options,
                        ]
                      : options
                  }
                  onChange={(e) => setValue(input.name, e.target.value)}
                />
              );
            }
            const hint =
              isOutlinePick(input) && outlinePick.live === input.name
                ? "Click a closed sketch in the viewport or the browser."
                : null;
            const ends =
              measured && input.name === DISTANCE ? (
                <EndsReadout
                  ends={endDistances(
                    distanceMm(value, unit, form.stored?.[DISTANCE]),
                    form.values[MEASURE_FROM] ?? "",
                    host,
                  )}
                  reference={
                    host === null
                      ? null
                      : form.values[MEASURE_FROM] === "nearer"
                        ? nearerEnd(host)
                        : (form.values[MEASURE_FROM] ?? null)
                  }
                  format={(mm) => formatLength(mm, unit)}
                  onPick={measureFromEnd}
                />
              ) : null;
            return (
              <div key={input.name} className="flex flex-col gap-0.5">
                {field}
                {ends}
                {hint !== null ? (
                  <p
                    className="font-body text-2xs text-brass"
                    data-testid={`${testId}-hint`}
                  >
                    {hint}
                  </p>
                ) : null}
                {input.description ? (
                  <p className="font-body text-2xs text-gauge">
                    {input.description}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      </Panel>
    </EditorCard>
  );
}

/**
 * The opening's distance from both wall ends ("48 in from start · 192 in
 * from end"), as Revit's temporary dimensions read it: a click on either
 * makes that end the reference.
 */
function EndsReadout({
  ends,
  reference,
  format,
  onPick,
}: {
  ends: { start: number; end: number } | null;
  reference: string | null;
  format: (mm: number) => string;
  onPick: (end: WallEnd) => void;
}) {
  if (ends === null) return null;
  const cell = (end: WallEnd, mm: number) => (
    <button
      type="button"
      data-testid={`opening-ends-${end}`}
      aria-pressed={reference === end}
      title={`Measure from the wall ${end}`}
      onClick={() => onPick(end)}
      className={
        "rounded-sm px-0.5 font-data underline decoration-dotted underline-offset-2 " +
        "transition-colors duration-fast hover:text-brass " +
        "focus-visible:outline focus-visible:outline-1 focus-visible:outline-brass " +
        (reference === end ? "text-mist" : "text-gauge")
      }
    >
      {format(mm)} from {end}
    </button>
  );
  return (
    <p data-testid="opening-ends" className="font-data text-2xs text-gauge">
      {cell("start", ends.start)}
      {" · "}
      {cell("end", ends.end)}
    </p>
  );
}

/** The card for a feature this server cannot edit (or before the catalog). */
function ReadOnlyCard({
  pluginId,
  pluginVersion,
  stored,
  features,
  onCancel,
  loading,
}: PluginFeatureEditorProps & { loading: boolean }) {
  useCommandBridge(onCancel, false);
  const name = (id: string) =>
    features.find((row) => row.id === id)?.name ?? id;
  const rows = Object.entries(stored?.inputs ?? {}).map(([key, value]) => [
    key,
    Array.isArray(value)
      ? (value as unknown[])
          .map((item) =>
            typeof item === "string"
              ? item
              : typeof item === "object" &&
                  item !== null &&
                  "feature_id" in item
                ? name(String(item.feature_id))
                : `(${Object.values(item as object).join(" ")})`,
          )
          .join(", ")
      : typeof value === "object"
        ? name(value.feature_id)
        : String(value),
  ]);
  return (
    <EditorCard
      footer={
        <div className="grid grid-cols-1 border border-hairline bg-anvil">
          <PanelActionCell
            label="Close"
            caption="Esc"
            data-testid="plugin-cancel"
            onClick={onCancel}
          />
        </div>
      }
    >
      <Panel aria-label="Custom feature" data-testid="plugin-editor">
        <div className="flex items-baseline gap-2 px-3 pb-1 pt-3">
          <h2 className="grow font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {pluginId}
          </h2>
          <Stamp tone="gauge" data-testid="plugin-read-only">
            Read-only
          </Stamp>
        </div>
        <div className="px-3 pb-2">
          {loading ? (
            <p className="font-body text-xs text-gauge">Loading plugins…</p>
          ) : (
            <Notice
              role="status"
              tone="gauge"
              label="Plugin missing"
              layout="stacked"
              data-testid="plugin-missing"
            >
              {`${pluginId} v${pluginVersion} is not installed on this server. The feature rebuilds from its stored members and cannot be edited here.`}
            </Notice>
          )}
        </div>
        {rows.length > 0 ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 px-3 pb-3">
            {rows.map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="font-body text-xs text-gauge">{key}</dt>
                <dd className="truncate font-data text-xs text-mist">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </Panel>
    </EditorCard>
  );
}
