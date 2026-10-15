/**
 * EDIT IN PLACE — the part workspace opened inside an assembly
 * (ASM-A3-IN-CONTEXT, RESEARCH §24).
 *
 * `/parts/<id>?context=<assembly>&occurrence=<host>` evaluates that assembly
 * (the documents-built request, so a nested host and every sub-assembly come
 * with it) and offers what the workspace needs to edit the part where it sits:
 * every other component's mesh at its pose RELATIVE to this part, its pick
 * overlay while Project is armed, and the in-context errors of this part.
 *
 * The assembly is re-evaluated whenever this part's tree moves on. That
 * evaluation is what keeps the links current: the gateway stores the values it
 * resolved, so when one of THIS part's links changed, the part's own body and
 * tree are refetched and the sketch rebuilds from them.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { MESH_LINEAR_DEFLECTION_MM } from "../../api/client";
import {
  evaluateAssembly,
  fetchAssemblyEvaluationRequest,
  fetchAssemblyGraph,
} from "../../api/assemblies";
import { fetchBodyMesh } from "../../api/mesh";
import { fetchOverlay, type OverlayResult } from "../../api/measure";
import {
  type ContextComponent,
  contextOf,
  type InContextStatus,
} from "../../assembly/inContext";
import { partRoute } from "../../router";
import { useSketchStore } from "../../sketch/store";
import {
  type InstanceGeometry,
  useInstanceGeometries,
} from "../../viewport/useInstanceGeometries";

export interface InContextSession {
  assemblyId: string;
  hostOccurrenceId: string;
  assemblyName: string | null;
  /** The other components, posed in this part's frame. */
  components: ContextComponent[];
  geometryOf: (component: ContextComponent) => InstanceGeometry | null;
  /** Pick overlays by part id, fetched while Project is armed. */
  overlays: ReadonlyMap<string, OverlayResult>;
  /** Every link of THIS part the evaluation reported on. */
  statuses: InContextStatus[];
  /** Set when the part is not at the occurrence, or the load failed. */
  problem: string | null;
  loading: boolean;
}

export function useInContext({
  partId,
  treeVersion,
  drawing,
}: {
  partId: string;
  /** The part's tree version: a new one re-evaluates the assembly. */
  treeVersion: number | undefined;
  /** Sketching (mode "draw"): Project may be armed. */
  drawing: boolean;
}): InContextSession | null {
  const search = partRoute.useSearch();
  const assemblyId = search.context ?? null;
  const hostOccurrenceId = search.occurrence ?? null;
  const active = assemblyId !== null && hostOccurrenceId !== null;
  const queryClient = useQueryClient();

  const graph = useQuery({
    queryKey: ["in-context-graph", assemblyId],
    enabled: active,
    queryFn: () => fetchAssemblyGraph(assemblyId ?? ""),
    staleTime: Infinity,
  });
  const solved = useQuery({
    queryKey: ["in-context-eval", assemblyId, partId, treeVersion],
    enabled: active && treeVersion !== undefined,
    queryFn: async () => {
      const request = await fetchAssemblyEvaluationRequest(assemblyId ?? "");
      const evaluation = await evaluateAssembly({
        ...request,
        linear_deflection: MESH_LINEAR_DEFLECTION_MM,
      });
      return { request, evaluation };
    },
    staleTime: Infinity,
    retry: false,
  });

  const evaluation = solved.data?.evaluation;
  useEffect(() => {
    if (evaluation === undefined || assemblyId === null) return;
    // The assembly's workspace caches its parts' trees: the way back must
    // show this part as it is now, not as it was when Edit in Place began.
    void queryClient.invalidateQueries({
      queryKey: ["assembly-part-docs", assemblyId],
    });
    void queryClient.invalidateQueries({ queryKey: ["assembly-sub-requests"] });
    // A link of this part moved: the gateway stored it, so rebuild from it.
    const moved = (evaluation.in_context ?? []).some(
      (status) => status.part_id === partId && status.changed,
    );
    if (!moved) return;
    void queryClient.invalidateQueries({ queryKey: ["features", partId] });
    void queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
  }, [evaluation, assemblyId, partId, queryClient]);

  const scene = useMemo(
    () =>
      solved.data === undefined || hostOccurrenceId === null
        ? null
        : contextOf(
            solved.data.evaluation,
            solved.data.request,
            hostOccurrenceId,
          ),
    [solved.data, hostOccurrenceId],
  );
  const components = useMemo(() => scene?.components ?? [], [scene]);

  const meshIds = useMemo(
    () =>
      [
        ...new Set(
          components.flatMap((c) => (c.meshId === null ? [] : [c.meshId])),
        ),
      ].sort(),
    [components],
  );
  const meshes = useQuery({
    queryKey: ["in-context-meshes", meshIds.join("|")],
    enabled: meshIds.length > 0,
    queryFn: async () =>
      new Map<string, ArrayBuffer>(
        await Promise.all(
          meshIds.map(async (id) => [id, await fetchBodyMesh(id)] as const),
        ),
      ),
    staleTime: Infinity,
  });
  const meshMap = useMemo(
    () => meshes.data ?? new Map<string, ArrayBuffer>(),
    [meshes.data],
  );
  const { byMeshId } = useInstanceGeometries(meshMap);

  const projecting = useSketchStore((s) => s.tool === "project") && drawing;
  const partKey = useMemo(() => {
    const seen = new Map<string, ContextComponent>();
    for (const c of components) if (!seen.has(c.partId)) seen.set(c.partId, c);
    return seen;
  }, [components]);
  const overlays = useQuery({
    queryKey: [
      "in-context-overlays",
      assemblyId,
      [...partKey.keys()].sort().join("|"),
      treeVersion,
    ],
    enabled: active && projecting && partKey.size > 0,
    queryFn: async () =>
      new Map<string, OverlayResult>(
        await Promise.all(
          [...partKey.values()].map(
            async (c) =>
              [
                c.partId,
                await fetchOverlay({
                  part_id: c.partId,
                  tree_version: 0,
                  features: c.features,
                  linear_deflection: MESH_LINEAR_DEFLECTION_MM,
                }),
              ] as const,
          ),
        ),
      ),
    staleTime: Infinity,
    retry: false,
  });

  if (!active) return null;
  const failure = solved.error ?? graph.error;
  return {
    assemblyId,
    hostOccurrenceId,
    assemblyName: graph.data?.assembly.name ?? null,
    components,
    geometryOf: (c) => (c.meshId ? (byMeshId.get(c.meshId) ?? null) : null),
    overlays: overlays.data ?? new Map(),
    statuses: (evaluation?.in_context ?? []).filter(
      (status) => status.part_id === partId,
    ),
    problem:
      failure instanceof Error
        ? failure.message
        : scene !== null && scene.host === null
          ? "This part is no longer at that place in the assembly."
          : null,
    loading: solved.isFetching,
  };
}
