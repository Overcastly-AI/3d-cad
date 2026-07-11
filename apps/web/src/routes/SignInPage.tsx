import {
  Button,
  Panel,
  PanelActionCell,
  PanelSection,
  TextField,
} from "@loft/design";
import { Navigate, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { login, registerAccount } from "../api/auth";
import { useSessionStore } from "../auth/session";
import { LoftMark } from "../components/LoftMark";
import { SheetGrid } from "../components/SheetGrid";
import { validateAuthForm, type AuthFormErrors } from "../lib/authForm";

type Mode = "sign-in" | "register";

/**
 * The un-issued drawing sheet (frontend-design pass, 2026-07-10): before
 * sign-in there is no part, so the screen is an empty sheet — the carbide
 * ground carries the viewport's own grid (one palette, two renderers), a
 * hairline sheet frame, and the auth form composed as the sheet's title
 * block, anchored where title blocks live: the bottom-right corner (centered
 * below md). Same instrument as the modeler, not a marketing splash.
 */
export function SignInPage() {
  const token = useSessionStore((state) => state.token);
  if (token !== null) return <Navigate to="/" replace />;
  return (
    <div className="relative h-full overflow-hidden bg-carbide">
      <SheetGrid />
      {/* Drawing-sheet border. */}
      <div
        className="pointer-events-none absolute inset-3 border border-hairline"
        aria-hidden="true"
      />
      <div className="relative flex h-full items-center justify-center p-6 md:items-end md:justify-end md:p-12">
        <AuthTitleBlock />
      </div>
    </div>
  );
}

function AuthTitleBlock() {
  const navigate = useNavigate();
  const signIn = useSessionStore((state) => state.signIn);
  const expired = useSessionStore((state) => state.expired);

  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<AuthFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const switchMode = (next: Mode) => {
    setMode(next);
    setFieldErrors({});
    setServerError(null);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validateAuthForm(email, password, mode);
    setFieldErrors(errors);
    setServerError(null);
    if (errors.email !== undefined || errors.password !== undefined) return;
    setBusy(true);
    try {
      const credentials = { email: email.trim(), password };
      const session =
        mode === "register"
          ? await registerAccount(credentials)
          : await login(credentials);
      signIn(session.access_token, session.user);
      await navigate({ to: "/" });
    } catch (error) {
      setServerError(
        error instanceof Error ? error.message : "Sign-in failed — try again.",
      );
      setBusy(false);
    }
  };

  const submitLabel =
    mode === "register"
      ? busy
        ? "Creating account…"
        : "Create account"
      : busy
        ? "Signing in…"
        : "Sign in";

  return (
    <Panel className="w-inspector max-w-full" data-testid="auth-panel">
      <div className="flex items-baseline gap-2 border-b border-hairline px-3 py-2">
        <LoftMark />
        <span className="font-display text-md tracking-[0.32em] text-mist">
          LOFT
        </span>
        <span className="grow" />
        <span className="font-body text-xs text-gauge">Parametric CAD</span>
      </div>

      {expired ? (
        <p
          role="status"
          className="border-b border-hairline px-3 py-2 font-data text-xs text-gauge"
          data-testid="session-expired-notice"
        >
          Session expired — sign in again.
        </p>
      ) : null}

      <div
        role="group"
        aria-label="Sign in or create account"
        className="grid grid-cols-2 divide-x divide-hairline border-b border-hairline"
      >
        <PanelActionCell
          label="Sign in"
          selected={mode === "sign-in"}
          onClick={() => switchMode("sign-in")}
          data-testid="auth-mode-sign-in"
        />
        <PanelActionCell
          label="Create account"
          selected={mode === "register"}
          onClick={() => switchMode("register")}
          data-testid="auth-mode-register"
        />
      </div>

      <PanelSection eyebrow={mode === "register" ? "New account" : "Account"}>
        <form
          className="flex flex-col gap-2 px-3"
          onSubmit={(event) => void handleSubmit(event)}
          noValidate
          data-testid="auth-form"
        >
          <TextField
            label="Email"
            type="email"
            autoComplete="email"
            autoFocus
            value={email}
            error={fieldErrors.email ?? null}
            data-testid="auth-email"
            onChange={(event) => {
              setEmail(event.currentTarget.value);
              setFieldErrors((prev) =>
                prev.email ? { ...prev, email: undefined } : prev,
              );
            }}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete={
              mode === "register" ? "new-password" : "current-password"
            }
            value={password}
            error={fieldErrors.password ?? null}
            data-testid="auth-password"
            onChange={(event) => {
              setPassword(event.currentTarget.value);
              setFieldErrors((prev) =>
                prev.password ? { ...prev, password: undefined } : prev,
              );
            }}
          />
          {serverError !== null ? (
            <p
              role="alert"
              className="font-body text-xs text-flag"
              data-testid="auth-error"
            >
              {serverError}
            </p>
          ) : null}
          <div className="flex justify-end pb-1 pt-1">
            <Button
              type="submit"
              variant="solid"
              disabled={busy}
              data-testid="auth-submit"
            >
              {submitLabel}
            </Button>
          </div>
        </form>
      </PanelSection>
    </Panel>
  );
}
