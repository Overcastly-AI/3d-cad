/**
 * Build the `EvaluateAssemblyRequest` from the persisted assembly graph +
 * each referenced part's feature tree — pure, so it unit-tests without a
 * network or a browser. Geometry stays the sole evaluator: documents/gateway
 * send INTENT (the ordered feature prefix per part, the mate graph), never a
 * kernel body.
 *
 * The dedup key `part_key = f"{ref_document_id}@{version-or-tip}"` is what
 * makes two instances of the same part evaluate ONCE and share one
 * content-addressed mesh (design §4). v1 tracks tip (`ref_pinned_version`
 * null), so the suffix is `tip`; the schema is pin-ready for later.
 */
import type { FeatureTreeResponse } from "../api/parts";
import type {
  AssemblyGraphResponse,
  EvaluateAssemblyRequest,
  InstanceResponse,
} from "../api/assemblies";
import { MESH_LINEAR_DEFLECTION_MM } from "../api/client";

/** The dedup key for an instance's referenced document (design §4). */
export function partKey(instance: InstanceResponse): string {
  const version =
    instance.ref_pinned_version === null
      ? "tip"
      : String(instance.ref_pinned_version);
  return `${instance.ref_document_id}@${version}`;
}

/** The part's ordered, non-rolled-back feature prefix (feature-tree §4). */
function featurePrefix(tree: FeatureTreeResponse) {
  return tree.features
    .filter((feature) => !feature.rolled_back)
    .map((feature) => ({ id: feature.id, feature: feature.feature }));
}

/**
 * Assemble the evaluation request. `partTrees` maps a `ref_document_id` to
 * that part's feature tree (fetched once per unique part — instances sharing a
 * part share its tree). An instance whose tree is missing contributes an empty
 * prefix (the backend then reports a typed `no_body` for it, never a crash).
 */
export function buildEvaluateAssemblyRequest(
  graph: AssemblyGraphResponse,
  partTrees: ReadonlyMap<string, FeatureTreeResponse>,
): EvaluateAssemblyRequest {
  return {
    assembly_id: graph.assembly.id,
    version: graph.doc_version,
    linear_deflection: MESH_LINEAR_DEFLECTION_MM,
    instances: graph.instances.map((instance) => {
      const tree = partTrees.get(instance.ref_document_id);
      return {
        instance_id: instance.id,
        part_key: partKey(instance),
        grounded: instance.grounded,
        placement: instance.placement,
        features: tree ? featurePrefix(tree) : [],
      };
    }),
    mates: graph.mates.map((mate) => ({
      mate_id: mate.id,
      order_index: mate.order_index,
      mate: mate.mate,
    })),
  };
}

/** The unique referenced part-document ids in the graph (dedup for fetching). */
export function uniquePartDocumentIds(graph: AssemblyGraphResponse): string[] {
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const instance of graph.instances) {
    if (instance.ref_document_kind !== "part") continue;
    if (seen.has(instance.ref_document_id)) continue;
    seen.add(instance.ref_document_id);
    ids.push(instance.ref_document_id);
  }
  return ids;
}
