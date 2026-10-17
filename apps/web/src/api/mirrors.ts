/**
 * Component mirrors data layer (ASM-MIRROR-COMPONENT): create, replace and
 * delete an assembly's mirrors through the gateway. Every type is the
 * generated contract's; each function surfaces the server envelope's own
 * message.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import type { AssemblyGraphResponse } from "./assemblies";
import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type MirrorResponse = components["schemas"]["MirrorResponse"];
export type ComponentMirror = MirrorResponse["mirror"];
export type MirrorState = components["schemas"]["MirrorState"];
export type MirrorCopyRef = components["schemas"]["MirrorCopyRef"];
type MirrorMutationResponse = components["schemas"]["MirrorMutationResponse"];

export async function createMirror(
  assemblyId: string,
  mirror: ComponentMirror,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<MirrorMutationResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/mirrors",
    {
      params: { path: { assembly_id: assemblyId } },
      body: { expected_version: expectedVersion, mirror },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The mirror could not be added."));
  }
  return data;
}

export async function updateMirror(
  assemblyId: string,
  mirrorId: string,
  mirror: ComponentMirror,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<MirrorMutationResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/assemblies/{assembly_id}/mirrors/{mirror_id}",
    {
      params: { path: { assembly_id: assemblyId, mirror_id: mirrorId } },
      body: { expected_version: expectedVersion, mirror },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The mirror could not be changed."));
  }
  return data;
}

export async function deleteMirror(
  assemblyId: string,
  mirrorId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/assemblies/{assembly_id}/mirrors/{mirror_id}",
    {
      params: {
        path: { assembly_id: assemblyId, mirror_id: mirrorId },
        query: { expected_version: expectedVersion },
      },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The mirror could not be removed."));
  }
  return data;
}
