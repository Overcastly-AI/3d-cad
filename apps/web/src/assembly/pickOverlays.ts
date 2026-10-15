/**
 * PICK GEOMETRY FOR AN ASSEMBLY — one part's overlay never costs another's.
 *
 * BIKE2-FAILED-PART-KILLS-PICKS (blocking): every assembly holding a crank arm
 * whose feature failed (`profile_unsupported`) lost ALL edge picking — no joint
 * origins on nested parts, 0 projectable edges in Edit in Place after 90 s, the
 * on-holes picker stuck at "PICKING…". Root cause: the workspace fetched the
 * pick overlay of every part in ONE `Promise.all`, and geometry answers a
 * failed part's overlay with a typed 422. One rejection rejected the whole
 * query (with `retry: false`), so no part got an overlay and nothing said why.
 *
 * Here each part's overlay settles on its own: a part that fails — or does not
 * answer within {@link PICK_GEOMETRY_TIMEOUT_MS} — is a named failure, and
 * every other part's overlay is still delivered. Fusion and SolidWorks do the
 * same: a component that failed to rebuild is flagged, the rest stay pickable.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { InstanceResponse } from "../api/assemblies";
import { MESH_LINEAR_DEFLECTION_MM } from "../api/client";
import {
  fetchOverlay,
  type EvaluateTreeRequest,
  type OverlayResult,
} from "../api/measure";
import type { FeatureTreeResponse } from "../api/parts";
import { buildEvaluateTree } from "../measure/geometry";
import { partNameOf } from "./partFailures";
import type { NestedPart } from "./subAssemblies";

/**
 * How long one part's overlay may take before its picker says so instead of
 * waiting. A healthy overlay of a dense part answers in well under 5 s here.
 */
export const PICK_GEOMETRY_TIMEOUT_MS = 30_000;

/** The overlays that arrived, and why each of the others did not. */
export interface SettledOverlays<K> {
  readonly overlays: Map<K, OverlayResult>;
  readonly failures: Map<K, string>;
}

class OverlayTimeout extends Error {}

function withTimeout<T>(work: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () =>
        reject(
          new OverlayTimeout(
            `Its pick geometry did not arrive within ${Math.round(ms / 1000)} s.`,
          ),
        ),
      ms,
    );
  });
  return Promise.race([work, timeout]).finally(() => clearTimeout(timer));
}

/**
 * Fetch each job's overlay independently. Never rejects: a failed or
 * timed-out part lands in `failures` with its message, the rest in `overlays`.
 */
export async function fetchOverlaysSettled<K>(
  jobs: readonly (readonly [K, EvaluateTreeRequest])[],
  fetcher: (tree: EvaluateTreeRequest) => Promise<OverlayResult> = fetchOverlay,
  timeoutMs: number = PICK_GEOMETRY_TIMEOUT_MS,
): Promise<SettledOverlays<K>> {
  const settled = await Promise.allSettled(
    jobs.map(([, tree]) => withTimeout(fetcher(tree), timeoutMs)),
  );
  const overlays = new Map<K, OverlayResult>();
  const failures = new Map<K, string>();
  settled.forEach((outcome, index) => {
    const key = (jobs[index] as readonly [K, EvaluateTreeRequest])[0];
    if (outcome.status === "fulfilled") overlays.set(key, outcome.value);
    else {
      const reason: unknown = outcome.reason;
      failures.set(
        key,
        reason instanceof Error ? reason.message : "It could not be built.",
      );
    }
  });
  return { overlays, failures };
}

/** A part whose pick geometry is missing, by the name the user knows. */
export interface PickGeometryFailure {
  readonly partDocumentId: string;
  readonly name: string;
  readonly message: string;
}

export interface PickOverlays {
  /** Each pickable instance / nested occurrence's overlay. */
  readonly byInstance: ReadonlyMap<string, OverlayResult>;
  /** Overlays are still on their way (a picker should say so). */
  readonly loading: boolean;
  /** Parts that have no pick geometry, and why. */
  readonly failures: readonly PickGeometryFailure[];
}

const EMPTY: SettledOverlays<string> = {
  overlays: new Map(),
  failures: new Map(),
};

/**
 * The assembly workspace's pick overlays: one fetch per unique part document
 * (top-level and inside sub-assemblies), shared by its every occurrence.
 */
export function usePickOverlays({
  active,
  assemblyId,
  docVersion,
  partTrees,
  instances,
  nested,
  nestedStamp,
}: {
  active: boolean;
  assemblyId: string;
  docVersion: number | undefined;
  partTrees: ReadonlyMap<string, FeatureTreeResponse> | undefined;
  instances: readonly InstanceResponse[];
  nested: ReadonlyMap<string, NestedPart>;
  /** `SubAssemblies.stamp`: a part edited inside re-reads its overlay. */
  nestedStamp: string;
}): PickOverlays {
  // Top-level part documents → their tree and the name the user knows.
  const topLevel = useMemo(() => {
    const docs = new Map<string, string>();
    for (const instance of instances) {
      if (instance.ref_document_kind !== "part") continue;
      if (!docs.has(instance.ref_document_id)) {
        docs.set(instance.ref_document_id, partNameOf(instance.name));
      }
    }
    return docs;
  }, [instances]);
  const topKey = [...topLevel.keys()].sort().join("|");
  const top = useQuery({
    queryKey: ["assembly-overlays", assemblyId, docVersion, topKey],
    enabled: active && partTrees !== undefined && topLevel.size > 0,
    queryFn: () =>
      fetchOverlaysSettled(
        [...topLevel.keys()].flatMap((id) => {
          const tree = partTrees?.get(id);
          return tree ? [[id, buildEvaluateTree(tree)] as const] : [];
        }),
      ),
    staleTime: Infinity,
    retry: false,
  });

  // Parts inside sub-assemblies, one per document.
  const inner = useMemo(() => {
    const docs = new Map<string, NestedPart>();
    for (const part of nested.values()) {
      if (part.partDocumentId === "" || docs.has(part.partDocumentId)) continue;
      docs.set(part.partDocumentId, part);
    }
    return docs;
  }, [nested]);
  const innerKey = [...inner.keys()].sort().join("|");
  const sub = useQuery({
    queryKey: ["assembly-nested-overlays", innerKey, nestedStamp],
    enabled: active && inner.size > 0,
    queryFn: () =>
      fetchOverlaysSettled(
        [...inner.entries()].map(
          ([docId, part]) =>
            [
              docId,
              {
                part_id: docId,
                tree_version: 0,
                linear_deflection: MESH_LINEAR_DEFLECTION_MM,
                features: part.features,
              },
            ] as const,
        ),
      ),
    staleTime: Infinity,
    retry: false,
  });

  return useMemo(() => {
    const byInstance = new Map<string, OverlayResult>();
    if (!active) return { byInstance, loading: false, failures: [] };
    const topData = top.data ?? EMPTY;
    const subData = sub.data ?? EMPTY;
    for (const part of nested.values()) {
      const overlay = subData.overlays.get(part.partDocumentId);
      if (overlay) byInstance.set(part.id, overlay);
    }
    for (const instance of instances) {
      const overlay = topData.overlays.get(instance.ref_document_id);
      if (overlay) byInstance.set(instance.id, overlay);
    }
    const failures: PickGeometryFailure[] = [];
    for (const [id, message] of topData.failures) {
      failures.push({
        partDocumentId: id,
        name: topLevel.get(id) ?? "A part",
        message,
      });
    }
    for (const [id, message] of subData.failures) {
      if (topData.failures.has(id)) continue;
      const part = inner.get(id);
      failures.push({
        partDocumentId: id,
        name: part ? partNameOf(part.name) : "A part",
        message,
      });
    }
    return {
      byInstance,
      loading: top.isFetching || sub.isFetching,
      failures,
    };
  }, [
    active,
    top.data,
    top.isFetching,
    sub.data,
    sub.isFetching,
    instances,
    nested,
    topLevel,
    inner,
  ]);
}
