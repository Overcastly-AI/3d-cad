/**
 * What the ASSEMBLY title block is entitled to say about mass — the drawer-mate
 * of `features/materials.ts`, kept out of the component so the claim can be
 * tested without a DOM.
 *
 * The defect (materials.md §6.1, second address): the panel carried a section
 * titled **"Combined mass"** that reported Volume / Area / Centroid and no mass
 * at all — the identical overstated title the part inspector shipped for months
 * before #57b, at a surface nobody re-read. A title is a claim; this module
 * decides whether the claim is earned.
 *
 * The roll-up's own rule is why absence needs a sentence rather than a dash:
 * `mass_g` is null unless EVERY placed instance has a material
 * (`geometry.assembly.evaluate` — "a partial sum would silently under-report the
 * assembly's mass"). So "no mass" here almost always means ONE component is
 * unassigned, and the wire already says which: each `InstancePlacementResult`
 * carries its own part's `properties.mass_g`. Going quiet while holding the name
 * is the confidently-vague half of the same defect class as claiming a mass we
 * never computed.
 *
 * One distinction the naming must not blur: an instance whose part produced NO
 * BODY has `properties: null`. That is a different absence — it contributes
 * nothing to the roll-up at all (it never enters `items`), so it can never be
 * the reason the total went null, and it is never named as lacking a material.
 */
import type {
  EvaluateAssemblyResult,
  InstanceResponse,
} from "../api/assemblies";

/**
 * The four things the panel may say about combined mass.
 *
 *  - `unsolved` — nothing has been evaluated yet. Not a mass claim at all.
 *  - `known` — every contributing instance has a material; the total is real.
 *  - `partial` — some instances are assigned and at least one is not; the
 *    unassigned ones are NAMED.
 *  - `unassigned` — nothing in the assembly has a material. Nothing to name
 *    usefully; the fix is in the parts.
 */
export type AssemblyMassState =
  | { readonly kind: "unsolved" }
  | { readonly kind: "known"; readonly massG: number }
  | { readonly kind: "partial"; readonly missing: readonly string[] }
  | { readonly kind: "unassigned" };

/** Classify the roll-up's mass from the wire + the graph's instance names. */
export function assemblyMassState(
  evaluation: EvaluateAssemblyResult | undefined,
  instances: readonly InstanceResponse[] = [],
): AssemblyMassState {
  const properties = evaluation?.properties ?? null;
  if (evaluation === undefined || properties === null) {
    return { kind: "unsolved" };
  }
  const massG = properties.mass_g ?? null;
  if (massG !== null) return { kind: "known", massG };

  const nameById = new Map(instances.map((i) => [i.id, i.name]));
  // Only instances that CONTRIBUTED a body can be the reason the sum is null.
  const contributors = evaluation.instances.filter(
    (placed) => (placed.properties ?? null) !== null,
  );
  const missing = contributors
    .filter((placed) => (placed.properties?.mass_g ?? null) === null)
    .map((placed) => nameById.get(placed.instance_id) ?? "An instance");
  const anyAssigned = contributors.some(
    (placed) => (placed.properties?.mass_g ?? null) !== null,
  );
  return missing.length > 0 && anyAssigned
    ? { kind: "partial", missing }
    : { kind: "unassigned" };
}

/**
 * The section eyebrow. "Combined mass" over a section with no mass in it is the
 * claim this module exists to withdraw — the words are earned by the presence of
 * a MASS, never by the presence of a mass field.
 */
export function combinedEyebrow(state: AssemblyMassState): string {
  return state.kind === "known" ? "Combined mass" : "Combined properties";
}
