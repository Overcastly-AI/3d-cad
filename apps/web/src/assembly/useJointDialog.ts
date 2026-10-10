/**
 * The joint dialog's workspace half: it opens when the second origin is
 * picked, previews the draft through the SERVER's solve (B snaps to A as the
 * fields change, nothing persisted), flags a preview that drives B's body
 * through A (the cue to press Flip), and on OK sends ONE write: a POST for a
 * new joint, a PATCH for an edited one. A refusal (a value past a limit) keeps
 * the dialog open with the server's own words.
 *
 * After OK the last preview is HELD until the re-solve for the new
 * `doc_version` is drawn, the same hand-over `useMoveSession` makes, so B does
 * not jump back to its old pose for the length of the solve.
 */
import type { LengthUnit } from "@loft/design";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  checkInterference,
  createMate,
  evaluateAssembly,
  type EvaluateAssemblyRequest,
  type JointMate,
  type MateResponse,
  updateMate,
} from "../api/assemblies";
import { useJointDialogStore } from "./jointDialogStore";
import {
  applyJointEdit,
  buildJointMate,
  isJoint,
  JOINT_MOTIONS,
  jointLabels,
  jointUpdate,
  parseJointDraft,
} from "./joints";
import { useMateAuthoringStore } from "./mateStore";
import type { Placement } from "./placement";

/** The draft joint's id in a preview request; never stored. */
export const PREVIEW_MATE_ID = "00000000-0000-4000-8000-00000000a11e";

/** Overlap below this (mm³) is a touching seat, not a body through a body. */
const THROUGH_MM3 = 0.01;

/** How long the fields must rest before the preview re-solves. */
const PREVIEW_DEBOUNCE_MS = 180;

export interface UseJointDialogOptions {
  assemblyId: string;
  docVersion: number;
  unit: LengthUnit;
  mates: readonly MateResponse[];
  /** The persisted world's evaluate request (null while it loads). */
  evaluateRequest: EvaluateAssemblyRequest | null;
  refreshGraph: () => Promise<unknown>;
}

export function useJointDialog({
  assemblyId,
  docVersion,
  unit,
  mates,
  evaluateRequest,
  refreshGraph,
}: UseJointDialogOptions) {
  const target = useJointDialogStore((s) => s.target);
  const draft = useJointDialogStore((s) => s.draft);
  const submitting = useJointDialogStore((s) => s.submitting);
  const tool = useMateAuthoringStore((s) => s.tool);
  const picks = useMateAuthoringStore((s) => s.picks);

  // The second origin opens the dialog; disarming the tool closes a new one.
  useEffect(() => {
    const store = useJointDialogStore.getState();
    if (tool === "joint" && picks.length === 2 && store.target === null) {
      const [a, b] = picks;
      if (a?.kind === "origin" && b?.kind === "origin") {
        store.openCreate(a.origin, b.origin);
      }
    } else if (tool !== "joint" && store.target?.mode === "create") {
      store.close();
    }
  }, [tool, picks]);
  // Leaving the workspace drops the dialog.
  useEffect(() => () => useJointDialogStore.getState().close(), []);

  const parsed = useMemo(() => parseJointDraft(draft, unit), [draft, unit]);
  const supported =
    JOINT_MOTIONS.find((m) => m.motion === draft.motion)?.supported ?? false;

  /** The joint the dialog describes right now, or null while it cannot. */
  const draftJoint = useMemo<JointMate | null>(() => {
    if (target === null || !parsed.ok) return null;
    return target.mode === "create"
      ? buildJointMate(draft, parsed.parsed, target.a, target.b)
      : applyJointEdit(target.joint, draft, parsed.parsed);
  }, [target, draft, parsed]);

  const previewRequest = useMemo<EvaluateAssemblyRequest | null>(() => {
    if (evaluateRequest === null || target === null) return null;
    if (draftJoint === null || !supported) return null;
    const base = evaluateRequest.mates ?? [];
    const next =
      target.mode === "create"
        ? [
            ...base,
            {
              mate_id: PREVIEW_MATE_ID,
              order_index:
                base.reduce((max, m) => Math.max(max, m.order_index), 0) + 1,
              mate: draftJoint,
            },
          ]
        : base.map((m) =>
            m.mate_id === target.mateId ? { ...m, mate: draftJoint } : m,
          );
    return { ...evaluateRequest, mates: next };
  }, [evaluateRequest, target, draftJoint, supported]);

  // Debounced: a keystroke in a field is not a solve.
  const [settledRequest, setSettledRequest] =
    useState<EvaluateAssemblyRequest | null>(null);
  useEffect(() => {
    if (previewRequest === null) {
      setSettledRequest(null);
      return;
    }
    const timer = setTimeout(
      () => setSettledRequest(previewRequest),
      PREVIEW_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [previewRequest]);
  const previewKey =
    settledRequest === null ? "" : JSON.stringify(settledRequest.mates);

  const previewQuery = useQuery({
    queryKey: ["assembly-joint-preview", assemblyId, docVersion, previewKey],
    enabled: settledRequest !== null,
    queryFn: () => evaluateAssembly(settledRequest as EvaluateAssemblyRequest),
    staleTime: Infinity,
    placeholderData: keepPreviousData,
    retry: false,
  });
  const clashQuery = useQuery({
    queryKey: ["assembly-joint-clash", assemblyId, docVersion, previewKey],
    enabled: settledRequest !== null,
    queryFn: () => checkInterference(settledRequest as EvaluateAssemblyRequest),
    staleTime: Infinity,
    retry: false,
  });

  const open = target !== null;
  const previewPlacements = useMemo(() => {
    const map = new Map<string, Placement>();
    if (!open || previewQuery.data === undefined) return map;
    for (const inst of previewQuery.data.instances) {
      map.set(inst.instance_id, inst.placement);
    }
    return map;
  }, [open, previewQuery.data]);

  /** The two components the joint relates. */
  const pair = useMemo<[string, string] | null>(() => {
    if (target === null) return null;
    return target.mode === "create"
      ? [target.a.instanceId, target.b.instanceId]
      : [target.joint.a.instance_id, target.joint.b.instance_id];
  }, [target]);

  /** The preview drives one body through the other: Fusion's Flip cue. */
  const throughEachOther =
    open &&
    pair !== null &&
    (clashQuery.data?.clashes ?? []).some(
      (c) =>
        !c.unresolved &&
        c.overlap_volume_mm3 > THROUGH_MM3 &&
        pair.includes(c.instance_a) &&
        pair.includes(c.instance_b),
    );

  /** Why the preview could not place the joint (an unresolved origin), or null. */
  const previewId =
    target === null
      ? null
      : target.mode === "create"
        ? PREVIEW_MATE_ID
        : target.mateId;
  const previewProblem =
    (open &&
      previewQuery.data?.mate_errors?.find((e) => e.mate_id === previewId)
        ?.error.message) ||
    null;

  // ——— the hold across the re-solve ————————————————————————————————————
  const [held, setHeld] = useState<{
    placements: Map<string, Placement>;
    version: number;
  } | null>(null);

  const previewFor = useCallback(
    (instanceId: string): Placement | null =>
      previewPlacements.get(instanceId) ??
      held?.placements.get(instanceId) ??
      null,
    [previewPlacements, held],
  );

  const releaseHeld = useCallback(() => setHeld(null), []);

  const cancel = useCallback(() => {
    const store = useJointDialogStore.getState();
    if (store.target?.mode === "create") {
      useMateAuthoringStore.getState().setTool(null);
    }
    store.close();
  }, []);

  const submit = useCallback(() => {
    const store = useJointDialogStore.getState();
    const current = store.target;
    if (current === null || store.submitting) return;
    const result = parseJointDraft(store.draft, unit);
    if (!result.ok) return;
    const snapshot = previewPlacements;
    store.setSubmitting(true);
    store.setError(null);
    void (async () => {
      try {
        const reply =
          current.mode === "create"
            ? await createMate(assemblyId, {
                expected_version: docVersion,
                mate: buildJointMate(
                  store.draft,
                  result.parsed,
                  current.a,
                  current.b,
                ),
              })
            : await updateMate(
                assemblyId,
                current.mateId,
                jointUpdate(store.draft, result.parsed, docVersion),
              );
        setHeld({ placements: snapshot, version: reply.doc_version });
        useJointDialogStore.getState().close();
        if (current.mode === "create") {
          useMateAuthoringStore.getState().setTool(null);
        }
        await refreshGraph();
      } catch (error) {
        const live = useJointDialogStore.getState();
        live.setSubmitting(false);
        live.setError(
          error instanceof Error ? error.message : "The joint was refused.",
        );
      }
    })();
  }, [assemblyId, docVersion, unit, previewPlacements, refreshGraph]);

  /** Re-open a stored joint (the tree row's double-click). */
  const openEdit = useCallback(
    (row: MateResponse) => {
      if (!isJoint(row.mate)) return;
      useMateAuthoringStore.getState().setTool(null);
      const label = jointLabels(mates).get(row.id) ?? "Joint";
      useJointDialogStore.getState().openEdit(row.id, label, row.mate, unit);
    },
    [mates, unit],
  );

  return {
    open,
    submitting,
    /** The draft's preview pose for an instance, while the dialog is open. */
    previewFor,
    previewing: previewQuery.isFetching,
    throughEachOther,
    previewProblem,
    heldVersion: held?.version ?? null,
    releaseHeld,
    submit,
    cancel,
    openEdit,
  };
}

export type JointDialogApi = ReturnType<typeof useJointDialog>;

/** Drop the held preview once the solve for its version is on screen. */
export function useReleaseJointHold(
  dialog: JointDialogApi,
  docVersion: number,
  solveSettled: boolean,
): void {
  const { heldVersion, releaseHeld } = dialog;
  useEffect(() => {
    if (heldVersion === null) return;
    if (docVersion >= heldVersion && solveSettled) releaseHeld();
  }, [heldVersion, docVersion, solveSettled, releaseHeld]);
}
