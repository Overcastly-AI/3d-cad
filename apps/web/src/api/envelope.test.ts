import { describe, expect, it } from "vitest";

import { envelopeCode, envelopeMessage, parseErrorEnvelope } from "./envelope";

const ENVELOPE = {
  error: {
    code: "invalid_credentials",
    message: "Invalid email or password.",
    details: null,
    request_id: "req-1",
  },
};

describe("parseErrorEnvelope", () => {
  it("reads code and message from a py-kit envelope", () => {
    expect(parseErrorEnvelope(ENVELOPE)).toEqual({
      code: "invalid_credentials",
      message: "Invalid email or password.",
    });
  });

  it.each([
    ["null", null],
    ["a string", "boom"],
    ["missing error key", { detail: [] }],
    ["non-string code", { error: { code: 401, message: "x" } }],
    ["missing message", { error: { code: "x" } }],
  ])("returns null for %s", (_name, body) => {
    expect(parseErrorEnvelope(body)).toBeNull();
  });
});

describe("envelopeCode / envelopeMessage", () => {
  it("extracts the code and message", () => {
    expect(envelopeCode(ENVELOPE)).toBe("invalid_credentials");
    expect(envelopeMessage(ENVELOPE, "fallback")).toBe(
      "Invalid email or password.",
    );
  });

  it("falls back on foreign shapes", () => {
    expect(envelopeCode({ detail: [] })).toBeNull();
    expect(envelopeMessage({ detail: [] }, "fallback")).toBe("fallback");
  });
});
