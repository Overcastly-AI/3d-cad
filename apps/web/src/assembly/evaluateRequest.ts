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
import type { MaterialAssignment } from "../api/materials";
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
 *
 * `partMaterials` maps the same id to that part's stored assignment. It is what
 * lets the roll-up report a MASS at all: the field has been on the wire since
 * #57 (`EvaluatedInstance.materials`, "forwarded verbatim into that part's
 * evaluation so the assembly rolls up a real mass") and documents' own
 * server-side builder has always set it — but this browser-side builder never
 * did, so an assembly of fully-assigned parts came back `mass_g: null` forever
 * and the panel's mass row was unreachable code. Absent/unknown stays `null`,
 * which the roll-up reads as "no mass", never as zero.
 *
 * `name` is the same class of omission and the same fix (STEPNAME-1B). This
 * request is also the EXPORT request — `exportAssembly` spreads it and adds a
 * `format` — so an instance sent without a name is an instance the STEP writer
 * has to fall back to naming by its UUID, which is what the audit read back out
 * of an assembly STEP (`AUDIT-PRODUCT` S-22). The writer was never the defect:
 * it has carried the name into the NAUO and the PRODUCT since `0d3ea59`, and
 * `services/documents`' own builder sends it, which is why the gap was
 * invisible from the backend. It matters more than its size: a STEP file is
 * what the user hands to a machinist or a supplier, and a UUID is worse than no
 * name — it is unreadable AND it looks deliberate.
 *
 * The name sent is the INSTANCE name (`"Bracket <2>"`), verbatim, because that
 * is the shape the writer's contract is written against: the occurrence (NAUO)
 * takes it whole, and the shared PRODUCT takes it with the `<n>` suffix
 * stripped, so N instances of one part correctly share ONE named PRODUCT.
 * `AssemblyPage` mints exactly that shape (`${part.name} <${n}>`), so the two
 * halves already agree — this only stops throwing the name away in between.
 */
export function buildEvaluateAssemblyRequest(
  graph: AssemblyGraphResponse,
  partTrees: ReadonlyMap<string, FeatureTreeResponse>,
  partMaterials: ReadonlyMap<string, MaterialAssignment | null> = new Map(),
): EvaluateAssemblyRequest {
  return {
    assembly_id: graph.assembly.id,
    version: graph.doc_version,
    linear_deflection: MESH_LINEAR_DEFLECTION_MM,
    instances: graph.instances.map((instance) => {
      const tree = partTrees.get(instance.ref_document_id);
      return {
        instance_id: instance.id,
        name: instance.name,
        part_key: partKey(instance),
        grounded: instance.grounded,
        placement: instance.placement,
        features: tree ? featurePrefix(tree) : [],
        materials: partMaterials.get(instance.ref_document_id) ?? null,
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
