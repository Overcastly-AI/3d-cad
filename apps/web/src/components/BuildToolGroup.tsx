/**
 * The Build group (PLUGIN-UI, RESEARCH §23): every installed plugin as an
 * ordinary tool, titled from its manifest, with no install step — Onshape's
 * custom features sit in the toolbar exactly like the built-in ones.
 *
 * One tool per plugin, at its latest version (what a new feature is inserted
 * with). The group is absent while the catalog loads and when no plugin is
 * installed: an empty group would be chrome with nothing in it.
 */
import { ToolButton, ToolGroup, VerbGlyph } from "@loft/design";

import type { PluginManifest } from "../api/plugins";
import { buildTools } from "../features/customFeature";

/**
 * Words before Create's and Modify's: a plugin's glyph is generic, so its
 * title is the only thing that names it (`CreateStrip`'s LABEL_PRIORITY).
 */
export const BUILD_LABEL_PRIORITY = 35;

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
  return (
    <ToolGroup
      eyebrow="Build"
      labelPriority={BUILD_LABEL_PRIORITY}
      data-testid="build-tools"
    >
      {tools.map((manifest) => (
        <ToolButton
          key={manifest.id}
          icon={<VerbGlyph verb="custom" />}
          showLabel
          label={manifest.title}
          data-testid={`plugin-tool-${manifest.id}`}
          aria-label={`${manifest.title} — ${manifest.description}`}
          caption={
            locked
              ? `Finish ${activeCommand} first`
              : treeReady
                ? undefined
                : "Loading the part"
          }
          disabled={locked || !treeReady}
          onClick={() => onOpen(manifest)}
        />
      ))}
    </ToolGroup>
  );
}
