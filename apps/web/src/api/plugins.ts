/**
 * Plugins data layer (PLUGIN-UI, RESEARCH §23): the served manifests and the
 * custom-feature envelope. Every type comes from the generated
 * `@loft/ts-client`; the form, the Build toolbar and the tree node are built
 * from what the gateway serves, so no plugin has a hand-written form here.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";
import type { FeatureCreate, FeatureUpdate } from "./parts";

export type PluginManifest = components["schemas"]["PluginManifest"];
export type PluginCatalog = components["schemas"]["PluginCatalog"];
/** One typed input of a manifest, discriminated on `kind`. */
export type PluginInput = PluginManifest["inputs"][number];
export type CustomFeature = components["schemas"]["CustomFeature"];
export type CustomParams = components["schemas"]["CustomParamsV1"];
/** One stored input value: a number, an option or material key, or a feature. */
export type CustomInputValue = CustomParams["inputs"][string];
export type ExpandedMember = components["schemas"]["ExpandedMember"];

/** Every released version of every installed plugin (newest first per id). */
export async function fetchPlugins(
  client: GatewayClient = gatewayClient,
): Promise<PluginManifest[]> {
  const { data, error } = await client.GET("/api/v1/plugins");
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The plugins could not be loaded."));
  }
  return data.plugins;
}

/** What a custom-feature write sends: the pin and the inputs (documents
 * expands it and stores the members, so a client never sends `expansion`). */
export interface CustomFeatureWrite {
  pluginId: string;
  pluginVersion: string;
  inputs: Record<string, CustomInputValue>;
}

function customEnvelope(write: CustomFeatureWrite): CustomFeature {
  return {
    type: "custom",
    version: 1,
    params: {
      plugin_id: write.pluginId,
      plugin_version: write.pluginVersion,
      inputs: write.inputs,
    },
  };
}

export function customFeatureCreate(
  name: string,
  write: CustomFeatureWrite,
  expectedTreeVersion: number,
): FeatureCreate {
  return {
    name,
    expected_tree_version: expectedTreeVersion,
    feature: customEnvelope(write),
  };
}

export function customFeatureUpdate(
  write: CustomFeatureWrite,
  expectedTreeVersion: number,
): FeatureUpdate {
  return {
    expected_tree_version: expectedTreeVersion,
    feature: customEnvelope(write),
  };
}
