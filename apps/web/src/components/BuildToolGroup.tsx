/**
 * The Build group (PLUGIN-UI, RESEARCH §23): every installed plugin as an
 * ordinary tool, titled from its manifest, with no install step — Onshape's
 * custom features sit in the toolbar exactly like the built-in ones.
 *
 * One tool per plugin, at its latest version (what a new feature is inserted
 * with). The group is absent while the catalog loads and when no plugin is
 * installed: an empty group would be chrome with nothing in it.
 *
 * The row holds the building generators ({@link BUILD_ROW}, in Chief
 * Architect's Build-menu order: walls first); every other plugin sits behind
 * the group's eyebrow, "BUILD ▾", as Create and Modify keep their
 * low-frequency verbs (`ToolGroup.more`). Every plugin shares one generic
 * glyph, so a Build tool cannot shed its label to an icon that names it, and
 * a row cell per plugin would outgrow the band.
 */
import { ToolButton, ToolGroup, VerbGlyph } from "@loft/design";
import type { FlyoutItem } from "@loft/design";

import type { PluginManifest } from "../api/plugins";
import { buildTools } from "../features/customFeature";

/**
 * Words before Create's and Modify's: a plugin's glyph is generic, so its
 * title is the only thing that names it (`CreateStrip`'s LABEL_PRIORITY).
 */
export const BUILD_LABEL_PRIORITY = 35;

/**
 * The plugins on the Build row, in order; the rest are in BUILD ▾.
 * Interior wall and Cabinets sit in the menu: the band has no room for a
 * third labelled Build cell at 1280 px (toolbar-overflow's tiers).
 */
export const BUILD_ROW: readonly string[] = ["loft.wall", "loft.deck"];

export interface BuildToolGroupProps {
  catalog: readonly PluginManifest[] | undefined;
  /** The tree has loaded (a tool stays disabled until it has). */
  treeReady: boolean;
  /** The open command's name: every tool locks with this reason. */
  activeCommand: string | null;
  onOpen: (manifest: PluginManifest) => void;
}

export function BuildToolGroup({
  catalog,
  treeReady,
  activeCommand,
  onOpen,
}: BuildToolGroupProps) {
  const tools = buildTools(catalog);
  if (tools.length === 0) return null;
  const locked = activeCommand !== null && activeCommand !== "";
  const caption = locked
    ? `Finish ${activeCommand} first`
    : treeReady
      ? undefined
      : "Loading the part";
  const disabled = locked || !treeReady;
  // A server without the building generators shows its plugins on the row.
  const pinned = BUILD_ROW.flatMap((id) => tools.filter((m) => m.id === id));
  const row = pinned.length > 0 ? pinned : tools;
  const more: FlyoutItem[] = tools
    .filter((manifest) => !row.includes(manifest))
    .map((manifest) => ({
      key: manifest.id,
      icon: <VerbGlyph verb="custom" />,
      label: manifest.title,
      "data-testid": `plugin-tool-${manifest.id}`,
      "aria-label": `${manifest.title} — ${manifest.description}`,
      disabled,
      onSelect: () => onOpen(manifest),
    }));
  return (
    <ToolGroup
      eyebrow="Build"
      labelPriority={BUILD_LABEL_PRIORITY}
      more={more}
      moreTestId="build-more"
      data-testid="build-tools"
    >
      {row.map((manifest) => (
        <ToolButton
          key={manifest.id}
          icon={<VerbGlyph verb="custom" />}
          showLabel
          label={manifest.title}
          data-testid={`plugin-tool-${manifest.id}`}
          aria-label={`${manifest.title} — ${manifest.description}`}
          caption={caption}
          disabled={disabled}
          onClick={() => onOpen(manifest)}
        />
      ))}
    </ToolGroup>
  );
}
