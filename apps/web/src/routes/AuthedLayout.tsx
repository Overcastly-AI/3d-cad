import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "@tanstack/react-router";

import { fetchMe } from "../api/auth";
import { useSessionStore } from "../auth/session";

/**
 * Gate for everything behind sign-in. Reactive on purpose: a mid-session
 * global expiry (transport.ts catching an `invalid_token` 401) clears the
 * store and this component immediately routes to the sign-in sheet — no
 * reload needed, no silent failure.
 */
export function AuthedLayout() {
  const token = useSessionStore((state) => state.token);
  if (token === null) return <Navigate to="/sign-in" replace />;
  return (
    <>
      <SessionProbe token={token} />
      <Outlet />
    </>
  );
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
