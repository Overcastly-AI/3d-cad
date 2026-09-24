import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { fetchMe } from "../api/auth";
import { useSessionStore } from "../auth/session";
import { ShortcutSheetHost } from "../components/ShortcutSheet";

/**
 * Gate for everything behind sign-in. Reactive on purpose: a mid-session
 * global expiry (transport.ts catching an `invalid_token` 401) clears the
 * store and this component immediately routes to the sign-in sheet — no
 * reload needed, no silent failure.
 */
export function AuthedLayout() {
  const token = useSessionStore((state) => state.token);
  if (token === null) return <ToSignIn />;
  return (
    <>
      <SessionProbe token={token} />
      {/* `?` opens the key card from any authed surface (UI-REVIEW F4).
          Mounted HERE rather than per page so there is one listener and one
          reference, and so no surface can ship without it. */}
      <ShortcutSheetHost />
      <Outlet />
    </>
  );
}

/**
 * Signed out on a page behind sign-in: go to the sign-in sheet, and ask the
 * store to remember this page so sign-in comes back to it
 * (DEEPLINK-SIGNIN-RETURN-1). Whether it is remembered is the store's call:
 * a first visit is, a deliberate sign-out is not, and an expiry has already
 * recorded its own path. The store write comes first, in the same effect,
 * so it is in place before the sign-in page reads it.
 *
 * The page is read ONCE, at mount. This component is still mounted when the
 * location has already become "/sign-in" (the route match switches after
 * the location does), and a live read re-ran the effect with that, wiping
 * the path it had just recorded (seen in e2e).
 */
function ToSignIn() {
  const navigate = useNavigate();
  const href = useLocation({ select: (location) => location.href });
  const [from] = useState(href);
  const rememberDeepLink = useSessionStore((state) => state.rememberDeepLink);
  useEffect(() => {
    rememberDeepLink(from);
    void navigate({ to: "/sign-in", replace: true });
  }, [from, navigate, rememberDeepLink]);
  return null;
}

/**
 * Boot-time session validation — a persisted token is a claim, not a fact
 * (it may have expired while the tab was closed). `GET /auth/me` confirms
 * it; an `invalid_token` 401 is caught globally by the transport middleware,
 * which expires the session and thereby redirects. A *network* failure
 * deliberately keeps the session: the gateway being briefly unreachable is
 * not a credential defect, and per-request errors surface on their own.
 */
function SessionProbe({ token }: { token: string }) {
  useQuery({
    queryKey: ["auth", "me", token],
    queryFn: () => fetchMe(),
    staleTime: Infinity,
    retry: false,
  });
  return null;
}
