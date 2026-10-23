/**
 * THE FORM GENERATOR for custom features (PLUGIN-UI, RESEARCH §23).
 *
 * A plugin's dialog is never hand-written: it is generated from the served
 * manifest's typed inputs, as Onshape builds a custom feature's dialog from
 * its FeatureScript precondition. This module is the pure half — what each
 * input's field holds, what it seeds with, how it validates and what the
 * write sends — so the generated form is unit-tested without a DOM.
 *
 *  - length / angle / count: a numeric `<ValueField>` (a number in the
 *    document unit, or a §20 formula such as `twist*2`), checked against the
 *    manifest's bounds. Its formula is kept by pointer, `/inputs/<name>`,
 *    which is where documents resolves it.
 *  - choice: one of the manifest's options.
 *  - profile / feature reference: an earlier feature of the right type.
 *  - feature list: several earlier features (a roof's walls), picked as a
 *    checklist; the field holds their ids, comma-separated, in pick order.
 *  - material: a library key, or none.
 *
 * A stored number round-trips exactly (`features/storedNumber`): opening a
 * custom feature and saving it unchanged sends the stored inputs as they are.
 */
import {
  formatLength,
  type LengthUnit,
  lengthUnitLabel,
  parseLength,
} from "@loft/design";

import type {
  CustomInputValue,
  CustomParams,
  PluginInput,
  PluginManifest,
} from "../api/plugins";
import type { FeatureResponse } from "../api/parts";
import type { FieldKind } from "../units/length";
import {
  segmentSides,
  segmentsOutlineSketch,
  segmentsPickPartitions,
  sideName,
  supersededInputs,
} from "./outline";
import {
  storedLengthInput,
  storedLengthMm,
  storedNumber,
  storedNumberInput,
} from "./storedNumber";

/** The text (or key) each input's field holds, by input name. */
export interface PluginForm {
  readonly values: Readonly<Record<string, string>>;
  /** The stored inputs this form was seeded from (edit), for exact round trips. */
  readonly stored: Readonly<Record<string, CustomInputValue>> | null;
}

export type NumericInput = Extract<
  PluginInput,
  { kind: "length" | "angle" | "count" }
>;

export function isNumericInput(input: PluginInput): input is NumericInput {
  return (
    input.kind === "length" || input.kind === "angle" || input.kind === "count"
  );
}

/** The ValueField kind an input's field reads. */
export function fieldKind(input: NumericInput): FieldKind {
  if (input.kind === "length") return "length";
  if (input.kind === "angle") return "angle";
  return "int";
}

/** The JSON pointer a formula on this input drives (`/inputs/<name>`). */
export function inputPointer(name: string): string {
  return `/inputs/${name}`;
}

/** The unit shown at the field's tail. */
export function inputUnit(input: NumericInput, unit: LengthUnit): string {
  if (input.kind === "length") return lengthUnitLabel(unit);
  if (input.kind === "angle") return "°";
  return "";
}

/** One option of a reference or material select. */
export interface InputOption {
  readonly value: string;
  readonly label: string;
}

/**
 * The features a profile / feature-reference input may name: the earlier
 * features of the right type (a custom feature reads only what is before it).
 * `selfId` is the feature being edited, or null for a new one (at the end).
 */
export function referenceOptions(
  input: Extract<PluginInput, { kind: "profile" | "feature" | "features" }>,
  features: readonly FeatureResponse[],
  selfId: string | null,
): InputOption[] {
  const at =
    selfId === null ? -1 : features.findIndex((row) => row.id === selfId);
  const earlier = at === -1 ? features : features.slice(0, at);
  const types =
    input.kind === "profile" ? ["sketch"] : (input.feature_types ?? []);
  // A host input names custom features of given plugins (a window's wall).
  const plugins = input.kind === "profile" ? null : (input.plugin_ids ?? null);
  return earlier
    .filter((row) => types.includes("*") || types.includes(row.feature.type))
    .filter(
      (row) =>
        plugins === null ||
        (row.feature.type === "custom" &&
          plugins.includes(row.feature.params.plugin_id)),
    )
    .map((row) => ({ value: row.id, label: row.name }));
}

/** The ids a feature-list field holds, in pick order. */
export function pickedIds(text: string): string[] {
  return text === "" ? [] : text.split(",");
}

/** *text* with *id* picked (appended) or unpicked. */
export function togglePick(text: string, id: string): string {
  const ids = pickedIds(text);
  return (
    ids.includes(id) ? ids.filter((other) => other !== id) : [...ids, id]
  ).join(",");
}

function lastOption(options: readonly InputOption[]): string {
  return options.length > 0 ? (options[options.length - 1]?.value ?? "") : "";
}

/** A new feature's form: every input at its manifest default. */
export function defaultPluginForm(
  manifest: PluginManifest,
  unit: LengthUnit,
  features: readonly FeatureResponse[],
): PluginForm {
  const values: Record<string, string> = {};
  for (const input of manifest.inputs) {
    switch (input.kind) {
      case "length":
        values[input.name] = storedLengthInput(input.default, unit);
        break;
      case "angle":
      case "count":
        values[input.name] = storedNumberInput(input.default);
        break;
      case "choice":
        values[input.name] = input.default;
        break;
      case "material":
        values[input.name] = input.default ?? "";
        break;
      case "profile":
        // The latest sketch, as Extrude proposes the sketch just drawn.
        values[input.name] = lastOption(
          referenceOptions(input, features, null),
        );
        break;
      case "feature":
        values[input.name] = input.optional
          ? ""
          : lastOption(referenceOptions(input, features, null));
        break;
      case "features":
      case "segments":
        values[input.name] = "";
        break;
    }
  }
  return { values, stored: null };
}

/** An existing feature's form, from its stored inputs. */
export function formFromCustomParams(
  manifest: PluginManifest,
  params: CustomParams,
  unit: LengthUnit,
): PluginForm {
  const values: Record<string, string> = {};
  for (const input of manifest.inputs) {
    const stored = params.inputs[input.name];
    if (stored === undefined) {
      values[input.name] = "";
    } else if (typeof stored === "number") {
      values[input.name] =
        input.kind === "length"
          ? storedLengthInput(stored, unit)
          : storedNumberInput(stored);
    } else if (typeof stored === "string") {
      values[input.name] = stored;
    } else if (Array.isArray(stored)) {
      // Feature picks by id; a segments input's sketch line ids as they are.
      values[input.name] = stored
        .map((item) => (typeof item === "string" ? item : item.feature_id))
        .join(",");
    } else {
      values[input.name] = stored.feature_id;
    }
  }
  return { values, stored: params.inputs };
}

const PLAIN_NUMBER_RE = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i;

function parsePlain(text: string): number | null {
  const trimmed = text.trim();
  if (!PLAIN_NUMBER_RE.test(trimmed)) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** A number in the input's own unit (mm, degrees, a count), or null. */
function numericValue(
  input: NumericInput,
  text: string,
  unit: LengthUnit,
  stored: CustomInputValue | undefined,
): number | null {
  const storedValue = typeof stored === "number" ? stored : null;
  if (input.kind === "length") {
    return storedLengthMm(text, unit, storedValue, (t, u) => parseLength(t, u));
  }
  return storedNumber(text, storedValue, parsePlain);
}

function formatBound(
  input: NumericInput,
  value: number,
  unit: LengthUnit,
): string {
  if (input.kind === "length") return formatLength(value, unit);
  if (input.kind === "angle") return `${value}°`;
  return String(value);
}

/**
 * The manifest's bounds as one phrase (`more than 0 mm`, `-3600° to 3600°`,
 * `1 to 50`), or null when the input is unbounded.
 */
export function boundsPhrase(
  input: NumericInput,
  unit: LengthUnit,
): string | null {
  const low = input.minimum ?? null;
  const high = input.maximum ?? null;
  const open = input.kind !== "count" && input.exclusive_minimum;
  if (low !== null && high !== null) {
    const lowText = formatBound(input, low, unit);
    const highText = formatBound(input, high, unit);
    return open
      ? `more than ${lowText}, at most ${highText}`
      : `${lowText} to ${highText}`;
  }
  if (low !== null) {
    return `${open ? "more than" : "at least"} ${formatBound(input, low, unit)}`;
  }
  if (high !== null) return `at most ${formatBound(input, high, unit)}`;
  return null;
}

function numericError(
  input: NumericInput,
  text: string,
  unit: LengthUnit,
  stored: CustomInputValue | undefined,
): string | null {
  if (text.trim() === "") return `Enter ${input.label.toLowerCase()}.`;
  const value = numericValue(input, text, unit, stored);
  if (value === null) return "Enter a number or a formula.";
  if (input.kind === "count" && !Number.isInteger(value)) {
    return "Must be a whole number.";
  }
  const low = input.minimum ?? null;
  const high = input.maximum ?? null;
  const open = input.kind !== "count" && input.exclusive_minimum;
  const below = low !== null && (open ? value <= low : value < low);
  const above = high !== null && value > high;
  if (below || above) {
    const phrase = boundsPhrase(input, unit) ?? "";
    return `Must be ${phrase}.`;
  }
  return null;
}

/**
 * What is wrong with each field, by input name (absent = fine). The same
 * check the server makes against the manifest, so the reason is on the field
 * before a round trip, and the Create/Save gate states the first of them.
 */
export function validatePluginForm(
  manifest: PluginManifest,
  form: PluginForm,
  unit: LengthUnit,
  features: readonly FeatureResponse[],
  selfId: string | null,
): Record<string, string> {
  const errors: Record<string, string> = {};
  // A field a pick has replaced is neither shown nor checked (superseded_by).
  const hidden = supersededInputs(manifest, form.values);
  for (const input of manifest.inputs) {
    if (hidden.has(input.name)) continue;
    const text = form.values[input.name] ?? "";
    let error: string | null = null;
    if (isNumericInput(input)) {
      error = numericError(input, text, unit, form.stored?.[input.name]);
    } else if (input.kind === "choice") {
      if (!input.options.some((option) => option.value === text)) {
        error = `Choose ${input.label.toLowerCase()}.`;
      }
    } else if (input.kind === "profile" || input.kind === "feature") {
      const options = referenceOptions(input, features, selfId);
      const optional = input.kind === "feature" && input.optional;
      if (text === "" && !optional) {
        error =
          options.length === 0
            ? input.kind === "profile"
              ? "Draw a sketch first."
              : input.plugin_ids
                ? `Add a ${input.label.toLowerCase()} first.`
                : `Add a ${input.feature_types.join(" or ")} first.`
            : `Pick ${input.label.toLowerCase()}.`;
      } else if (text !== "" && !options.some((o) => o.value === text)) {
        error = `${input.label} must be an earlier feature.`;
      }
    } else if (input.kind === "features") {
      const options = referenceOptions(input, features, selfId);
      const ids = pickedIds(text);
      if (ids.some((id) => !options.some((o) => o.value === id))) {
        error = `${input.label} must be earlier features.`;
      } else if (ids.length < input.min_items) {
        error = `Pick at least ${input.min_items}.`;
      } else if (ids.length > input.max_items) {
        error = `Pick at most ${input.max_items}.`;
      }
    } else if (input.kind === "segments") {
      // Lines of an outline by sketch id (BUILDING-OUTLINE), named by side.
      const ids = pickedIds(text);
      const sketch = segmentsOutlineSketch(
        manifest,
        input,
        form.values,
        features,
      );
      const partitions = segmentsPickPartitions(
        manifest,
        input,
        form.values,
        features,
      );
      const sides =
        sketch?.feature.type === "sketch"
          ? segmentSides(partitions, sketch.feature.params.entities)
          : null;
      const stray =
        sides === null
          ? undefined
          : ids.find((id) => !sides.some((side) => side.lineId === id));
      if (ids.length > 0 && sketch === null) {
        error = "Pick an outline first.";
      } else if (stray !== undefined) {
        error = partitions
          ? `${sideName(sides, stray)} is not a partition.`
          : `${sideName(sides, stray)} is not a line of the outline.`;
      } else if (ids.length < input.min_items) {
        error = `Pick at least ${input.min_items}.`;
      } else if (ids.length > input.max_items) {
        error = `Pick at most ${input.max_items}.`;
      }
    }
    if (error !== null) errors[input.name] = error;
  }
  return errors;
}

/**
 * The inputs a write sends, or null while any field is invalid. Numbers go
 * in the input's own unit (mm, degrees, a whole count); an empty optional
 * reference or material is left out.
 */
export function pluginInputsFromForm(
  manifest: PluginManifest,
  form: PluginForm,
  unit: LengthUnit,
  features: readonly FeatureResponse[],
  selfId: string | null,
): Record<string, CustomInputValue> | null {
  const errors = validatePluginForm(manifest, form, unit, features, selfId);
  if (Object.keys(errors).length > 0) return null;
  const inputs: Record<string, CustomInputValue> = {};
  const hidden = supersededInputs(manifest, form.values);
  for (const input of manifest.inputs) {
    const text = form.values[input.name] ?? "";
    if (isNumericInput(input)) {
      const value = numericValue(input, text, unit, form.stored?.[input.name]);
      if (value === null) {
        // A hidden field is unused: left out rather than blocking the write.
        if (hidden.has(input.name)) continue;
        return null;
      }
      inputs[input.name] = value;
    } else if (input.kind === "profile" || input.kind === "feature") {
      if (text !== "")
        inputs[input.name] = { kind: "feature", feature_id: text };
    } else if (input.kind === "features") {
      const ids = pickedIds(text);
      if (ids.length > 0)
        inputs[input.name] = ids.map((id) => ({
          kind: "feature" as const,
          feature_id: id,
        }));
    } else if (input.kind === "segments") {
      const ids = pickedIds(text);
      if (ids.length > 0) inputs[input.name] = ids;
    } else if (text !== "") {
      inputs[input.name] = text;
    }
  }
  return inputs;
}

/** The first field error in manifest order: the Create/Save gate's reason. */
export function firstPluginBlocker(
  manifest: PluginManifest,
  errors: Readonly<Record<string, string>>,
): string | null {
  for (const input of manifest.inputs) {
    const error = errors[input.name];
    if (error !== undefined) return `${input.label}: ${error}`;
  }
  return null;
}

/**
 * The form's values with *name* set to *value*, and every side pick whose
 * outline that changes cleared (BUILDING-OUTLINE). Side picks store sketch
 * line ids, and every rectangle's lines are e1..e4, so a kept `e2` would
 * silently name a different wall of the new outline; Fusion drops a
 * selection whose source changed, and so does this.
 */
export function withPluginValue(
  manifest: PluginManifest,
  values: Readonly<Record<string, string>>,
  name: string,
  value: string,
  features: readonly FeatureResponse[],
): Record<string, string> {
  const next: Record<string, string> = { ...values, [name]: value };
  for (const input of manifest.inputs) {
    if (input.kind !== "segments" || input.outline_input !== name) continue;
    if ((next[input.name] ?? "") === "") continue;
    const before = segmentsOutlineSketch(manifest, input, values, features);
    const after = segmentsOutlineSketch(manifest, input, next, features);
    if (before?.id !== after?.id) next[input.name] = "";
  }
  return next;
}
