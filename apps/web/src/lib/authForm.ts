/**
 * Client-side pre-checks for the sign-in / create-account form. The gateway
 * remains the authority (it re-enforces both rules); these exist so the
 * common mistakes get a field-level message instead of a generic 422.
 * Bounds mirror the gateway policy (RegisterRequest: 8–256 chars).
 */

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 256;

export interface AuthFormErrors {
  email?: string;
  password?: string;
}

/** Light shape check — full validation stays server-side (pydantic). */
export function validateEmail(email: string): string | undefined {
  if (email.trim() === "") return "Enter your email.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    return "Enter a valid email address.";
  }
  return undefined;
}

export function validatePassword(
  password: string,
  mode: "sign-in" | "register",
): string | undefined {
  if (password === "") return "Enter your password.";
  // Length policy only gates NEW passwords; existing accounts must be able
  // to sign in with whatever the server accepted.
  if (mode === "register" && password.length < PASSWORD_MIN_LENGTH) {
    return `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`;
  }
  if (mode === "register" && password.length > PASSWORD_MAX_LENGTH) {
    return `Password must be at most ${PASSWORD_MAX_LENGTH} characters.`;
  }
  return undefined;
}

export function validateAuthForm(
  email: string,
  password: string,
  mode: "sign-in" | "register",
): AuthFormErrors {
  const errors: AuthFormErrors = {};
  const emailError = validateEmail(email);
  if (emailError !== undefined) errors.email = emailError;
  const passwordError = validatePassword(password, mode);
  if (passwordError !== undefined) errors.password = passwordError;
  return errors;
}
