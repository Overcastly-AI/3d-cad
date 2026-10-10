/**
 * A part's parameter table (PART-PARAMETERS, docs/RESEARCH.md §20): read it,
 * and replace it whole. Types are the generated `@loft/ts-client` schemas.
 *
 * A PUT is ONE undoable tree edit under the same tree-version OCC as every
 * other write, so a stale one throws `StaleTreeVersionError` and the workspace
 * resyncs exactly as a feature save does. A table that does not evaluate is a
 * 422 carrying the expression error's stable code, the row it blames
 * (`details.parameter`) and, for a loop, the chain (`details.chain`); those
 * come back as a typed {@link ParameterTableError} so the panel can put the
 * message on the row instead of in a toast.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";
import { StaleTreeVersionError } from "./parts";

export type PartParameter = components["schemas"]["PartParameter"];
export type PartParameterInput = components["schemas"]["PartParameterInput"];
export type PartParametersResponse =
  components["schemas"]["PartParametersResponse"];
/** What a parameter measures: `length` (mm), `angle` (degrees) or `unitless`. */
export type ParameterUnit = PartParameter["unit"];

/** The server refused the table: one stable code, and the row it blames. */
export class ParameterTableError extends Error {
  constructor(
    message: string,
    /** The stable code, e.g. `expression_cycle`, `expression_unknown_name`. */
    readonly code: string,
    /** The NAME of the row at fault, when the server named one. */
    readonly parameter: string | null,
    /** The loop, first name repeated last (`["a", "b", "a"]`), for a cycle. */
    readonly chain: readonly string[],
  ) {
    super(message);
    this.name = "ParameterTableError";
  }
}

/** The envelope's `details` object, narrowed; `{}` when there is none. */
function envelopeDetails(body: unknown): Record<string, unknown> {
  if (typeof body !== "object" || body === null) return {};
  const error = (body as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return {};
  const details = (error as { details?: unknown }).details;
  return typeof details === "object" && details !== null
    ? (details as Record<string, unknown>)
    : {};
}

/** Turn a refused PUT's body into the error the panel maps onto a row. */
export function parameterTableError(body: unknown): Error {
  const message = envelopeMessage(body, "The parameters could not be saved.");
  const code = envelopeCode(body);
  if (code === "stale_tree_version") return new StaleTreeVersionError(message);
  if (code === null) return new Error(message);
  const details = envelopeDetails(body);
  const parameter =
    typeof details.parameter === "string" ? details.parameter : null;
  const chain = Array.isArray(details.chain)
    ? details.chain.filter((name): name is string => typeof name === "string")
    : [];
  return new ParameterTableError(message, code, parameter, chain);
}

/** The part's parameter table, in its stored order. */
export async function fetchPartParameters(
  partId: string,
  client: GatewayClient = gatewayClient,
): Promise<PartParametersResponse> {
  const { data, error } = await client.GET(
    "/api/v1/parts/{part_id}/parameters",
    { params: { path: { part_id: partId } } },
  );
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The parameters could not be loaded."),
    );
  }
  return data;
}

/**
 * Replace the whole table: one undoable edit. Answers with the stored rows
 * (each with its server-computed `value`) and the new `tree_version`.
 */
export async function putPartParameters(
  partId: string,
  parameters: readonly PartParameterInput[],
  expectedTreeVersion: number,
  client: GatewayClient = gatewayClient,
): Promise<PartParametersResponse> {
  const { data, error } = await client.PUT(
    "/api/v1/parts/{part_id}/parameters",
    {
      params: { path: { part_id: partId } },
      body: {
        expected_tree_version: expectedTreeVersion,
        parameters: [...parameters],
      },
    },
  );
  if (error !== undefined) throw parameterTableError(error);
  return data;
}
