/**
 * The workspace's sub-assembly data (ASM-A3): each referenced sub-assembly's
 * evaluation request (embedded in the parent's evaluate / export / clash
 * requests), and the pick overlays of the parts inside them.
 *
 * The requests are fetched on every mount and focus (no stale window): a part
 * edited inside a sub-assembly does not move the parent's `doc_version`, so
 * re-reading them is how the parent picks the edit up. `stamp` changes with
 * their content and keys the evaluation.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  fetchAssemblyEvaluationRequest,
  type AssemblyGraphResponse,
  type SubAssemblyRequest,
} from "../api/assemblies";
import { MESH_LINEAR_DEFLECTION_MM } from "../api/client";
import { fetchOverlay, type OverlayResult } from "../api/measure";
import type {
  EvaluateAssemblyRequest,
  EvaluateAssemblyResult,
  Placement,
} from "../api/assemblies";
import {
  nestedParts,
  subAssemblyPoses,
  subAssemblyStamp,
  uniqueSubAssemblyIds,
  type NestedPart,
} from "./subAssemblies";

const NO_REQUESTS: ReadonlyMap<string, SubAssemblyRequest> = new Map();

export interface SubAssemblies {
  requests: ReadonlyMap<string, SubAssemblyRequest>;
  stamp: string;
  /** Every referenced sub-assembly has loaded (true when there are none). */
  ready: boolean;
  fetching: boolean;
  error: Error | null;
}

export function useSubAssemblies(
  assemblyId: string,
  graph: AssemblyGraphResponse | undefined,
): SubAssemblies {
  const ids = useMemo(
    () => (graph ? uniqueSubAssemblyIds(graph) : []),
    [graph],
  );
  const key = ids.join("|");
  const query = useQuery({
    queryKey: ["assembly-sub-requests", assemblyId, graph?.doc_version, key],
    enabled: ids.length > 0,
    queryFn: async () =>
      new Map(
        await Promise.all(
          ids.map(
            async (id) =>
              [id, await fetchAssemblyEvaluationRequest(id)] as const,
          ),
        ),
      ),
    staleTime: 0,
  });
  const requests = ids.length === 0 ? NO_REQUESTS : query.data;
  return {
    requests: requests ?? NO_REQUESTS,
    stamp: requests ? subAssemblyStamp(requests) : "",
    ready: requests !== undefined,
    fetching: query.isFetching,
    error: query.error,
  };
}

/** Pick overlays for the parts inside sub-assemblies, by occurrence id. */
export function useNestedOverlays(
  active: boolean,
  nested: ReadonlyMap<string, NestedPart>,
  /** `SubAssemblies.stamp`: a part edited inside re-reads its overlay. */
  stamp: string,
): ReadonlyMap<string, OverlayResult> {
  // One overlay per part document, shared by its every occurrence.
  const byDocument = useMemo(() => {
    const docs = new Map<string, NestedPart>();
    for (const part of nested.values()) {
      if (!docs.has(part.partDocumentId)) docs.set(part.partDocumentId, part);
    }
    return docs;
  }, [nested]);
  const key = [...byDocument.keys()].sort().join("|");
  const query = useQuery({
    queryKey: ["assembly-nested-overlays", key, stamp],
    enabled: active && byDocument.size > 0,
    queryFn: async () =>
      new Map(
        await Promise.all(
          [...byDocument.entries()].map(
            async ([docId, part]) =>
              [
                docId,
                await fetchOverlay({
                  part_id: docId,
                  tree_version: 0,
                  linear_deflection: MESH_LINEAR_DEFLECTION_MM,
                  features: part.features,
                }),
              ] as const,
          ),
        ),
      ),
    staleTime: Infinity,
    retry: false,
  });
  return useMemo(() => {
    const out = new Map<string, OverlayResult>();
    if (!active || query.data === undefined) return out;
    for (const part of nested.values()) {
      const overlay = query.data.get(part.partDocumentId);
      if (overlay) out.set(part.id, overlay);
    }
    return out;
  }, [active, query.data, nested]);
}

/** The solve's nested parts (by occurrence id) and sub-assembly poses. */
export function useNestedSolve(
  evaluation: EvaluateAssemblyResult | undefined,
  request: EvaluateAssemblyRequest | null,
): {
  nested: ReadonlyMap<string, NestedPart>;
  subPoses: ReadonlyMap<string, Placement>;
} {
  const nested = useMemo(
    () => nestedParts(evaluation, request),
    [evaluation, request],
  );
  const subPoses = useMemo(() => subAssemblyPoses(evaluation), [evaluation]);
  return { nested, subPoses };
}
