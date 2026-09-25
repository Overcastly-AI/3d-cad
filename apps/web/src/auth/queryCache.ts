/**
 * The query cache belongs to ONE signed-in user (QUERY-CACHE-USER-SWITCH-1).
 *
 * The app has one module-level `QueryClient`, and its keys name documents,
 * not people (`["parts"]`, `["part", id]`). With a 30 s `staleTime` on the
 * parts list, a second person signing in on a shared browser was SERVED the
 * first person's cached list, with no request made at all.
 *
 * So the cache is dropped whenever the identity changes, null included:
 * sign-out, a session that expired, the session_mismatch drop (`abandon`),
 * and a sign-in as someone else. The trade, named: a session that expires and
 * is resumed by the SAME person refetches its pages instead of reusing them.
 * That is the same call session.ts makes for sketch drafts on expiry, for the
 * same reason: expiry is also the path by which A's session ends and B signs
 * in without anyone pressing "sign out". A renewal (same user, new token) is
 * not an identity change and keeps the cache.
 */
import type { QueryClient } from "@tanstack/react-query";

import type { SessionState } from "./session";

/** The part of a zustand store this needs (tests pass a real one). */
export interface SessionSubscribable {
  subscribe(
    listener: (state: SessionState, previous: SessionState) => void,
  ): () => void;
}

/**
 * Clear *queryClient* whenever *store*'s user id changes. Returns the
 * unsubscribe. Runs synchronously inside the store update, so the cache is
 * empty before anything renders for the new identity.
 */
export function clearQueriesOnUserChange(
  store: SessionSubscribable,
  queryClient: QueryClient,
): () => void {
  return store.subscribe((state, previous) => {
    if ((state.user?.id ?? null) !== (previous.user?.id ?? null)) {
      queryClient.clear();
    }
  });
}
