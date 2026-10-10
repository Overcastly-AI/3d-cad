/**
 * The Move command's session — Fusion 360's Move (Copy is `useCopyComponent`,
 * which opens this session on the new copy).
 *
 * A session is bound to ONE instance and holds the pose the user is shaping.
 * Nothing is persisted while it is shaped: a triad drag and a typed cell only
 * move the PREVIEW, which the page draws in place of the solved pose. A commit
 * (triad release, Enter, OK) sends exactly ONE `PATCH /instances/{id}` with the
 * placement, which the documents service records as ONE undo step.
 *
 * After a commit the preview is HELD, not dropped, until the re-solve for the
 * new `doc_version` has landed and been drawn (`solveSettled`). Dropping it on
 * the PATCH reply would snap the part back to its old pose for the length of
 * the re-solve — the evaluation is kept as placeholder data across a refetch on
 * purpose — and then forward again. Once the solve is in, the SOLVED pose is
 * what the page draws: a mated instance lands where the solver puts it, not
 * where it was dropped (joints come later; the solver wins today).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { updateInstance } from "../api/assemblies";
import { samePlacement } from "./movePose";
import type { Placement } from "./placement";

export interface MoveSession {
  instanceId: string;
  /**
   * Bumped whenever the pose changes from OUTSIDE the panel (start, a triad
   * drag, a landed solve), so the typed cells re-seed — and never on the
   * panel's own keystrokes, which would clobber what is being typed.
   */
  seed: number;
}

export interface UseMoveSessionOptions {
  assemblyId: string;
  docVersion: number;
  refreshGraph: () => Promise<unknown>;
  onError: (message: string) => void;
}

export function useMoveSession({
  assemblyId,
  docVersion,
  refreshGraph,
  onError,
}: UseMoveSessionOptions) {
  const [session, setSession] = useState<MoveSession | null>(null);
  /** The uncommitted pose being shaped (triad or typed), or null. */
  const [draft, setDraftState] = useState<Placement | null>(null);
  // Mirrored in a ref: a triad release reads the LAST reported pose, which may
  // not have rendered yet when the pointer comes up.
  const draftRef = useRef<Placement | null>(null);
  const setDraft = useCallback((next: Placement | null) => {
    draftRef.current = next;
    setDraftState(next);
  }, []);
  /** A committed pose held on screen until its re-solve lands. */
  const [held, setHeld] = useState<{
    instanceId: string;
    placement: Placement;
    version: number;
  } | null>(null);
  const [committing, setCommitting] = useState(false);

  /** Drop the held pose: its solve is on screen (`useReleaseWhenSolved`). */
  const releaseHeld = useCallback(() => {
    setHeld(null);
    setSession((s) => (s === null ? s : { ...s, seed: s.seed + 1 }));
  }, []);

  const start = useCallback(
    (instanceId: string) => {
      setDraft(null);
      setSession((s) => ({ instanceId, seed: (s?.seed ?? 0) + 1 }));
    },
    [setDraft],
  );

  /** Esc / Cancel: drop the uncommitted pose; the part returns to its pose. */
  const cancel = useCallback(() => {
    setDraft(null);
    setSession(null);
  }, [setDraft]);

  /** A live pose. `fromTriad` re-seeds the cells to follow the drag. */
  const preview = useCallback(
    (placement: Placement, fromTriad: boolean) => {
      setDraft(placement);
      if (fromTriad) {
        setSession((s) => (s === null ? s : { ...s, seed: s.seed + 1 }));
      }
    },
    [setDraft],
  );

  /**
   * Send the ONE `PATCH` for the current draft. A pose equal to `current`
   * writes nothing — a click on a handle is not an edit. `close` ends the
   * session (Enter / OK); a triad release keeps it open for the next drag.
   */
  const commit = useCallback(
    (current: Placement, close: boolean) => {
      if (session === null || committing) return;
      const target = draftRef.current;
      const instanceId = session.instanceId;
      if (close) setSession(null);
      if (target === null || samePlacement(target, current)) {
        setDraft(null);
        return;
      }
      setCommitting(true);
      setHeld({ instanceId, placement: target, version: Infinity });
      setDraft(null);
      void (async () => {
        try {
          const reply = await updateInstance(assemblyId, instanceId, {
            expected_version: docVersion,
            placement: target,
          });
          setHeld({
            instanceId,
            placement: target,
            version: reply.doc_version,
          });
          await refreshGraph();
        } catch (error) {
          setHeld(null);
          onError(
            error instanceof Error
              ? error.message
              : "The component could not be moved.",
          );
        } finally {
          setCommitting(false);
        }
      })();
    },
    [
      session,
      committing,
      setDraft,
      assemblyId,
      docVersion,
      refreshGraph,
      onError,
    ],
  );

  /** The pose to DRAW for an instance in place of its solve, if any. */
  const overrideFor = useCallback(
    (instanceId: string): Placement | null => {
      if (draft !== null && session?.instanceId === instanceId) return draft;
      if (held !== null && held.instanceId === instanceId) {
        return held.placement;
      }
      return null;
    },
    [draft, session, held],
  );

  return {
    session,
    committing,
    /** A write is in flight or its solve has not landed (history must wait). */
    busy: committing || held !== null,
    /** The `doc_version` the held pose waits for (Infinity until the reply). */
    heldVersion: held?.version ?? null,
    releaseHeld,
    start,
    cancel,
    preview,
    commit,
    overrideFor,
  };
}

export type MoveSessionApi = ReturnType<typeof useMoveSession>;

/**
 * Release the held pose once the settled solve for (at least) its version is
 * on screen. A separate hook because "settled" is derived from the very scene
 * the held pose feeds — the page calls this after it has derived its solve.
 */
export function useReleaseWhenSolved(
  move: MoveSessionApi,
  docVersion: number,
  solveSettled: boolean,
): void {
  const { heldVersion, committing, releaseHeld } = move;
  useEffect(() => {
    if (heldVersion === null || committing) return;
    if (docVersion >= heldVersion && solveSettled) releaseHeld();
  }, [heldVersion, committing, docVersion, solveSettled, releaseHeld]);
}
