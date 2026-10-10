/**
 * The sketch's persistence: the serialized write chain, the FLOW-A2 draft
 * and leave guard, the live debounce loop and the solve feedback.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useBlocker } from "@tanstack/react-router";

import {
  createFeature,
  fetchFeatureTree,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  updateFeature,
} from "../../api/parts";
import { FeatureWriteError } from "../../api/envelope";
import {
  describeInputError,
  INPUT_ERROR_CODES,
} from "../../features/fieldFormulas";
import { type SolveInfo } from "../../sketch/solveFeedback";
import { planeRefFromSpec } from "../../sketch/plane";
import { useSketchStore } from "../../sketch/store";
import {
  clearSketchDraft,
  readSketchDraft,
  writeSketchDraft,
} from "../sketchDraft";
import { SYNC_DEBOUNCE_MS } from "./openEditor";
import type { PartDocument } from "./usePartDocument";

type SketchPersistenceParams = Pick<
  PartDocument,
  | "partId"
  | "queryClient"
  | "mode"
  | "revision"
  | "featureId"
  | "userConstrained"
  | "entityCount"
  | "constraintCount"
  | "treeVersion"
  | "evaluation"
>;

export function useSketchPersistence({
  partId,
  queryClient,
  mode,
  revision,
  featureId,
  userConstrained,
  entityCount,
  constraintCount,
  treeVersion,
  evaluation,
}: SketchPersistenceParams) {
  // ---------------------------------------------------------------------
  // Persistence — one serialized write chain (create binds, update PATCHes;
  // stale tree versions refetch + retry once, so debounced edits never race
  // each other into 422s).
  // ---------------------------------------------------------------------
  const [syncPending, setSyncPending] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const lastSynced = useRef(0);
  const failedRevision = useRef<number | null>(null);
  const treeVersionRef = useRef<number | undefined>(undefined);
  const chain = useRef<Promise<void>>(Promise.resolve());
  const inFlight = useRef(0);
  // A create for the still-unbound sketch is in flight. Guards the double-fire
  // that used to mint duplicate "Sketch1" features (double-Escape during the
  // async save — UI-REVIEW 2026-07-16, Track C P2). A finish requested while a
  // create runs is remembered and lands once the feature binds.
  const creatingRef = useRef(false);
  const pendingExitRef = useRef(false);

  useEffect(() => {
    if (treeVersion !== undefined) treeVersionRef.current = treeVersion;
  }, [treeVersion]);

  const persistBuffer = useCallback(
    (exitAfter: boolean) => {
      const state = useSketchStore.getState();
      if (state.plane === null || state.entities.length === 0) {
        if (exitAfter) state.exit();
        return;
      }
      const payload = {
        plane: state.plane,
        entities: state.entities,
        constraints: state.constraints,
        featureId: state.featureId,
        revision: state.revision,
      };
      const isCreate = payload.featureId === null;
      // Idempotent finish: a create for this unbound sketch is already running —
      // don't enqueue a second (the duplicate-"Sketch1" bug). Defer the exit so
      // the finish still lands the moment the in-flight create binds.
      if (isCreate && creatingRef.current) {
        if (exitAfter) pendingExitRef.current = true;
        return;
      }
      if (isCreate) creatingRef.current = true;
      inFlight.current += 1;
      setSyncPending(true);
      chain.current = chain.current
        .then(async () => {
          // Everything that can throw — including plane resolution — lives inside
          // the try so the `finally` ALWAYS clears `creatingRef`. A throw before
          // the try (the old shape) skipped the finally and wedged the create
          // guard on, hard-locking the user in sketch mode (worse than the soft
          // sync error it replaced).
          try {
            const planeRef = planeRefFromSpec(payload.plane);
            // Default sketch name numbers off the FRESHEST tree, never a stale
            // query — first sketch "Sketch1", next "Sketch2", never a dupe.
            const runCreate = async () => {
              const fresh = await fetchFeatureTree(partId);
              const count = fresh.features.filter(
                (f) => f.feature.type === "sketch",
              ).length;
              return createFeature(
                partId,
                sketchFeatureCreate(
                  `Sketch${count + 1}`,
                  planeRef,
                  payload.entities,
                  payload.constraints,
                  fresh.tree_version,
                ),
              );
            };
            const runUpdate = (version: number) =>
              updateFeature(
                partId,
                payload.featureId as string,
                sketchFeatureUpdate(
                  planeRef,
                  payload.entities,
                  payload.constraints,
                  version,
                ),
              );
            let response;
            if (isCreate) {
              response = await runCreate();
            } else {
              try {
                response = await runUpdate(
                  treeVersionRef.current ??
                    (await fetchFeatureTree(partId)).tree_version,
                );
              } catch {
                // Stale tree version (or a hiccup): refetch, retry once.
                response = await runUpdate(
                  (await fetchFeatureTree(partId)).tree_version,
                );
              }
            }
            treeVersionRef.current = response.tree_version;
            lastSynced.current = Math.max(lastSynced.current, payload.revision);
            failedRevision.current = null;
            setSyncError(null);
            const now = useSketchStore.getState();
            if (now.mode === "draw") {
              if (isCreate && now.featureId === null)
                now.bind(response.feature.id);
              if (exitAfter || pendingExitRef.current) now.exit();
            }
            await queryClient.invalidateQueries({
              queryKey: ["features", partId],
            });
          } catch (error) {
            failedRevision.current = payload.revision;
            setSyncError(
              error instanceof Error
                ? error.message
                : "The sketch could not be saved — reload and try again.",
            );
            // A dimension formula documents refuses at write (an unknown
            // name, a cycle, a unit clash: PART-PARAMETERS step 4) never
            // reaches the solver, so it takes the same diagnostic stamp a
            // formula the solver refuses does, in the field's words.
            if (
              error instanceof FeatureWriteError &&
              error.code?.startsWith("expression_") === true
            ) {
              useSketchStore.getState().adoptSolved(null, {
                status: "invalid",
                dof: null,
                conflicting: [],
                redundant: [],
                message: describeInputError(error.message),
              });
            }
          } finally {
            if (isCreate) {
              creatingRef.current = false;
              pendingExitRef.current = false;
            }
            inFlight.current -= 1;
            if (inFlight.current === 0) setSyncPending(false);
          }
        })
        .catch(() => {
          // Belt-and-suspenders: the inner try/catch/finally already handles
          // every expected failure, so this only fires if something truly
          // unexpected throws. Never let a freak error wedge the create guard
          // (which hard-locks sketch mode) or leave the chain permanently
          // rejected for all later saves.
          creatingRef.current = false;
          pendingExitRef.current = false;
        });
    },
    [partId, queryClient],
  );

  /** Strip action: first save persists + closes; bound = finish (flush). */
  const finishSketch = useCallback(() => {
    const state = useSketchStore.getState();
    if (state.featureId !== null && state.revision <= lastSynced.current) {
      state.exit();
      return;
    }
    persistBuffer(true);
  }, [persistBuffer]);

  // ---------------------------------------------------------------------
  // FLOW-A2 — THE THREE ORDINARY EXITS, AND THE DRAFT BEHIND THEM.
  //
  // AUDIT-FLOW-2026-09 A2: Back, the breadcrumb and a reload each destroyed a
  // four-entity, nine-constraint sketch with no prompt and no recovery. There
  // was no navigation guard of any kind in the app.
  //
  // Two halves, and they are not interchangeable. The GUARD (`useBlocker` —
  // the router's own primitive, so in-app pushes and the popstate of the Back
  // button go through one code path, and `enableBeforeUnload` covers the
  // reload the router cannot see) stops the silent exit. The DRAFT
  // (`sketchDraft.ts`) is what lets the guard say something other than a
  // threat: a tab that dies unasked still gets its entities back, so the
  // prompt explains the difference between work that is IN THE PART and work
  // that is only in this browser.
  //
  // Why the unsaved test is `featureId === null || revision > lastSynced` and
  // not "are there entities": a BOUND sketch debounce-saves every edit, so its
  // work is already in the part between keystrokes and prompting on the way
  // out would be a lie. An UNBOUND one has never been written anywhere.
  // ---------------------------------------------------------------------
  /**
   * Read at EVENT time by the blocker, not at registration time — the router
   * registers the blocker once and calls it later, so the flag has to be a ref.
   * The one effect below owns both it and the stored bytes, so a guard that
   * fires and a draft that exists can never disagree about whether there is
   * unsaved work.
   */
  const unsavedSketchRef = useRef(false);
  /**
   * Is the browser actually holding the draft? `writeSketchDraft` reports it
   * rather than swallowing it, because the middle rung of the exit prompt
   * PROMISES the entities come back — and a promise storage quietly declined to
   * keep (quota, private mode) would be a new ambiguous exit inside the fix for
   * ambiguous exits. When this is false the prompt says so instead.
   */
  const [draftHeld, setDraftHeld] = useState(true);
  const [restoredDraft, setRestoredDraft] = useState<{
    entities: number;
    savedAt: number;
  } | null>(null);
  const [leaveSaving, setLeaveSaving] = useState(false);

  /**
   * Which part this page last looked for a draft under. Not a boolean: it has
   * to detect the route swapping parts beneath one mounted page, and it is what
   * lets the mirror below know the restore has already had its look.
   *
   * NOTE it deliberately does NOT gate the restore itself. StrictMode mounts,
   * tears down and re-mounts every effect in dev, and the workspace's own
   * `exit()`-on-unmount cleanup fires in that teardown — so a restore that
   * refused to run twice restored the buffer, watched it be wiped, and then
   * declined to put it back. Measured: the "Draft restored" note appeared over
   * an empty part, which is the worst of both answers.
   */
  const restoreCheckedFor = useRef<string | null>(null);

  /**
   * RESTORE ON RE-ENTRY, AND IT MUST RUN BEFORE THE MIRROR BELOW. A draft only
   * exists while there is work outside the part, so finding one means the last
   * session ended without saving — by Back, by the breadcrumb, or by the tab
   * dying.
   *
   * The ordering is not a style choice and it is stated twice on purpose (here,
   * and as the `restoreCheckedFor` gate the mirror reads). On mount the store
   * is at `mode: "off"`, which the mirror correctly reads as "nothing to keep"
   * — so a mirror that ran first would DELETE the very draft this effect is
   * about to load, every single time. Measured: with the two effects the other
   * way round, all three exits prompted correctly and not one of them ever
   * restored anything.
   *
   * `setState` rather than an action because the store has no verb for this:
   * `beginEdit` re-opens a sketch that is already a FEATURE (it demands an id),
   * and the case that hurts is the buffer that never became one. Writing the
   * fields directly is also the correct history behaviour — a restore is a
   * session STARTING, not an edit, so it must not become an undo step.
   *
   * Every transient field (tool, selection, hint, solve readouts, the undo
   * stacks) is already at its initial value here: reaching the write requires
   * `mode === "off"`, which the store is only ever in via `INITIAL` or
   * `freshSession`. So the payload is all that needs writing.
   */
  useEffect(() => {
    // Swapping parts under one mounted page: whatever is in the store belongs
    // to the part being left, and mirroring it under THIS part's key would file
    // one part's geometry under another part's name.
    const switching =
      restoreCheckedFor.current !== null &&
      restoreCheckedFor.current !== partId;
    if (switching && useSketchStore.getState().mode !== "off") {
      useSketchStore.getState().exit();
    }
    restoreCheckedFor.current = partId;
    setRestoredDraft(null);
    const draft = readSketchDraft(partId);
    if (draft === null) return;
    if (useSketchStore.getState().mode !== "off") return;
    useSketchStore.setState({
      mode: "draw",
      plane: draft.plane,
      entities: draft.entities,
      constraints: draft.constraints,
      featureId: draft.featureId,
      nextIdIndex: draft.nextIdIndex,
      revision: draft.revision,
      userConstrained: draft.userConstrained,
    });
    setRestoredDraft({
      entities: draft.entities.length,
      savedAt: draft.savedAt,
    });
  }, [partId]);

  /**
   * THE MIRROR — the live buffer, kept on disk while it is not in the part.
   * Runs AFTER the restore above; see there for why that is load-bearing.
   */
  useEffect(() => {
    // Never clear a draft the restore has not had its chance to read. The hook
    // order already guarantees this; the gate says so out loud, so a later
    // reshuffle of these effects fails loudly rather than silently eating
    // everybody's in-progress sketches.
    if (restoreCheckedFor.current !== partId) return;
    const state = useSketchStore.getState();
    const plane = state.plane;
    const unsaved =
      state.mode === "draw" &&
      plane !== null &&
      state.entities.length > 0 &&
      (state.featureId === null || state.revision > lastSynced.current);
    unsavedSketchRef.current = unsaved;
    if (!unsaved || plane === null) {
      // Nothing to keep: either the buffer is in the part now (saved) or the
      // user threw it away (the strip's discard). Both are deliberate ends to
      // the session, so the draft goes with them.
      //
      // THE UNMOUNT DISCARD CANNOT REACH HERE, which is the whole reason this
      // is an effect and not a store subscription: leaving the workspace fires
      // `exit()` from a cleanup, and an effect of an unmounting component does
      // not run again. A subscription would see that `exit()`, read it as a
      // discard, and delete the draft at exactly the moment it is needed.
      clearSketchDraft(partId);
      setDraftHeld(true);
      return;
    }
    const held = writeSketchDraft(partId, {
      plane,
      entities: [...state.entities],
      constraints: [...state.constraints],
      featureId: state.featureId,
      nextIdIndex: state.nextIdIndex,
      revision: state.revision,
      userConstrained: state.userConstrained,
    });
    setDraftHeld(held);
  }, [
    partId,
    mode,
    revision,
    featureId,
    entityCount,
    constraintCount,
    // Not read directly — it is the render that a completed save produces, and
    // therefore the only reactive signal that `lastSynced` has moved.
    syncPending,
  ]);

  /** Stable by construction — the router registers the blocker exactly once. */
  const shouldBlockLeave = useCallback(() => unsavedSketchRef.current, []);
  const leaveGuard = useBlocker({
    shouldBlockFn: shouldBlockLeave,
    enableBeforeUnload: shouldBlockLeave,
    withResolver: true,
  });

  /**
   * Where the blocked navigation was heading, in the user's words. The Back
   * button is the exit people press without knowing where it goes, so the
   * prompt says — an unnamed destination is half of what makes an exit
   * ambiguous.
   */
  const leaveDestination = useMemo(() => {
    const path = leaveGuard.next?.pathname ?? "";
    if (path === "/") return "Parts";
    if (path.startsWith("/assemblies")) return "Assemblies";
    if (path.startsWith("/drawings")) return "Drawings";
    if (path.startsWith("/settings")) return "Settings";
    if (path.startsWith("/parts/")) return "another part";
    return "the page you asked for";
  }, [leaveGuard.next]);

  /**
   * The top rung: put the work in the part, then go. The save is the existing
   * exit-after-persist chain, so this cannot drift from what the strip's Save
   * does; the completion is watched below rather than awaited, because
   * `persistBuffer` owns its own serialized chain.
   */
  const saveAndLeave = useCallback(() => {
    setSyncError(null);
    setLeaveSaving(true);
    persistBuffer(true);
  }, [persistBuffer]);

  useEffect(() => {
    if (!leaveSaving) return;
    if (syncError !== null) {
      // No dead end: the prompt stays up wearing the reason, and the other two
      // rungs still work — the draft has the entities either way.
      setLeaveSaving(false);
      return;
    }
    if (mode === "off" && leaveGuard.status === "blocked") {
      setLeaveSaving(false);
      leaveGuard.proceed();
    }
  }, [leaveSaving, mode, syncError, leaveGuard]);

  // The live loop: debounce-save every edit once constraints exist or the
  // sketch is bound. Plain entity drawing before the first save stays local
  // (the explicit SAVE action owns that moment).
  useEffect(() => {
    if (mode !== "draw") return;
    if (revision === 0 || revision <= lastSynced.current) return;
    if (revision === failedRevision.current) return; // next edit retries
    if (featureId === null && !userConstrained) return;
    const timer = window.setTimeout(
      () => persistBuffer(false),
      SYNC_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [mode, revision, featureId, userConstrained, syncPending, persistBuffer]);

  // Feed the solve back in: adopt solved positions + diagnosis for the
  // bound feature (only when the buffer is clean — indices and positions
  // must refer to what was actually solved).
  useEffect(() => {
    if (mode !== "draw" || featureId === null || evaluation.data === undefined)
      return;
    const store = useSketchStore.getState();
    const clean =
      store.revision <= lastSynced.current && inFlight.current === 0;
    if (!clean) return;
    const result = evaluation.data.features.find(
      (f) => f.feature_id === featureId,
    );
    if (result === undefined) return;
    if (result.status === "ok" && result.data?.kind === "solved_sketch") {
      const info: SolveInfo = {
        status: result.data.status,
        dof: result.data.dof ?? null,
        conflicting: result.data.conflicting_constraints ?? [],
        redundant: result.data.redundant_constraints ?? [],
      };
      // The per-dimension readouts line each glyph up with its authored
      // constraint (a driving dim's evaluated value / a driven dim's measured).
      // BOTH lists, always: the solver reports linear and angular separately so
      // no consumer can read a degree out of `value_mm`, and passing only the
      // linear half is QA-R2 — an expression-driven angle whose glyph kept the
      // placeholder 30 while the model moved to 45.
      store.adoptSolved(
        result.data.entities,
        info,
        result.data.dimensions ?? [],
        result.data.angles ?? [],
        // Which projected entities followed their edge, and which went sick.
        result.data.projections ?? [],
      );
      return;
    }
    if (result.status === "error" && result.error != null) {
      // A bad expression / cycle / unknown-or-driven ref / div-by-zero comes
      // back as `sketch_invalid` — surface the server's message in the
      // diagnostic stamp (never swallow it), keeping the last-good geometry.
      // A formula over the part's parameters that no longer resolves (a name
      // gone, a value out of range) is the sketch's `input_error`
      // (SKETCH-STAMP-UNRESOLVED) and takes the same stamp, in the field's
      // words.
      if (
        result.error.code === "sketch_invalid" ||
        INPUT_ERROR_CODES.has(result.error.code)
      ) {
        store.adoptSolved(null, {
          status: "invalid",
          dof: null,
          conflicting: [],
          redundant: [],
          message:
            result.error.code === "sketch_invalid"
              ? result.error.message
              : describeInputError(result.error.message),
        });
        return;
      }
      if (result.error.code === "sketch_conflicting") {
        // BACKLOG #6: read the offending ids from the TYPED diagnosis, not by
        // regex-parsing the human message (brittle, now removed).
        const diag = result.error.sketch_diagnosis;
        store.adoptSolved(null, {
          status: "conflicting",
          dof: null,
          conflicting: diag?.conflicting_constraints ?? [],
          redundant: diag?.redundant_constraints ?? [],
        });
        return;
      }
      if (result.error.code === "sketch_diverged") {
        store.adoptSolved(null, {
          status: "diverged",
          dof: null,
          conflicting: [],
          redundant: [],
        });
      }
    }
  }, [mode, featureId, evaluation.data]);
  return {
    syncPending,
    syncError,
    setSyncError,
    lastSynced,
    failedRevision,
    finishSketch,
    draftHeld,
    restoredDraft,
    setRestoredDraft,
    leaveSaving,
    leaveGuard,
    leaveDestination,
    saveAndLeave,
  };
}

export type SketchPersistence = ReturnType<typeof useSketchPersistence>;
