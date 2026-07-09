// GENERATED — do not edit; run `just gen`.
// Thin typed fetch wrapper for the documents service
// (source contract: packages/contracts/documents.openapi.json).
import createClient from "openapi-fetch";
import type { ClientOptions } from "openapi-fetch";
import type { paths } from "./schema";

export type * from "./schema";

/** Create a typed openapi-fetch client for the documents service. */
export function createDocumentsClient(options?: ClientOptions) {
  return createClient<paths>(options);
}

export type DocumentsClient = ReturnType<typeof createDocumentsClient>;
