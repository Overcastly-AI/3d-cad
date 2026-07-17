/**
 * Assemblies data layer — instances + mates CRUD and the shared-mesh
 * evaluation, all proxied through the gateway. Every type comes from the
 * generated `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule);
 * this module never hand-writes an API shape, and each function surfaces the
 * server envelope's own message on failure.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type AssemblyResponse = components["schemas"]["AssemblyResponse"];
/** Document display unit — the single source is the generated contract. */
export type LengthUnit = AssemblyResponse["length_unit"];
export type AssemblyGraphResponse =
  components["schemas"]["AssemblyGraphResponse"];
export type InstanceResponse = components["schemas"]["InstanceResponse"];
export type InstanceCreate = components["schemas"]["InstanceCreate"];
export type InstanceUpdate = components["schemas"]["InstanceUpdate"];
export type InstanceMutationResponse =
  components["schemas"]["InstanceMutationResponse"];
export type MateResponse = components["schemas"]["MateResponse"];
export type MateCreate = components["schemas"]["MateCreate"];
export type MateMutationResponse =
  components["schemas"]["MateMutationResponse"];
export type Mate = MateResponse["mate"];
export type CoincidentMate = components["schemas"]["CoincidentMate"];
export type ConcentricMate = components["schemas"]["ConcentricMate"];
export type LockMate = components["schemas"]["LockMate"];
export type MateFaceRef = components["schemas"]["MateFaceRef"];
export type MateAxisRef = components["schemas"]["MateAxisRef"];
export type Placement = components["schemas"]["Placement"];
export type EvaluateAssemblyRequest =
  components["schemas"]["EvaluateAssemblyRequest"];
export type EvaluateAssemblyResult =
  components["schemas"]["EvaluateAssemblyResult"];
export type InstancePlacementResult =
  components["schemas"]["InstancePlacementResult"];
export type AssemblySolveDiagnosis =
  components["schemas"]["AssemblySolveDiagnosis"];
export type MateEvaluationError = components["schemas"]["MateEvaluationError"];
export type AssemblyStatus = EvaluateAssemblyResult["status"];

/**
 * The chosen name already belongs to another of the caller's assemblies
 * (documents enforces a per-owner unique index → gateway 409). Typed so the
 * register can pin it to the name field, mirroring `PartNameTakenError`.
 */
export class AssemblyNameTakenError extends Error {
  constructor(
    readonly assemblyName: string,
    message: string,
  ) {
    super(message);
    this.name = "AssemblyNameTakenError";
  }
}

/** The caller's assemblies, oldest first (register order). */
export async function fetchAssemblies(
  client: GatewayClient = gatewayClient,
): Promise<AssemblyResponse[]> {
  const { data, error } = await client.GET("/api/v1/assemblies");
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "Your assemblies could not be loaded."),
    );
  }
  return data.assemblies;
}

/** Create an assembly owned by the caller (201). A duplicate name → 409. */
export async function createAssembly(
  name: string,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyResponse> {
  const { data, error } = await client.POST("/api/v1/assemblies", {
    // length_unit is DISPLAY metadata (docs/design/units.md §U1); new
    // assemblies default to canonical mm. The document-unit selector (U2)
    // changes it via the update route.
    body: { name, length_unit: "mm" },
  });
  if (error !== undefined) {
    if (
      envelopeCode(error) === "assembly_name_taken" ||
      envelopeCode(error) === "name_taken"
    ) {
      throw new AssemblyNameTakenError(
        name,
        envelopeMessage(error, `An assembly named "${name}" already exists.`),
      );
    }
    throw new Error(
      envelopeMessage(error, "The assembly could not be created."),
    );
  }
  return data;
}

/**
 * Change the assembly's document display unit (docs/design/units.md §U2).
 * DISPLAY metadata only — no stored mm value is touched, so this never
 * re-solves the assembly; it bumps `doc_version` under the OCC guard. The route
 * + types are generated; the server envelope surfaces verbatim on a stale
 * version (422) or unknown assembly (404).
 */
export async function updateAssemblyUnit(
  assemblyId: string,
  lengthUnit: LengthUnit,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/assemblies/{assembly_id}",
    {
      params: { path: { assembly_id: assemblyId } },
      body: { length_unit: lengthUnit, expected_version: expectedVersion },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The document unit could not be changed."),
    );
  }
  return data;
}

/** Delete one of the caller's assemblies (204; 404 for unknown/foreign ids). */
export async function deleteAssembly(
  assemblyId: string,
  client: GatewayClient = gatewayClient,
): Promise<void> {
  const { error } = await client.DELETE("/api/v1/assemblies/{assembly_id}", {
    params: { path: { assembly_id: assemblyId } },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The assembly could not be deleted."),
    );
  }
}

/** The assembly's full instance + mate graph and its concurrency token. */
export async function fetchAssemblyGraph(
  assemblyId: string,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.GET("/api/v1/assemblies/{assembly_id}", {
    params: { path: { assembly_id: assemblyId } },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The assembly could not be loaded."),
    );
  }
  return data;
}

/** Add a part instance to an assembly (201; 422 on a stale version). */
export async function createInstance(
  assemblyId: string,
  body: InstanceCreate,
  client: GatewayClient = gatewayClient,
): Promise<InstanceMutationResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/instances",
    { params: { path: { assembly_id: assemblyId } }, body },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The part could not be added to the assembly."),
    );
  }
  return data;
}

/** Re-place / rename / (un)ground an instance (200; 422 on a stale version). */
export async function updateInstance(
  assemblyId: string,
  instanceId: string,
  body: InstanceUpdate,
  client: GatewayClient = gatewayClient,
): Promise<InstanceMutationResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
    {
      params: { path: { assembly_id: assemblyId, instance_id: instanceId } },
      body,
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The instance could not be updated."),
    );
  }
  return data;
}

/** Remove an instance; returns the renumbered graph + new version. */
export async function deleteInstance(
  assemblyId: string,
  instanceId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
    {
      params: {
        path: { assembly_id: assemblyId, instance_id: instanceId },
        query: { expected_version: expectedVersion },
      },
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The instance could not be removed."),
    );
  }
  return data;
}

/** Add a mate to an assembly (201; 422 on a stale version). */
export async function createMate(
  assemblyId: string,
  body: MateCreate,
  client: GatewayClient = gatewayClient,
): Promise<MateMutationResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/mates",
    { params: { path: { assembly_id: assemblyId } }, body },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The mate could not be added."));
  }
  return data;
}

/** Remove a mate; returns the graph + new version. */
export async function deleteMate(
  assemblyId: string,
  mateId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.DELETE(
    "/api/v1/assemblies/{assembly_id}/mates/{mate_id}",
    {
      params: {
        path: { assembly_id: assemblyId, mate_id: mateId },
        query: { expected_version: expectedVersion },
      },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The mate could not be removed."));
  }
  return data;
}

/**
 * Evaluate the assembly: geometry evaluates each unique part once (one
 * content-addressed mesh shared by every instance of it), solves the mate
 * graph, and returns per-instance `{shared mesh id, solved placement}` plus the
 * combined roll-up. A bad part / mate / solve is a 200 with typed per-entry
 * errors or a non-`well_constrained` status (never a 5xx); the envelope stays
 * reserved for transport/validation failures of this call itself.
 */
export async function evaluateAssembly(
  request: EvaluateAssemblyRequest,
  client: GatewayClient = gatewayClient,
): Promise<EvaluateAssemblyResult> {
  const { data, error } = await client.POST(
    "/api/v1/geometry/assembly/evaluate",
    { body: request },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The assembly could not be evaluated."),
    );
  }
  return data;
}
