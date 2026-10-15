/**
 * IN-CONTEXT EDITING, the pure half (ASM-A3-IN-CONTEXT, RESEARCH §24).
 *
 * Edit in Place opens a part's workspace inside one of the assemblies it is
 * placed in: the other components are drawn around it where the solve put
 * them RELATIVE to it, and the sketcher's Project tool offers their edges. A
 * projected edge becomes an entity linked IN CONTEXT: geometry keeps it
 * following that component whenever the assembly is evaluated.
 *
 * No three.js and no store here, so the maths and the words unit-test in Node:
 *
 *  - {@link contextOf}: the host's pose and every other component's pose in
 *    the host's frame, from the assembly evaluation and its request;
 *  - {@link carryOverlayEdge}: a component's pickable edge carried into the
 *    host's frame, for the first draw on the sketch plane;
 *  - {@link IN_CONTEXT_REASON_TEXT}: each typed error, in plain words.
 */
import type { components } from "@loft/ts-client/gateway";

import type {
  EvaluateAssemblyResult,
  EvaluatedInstance,
  Placement,
} from "../api/assemblies";
import type { OverlayEdge, Vec3 } from "../api/measure";
import { composePlacement, invertPlacement } from "./subAssemblies";

export type InContextLink = components["schemas"]["InContextLink"];
export type InContextStatus = components["schemas"]["InContextStatus"];
export type InContextReason = NonNullable<InContextStatus["reason"]>;

/** Each typed in-context error, said to the user. */
export const IN_CONTEXT_REASON_TEXT: Readonly<Record<InContextReason, string>> =
  {
    component_missing:
      "The referenced component was removed from the assembly. The geometry stays where it last was; Break link or re-project it.",
    component_replaced:
      "The referenced component now places a different part. The geometry stays where it last was.",
    component_failed:
      "The referenced component's part has no body. The geometry stays where it last was.",
    host_missing:
      "This part is no longer at the place in the assembly it was edited in.",
    edge_unresolved:
      "The referenced edge no longer exists on its component. The geometry stays where it last was.",
    edge_ambiguous:
      "More than one edge of the component matches the reference. The geometry stays where it last was.",
    unsupported_curve:
      "The referenced edge is no longer a line or a circle. The geometry stays where it last was.",
    cycle:
      "This reference is part of a loop of in-context references, so none of them update.",
    not_converged:
      "The assembly kept moving as its in-context references updated. The geometry stays where it last was.",
  };

/** The part document id in a `"<id>@<version>"` part key. */
export function partIdOfKey(partKey: string): string {
  return partKey.split("@")[0] ?? partKey;
}

/** A component drawn around the part being edited in place. */
export interface ContextComponent {
  /** Its occurrence id (what a link names). */
  occurrenceId: string;
  partId: string;
  name: string;
  meshId: string | null;
  /** Its solved pose in the HOST part's frame. */
  placement: Placement;
  /** Its part's feature prefix, for the pick overlay. */
  features: EvaluatedInstance["features"];
}

export interface InContextScene {
  /** The host occurrence's solved world pose, or null if it is not placed. */
  host: Placement | null;
  components: ContextComponent[];
}

function leafAt(
  instances: readonly EvaluatedInstance[],
  path: readonly string[],
): EvaluatedInstance | null {
  let level: readonly EvaluatedInstance[] = instances;
  let found: EvaluatedInstance | null = null;
  for (const id of path) {
    found = level.find((instance) => instance.instance_id === id) ?? null;
    if (found === null) return null;
    level = found.sub_assembly?.instances ?? [];
  }
  return found;
}

/**
 * The host's pose and every other placed part's pose relative to it. A
 * pattern copy has no request instance of its own; it is the part its mesh
 * belongs to.
 */
export function contextOf(
  evaluation: EvaluateAssemblyResult,
  request: { instances: readonly EvaluatedInstance[] },
  hostOccurrenceId: string,
): InContextScene {
  const hostRow = evaluation.instances.find(
    (row) => row.instance_id === hostOccurrenceId,
  );
  if (hostRow === undefined) return { host: null, components: [] };
  const toHost = invertPlacement(hostRow.placement);
  const byMesh = new Map<string, EvaluatedInstance>();
  const leaves = evaluation.instances.map((row) => {
    const path =
      (row.path ?? []).length > 0 ? (row.path ?? []) : [row.instance_id];
    const leaf = leafAt(request.instances, path);
    if (leaf !== null && row.part_mesh_glb_id) {
      byMesh.set(row.part_mesh_glb_id, leaf);
    }
    return leaf;
  });
  const components: ContextComponent[] = [];
  evaluation.instances.forEach((row, index) => {
    if (row.instance_id === hostOccurrenceId) return;
    const leaf =
      leaves[index] ??
      (row.part_mesh_glb_id ? byMesh.get(row.part_mesh_glb_id) : undefined);
    if (leaf === undefined || leaf === null) return;
    components.push({
      occurrenceId: row.instance_id,
      partId: partIdOfKey(leaf.part_key),
      name: leaf.name ?? "Part",
      meshId: row.part_mesh_glb_id ?? null,
      placement: composePlacement(toHost, row.placement),
      features: leaf.features,
    });
  });
  return { host: hostRow.placement, components };
}

function carryPoint(placement: Placement, p: Vec3): Vec3 {
  return composePlacement(placement, {
    position: p,
    orientation: { x: 0, y: 0, z: 0, w: 1 },
  }).position;
}

/**
 * A component's overlay edge (its own frame) carried by `placement` into the
 * host part's frame: what the sketch plane sees. Only the first draw uses it;
 * the link stores the edge's signature in the component's own frame.
 */
export function carryOverlayEdge(
  edge: OverlayEdge,
  placement: Placement,
): OverlayEdge {
  const at = (p: Vec3) => carryPoint(placement, p);
  const { signature } = edge;
  return {
    ...edge,
    start: at(edge.start),
    end: at(edge.end),
    polyline: edge.polyline.map(at),
    signature: {
      ...signature,
      end_a: at(signature.end_a),
      end_b: at(signature.end_b),
      midpoint: at(signature.midpoint),
      adjacent_faces: null,
    },
  };
}

/** The link a picked component edge stores. */
export function inContextLink(args: {
  assemblyId: string;
  hostOccurrenceId: string;
  component: ContextComponent;
  edge: OverlayEdge;
}): InContextLink {
  return {
    assembly_id: args.assemblyId,
    host_occurrence_id: args.hostOccurrenceId,
    occurrence_id: args.component.occurrenceId,
    part_id: args.component.partId,
    edge: args.edge.signature,
  };
}

/** The errors among `statuses` that concern `partId`, by entity id. */
export function inContextErrors(
  statuses: readonly InContextStatus[],
  partId: string,
): InContextStatus[] {
  return statuses.filter(
    (status) => status.part_id === partId && status.state === "error",
  );
}
