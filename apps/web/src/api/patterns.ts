/**
 * Component patterns data layer (ASM-A3-PATTERN): create, replace and delete
 * an assembly's patterns through the gateway. Every type is the generated
 * contract's; each function surfaces the server envelope's own message.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import type { AssemblyGraphResponse } from "./assemblies";
import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type PatternResponse = components["schemas"]["PatternResponse"];
export type ComponentPattern = PatternResponse["pattern"];
export type LinearComponentPattern =
  components["schemas"]["LinearComponentPattern"];
export type CircularComponentPattern =
  components["schemas"]["CircularComponentPattern"];
export type HoleComponentPattern =
  components["schemas"]["HoleComponentPattern"];
export type EdgeAxisRef = components["schemas"]["EdgeAxisRef"];
export type OriginAxisRef = components["schemas"]["OriginAxisRef"];
export type PatternCount = components["schemas"]["PatternCount"];
export type PatternCopyRef = components["schemas"]["PatternCopyRef"];
type PatternMutationResponse = components["schemas"]["PatternMutationResponse"];

export async function createPattern(
  assemblyId: string,
  pattern: ComponentPattern,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PatternMutationResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/patterns",
    {
      params: { path: { assembly_id: assemblyId } },
      body: { expected_version: expectedVersion, pattern },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The pattern could not be added."));
  }
  return data;
}

export async function updatePattern(
  assemblyId: string,
  patternId: string,
  pattern: ComponentPattern,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PatternMutationResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/assemblies/{assembly_id}/patterns/{pattern_id}",
    {
      params: { path: { assembly_id: assemblyId, pattern_id: patternId } },
      body: { expected_version: expectedVersion, pattern },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The pattern could not be changed."),
    );
  }
  return data;
}

export async function deletePattern(
  assemblyId: string,
  patternId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/assemblies/{assembly_id}/patterns/{pattern_id}",
    {
      params: {
        path: { assembly_id: assemblyId, pattern_id: patternId },
        query: { expected_version: expectedVersion },
      },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The pattern could not be removed."),
    );
  }
  return data;
}
