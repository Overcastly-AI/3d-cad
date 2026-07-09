// GENERATED — do not edit; run `just gen`.
// Thin typed fetch wrapper for the gateway service
// (source contract: packages/contracts/gateway.openapi.json).
import createClient from "openapi-fetch";
import type { ClientOptions } from "openapi-fetch";
import type { paths } from "./schema";

export type * from "./schema";

/** Create a typed openapi-fetch client for the gateway service. */
export function createGatewayClient(options?: ClientOptions) {
  return createClient<paths>(options);
}

export type GatewayClient = ReturnType<typeof createGatewayClient>;
