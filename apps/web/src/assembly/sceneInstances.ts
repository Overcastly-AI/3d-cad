/**
 * The viewport's scene instances: the graph's components at their poses, with
 * each rigid sub-assembly drawn as the parts inside it (ASM-A3).
 *
 * A part instanced directly is one scene instance, as before. A sub-assembly
 * instance becomes one scene instance per part it places, keyed by that part's
 * occurrence id and tagged with the sub-assembly (`groupId`): they share its
 * balloon number, grounding and visibility, and a Move or joint drive of the
 * sub-assembly carries them all with it.
 */
import type {
  EvaluateAssemblyResult,
  InstancePlacementResult,
  InstanceResponse,
  Placement,
} from "../api/assemblies";
import type { InstanceGeometry } from "../viewport/useInstanceGeometries";
import type { SceneInstance } from "../viewport/AssemblyScene";
import {
  visibilityModeOf,
  type VisibilityState,
} from "../viewport/instanceVisibility";
import { placementToScene } from "./placement";
import { nestedPlacement, type NestedPart } from "./subAssemblies";

export interface SceneInputs {
  instances: readonly InstanceResponse[];
  evaluation: EvaluateAssemblyResult | undefined;
  nested: ReadonlyMap<string, NestedPart>;
  subPoses: ReadonlyMap<string, Placement>;
  /** A component's pose held by Move or a joint drive, else null. */
  componentOverride: (instanceId: string) => Placement | null;
  /** The joint dialog's server-solved preview of any placed part, else null. */
  preview: (id: string) => Placement | null;
  byMeshId: ReadonlyMap<string, InstanceGeometry>;
  visibility: VisibilityState;
}

export function buildSceneInstances(input: SceneInputs): SceneInstance[] {
  const rows = new Map<string, InstancePlacementResult>(
    (input.evaluation?.instances ?? []).map((row) => [row.instance_id, row]),
  );
  const partsOf = new Map<string, NestedPart[]>();
  for (const part of input.nested.values()) {
    const list = partsOf.get(part.groupId) ?? [];
    list.push(part);
    partsOf.set(part.groupId, list);
  }
  const geometryOf = (row: InstancePlacementResult | undefined) => {
    const id = row?.part_mesh_glb_id ?? null;
    return id ? (input.byMeshId.get(id) ?? null) : null;
  };

  const out: SceneInstance[] = [];
  input.instances.forEach((instance, index) => {
    const visibility = visibilityModeOf(input.visibility, instance.id);
    const held = input.componentOverride(instance.id);
    if (instance.ref_document_kind === "assembly") {
      const solvedGroup = input.subPoses.get(instance.id) ?? instance.placement;
      for (const part of partsOf.get(instance.id) ?? []) {
        const row = rows.get(part.id);
        const solved = row?.placement ?? solvedGroup;
        const placement =
          (held !== null
            ? nestedPlacement(held, solvedGroup, solved)
            : input.preview(part.id)) ?? solved;
        out.push({
          id: part.id,
          name: `${instance.name} / ${part.name}`,
          balloon: index + 1,
          grounded: instance.grounded,
          transform: placementToScene(placement),
          geometry: geometryOf(row),
          visibility,
          groupId: instance.id,
          patternCopy: part.copy === true,
        });
      }
      return;
    }
    const row = rows.get(instance.id);
    const placement =
      held ??
      input.preview(instance.id) ??
      row?.placement ??
      instance.placement;
    out.push({
      id: instance.id,
      name: instance.name,
      balloon: index + 1,
      grounded: instance.grounded,
      transform: placementToScene(placement),
      geometry: geometryOf(row),
      visibility,
    });
  });
  // Component pattern copies (ASM-A3): placed by geometry after the solve and
  // drawn like their seed. A click on one selects the seed, as in Fusion,
  // where a pattern's copies follow the component they repeat.
  for (const row of input.evaluation?.instances ?? []) {
    const ref = row.pattern;
    if (ref === undefined || ref === null) continue;
    const index = input.instances.findIndex(
      (i) => i.id === ref.seed_instance_id,
    );
    const seed = input.instances[index];
    if (seed === undefined) continue;
    out.push({
      id: row.instance_id,
      name: `${seed.name} (${ref.index + 1})`,
      balloon: index + 1,
      grounded: false,
      transform: placementToScene(row.placement),
      geometry: geometryOf(row),
      visibility: visibilityModeOf(input.visibility, seed.id),
      groupId: seed.id,
      patternCopy: true,
    });
  }
  return out;
}

/** A component's current pose: held by Move / a drive, else solved, else seed. */
export function componentPose(
  instance: InstanceResponse,
  evaluation: EvaluateAssemblyResult | undefined,
  subPoses: ReadonlyMap<string, Placement>,
): Placement {
  if (instance.ref_document_kind === "assembly") {
    return subPoses.get(instance.id) ?? instance.placement;
  }
  return (
    evaluation?.instances.find((row) => row.instance_id === instance.id)
      ?.placement ?? instance.placement
  );
}
