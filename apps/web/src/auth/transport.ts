/**
 * Auth transport — wires the session into the ONE gateway client:
 *
 * - every request carries `Authorization: Bearer <token>` while signed in;
 * - every 401 whose envelope code is `invalid_token` (expired, tampered, or
 *   ghost-user token — the gateway is deliberately uniform) clears the
 *   session globally and flags the quiet "session expired" notice. Tokens
 *   live 1 h with no refresh, so this is THE expiry story: no silent
 *   failures, no assumed-persistent sessions. Login's `invalid_credentials`
 *   401 is NOT a session defect and passes through untouched.
 */
import type { Middleware } from "openapi-fetch";

import { envelopeCode } from "../api/envelope";
import { gatewayClient } from "../api/client";
import { useSessionStore } from "./session";

/** What the middleware needs from the session (injectable for tests). */
export interface SessionTransport {
  getToken(): string | null;
  expire(): void;
}

export function createAuthMiddleware(session: SessionTransport): Middleware {
  return {
    async onRequest({ request }) {
      const token = session.getToken();
      if (token !== null) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
    async onResponse({ response }) {
      if (response.status === 401) {
        let body: unknown = null;
        try {
          body = await response.clone().json();
        } catch {
          body = null; // Non-JSON 401 — not ours to interpret.
        }
        if (envelopeCode(body) === "invalid_token") {
          session.expire();
        }
      }
      return response;
    },
  };
}

let installed = false;

/** Install the auth middleware on the app's gateway client (idempotent). */
export function installAuthTransport(): void {
  if (installed) return;
  installed = true;
  gatewayClient.use(
    createAuthMiddleware({
      getToken: () => useSessionStore.getState().token,
      expire: () => useSessionStore.getState().expire(),
    }),
  );
}
