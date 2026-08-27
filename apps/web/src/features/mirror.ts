/**
 * Mirror-feature view logic — the pure functions the {@link MirrorEditor} and
 * PartPage share, kept out of the component so they can be unit-tested without a
 * DOM. Param shapes come from the generated client (CLAUDE.md DRY rule); the
 * create/update builders live in `../api/parts`.
 *
 * A mirror reflects the WHOLE current body about a plane and unions the
 * reflection back in — the reflective sibling of a pattern (design §7.6). v1
 * needs ONLY a plane choice: no face pick, no point pick. That plane is the SAME
 * `GeomRef` vocabulary a sketch's plane / the section author use — an origin
 * datum (XY/XZ/YZ) or a reusable in-tree datum feature (a `FeatureRef`) — so the
 * picker reuses {@link resolveDatumPlaneOptions} verbatim, introducing no
 * parallel plane taxonomy.
 */
import type {
  FeatureResponse,
  MirrorParams,
  MirrorPlaneRef,
} from "../api/parts";
import {
  DATUM_PLANES,
  type DatumPlaneOption,
  planeRefFromSpec,
  type SketchPlaneSpec,
} from "../sketch/plane";
// WHAT a mirror reflects is the SAME decision a pattern makes about what it
// repeats, asked with the same words and built from the same module (§2).
import {
  asMirrorScope,
  buildScope,
  defaultScopeMode,
  type ScopeFeature,
  type ScopeMode,
  type ScopeSeed,
  scopeFromParams,
} from "./patternScope";

/**
 * The editable mirror form. `plane` is the persisted wire ref when editing an
 * existing mirror, or null for a new one (the editor then defaults to the first
 * origin datum). Serialisable — the editor derives its selection from it.
 */
export interface MirrorForm {
  plane: MirrorPlaneRef | null;
  /** WHAT is reflected: the whole body, or the named features. */
  scope: ScopeMode;
  /** The named subject, carried with its NAME so the row can render it. */
  scopeFeatures: readonly ScopeFeature[];
}

/**
 * The default new-mirror form: no plane chosen yet (defaults to XY in the UI),
 * scoped to whatever the tree proposes (a selected row, else the tip).
 */
export function defaultMirrorForm(seed: ScopeSeed | null = null): MirrorForm {
  return {
    plane: null,
    scope: defaultScopeMode(seed),
    scopeFeatures: seed === null ? [] : [seed],
  };
}

/** Seed the form from an existing mirror feature for editing. */
export function formFromMirrorParams(
  params: MirrorParams,
  features: readonly FeatureResponse[] = [],
): MirrorForm {
  const scope = scopeFromParams(params.scope, features);
  return {
    plane: params.plane,
    scope: scope.mode,
    scopeFeatures: scope.features,
  };
}

/** One selectable mirror plane — an origin datum or a reusable in-tree datum. */
export interface MirrorPlaneChoice {
  key: string;
  label: string;
  testId: string;
  spec: SketchPlaneSpec;
}

/**
 * The mirror plane choices: the three origin datums first (the common case),
 * then any reusable in-tree datum features. The ONE derivation the sketch plane
 * picker + section author read too, so a datum means the same plane everywhere.
 */
export function mirrorPlaneChoices(
  datumPlanes: readonly DatumPlaneOption[],
): MirrorPlaneChoice[] {
  const origins: MirrorPlaneChoice[] = DATUM_PLANES.map((name) => ({
    key: `origin:${name}`,
    label: `${name} plane`,
    testId: `mirror-plane-${name}`,
    spec: { kind: "origin", base: name },
  }));
  const datums: MirrorPlaneChoice[] = datumPlanes.map((datum) => ({
    key: `datum:${datum.id}`,
    label: datum.name,
    testId: `mirror-plane-datum-${datum.id}`,
    spec: datum.spec,
  }));
  return [...origins, ...datums];
}

/** The choice key a persisted plane ref maps to (`origin:XY` / `datum:<id>`). */
export function planeRefKey(plane: MirrorPlaneRef): string {
  return plane.kind === "datum_plane"
    ? `origin:${plane.plane}`
    : `datum:${plane.feature_id}`;
}

/**
 * The choice a form's plane selects, or the first choice (XY) when the form has
 * no plane yet or its persisted plane is no longer in the tree (a deleted datum
 * — the mirror falls back to a valid choice rather than an empty picker).
 */
export function selectedChoice(
  choices: readonly MirrorPlaneChoice[],
  form: MirrorForm,
): MirrorPlaneChoice | null {
  if (form.plane !== null) {
    const key = planeRefKey(form.plane);
    const match = choices.find((c) => c.key === key);
    if (match !== undefined) return match;
  }
  return choices[0] ?? null;
}

/**
 * Build the `MirrorParamsV1` for a chosen plane (its persisted `GeomRef`) and
 * the form's scope. Null when the scope names nothing (`min_length=1`); `scope`
 * is always sent, for the reason `buildPatternParams` states.
 */
export function buildMirrorParams(
  spec: SketchPlaneSpec,
  form: Pick<MirrorForm, "scope" | "scopeFeatures">,
): MirrorParams | null {
  const scope = buildScope(form.scope, form.scopeFeatures);
  if (scope === null) return null;
  return { plane: planeRefFromSpec(spec), scope: asMirrorScope(scope) };
}
