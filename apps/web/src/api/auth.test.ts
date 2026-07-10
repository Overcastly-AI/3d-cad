import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { fetchMe, login, registerAccount } from "./auth";

const USER = {
  id: "6f2f0e6a-9c1e-4be5-9d3e-6a1c76a3c001",
  email: "alice@example.com",
  created_at: "2026-07-10T12:00:00Z",
};

const TOKEN_BODY = {
  access_token: "tok-jwt",
  token_type: "bearer",
  expires_in: 3600,
  user: USER,
};

/** Typed client whose transport is a canned response — no network. */
function clientReturning(status: number, body: unknown) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: () =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      ),
  });
}

const CREDENTIALS = { email: "alice@example.com", password: "hunter2-long" };

describe("registerAccount", () => {
  it("returns the token response on 201", async () => {
    const client = clientReturning(201, TOKEN_BODY);
    const session = await registerAccount(CREDENTIALS, client);
    expect(session.access_token).toBe("tok-jwt");
    expect(session.user.email).toBe("alice@example.com");
  });

  it("surfaces the server envelope message on 409", async () => {
    const client = clientReturning(409, {
      error: {
        code: "email_taken",
        message: "An account with this email already exists.",
        details: null,
        request_id: "r",
      },
    });
    await expect(registerAccount(CREDENTIALS, client)).rejects.toThrow(
      "An account with this email already exists.",
    );
  });
});

describe("login", () => {
  it("returns the token response on 200", async () => {
    const client = clientReturning(200, TOKEN_BODY);
    const session = await login(CREDENTIALS, client);
    expect(session.access_token).toBe("tok-jwt");
  });

  it("surfaces the uniform 401 message", async () => {
    const client = clientReturning(401, {
      error: {
        code: "invalid_credentials",
        message: "Invalid email or password.",
        details: null,
        request_id: "r",
      },
    });
    await expect(login(CREDENTIALS, client)).rejects.toThrow(
      "Invalid email or password.",
    );
  });

  it("uses the fallback message for a foreign error body", async () => {
    const client = clientReturning(500, { detail: "?" });
    await expect(login(CREDENTIALS, client)).rejects.toThrow(
      "Sign-in failed — try again.",
    );
  });
});

describe("fetchMe", () => {
  it("returns the account on 200", async () => {
    const client = clientReturning(200, USER);
    await expect(fetchMe(client)).resolves.toEqual(USER);
  });

  it("rejects with the envelope message on 401", async () => {
    const client = clientReturning(401, {
      error: {
        code: "invalid_token",
        message: "Invalid or expired token.",
        details: null,
        request_id: "r",
      },
    });
    await expect(fetchMe(client)).rejects.toThrow("Invalid or expired token.");
  });
});
