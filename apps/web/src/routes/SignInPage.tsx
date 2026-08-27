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
import {
  ProjectionPlate,
  ThirdAngleSymbol,
} from "../components/ProjectionPlate";
import { SheetGrid } from "../components/SheetGrid";
import { validateAuthForm, type AuthFormErrors } from "../lib/authForm";

type Mode = "sign-in" | "register";

/**
 * THE ISSUED SHEET (frontend-design pass 2026-08-26 — SIGNIN-1).
 *
 * The 2026-07-10 pass called this screen "the un-issued drawing sheet": nothing
 * is drawn yet, so the sheet is blank and the auth form sits where a title block
 * sits, the bottom-right corner. The metaphor was right; the execution had a
 * units bug that four audit passes filed and nobody fixed, because it kept being
 * read as a styling nit rather than as the structural fault it was. The SHEET
 * was the browser window. A window has no edges, so "the bottom-right corner of
 * the sheet" resolved to 82 % across a 1600 px void: a 320x260 card at
 * (1233, 692) with 94.8 % of the frame empty grid. Nothing in the CSS was wrong.
 * The object the composition was anchored to did not exist.
 *
 * Two changes, and the first is the whole fix:
 *
 *  1. THE SHEET IS A BOUNDED OBJECT — a real drawn rectangle, centred in the
 *     frame at `max-w-sheet` (see `layout.sheetWidth`), with the grid and the
 *     bench visible around it. The title block is now in the corner OF SOMETHING,
 *     which is the only condition under which "title block in the corner" was
 *     ever a design and not an accident. The card's centre moves from (82 %,
 *     82 %) of the frame to roughly (67 %, 50 %): still deliberately
 *     right-of-centre, because that is where a title block belongs and centring
 *     it would have thrown away the idea instead of fixing it, but unmistakably
 *     part of a composition. `e2e/first-impression.spec.ts` asserts the centre
 *     fraction, so this cannot silently drift back.
 *
 *  2. SOMETHING IS DRAWN ON IT. An empty sheet was the thesis and it is a thesis
 *     that cannot survive a screenshot: to a visitor it is indistinguishable
 *     from a page that failed to load. The sheet now carries a third-angle
 *     orthographic plate of a machined bracket (`ProjectionPlate`) — the
 *     artefact this product exists to produce, drawn in the sketcher's own ink
 *     tokens, with the title strip printing what a real sheet prints: drawing
 *     number, scale, projection convention, licence.
 *
 * Everything else is unchanged on purpose. Same panel primitive, same test ids,
 * same keyboard-first behaviour (the email cell still takes focus on load), no
 * animation, no new colour.
 */
export function SignInPage() {
  const token = useSessionStore((state) => state.token);
  if (token !== null) return <Navigate to="/" replace />;
  return (
    <div className="relative h-full overflow-hidden bg-carbide">
      <SheetGrid />
      <div className="relative flex h-full items-center justify-center p-4 sm:p-6 md:p-8">
        {/* `bg-carbide/85` is not a colour, it is a MASK: the sheet is the same
            ink as the bench it lies on, so the only thing the fill does is quiet
            the bench grid showing through it. That is what makes the frame read
            as a sheet lying on the table rather than as a box drawn on it, and
            it keeps the plate legible against a settled ground. */}
        <div
          className="flex max-h-full w-full max-w-sheet flex-col border border-hairline bg-carbide/85 shadow-float"
          data-testid="sign-in-sheet"
        >
          <div className="flex min-h-0 grow flex-col-reverse md:flex-row md:items-stretch">
            {/* The sheet's drawing area. Not rendered below md, where there is
                not enough width to draw four views at a legible size — a plate
                squeezed to 300 px is not a smaller drawing, it is an unreadable
                one, and the form is what the screen is for. */}
            <div className="hidden min-w-0 grow items-center justify-center p-5 md:flex">
              {/* Width-driven, height from the viewBox's own aspect: the plate
                  fills the sheet at every width instead of being a fixed block
                  with air around it, which is how the sheet ends up covering
                  ~45 % of a 1600x1000 frame and ~71 % of a 1280x800 one against
                  the 5.2 % the audit measured. `max-h` is the guard for a short
                  frame; `meet` letterboxes rather than distorting. */}
              <ProjectionPlate className="max-h-[34rem] w-full" />
            </div>
            <div className="flex shrink-0 items-center p-3 md:w-[23rem]">
              <AuthTitleBlock />
            </div>
          </div>
          <SheetFooter />
        </div>
      </div>
    </div>
  );
}

/**
 * The strip a real drawing prints along its bottom edge. Every field is TRUE —
 * the design mandate's "a readout that only decorates is a defect" applies to a
 * decorative surface as much as to the modeller's chrome, so there is no
 * invented revision number and no fake company name. The projection symbol
 * states the convention the plate above is actually drawn in.
 */
function SheetFooter() {
  return (
    <div
      className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-hairline px-3 py-2 font-display text-2xs uppercase tracking-[0.16em] text-gauge"
      data-testid="sheet-footer"
    >
      <span>Loft &mdash; parametric CAD</span>
      <span className="text-etch" aria-hidden="true">
        |
      </span>
      <span>Open source, MIT</span>
      <span className="text-etch" aria-hidden="true">
        |
      </span>
      <span>Self-hostable</span>
      <span className="grow" />
      <span className="hidden items-center gap-2 sm:flex">
        Third angle
        <ThirdAngleSymbol className="h-3 w-[34px] shrink-0" />
      </span>
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
    <Panel className="w-full" data-testid="auth-panel">
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
