/**
 * Custom features in the authoring seat (PLUGIN-UI): open a plugin's form
 * from the Build toolbar, and save it through the shared feature save path
 * (fresh tree version, one retry, the formulas on the envelope, a refresh).
 */
import { useCallback } from "react";

import type { FeatureResponse } from "../../api/parts";
import {
  type CustomFeatureWrite,
  customFeatureCreate,
  customFeatureUpdate,
  type PluginManifest,
} from "../../api/plugins";
import { useMeasureStore } from "../../measure/store";
import type { EditorSeat } from "./useEditorSeat";
import type { FeatureSubmit } from "./useFeatureSubmit";
import type { OpenEditor } from "./openEditor";

/** `Twisted prism 2`: the plugin's title and the next free number. */
export function nextCustomName(
  manifest: Pick<PluginManifest, "id" | "title">,
  features: readonly FeatureResponse[],
): string {
  const taken = new Set(features.map((row) => row.name));
  let n =
    features.filter(
      (row) =>
        row.feature.type === "custom" &&
        row.feature.params.plugin_id === manifest.id,
    ).length + 1;
  while (taken.has(`${manifest.title} ${n}`)) n += 1;
  return `${manifest.title} ${n}`;
}

export function usePluginFeature({
  features,
  catalog,
  editor,
  setEditor,
  setEditorError,
  setSelectedFeatureId,
  runFeatureSave,
}: {
  features: readonly FeatureResponse[];
  catalog: readonly PluginManifest[] | undefined;
  editor: OpenEditor | null;
  setEditor: EditorSeat["setEditor"];
  setEditorError: EditorSeat["setEditorError"];
  setSelectedFeatureId: EditorSeat["setSelectedFeatureId"];
  runFeatureSave: FeatureSubmit["runFeatureSave"];
}) {
  const openCreatePlugin = useCallback(
    (manifest: PluginManifest) => {
      useMeasureStore.getState().deactivate();
      setEditorError(null);
      setSelectedFeatureId(null);
      setEditor({
        kind: "custom",
        mode: "create",
        pluginId: manifest.id,
        pluginVersion: manifest.version,
        title: manifest.title,
      });
    },
    [setEditor, setEditorError, setSelectedFeatureId],
  );

  const submitCustom = useCallback(
    (write: CustomFeatureWrite) => {
      const current = editor;
      if (current === null || current.kind !== "custom") return;
      const manifest = catalog?.find(
        (m) => m.id === write.pluginId && m.version === write.pluginVersion,
      );
      const name = nextCustomName(
        manifest ?? { id: write.pluginId, title: current.title },
        features,
      );
      runFeatureSave(
        (version) => customFeatureCreate(name, write, version),
        (version) => customFeatureUpdate(write, version),
        current.mode === "create",
        current.featureId,
        `The ${current.title} could not be saved.`,
      );
    },
    [editor, catalog, features, runFeatureSave],
  );

  return { openCreatePlugin, submitCustom };
}

export type PluginFeature = ReturnType<typeof usePluginFeature>;
