/**
 * Auth data layer — all types come from the generated `@loft/ts-client`
 * (pydantic → OpenAPI → TS; CLAUDE.md DRY rule). Errors surface the server
 * envelope's own message (e.g. "Invalid email or password.") so the UI and
 * the API speak with one voice.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type AuthTokenResponse = components["schemas"]["AuthTokenResponse"];
export type UserResponse = components["schemas"]["UserResponse"];

export interface Credentials {
  email: string;
  password: string;
}

/** Create an account and sign it in (gateway returns 201 + token). */
export async function registerAccount(
  credentials: Credentials,
  client: GatewayClient = gatewayClient,
): Promise<AuthTokenResponse> {
  const { data, error } = await client.POST("/api/v1/auth/register", {
    body: credentials,
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The account could not be created — try again."),
    );
  }
  return data;
}

/** Exchange email + password for an access token. */
export async function login(
  credentials: Credentials,
  client: GatewayClient = gatewayClient,
): Promise<AuthTokenResponse> {
  const { data, error } = await client.POST("/api/v1/auth/login", {
    body: credentials,
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "Sign-in failed — try again."));
  }
  return data;
}

/**
 * The authenticated account. A stale/tampered token makes the gateway answer
 * 401 `invalid_token`, which the transport middleware turns into a global
 * session expiry before this even rejects.
 */
export async function fetchMe(
  client: GatewayClient = gatewayClient,
): Promise<UserResponse> {
  const { data, error } = await client.GET("/api/v1/auth/me");
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The session could not be confirmed."),
    );
  }
  return data;
}
