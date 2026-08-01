/**
 * When to speculate — the browser half of docs/PERF.md PERF-1b.
 *
 * The geometry worker cannot tell a guess worth making from a guess worth
 * nothing; intent lives here and nowhere else. Two things in this app are
 * genuine declarations of it, and only two:
 *
 * 1. **An open feature editor.** Opening the editor for feature N declares
 *    features 1..N-1 stable for as long as the dialog is open, so the commit can
 *    cost one feature's work instead of the whole tree — and so can the FIRST
 *    FACE PICK after it, which is the wait a modeller actually sees.
 * 2. **The timeline travel stop.** Dragging it walks prefixes that are already
 *    cache keys. Only BACKWARD travel needs help: rolling forward is an append,
 *    which the rebuild cache already serves in one feature's work, while a
 *    shorter tree is a fresh key and pays the full rebuild.
 *
 * Register/document hover prefetch is deliberately absent — that is ordinary
 * client-side query prefetch and worth nothing against a rebuild curve.
 *
 * THE HOOK'S CONTRACT, and why each half is load-bearing:
 *
 * * the ticket identifies the INTENT INSTANCE (kind + part + feature), so a
 *   re-render re-declares the same ticket — which the worker treats as a no-op
 *   rather than restarting the warm it is waiting on — while moving to another
 *   feature is a NEW ticket, which supersedes the old one;
 * * a settle delay, so a drag across twenty stops does not fire twenty warms
 *   for stops the user passed through at speed;
 * * **cancel on cleanup**, always. Prefetch hides latency; it does not reduce
 *   work. The editor closing or the drag ending must stop the speculation it
 *   funded, or a user who opens and abandons dialogs quietly costs a core.
 */
import { useEffect, useRef } from "react";

import {
  cancelPrefetch,
  prefetchPrefix,
  type PrefetchTargetKind,
} from "../api/prefetch";

/** What the user has declared: the feature, and how they declared it. */
export interface PrefetchIntent {
  partId: string;
  featureId: string;
  kind: PrefetchTargetKind;
}

/**
 * How long an intent must hold still before it is worth spending CPU on.
 * 150 ms is below the ~200 ms an interaction reads as instant, and above the
 * frame rate a pointer drag changes slots at.
 */
export const PREFETCH_SETTLE_MS = 150;

/**
 * The ticket for an intent: stable across re-renders of the SAME intent,
 * different for any other. The worker's whole supersede/idempotence protocol
 * hangs off this string, so it is derived, never generated.
 */
export function prefetchTicket(intent: PrefetchIntent): string {
  return `${intent.kind}:${intent.partId}:${intent.featureId}`;
}

/**
 * Warm the prefix *intent* settles, and cancel it when the intent goes away.
 *
 * `null` (or `enabled: false`) means "nothing is declared" and cancels anything
 * this hook had started — which is how a closing editor, an ending drag, and an
 * unmounting workspace all reach the worker through one path.
 */
export function usePrefetchIntent(
  intent: PrefetchIntent | null,
  options: { delayMs?: number; enabled?: boolean } = {},
): void {
  const { delayMs = PREFETCH_SETTLE_MS, enabled = true } = options;
  const partId = intent?.partId ?? null;
  const featureId = intent?.featureId ?? null;
  const kind = intent?.kind ?? null;
  // Only cancel a ticket that was actually submitted: a cancel for a warm that
  // never started is a pointless round trip on every keystroke-fast re-render.
  const submitted = useRef(false);

  useEffect(() => {
    if (!enabled || partId === null || featureId === null || kind === null) {
      return;
    }
    const ticket = prefetchTicket({ partId, featureId, kind });
    submitted.current = false;
    const timer = setTimeout(() => {
      submitted.current = true;
      void prefetchPrefix({
        ticket,
        part_id: partId,
        feature_id: featureId,
        kind,
      });
    }, delayMs);
    return () => {
      clearTimeout(timer);
      if (submitted.current) void cancelPrefetch(ticket);
    };
  }, [partId, featureId, kind, delayMs, enabled]);
}
