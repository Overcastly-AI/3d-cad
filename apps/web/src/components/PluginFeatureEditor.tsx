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
  Stamp,
} from "@loft/design";
import { useQuery } from "@tanstack/react-query";
import { type KeyboardEvent, useCallback, useState } from "react";

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
} from "../features/pluginForm";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";
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
}

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

  const setValue = useCallback((name: string, value: string) => {
    setForm((f) => ({ ...f, values: { ...f.values, [name]: value } }));
  }, []);

  const errors = validatePluginForm(manifest, form, unit, features, selfId);
  const blocker = saving ? null : firstPluginBlocker(manifest, errors);
  const canSubmit = blocker === null && !saving;

  const submit = useCallback(() => {
    const inputs = pluginInputsFromForm(manifest, form, unit, features, selfId);
    if (inputs === null) return;
    onSubmit({
      pluginId: manifest.id,
      pluginVersion: manifest.version,
      inputs,
    });
  }, [manifest, form, unit, features, selfId, onSubmit]);
  useCommandBridge(submit, canSubmit);

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
        <p className="px-3 pb-1 font-body text-xs text-gauge">
          {manifest.description}
        </p>
        <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
          {manifest.inputs.map((input, index) => {
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
              field = (
                <SelectField
                  label={input.label}
                  data-testid={testId}
                  autoFocus={index === 0}
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
            return (
              <div key={input.name} className="flex flex-col gap-0.5">
                {field}
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
      ? value.map((ref) => name(ref.feature_id)).join(", ")
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
