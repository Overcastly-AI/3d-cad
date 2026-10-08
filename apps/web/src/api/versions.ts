/**
 * Named part versions (LOFT-VERSIONS, docs/FILE-FORMAT.md "Named versions"):
 * save, list and restore. Types are the generated `@loft/ts-client` schemas.
 *
 * Saving is not an edit (the tree version and the undo ring do not move);
 * restoring is ONE undoable edit under the same tree-version OCC as every
 * other write, so a stale restore throws `StaleTreeVersionError` and the
 * workspace resyncs exactly as undo/redo do.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";
import { StaleTreeVersionError, type FeatureTreeResponse } from "./parts";

export type PartVersion = components["schemas"]["PartVersion"];

/**
 * The part is at a version cap (409 `part_version_limit`): 100 versions, or
 * 128 MiB of version trees. Typed so the dialog can say which cap and what to
 * do, instead of the server's byte count. Versions are never pruned, so the
 * only way on is a copy of the part.
 */
export class PartVersionLimitError extends Error {
  constructor(
    readonly cap: "count" | "bytes",
    readonly limit: number | null,
  ) {
    super(versionLimitMessage(cap, limit));
    this.name = "PartVersionLimitError";
  }
}

/** One sentence a person can act on, for either cap. */
export function versionLimitMessage(
  cap: "count" | "bytes",
  limit: number | null,
): string {
  const remedy =
    "Versions are never deleted, so duplicate the part to keep versioning it.";
  if (cap === "count") {
    return `This part already has ${limit ?? "the most"} versions, the limit for one part. ${remedy}`;
  }
  const mib = limit === null ? null : Math.round(limit / (1024 * 1024));
  return `This part's versions have reached the ${mib === null ? "storage" : `${mib} MiB`} limit for one part. ${remedy}`;
}

/** The 409's `details`, narrowed: which cap was hit, and its value. */
function limitError(body: unknown): PartVersionLimitError {
  const details =
    typeof body === "object" && body !== null
      ? ((body as { error?: { details?: unknown } }).error?.details ?? null)
      : null;
  const record =
    typeof details === "object" && details !== null
      ? (details as Record<string, unknown>)
      : {};
  if (typeof record.max_bytes === "number") {
    return new PartVersionLimitError("bytes", record.max_bytes);
  }
  return new PartVersionLimitError(
    "count",
    typeof record.max_versions === "number" ? record.max_versions : null,
  );
}

/** The part's named versions, newest first. */
export async function listPartVersions(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<PartVersion[]> {
  const { data, error } = await client.GET("/api/v1/parts/{part_id}/versions", {
    params: { path: { part_id: partId } },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The versions could not be loaded."),
    );
  }
  return data.versions;
}

export interface SaveVersionInput {
  name: string;
  /** Optional longer note: what changed and why. */
  message?: string;
  /**
   * The tree version on screen: the save is refused (`stale_tree_version`) if
   * the tree moved since, so the version holds what the user was looking at.
   */
  expectedTreeVersion?: number;
}

/** Name the part's current tree. Not an edit: undo is untouched. */
export async function savePartVersion(
  partId: string,
  input: SaveVersionInput,
  client: GatewayClient = gatewayClient,
): Promise<PartVersion> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/versions",
    {
      params: { path: { part_id: partId } },
      body: {
        name: input.name,
        message: input.message ?? "",
        expected_tree_version: input.expectedTreeVersion ?? null,
      },
    },
  );
  if (error !== undefined) {
    const code = envelopeCode(error);
    if (code === "part_version_limit") throw limitError(error);
    const message = envelopeMessage(error, "The version could not be saved.");
    if (code === "stale_tree_version") throw new StaleTreeVersionError(message);
    throw new Error(message);
  }
  return data;
}

/**
 * Make version `seq` the part's tree: one undoable edit. Answers with the
 * restored tree and its new `tree_version`.
 */
export async function restorePartVersion(
  partId: string,
  seq: number,
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<FeatureTreeResponse> {
  const { data, error } = await client.POST(
    "/api/v1/parts/{part_id}/versions/{seq}/restore",
    {
      params: { path: { part_id: partId, seq } },
      body: { expected_tree_version: expectedTreeVersion },
    },
  );
  if (error !== undefined) {
    const message = envelopeMessage(
      error,
      "The version could not be restored.",
    );
    if (envelopeCode(error) === "stale_tree_version") {
      throw new StaleTreeVersionError(message);
    }
    throw new Error(message);
  }
  return data;
}
