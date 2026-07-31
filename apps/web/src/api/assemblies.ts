/**
 * Assemblies data layer — instances + mates CRUD and the shared-mesh
 * evaluation, all proxied through the gateway. Every type comes from the
 * generated `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule);
 * this module never hand-writes an API shape, and each function surfaces the
 * server envelope's own message on failure.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import {
  gatewayClient,
  MESH_ANGULAR_DEFLECTION_RAD,
  MESH_LINEAR_DEFLECTION_MM,
} from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";
import {
  type ExportedFile,
  parseContentDispositionFilename,
} from "./exportPart";
// The dependency-409 reader lives with the parts API and is shared by all three
// registers (CLAUDE.md DRY): one narrowing of the documented `details` payload,
// not three.
import { DocumentHasDependentsError, parseDependents } from "./parts";

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
export type ExportAssemblyRequest =
  components["schemas"]["ExportAssemblyRequest"];
export type AssemblyExportFormat = ExportAssemblyRequest["format"];
export type InterferenceResult = components["schemas"]["InterferenceResult"];
export type ClashPair = components["schemas"]["ClashPair"];

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

/**
 * The write raced another edit: the sent `expected_version` no longer matches
 * the assembly (422 `stale_assembly_version`). Typed so undo/redo can resync
 * quietly (the design doc's "soft reload", docs/design/undo-redo.md) instead
 * of surfacing a scary error — the assembly twin of `StaleTreeVersionError`,
 * a narrowing the OpenAPI schema can't express.
 */
export class StaleAssemblyVersionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StaleAssemblyVersionError";
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
  lengthUnit: LengthUnit = "mm",
  client: GatewayClient = gatewayClient,
): Promise<AssemblyResponse> {
  const { data, error } = await client.POST("/api/v1/assemblies", {
    // length_unit is DISPLAY metadata (docs/design/units.md §U1) stamped at
    // creation: the default is canonical mm, the caller passes the user's
    // "units for new documents" preference (#58), and the document-unit
    // selector (U2) changes it afterwards via the update route.
    body: { name, length_unit: lengthUnit },
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

/**
 * Rename one of the caller's assemblies under the OCC guard (`expected_version`).
 * Renaming cannot orphan anything — instances and views reference by ID — and
 * it IS a history event server-side, so undo restores the old name.
 */
export async function renameAssembly(
  assemblyId: string,
  name: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyResponse> {
  const { data, error } = await client.PATCH(
    "/api/v1/assemblies/{assembly_id}",
    {
      params: { path: { assembly_id: assemblyId } },
      body: { name, expected_version: expectedVersion },
    },
  );
  if (error !== undefined) {
    const code = envelopeCode(error);
    if (code === "assembly_name_taken" || code === "name_taken") {
      throw new AssemblyNameTakenError(
        name,
        envelopeMessage(error, `An assembly named "${name}" already exists.`),
      );
    }
    if (code === "stale_assembly_version") {
      throw new StaleAssemblyVersionError(
        envelopeMessage(
          error,
          "This assembly changed somewhere else. Reopen the register and try again.",
        ),
      );
    }
    throw new Error(
      envelopeMessage(error, "The assembly could not be renamed."),
    );
  }
  return data;
}

/**
 * Copy an assembly's instances and mates — NOT the parts they name (201).
 * Both assemblies reference the same parts afterwards, because an instance IS
 * a reference. The server names the copy and returns it.
 */
export async function duplicateAssembly(
  assemblyId: string,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/duplicate",
    { params: { path: { assembly_id: assemblyId } } },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The assembly could not be duplicated."),
    );
  }
  return data;
}

/**
 * Delete one of the caller's assemblies (204; 404 for unknown/foreign ids).
 * An assembly still instanced as a SUB-assembly elsewhere is refused with the
 * referring documents named (`DocumentHasDependentsError`).
 */
export async function deleteAssembly(
  assemblyId: string,
  client: GatewayClient = gatewayClient,
): Promise<void> {
  const { error } = await client.DELETE("/api/v1/assemblies/{assembly_id}", {
    params: { path: { assembly_id: assemblyId } },
  });
  if (error !== undefined) {
    const dependents = parseDependents(error);
    if (dependents !== null) {
      throw new DocumentHasDependentsError(
        dependents,
        envelopeMessage(error, "The assembly could not be deleted."),
      );
    }
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
 * Undo one assembly-graph history step (docs/design/undo-redo.md §UR3):
 * restore the previous snapshot, instance/mate ids verbatim. Undo IS a
 * document edit — it takes the client's `expected_version` and returns the
 * restored graph + the new token; at the ring's floor it's a clean 200 no-op
 * echoing the current graph (version unchanged). A stale version throws the
 * typed `StaleAssemblyVersionError` so the caller can soft-reload quietly.
 */
export async function undoAssembly(
  assemblyId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/undo",
    {
      params: { path: { assembly_id: assemblyId } },
      body: { expected_version: expectedVersion },
    },
  );
  if (error !== undefined) {
    throw historyStepError(error, "The last edit could not be undone.");
  }
  return data;
}

/** Redo one assembly-graph history step — `undoAssembly`'s mirror. */
export async function redoAssembly(
  assemblyId: string,
  expectedVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<AssemblyGraphResponse> {
  const { data, error } = await client.POST(
    "/api/v1/assemblies/{assembly_id}/redo",
    {
      params: { path: { assembly_id: assemblyId } },
      body: { expected_version: expectedVersion },
    },
  );
  if (error !== undefined) {
    throw historyStepError(error, "The edit could not be redone.");
  }
  return data;
}

/** Shared undo/redo failure mapping: stale → typed, everything else verbatim. */
function historyStepError(error: unknown, fallback: string): Error {
  const message = envelopeMessage(error, fallback);
  return envelopeCode(error) === "stale_assembly_version"
    ? new StaleAssemblyVersionError(message)
    : new Error(message);
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

/**
 * Export the whole assembly as ONE multi-instance CAD file via the gateway.
 * Geometry runs the identical evaluate solve, then composes every instance at
 * its solved world placement into one STEP (AP214 product structure) or STL
 * (baked compound). The `request` is the evaluate request plus a `format`; the
 * file bytes stream back with a `Content-Disposition` filename (server is
 * authoritative). `client` is injectable for tests.
 */
export async function exportAssembly(
  request: EvaluateAssemblyRequest,
  format: AssemblyExportFormat,
  client: GatewayClient = gatewayClient,
): Promise<ExportedFile> {
  const { data, error, response } = await client.POST(
    "/api/v1/geometry/assembly/export",
    {
      body: {
        ...request,
        format,
        angular_deflection: MESH_ANGULAR_DEFLECTION_RAD,
        linear_deflection: MESH_LINEAR_DEFLECTION_MM,
      },
      parseAs: "blob",
    },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(
        error,
        `The geometry service rejected the ${format.toUpperCase()} export`,
      ),
    );
  }
  if (data === undefined) {
    throw new Error(`${format.toUpperCase()} export returned no file`);
  }
  // parseAs:"blob" makes the runtime payload a Blob (openapi-fetch pass-through);
  // the OpenAPI schema types binary content as string.
  const blob = data as unknown as Blob;
  const filename = parseContentDispositionFilename(
    response.headers.get("Content-Disposition"),
    `assembly.${format}`,
  );
  return { blob, filename };
}

/**
 * Interference (clash) check: geometry runs the SAME solve as
 * {@link evaluateAssembly}, then reports every unordered instance pair whose
 * solved-world bodies overlap with non-trivial volume (a merely-touching pair
 * is NO clash). A clash-free assembly is `clashes: []`; a bad part/mate/solve
 * is a 200 with a typed status + (possibly empty) clash list, never a 4xx/5xx
 * from the check itself — the envelope stays reserved for transport failures.
 */
export async function checkInterference(
  request: EvaluateAssemblyRequest,
  client: GatewayClient = gatewayClient,
): Promise<InterferenceResult> {
  const { data, error } = await client.POST(
    "/api/v1/geometry/assembly/interference",
    { body: request },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The interference check could not be run."),
    );
  }
  return data;
}
