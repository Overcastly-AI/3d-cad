/**
 * Rigid sub-assemblies in the assembly workspace (ASM-A3).
 *
 * A sub-assembly instance is ONE component of its parent (it is selected,
 * moved, grounded and listed as one), but its parts are drawn, picked and
 * clash-checked one by one. Geometry returns each such part as a result row
 * with a `path` (the instance ids from the top-level sub-assembly instance
 * down to the part instance) and an `instance_id` that is that path's
 * OCCURRENCE id; a joint picked on the part stores that id. The web never
 * derives occurrence ids itself: it reads them off the solve.
 *
 * This module is pure: which sub-assemblies to fetch, how to embed them in the
 * request, which rows are nested parts (and of which component), and where a
 * nested part sits while its component is being moved.
 */
import type {
  AssemblyGraphResponse,
  EvaluateAssemblyResult,
  EvaluatedInstance,
  Placement,
  SubAssemblyRequest,
} from "../api/assemblies";

/** The unique referenced sub-assembly ids in the graph (one fetch each). */
export function uniqueSubAssemblyIds(graph: AssemblyGraphResponse): string[] {
  const ids = new Set<string>();
  for (const instance of graph.instances) {
    if (instance.ref_document_kind === "assembly") {
      ids.add(instance.ref_document_id);
    }
  }
  return [...ids];
}

/** A part placed inside a sub-assembly instance, as the workspace sees it. */
export interface NestedPart {
  /** Its occurrence id: the result row's `instance_id`, a joint's ref. */
  id: string;
  /** The top-level sub-assembly instance it moves with. */
  groupId: string;
  /** The part instance's own name inside its sub-assembly ("Rim <1>"). */
  name: string;
  /** The part document, from the request's `part_key` ("<id>@tip"). */
  partDocumentId: string;
  /** Its feature prefix, for the pick overlay. */
  features: EvaluatedInstance["features"];
  /** A copy placed by a pattern inside the sub-assembly (ASM-A3). */
  copy?: boolean;
}

/** The request instance a result path names, walking down sub-assemblies. */
export function instanceAt(
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
 * Every nested part the solve placed, by occurrence id. Rows without a path
 * are parts instanced directly and are not listed.
 */
export function nestedParts(
  evaluation: EvaluateAssemblyResult | undefined,
  request: { instances: readonly EvaluatedInstance[] } | null,
): Map<string, NestedPart> {
  const out = new Map<string, NestedPart>();
  if (evaluation === undefined || request === null) return out;
  // A copy placed by a pattern inside a sub-assembly has no request instance
  // of its own; it is the same part as the row that shares its mesh.
  const byMesh = new Map<string, EvaluatedInstance>();
  const leaves = evaluation.instances.map((row) => {
    const leaf = instanceAt(request.instances, row.path ?? []);
    if (leaf !== null && row.part_mesh_glb_id) {
      byMesh.set(row.part_mesh_glb_id, leaf);
    }
    return leaf;
  });
  evaluation.instances.forEach((row, index) => {
    const path = row.path ?? [];
    const groupId = path[0];
    // Copies of THIS assembly's patterns are drawn with their seed instead.
    if (groupId === undefined || row.pattern) return;
    const leaf =
      leaves[index] ??
      (row.part_mesh_glb_id ? byMesh.get(row.part_mesh_glb_id) : undefined);
    out.set(row.instance_id, {
      id: row.instance_id,
      groupId,
      name: leaf?.name ?? "Part",
      partDocumentId: (leaf?.part_key ?? "").split("@")[0] ?? "",
      features: leaf?.features ?? [],
      ...(leaves[index] === null ? { copy: true } : {}),
    });
  });
  return out;
}

/** The component an id belongs to: its group for a nested part, else itself. */
export function componentOf(
  nested: ReadonlyMap<string, NestedPart>,
  id: string,
): string {
  return nested.get(id)?.groupId ?? id;
}

/**
 * A readable name for anything a joint or clash can name: a component's own
 * name, or "Wheel <1> / Rim <1>" for a part inside a sub-assembly.
 */
export function componentName(
  instances: readonly { id: string; name: string }[],
  nested: ReadonlyMap<string, NestedPart> | undefined,
  id: string,
): string | null {
  const part = nested?.get(id);
  const own = instances.find((i) => i.id === (part?.groupId ?? id));
  if (own === undefined) return null;
  return part === undefined ? own.name : `${own.name} / ${part.name}`;
}

/** Clash ids lifted to their components, for the component tree's badges. */
export function componentClashIds(
  ids: { measured: ReadonlySet<string>; unverifiedOnly: ReadonlySet<string> },
  nested: ReadonlyMap<string, NestedPart>,
): { measured: Set<string>; unverifiedOnly: Set<string> } {
  const lift = (set: ReadonlySet<string>) =>
    new Set([...set].map((id) => componentOf(nested, id)));
  return {
    measured: lift(ids.measured),
    unverifiedOnly: lift(ids.unverifiedOnly),
  };
}

// --- pose algebra (x, y, z, w quaternions; world = R·local + t) -------------

type Quat = Placement["orientation"];
type Vec = Placement["position"];

function qMul(a: Quat, b: Quat): Quat {
  return {
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
  };
}

function qConj(q: Quat): Quat {
  return { x: -q.x, y: -q.y, z: -q.z, w: q.w };
}

function rotate(q: Quat, v: Vec): Vec {
  const r = qMul(qMul(q, { x: v.x, y: v.y, z: v.z, w: 0 }), qConj(q));
  return { x: r.x, y: r.y, z: r.z };
}

/** `a ∘ b`: apply `b`, then `a`. */
export function composePlacement(a: Placement, b: Placement): Placement {
  const p = rotate(a.orientation, b.position);
  return {
    position: {
      x: p.x + a.position.x,
      y: p.y + a.position.y,
      z: p.z + a.position.z,
    },
    orientation: qMul(a.orientation, b.orientation),
  };
}

/** The inverse rigid transform. */
export function invertPlacement(a: Placement): Placement {
  const q = qConj(a.orientation);
  const p = rotate(q, a.position);
  return { position: { x: -p.x, y: -p.y, z: -p.z }, orientation: q };
}

/**
 * Where a nested part is drawn when its component is shown at `group` (a Move
 * preview, a joint drive): its solved pose carried along with the
 * component's, keeping its pose inside the component.
 */
export function nestedPlacement(
  group: Placement,
  solvedGroup: Placement,
  solvedPart: Placement,
): Placement {
  const inside = composePlacement(invertPlacement(solvedGroup), solvedPart);
  return composePlacement(group, inside);
}

/** Each top-level sub-assembly instance's solved pose, by instance id. */
export function subAssemblyPoses(
  evaluation: EvaluateAssemblyResult | undefined,
): Map<string, Placement> {
  return new Map(
    (evaluation?.sub_assemblies ?? []).map((s) => [s.instance_id, s.placement]),
  );
}

/**
 * A stamp that changes whenever any embedded sub-assembly request changes (a
 * part edited inside it), so the evaluation re-runs: the parent's own
 * `doc_version` does not move when a nested part does.
 */
export function subAssemblyStamp(
  requests: ReadonlyMap<string, SubAssemblyRequest>,
): string {
  let hash = 5381;
  const text = JSON.stringify([...requests.entries()].sort());
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(i)) | 0;
  }
  return `${requests.size}:${(hash >>> 0).toString(36)}`;
}
