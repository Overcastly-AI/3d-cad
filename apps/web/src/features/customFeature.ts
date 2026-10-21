/**
 * Custom features in the part workspace (PLUGIN-UI, RESEARCH §23): one tree
 * row stands for the members documents expanded it to.
 *
 * Geometry builds the MEMBERS (each under its stable member id), so the
 * evaluation reports them, not the row. {@link foldCustomResults} adds one
 * result per custom row, folded from its members, so every surface that reads
 * a row's status (the tree, the timeline, the build verdict) reads a custom
 * feature exactly as it reads an extrude.
 */
import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureResult,
} from "../api/parts";
import type {
  CustomFeature,
  CustomParams,
  ExpandedMember,
  PluginManifest,
} from "../api/plugins";

export type CustomRow = FeatureResponse & { feature: CustomFeature };

export function isCustomRow(row: FeatureResponse): row is CustomRow {
  return row.feature.type === "custom";
}

/** The stored members of a custom row, in expansion order. */
export function customMembers(params: CustomParams): ExpandedMember[] {
  return params.expansion ?? [];
}

/** The manifest a stored feature is pinned to, or undefined when absent. */
export function pinnedManifest(
  catalog: readonly PluginManifest[] | undefined,
  pluginId: string,
  version: string,
): PluginManifest | undefined {
  return catalog?.find(
    (manifest) => manifest.id === pluginId && manifest.version === version,
  );
}

/** The Build toolbar's tools: the latest version of each installed plugin. */
export function buildTools(
  catalog: readonly PluginManifest[] | undefined,
): PluginManifest[] {
  return (catalog ?? []).filter(
    (manifest) => manifest.latest && manifest.group === "build",
  );
}

/**
 * Whether this server can edit a custom feature: `loading` until the catalog
 * is in, `missing` when its plugin (or the pinned version) is not installed —
 * the feature then rebuilds from its stored members, read-only.
 */
export type PluginAvailability =
  | { readonly state: "loading" }
  | { readonly state: "ready"; readonly manifest: PluginManifest }
  | {
      readonly state: "missing";
      readonly pluginId: string;
      readonly version: string;
    };

export function pluginAvailability(
  catalog: readonly PluginManifest[] | undefined,
  params: Pick<CustomParams, "plugin_id" | "plugin_version">,
): PluginAvailability {
  if (catalog === undefined) return { state: "loading" };
  const manifest = pinnedManifest(
    catalog,
    params.plugin_id,
    params.plugin_version,
  );
  return manifest === undefined
    ? {
        state: "missing",
        pluginId: params.plugin_id,
        version: params.plugin_version,
      }
    : { state: "ready", manifest };
}

/** A member's role title from the manifest (`Twisted sweep`), else the role. */
export function roleTitle(
  manifest: PluginManifest | undefined,
  role: string,
): string {
  return manifest?.members.find((m) => m.role === role)?.title ?? role;
}

/**
 * One result for a custom row from its members' results: any error is the
 * row's error (the first, with its code and message); all suppressed is
 * suppressed; any skipped is skipped; else ok. Undefined when geometry
 * reported none of its members (nothing evaluated yet).
 */
export function foldMemberResults(
  rowId: string,
  members: readonly FeatureResult[],
): FeatureResult | undefined {
  if (members.length === 0) return undefined;
  const failed = members.find((result) => result.status === "error");
  if (failed !== undefined) {
    return { feature_id: rowId, status: "error", error: failed.error ?? null };
  }
  if (members.every((result) => result.status === "suppressed")) {
    return { feature_id: rowId, status: "suppressed" };
  }
  if (members.some((result) => result.status === "skipped")) {
    return { feature_id: rowId, status: "skipped" };
  }
  return { feature_id: rowId, status: "ok" };
}

/**
 * The evaluation with one folded result per custom row, placed after its
 * members, and `last_good_feature_id` read as a ROW: a custom feature's last
 * member is the custom feature; a member before its last means the feature
 * was not built through, so the last good row is the one before it. The
 * member results stay (a pick on a member still finds its own).
 */
export function foldCustomResults(
  evaluation: EvaluateTreeResult,
  features: readonly FeatureResponse[],
): EvaluateTreeResult {
  const custom = features.filter(isCustomRow);
  if (custom.length === 0) return evaluation;
  const owner = new Map<string, { row: CustomRow; last: boolean }>();
  for (const row of custom) {
    const members = customMembers(row.feature.params);
    members.forEach((member, index) =>
      owner.set(member.id, { row, last: index === members.length - 1 }),
    );
  }
  const byRow = new Map<string, FeatureResult[]>();
  const out: FeatureResult[] = [];
  for (const result of evaluation.features) {
    out.push(result);
    const own = owner.get(result.feature_id);
    if (own === undefined) continue;
    const list = byRow.get(own.row.id) ?? [];
    list.push(result);
    byRow.set(own.row.id, list);
    if (own.last) {
      const folded = foldMemberResults(own.row.id, list);
      if (folded !== undefined) out.push(folded);
    }
  }
  // A custom feature with no members (a door or window: its wall frames it)
  // reads as the custom feature it is hosted in, so the tree says whether
  // its framing built rather than nothing at all.
  const folded = new Map(out.map((result) => [result.feature_id, result]));
  for (const row of custom) {
    if (customMembers(row.feature.params).length > 0) continue;
    const host = Object.values(row.feature.params.inputs)
      .map((value) =>
        typeof value === "object" && value !== null && !Array.isArray(value)
          ? folded.get(value.feature_id)
          : undefined,
      )
      .find((result) => result !== undefined);
    if (host !== undefined) out.push({ ...host, feature_id: row.id });
  }
  let lastGood = evaluation.last_good_feature_id;
  const own = lastGood === null ? undefined : owner.get(lastGood);
  if (own !== undefined) {
    if (own.last) {
      lastGood = own.row.id;
    } else {
      const at = features.findIndex((row) => row.id === own.row.id);
      lastGood = at > 0 ? (features[at - 1]?.id ?? null) : null;
    }
  }
  return { ...evaluation, features: out, last_good_feature_id: lastGood };
}

/**
 * Feature ids with each custom row's member ids added: the faces geometry
 * attributes to a member are the custom feature's faces (tree selection
 * lights them, as it lights an extrude's).
 */
export function withMemberIds(
  ids: readonly string[],
  features: readonly FeatureResponse[],
): string[] {
  const out = [...ids];
  for (const row of features) {
    if (isCustomRow(row) && ids.includes(row.id)) {
      for (const member of customMembers(row.feature.params)) {
        out.push(member.id);
      }
    }
  }
  return out;
}

/** Headings for the typed refusals a custom-feature write can meet. */
const PLUGIN_ERROR_TITLE: Readonly<Record<string, string>> = {
  feature_limit_exceeded: "Too many features",
  plugin_expansion_too_large: "Too many members",
  plugin_expansion_timeout: "The plugin took too long",
  plugin_expansion_invalid: "The plugin built something invalid",
  plugin_input_invalid: "Input not accepted",
  plugin_input_unsupported: "Not supported here",
  plugin_not_found: "Plugin not installed",
  plugin_version_not_found: "Plugin version not installed",
  plugin_read_only: "Read-only",
};

/** `"Too many features: <server message>"`, or the message alone. */
export function pluginErrorSentence(
  code: string | null,
  message: string,
): string {
  const title = code === null ? undefined : PLUGIN_ERROR_TITLE[code];
  return title === undefined ? message : `${title}: ${message}`;
}

/**
 * A plugin code an evaluation carries inside its `input_error` message
 * (`[plugin_expansion_too_large] ...`), lifted out, or null.
 */
export function bracketedPluginCode(message: string): string | null {
  const match = /^\[([a-z_]+)\]\s*/.exec(message);
  return match === null ? null : (match[1] ?? null);
}
