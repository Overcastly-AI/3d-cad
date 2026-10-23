/**
 * A custom feature's tree node (PLUGIN-UI, RESEARCH §23): ONE row, as in
 * Onshape's feature list, that unfolds into the members the plugin generated.
 * The member rows are read-only — they are what the custom feature IS, edited
 * through its own form — and each carries what geometry said about it, so a
 * failing member is found without leaving the tree.
 *
 * A feature whose plugin (or pinned version) this server lacks still rebuilds
 * from its stored members; its row wears a read-only stamp with the version.
 */
import { CaretDownIcon, Stamp } from "@loft/design";

import type { FeatureResult } from "../api/parts";
import type { PluginManifest } from "../api/plugins";
import {
  customMembers,
  type CustomRow,
  memberLabel,
  pluginAvailability,
} from "../features/customFeature";
import { featureTypeLabel } from "../features/featureLabels";

/** The row's badge text, and whether the feature is read-only here. */
export function customFeatureBadge(
  row: CustomRow,
  catalog: readonly PluginManifest[] | undefined,
): { text: string; readOnly: boolean } {
  const params = row.feature.params;
  const availability = pluginAvailability(catalog, params);
  if (availability.state === "ready") {
    return { text: availability.manifest.title.toLowerCase(), readOnly: false };
  }
  if (availability.state === "loading") {
    return { text: params.plugin_id, readOnly: false };
  }
  return { text: `read-only · v${params.plugin_version}`, readOnly: true };
}

/** The read-only stamp the badge slot shows for a missing plugin. */
export function ReadOnlyBadge({
  row,
  index,
}: {
  row: CustomRow;
  index: number;
}) {
  const params = row.feature.params;
  return (
    <span
      className="flex shrink-0 items-center gap-1"
      title={`${params.plugin_id} v${params.plugin_version} is not installed here: the feature rebuilds from its stored members, read-only.`}
      data-testid={`feature-read-only-${index}`}
    >
      <Stamp tone="gauge">Read-only</Stamp>
      <span className="font-data text-2xs text-gauge">
        v{params.plugin_version}
      </span>
    </span>
  );
}

/** The caret that unfolds a custom feature into its members. */
export function UnfoldToggle({
  open,
  name,
  index,
  onToggle,
}: {
  open: boolean;
  name: string;
  index: number;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-label={`${open ? "Fold" : "Unfold"} ${name}`}
      data-testid={`feature-unfold-${index}`}
      className="-mx-1 flex min-h-target-dense w-5 shrink-0 items-center justify-center text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
    >
      <CaretDownIcon
        size={12}
        className={`transition-transform duration-fast ${open ? "" : "-rotate-90"}`}
      />
    </button>
  );
}

const MEMBER_STATUS: Record<string, string> = {
  ok: "OK",
  error: "ERR",
  skipped: "SKIP",
  suppressed: "SUPP",
};

/** The unfolded member rows, under the custom feature's row. */
export function CustomMemberRows({
  row,
  index,
  catalog,
  resultById,
  rolledBack,
}: {
  row: CustomRow;
  index: number;
  catalog: readonly PluginManifest[] | undefined;
  resultById: ReadonlyMap<string, FeatureResult>;
  rolledBack: boolean;
}) {
  const params = row.feature.params;
  const availability = pluginAvailability(catalog, params);
  const manifest =
    availability.state === "ready" ? availability.manifest : undefined;
  const members = customMembers(params);
  return (
    <li data-testid={`feature-members-${index}`}>
      <ol aria-label={`${row.name} members`}>
        {members.length === 0 ? (
          <li className="py-0.5 pr-2 pl-[52px] font-body text-xs text-gauge">
            No members yet.
          </li>
        ) : null}
        {members.map((member) => {
          const result = resultById.get(member.id);
          const status = rolledBack ? null : (result?.status ?? null);
          const label = memberLabel(members, member, manifest);
          return (
            <li
              key={member.id}
              className="flex min-h-target-dense items-center gap-2 border-l-2 border-transparent py-0 pr-2 pl-[52px]"
              data-testid="feature-member-row"
              data-role={member.role}
              aria-readonly="true"
            >
              <span className="min-w-0 grow truncate font-data text-xs text-gauge">
                {label}
              </span>
              <span className="shrink-0 font-body text-2xs text-gauge">
                {featureTypeLabel(member.feature.type)}
              </span>
              <span
                className={`w-8 shrink-0 text-right font-data text-2xs ${
                  status === "error" ? "text-flag" : "text-gauge"
                }`}
              >
                {status === null ? "—" : (MEMBER_STATUS[status] ?? status)}
              </span>
            </li>
          );
        })}
      </ol>
    </li>
  );
}
