/**
 * The installed plugins (PLUGIN-UI): read once per session, shared by the
 * Build toolbar, the custom-feature form and the tree node. The catalog is
 * the same for every part, so one cache entry serves them all.
 */
import { useQuery } from "@tanstack/react-query";

import { fetchPlugins, type PluginManifest } from "../../api/plugins";

export const PLUGINS_QUERY_KEY = ["plugins"] as const;

export function usePluginCatalog(): {
  catalog: PluginManifest[] | undefined;
  error: Error | null;
} {
  const query = useQuery({
    queryKey: PLUGINS_QUERY_KEY,
    queryFn: () => fetchPlugins(),
    staleTime: Infinity,
  });
  return { catalog: query.data, error: query.error };
}
