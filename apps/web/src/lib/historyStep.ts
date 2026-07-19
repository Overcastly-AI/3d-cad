/**
 * The document-agnostic undo/redo call path (docs/design/undo-redo.md §UR2/
 * UR3) — the one orchestration both workspaces share. History is SERVER-side
 * snapshot state and a step is a document edit under the same optimistic-
 * concurrency guard as every other write, so the sequence is identical for a
 * part's feature tree and an assembly's graph:
 *
 *   1. read the freshest concurrency token,
 *   2. POST the step with it,
 *   3. discriminate the boundary no-op (clean 200, version unchanged → adopt
 *      the echoed document, NO re-evaluate) from a real restore (hygiene +
 *      resync through the SAME post-mutation refresh path every save uses),
 *   4. a stale write (typed error) → quiet resync, never a scary banner,
 *   5. anything else → an honest failure message for the history-error alert.
 *
 * Only the PORTS differ per document type (version field, endpoints, query
 * keys, hygiene), so those are parameters; the page keeps a thin wrapper that
 * owns React state (in-flight ref, hold caption, error) and its own mutual
 * exclusions. Pure and node-tested — no React, no fetch.
 */
import type { HistoryStep } from "./undoRedoShortcut";

/** How one history step resolved — the page maps `failed` to its alert. */
export type HistoryStepOutcome =
  | { kind: "restored" }
  | { kind: "noop" }
  | { kind: "stale" }
  | { kind: "failed"; message: string };

/** The document-specific seams of the shared sequence above. */
export interface HistoryStepPorts<TDoc> {
  /** The freshest concurrency token to echo as the expected version. */
  version(): number | Promise<number>;
  /** POST the step (the generated-client call) — resolves the echoed document. */
  run(step: HistoryStep, expectedVersion: number): Promise<TDoc>;
  /** The concurrency token the response carries. */
  versionOf(doc: TDoc): number;
  /**
   * Boundary no-op (clean 200, version unchanged): adopt the echoed document
   * (fresh `can_undo`/`can_redo`) WITHOUT a re-evaluate cycle.
   */
  adoptNoOp(doc: TDoc): void;
  /**
   * A REAL restore happened (version moved): run the workspace hygiene (the
   * document changed under any picks/selection), then resync through the
   * shared post-mutation invalidation path.
   */
  onRestored(doc: TDoc): void | Promise<void>;
  /** Is this the typed stale-version error (someone else moved the document)? */
  isStale(error: unknown): boolean;
  /** Quiet resync after a stale write — the user re-issues against what they see. */
  resync(): void | Promise<void>;
}

/** Fallbacks when a failure carries no message of its own. */
export const HISTORY_STEP_FALLBACK: Record<HistoryStep, string> = {
  undo: "The last edit could not be undone.",
  redo: "The edit could not be redone.",
};

/** Run one undo/redo step through the shared sequence. Never throws. */
export async function executeHistoryStep<TDoc>(
  step: HistoryStep,
  ports: HistoryStepPorts<TDoc>,
): Promise<HistoryStepOutcome> {
  try {
    const expected = await ports.version();
    const doc = await ports.run(step, expected);
    if (ports.versionOf(doc) === expected) {
      ports.adoptNoOp(doc);
      return { kind: "noop" };
    }
    await ports.onRestored(doc);
    return { kind: "restored" };
  } catch (error) {
    if (ports.isStale(error)) {
      // Best-effort resync: the step WAS stale regardless of whether the
      // refetch settles, and this function's contract is never-throws (both
      // ports today are invalidateQueries-based and can't reject, but a future
      // port must not be able to break the contract).
      try {
        await ports.resync();
      } catch {
        // Swallow — a failed refetch re-triggers on the next interaction.
      }
      return { kind: "stale" };
    }
    // A transient network/server failure: the document is unchanged
    // server-side — say so honestly, never a silent busy flash.
    return {
      kind: "failed",
      message:
        error instanceof Error && error.message !== ""
          ? error.message
          : HISTORY_STEP_FALLBACK[step],
    };
  }
}
