// GENERATED — do not edit; run `just gen`.
// Thin typed fetch wrapper for the geometry service
// (source contract: packages/contracts/geometry.openapi.json).
import createClient from "openapi-fetch";
import type { ClientOptions } from "openapi-fetch";
import type { paths } from "./schema";

export type * from "./schema";

/** Create a typed openapi-fetch client for the geometry service. */
export function createGeometryClient(options?: ClientOptions) {
  return createClient<paths>(options);
}

export type GeometryClient = ReturnType<typeof createGeometryClient>;
