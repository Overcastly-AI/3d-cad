/**
 * Body renames (BODY-NAMES): the part's whole set of renames, replaced in one
 * `PATCH /parts/{id}` under the tree-version guard, as materials are. A rename
 * is display metadata: it changes no geometry.
 */
import type { GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";
import type { BodyName, PartResponse } from "./parts";

export async function updatePartBodyNames(
  partId: string,
  bodyNames: readonly BodyName[],
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PartResponse> {
  const { data, error } = await client.PATCH("/api/v1/parts/{part_id}", {
    params: { path: { part_id: partId } },
    body: {
      body_names: [...bodyNames],
      expected_tree_version: expectedTreeVersion,
    },
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The body could not be renamed."));
  }
  return data;
}
