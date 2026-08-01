/**
 * Prefetch data layer — tell the geometry worker which feature-tree prefix is
 * about to be needed, and tell it when to stop caring (docs/PERF.md PERF-1b).
 *
 * These are the only two calls in the app that ask for WORK and want NOTHING
 * back. The reply carries a ticket and a boolean, by construction: a
 * speculative rebuild that could be published would eventually be published for
 * a tree it does not exactly correspond to. All a warm can do is make the NEXT
 * ordinary evaluate resume from a cached checkpoint instead of feature 0.
 *
 * **Best-effort, and that is a design property, not laziness.** Every failure
 * mode here — offline, 429, an upstream 502, a part deleted between render and
 * click — has exactly one consequence: the next rebuild is as slow as it was
 * before. So nothing throws and nothing surfaces to the user; a prefetch that
 * reported errors would be a UI that interrupts you about an optimisation.
 * Types come from the generated `@loft/ts-client` (CLAUDE.md DRY rule).
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";

export type PrefetchRequest = components["schemas"]["PrefetchRequest"];
/** Which declaration of intent this is: an open editor, or a travel stop. */
export type PrefetchTargetKind = PrefetchRequest["kind"];
export type WarmTreeResult = components["schemas"]["WarmTreeResult"];

/**
 * Ask the worker to warm the prefix this intent settles.
 *
 * Resolves to whether the worker took the job (`false` = the same ticket was
 * already in flight, or there was no prefix worth warming) — useful in tests
 * and never acted on by the UI.
 */
export async function prefetchPrefix(
  request: PrefetchRequest,
  client: GatewayClient = gatewayClient,
): Promise<boolean> {
  try {
    const { data } = await client.POST("/api/v1/geometry/prefetch", {
      body: request,
    });
    return data?.accepted ?? false;
  } catch {
    return false;
  }
}

/**
 * Retire a warm ticket — the editor closed, the drag ended, the view unmounted.
 *
 * Required, not politeness (docs/PERF.md PERF-1b): prefetch hides latency, it
 * does not reduce work, so speculation whose reason has gone away must stop
 * competing with the requests that are not guesses.
 */
export async function cancelPrefetch(
  ticket: string,
  client: GatewayClient = gatewayClient,
): Promise<boolean> {
  try {
    const { data } = await client.POST("/api/v1/geometry/prefetch/cancel", {
      body: { ticket },
    });
    return data?.accepted ?? false;
  } catch {
    return false;
  }
}
