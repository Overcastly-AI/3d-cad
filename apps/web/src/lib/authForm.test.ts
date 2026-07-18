import { describe, expect, it } from "vitest";

import { validateAuthForm, validateEmail, validatePassword } from "./authForm";

describe("validateEmail", () => {
  it("accepts a plain address", () => {
    expect(validateEmail("alice@example.com")).toBeUndefined();
  });

  it("tolerates surrounding whitespace", () => {
    expect(validateEmail("  alice@example.com  ")).toBeUndefined();
  });

  it.each(["", "   "])("requires a value (%j)", (value) => {
    expect(validateEmail(value)).toBe("Enter your email.");
  });

  it.each(["nope", "a@b", "a b@c.d", "@example.com"])("rejects %j", (value) => {
    expect(validateEmail(value)).toBe("Enter a valid email address.");
  });
});

describe("validatePassword", () => {
  it("requires a value in both modes", () => {
    expect(validatePassword("", "sign-in")).toBe("Enter your password.");
    expect(validatePassword("", "register")).toBe("Enter your password.");
  });

  it("enforces the 8-char minimum only when creating an account", () => {
    expect(validatePassword("short7!", "register")).toBe(
      "Password must be at least 8 characters.",
    );
    // Sign-in must accept whatever the server accepted historically.
    expect(validatePassword("short7!", "sign-in")).toBeUndefined();
  });

  it("enforces the 256-char maximum when creating an account", () => {
    expect(validatePassword("x".repeat(257), "register")).toBe(
      "Password must be at most 256 characters.",
    );
    expect(validatePassword("x".repeat(256), "register")).toBeUndefined();
  });
});

describe("validateAuthForm", () => {
  it("returns no errors for a valid registration", () => {
    expect(
      validateAuthForm("alice@example.com", "long-enough-pw", "register"),
    ).toEqual({});
  });

  it("collects both field errors at once", () => {
    const errors = validateAuthForm("nope", "", "sign-in");
    expect(errors.email).toBe("Enter a valid email address.");
    expect(errors.password).toBe("Enter your password.");
  });
});
