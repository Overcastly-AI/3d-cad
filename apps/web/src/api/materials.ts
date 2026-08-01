/**
 * Materials data layer (docs/design/materials.md) — the served library and the
 * part's assignment. Every type comes from the generated `@loft/ts-client`
 * (pydantic → OpenAPI → TS; CLAUDE.md DRY rule): a density typed by hand here
 * would be a second source of truth for a physical constant, which is exactly
 * the failure the served library exists to prevent (design §4, "served, never
 * hardcoded client-side").
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";
import type { PartResponse } from "./parts";

/** One library material: key, display name, density (kg/m³). */
export type Material = components["schemas"]["Material"];
/** The closed material vocabulary — an unknown key is a boundary error. */
export type MaterialKey =
  components["schemas"]["BodyMaterialAssignment"]["material"];
/** A part's whole assignment: one document default + per-body overrides. */
export type MaterialAssignment = components["schemas"]["MaterialAssignment"];
/** One per-body override, keyed by the body's §MB-0 base feature id. */
export type BodyMaterialAssignment =
  components["schemas"]["BodyMaterialAssignment"];
/**
 * One evaluated body's per-body facts — lump count plus the RESOLVED material
 * and the mass that follows from it. This is what lets a surface say WHICH body
 * has no material instead of going quiet when the part total is null (§3).
 */
export type BodyLumpInfo = components["schemas"]["BodyLumpInfo"];

/**
 * A compile-time proof that the library entry and the assignment agree on the
 * key literal. They reach the client through different schemas
 * (`Material.key` from the library response, `BodyMaterialAssignment.material`
 * from the PATCH body), so a divergence would otherwise surface as the picker
 * offering a key the PATCH rejects — at runtime, on a user. This fails `tsc`
 * instead.
 */
type MutuallyAssignable<A, B> = [A] extends [B]
  ? [B] extends [A]
    ? true
    : false
  : false;
export const MATERIAL_KEYS_AGREE: MutuallyAssignable<
  MaterialKey,
  Material["key"]
> = true;

/**
 * The built-in library, served by the gateway (`b8e491f` added the proxy twin
 * so the picker never reaches past it — CLAUDE.md service boundaries). It is a
 * fixed table, so the caller fetches it once per session; a failure disables
 * the picker and says why, because a client-side fallback table would be the
 * second source of truth for a density this route exists to prevent.
 */
export async function fetchMaterials(
  client: GatewayClient = gatewayClient,
): Promise<Material[]> {
  const { data, error } = await client.GET("/api/v1/materials");
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The material library could not be loaded."),
    );
  }
  return data.materials;
}

/**
 * Replace the part's WHOLE material assignment (design §2). Wholesale, never a
 * merge: the request states the full intended state, so two concurrent edits
 * cannot interleave into an assignment neither of them sent. An assignment
 * naming nothing clears back to "no material", which makes mass unknown again.
 *
 * Unlike a rename or a unit change this genuinely invalidates the recorded
 * evaluate (mass was derived from it), so the caller must refetch the tree and
 * re-evaluate — the server bumps `tree_version` under the same optimistic-
 * concurrency guard every part edit uses (422 on a stale version).
 */
export async function updatePartMaterials(
  partId: string,
  materials: MaterialAssignment,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.PATCH("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
    body: { materials, expected_tree_version: expectedTreeVersion },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The material could not be assigned."),
    );
  }
  return data;
}
