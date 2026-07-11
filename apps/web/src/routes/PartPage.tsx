import { Chip } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchBodyMesh, MeshNotFoundError } from "../api/mesh";
import {
  createFeature,
  evaluatePart,
  extrudeFeatureCreate,
  extrudeFeatureUpdate,
  type FeatureResponse,
  fetchFeatureTree,
  fetchPart,
  moveRollbackBar,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  updateFeature,
} from "../api/parts";
import { BodyInspector, type BodyStatus } from "../components/BodyInspector";
import { ExtrudeEditor } from "../components/ExtrudeEditor";
import { FeatureTreePanel } from "../components/FeatureTreePanel";
import {
  defaultExtrudeForm,
  defaultProfileId,
  type ExtrudeForm,
  formFromParams,
  profileOptions,
} from "../features/extrude";
import { SketchDro } from "../components/SketchDro";
import { SketchStrip } from "../components/SketchStrip";
import { SolveDiagnostic } from "../components/SolveDiagnostic";
import { TopBar } from "../components/TopBar";
import {
  parseConflictIndices,
  resolveSketchKey,
  type SolveInfo,
} from "../sketch/constraints";
import { useSketchStore } from "../sketch/store";
import { escapeAction, TOOL_SHORTCUTS } from "../sketch/tools";
import { partRoute } from "../router";
import { SketchScene, type SolvedSketchLayer } from "../viewport/SketchScene";
import { Viewport } from "../viewport/Viewport";

/** Constraint/dimension edits persist after this quiet gap (the live loop). */
const SYNC_DEBOUNCE_MS = 400;

/** True for keystrokes that belong to a focused text control, not to us. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

/**
 * The part workspace: feature tree left, viewport hero, sketch mode inside
 * the viewport. Solved geometry ALWAYS comes from the evaluate payload —
 * the sketcher renders what the solver says, never its own input echo. The
 * live parametric loop: the first constraint action persists the sketch as
 * a feature; every edit after that debounce-saves, re-evaluates, and the
 * solved positions are adopted back into the buffer.
 */
export function PartPage() {
  const { partId } = partRoute.useParams();
  const queryClient = useQueryClient();

  const mode = useSketchStore((state) => state.mode);
  const revision = useSketchStore((state) => state.revision);
  const featureId = useSketchStore((state) => state.featureId);
  const constraintCount = useSketchStore((state) => state.constraints.length);
  const begin = useSketchStore((state) => state.begin);
  const setTool = useSketchStore((state) => state.setTool);
  const toggleSnap = useSketchStore((state) => state.toggleSnap);

  const part = useQuery({
    queryKey: ["part", partId],
    queryFn: () => fetchPart(partId),
    staleTime: Infinity,
  });
  const tree = useQuery({
    queryKey: ["features", partId],
    queryFn: () => fetchFeatureTree(partId),
  });
  const treeVersion = tree.data?.tree_version;
  const evaluation = useQuery({
    queryKey: ["evaluate", partId, treeVersion],
    queryFn: () => evaluatePart(partId),
    enabled: tree.data !== undefined && tree.data.features.length > 0,
    staleTime: Infinity,
  });

  // ---------------------------------------------------------------------
  // The body: a body-affecting feature (extrude) evaluates to a content-
  // addressed GLB. Fetch it through the gateway mesh proxy and render it in
  // the same GLB→mesh pipeline first light uses. `mesh_glb_id: null` means no
  // body yet — the sketch renders alone, no error.
  // ---------------------------------------------------------------------
  const meshGlbId = evaluation.data?.mesh_glb_id ?? null;
  const bodyProperties = evaluation.data?.properties ?? null;
  const body = useQuery({
    queryKey: ["mesh", partId, meshGlbId],
    queryFn: () => fetchBodyMesh(meshGlbId as string),
    enabled: meshGlbId !== null,
    staleTime: Infinity, // content-addressed: the bytes never change per id
    retry: (count, error) => !(error instanceof MeshNotFoundError) && count < 2,
  });

  // Honest failure (§7.8): a `mesh_not_found` 404 means the LRU evicted the
  // artifact — re-evaluate to regenerate it, then refetch. Guarded per content
  // address so a genuinely unservable body surfaces an error, never a loop.
  const regeneratedFor = useRef<Set<string>>(new Set());
  const [regenerating, setRegenerating] = useState(false);
  const [regenFailed, setRegenFailed] = useState(false);
  useEffect(() => {
    if (!(body.error instanceof MeshNotFoundError) || meshGlbId === null) {
      return;
    }
    if (regeneratedFor.current.has(meshGlbId)) {
      setRegenerating(false);
      setRegenFailed(true);
      return;
    }
    regeneratedFor.current.add(meshGlbId);
    setRegenFailed(false);
    setRegenerating(true);
    let cancelled = false;
    void (async () => {
      await queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
      await queryClient.invalidateQueries({ queryKey: ["mesh", partId] });
      if (!cancelled) setRegenerating(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [body.error, meshGlbId, partId, queryClient]);

  const retryBody = useCallback(() => {
    regeneratedFor.current.clear();
    setRegenFailed(false);
    void queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
    void queryClient.invalidateQueries({ queryKey: ["mesh", partId] });
  }, [partId, queryClient]);

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
      const sketchCount = (tree.data?.features ?? []).filter(
        (f) => f.feature.type === "sketch",
      ).length;
      inFlight.current += 1;
      setSyncPending(true);
      chain.current = chain.current.then(async () => {
        const attempt = (version: number) =>
          payload.featureId === null
            ? createFeature(
                partId,
                sketchFeatureCreate(
                  `Sketch${sketchCount + 1}`,
                  payload.plane,
                  payload.entities,
                  payload.constraints,
                  version,
                ),
              )
            : updateFeature(
                partId,
                payload.featureId,
                sketchFeatureUpdate(
                  payload.plane,
                  payload.entities,
                  payload.constraints,
                  version,
                ),
              );
        try {
          let response;
          try {
            response = await attempt(
              treeVersionRef.current ??
                (await fetchFeatureTree(partId)).tree_version,
            );
          } catch {
            // Stale tree version (or a hiccup): refetch, retry once.
            response = await attempt(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          treeVersionRef.current = response.tree_version;
          lastSynced.current = Math.max(lastSynced.current, payload.revision);
          failedRevision.current = null;
          setSyncError(null);
          const now = useSketchStore.getState();
          if (now.mode === "draw") {
            if (exitAfter) now.exit();
            else if (now.featureId === null) now.bind(response.feature.id);
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
        } finally {
          inFlight.current -= 1;
          if (inFlight.current === 0) setSyncPending(false);
        }
      });
    },
    [partId, queryClient, tree.data],
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

  // The live loop: debounce-save every edit once constraints exist or the
  // sketch is bound. Plain entity drawing before the first save stays local
  // (the explicit SAVE action owns that moment).
  useEffect(() => {
    if (mode !== "draw") return;
    if (revision === 0 || revision <= lastSynced.current) return;
    if (revision === failedRevision.current) return; // next edit retries
    if (featureId === null && constraintCount === 0) return;
    const timer = window.setTimeout(
      () => persistBuffer(false),
      SYNC_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [mode, revision, featureId, constraintCount, syncPending, persistBuffer]);

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
      store.adoptSolved(result.data.entities, info);
      return;
    }
    if (result.status === "error" && result.error != null) {
      if (result.error.code === "sketch_conflicting") {
        store.adoptSolved(null, {
          status: "conflicting",
          dof: null,
          conflicting: parseConflictIndices(result.error.message),
          redundant: [],
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

  /** Solved sketch layers: tree feature (plane) × evaluate result (geometry). */
  const solved = useMemo<SolvedSketchLayer[]>(() => {
    if (tree.data === undefined || evaluation.data === undefined) return [];
    const results = new Map(
      evaluation.data.features.map((f) => [f.feature_id, f]),
    );
    const layers: SolvedSketchLayer[] = [];
    for (const feature of tree.data.features) {
      if (feature.feature.type !== "sketch") continue;
      // The bound feature renders through the live draw layer while
      // sketching — never twice.
      if (mode === "draw" && feature.id === featureId) continue;
      const plane = feature.feature.params.plane;
      if (plane.kind !== "datum_plane") continue; // v1: datum planes only
      const result = results.get(feature.id);
      if (result?.status !== "ok" || result.data?.kind !== "solved_sketch") {
        continue;
      }
      layers.push({
        featureId: feature.id,
        plane: plane.plane,
        entities: result.data.entities,
      });
    }
    return layers;
  }, [tree.data, evaluation.data, mode, featureId]);

  // Keyboard-first: Escape cascade always; tools, snap, constraint verbs and
  // Delete while drawing. One keyboard, two vocabularies — selection
  // presence decides whether letters draw or constrain.
  useEffect(() => {
    if (mode === "off") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const store = useSketchStore.getState();
      if (event.key === "Escape") {
        event.preventDefault();
        const action = escapeAction(
          store.tool,
          store.pending.length,
          store.selection.length > 0 || store.selectedConstraint !== null,
          store.dimensionEdit !== null,
        );
        if (action === "exit") finishSketch();
        else store.escape();
        return;
      }
      if (mode !== "draw") return;
      if (event.key === "Delete" || event.key === "Backspace") {
        if (store.selectedConstraint !== null) {
          event.preventDefault();
          store.removeConstraint(store.selectedConstraint);
        }
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "g") {
        event.preventDefault();
        toggleSnap();
        return;
      }
      const resolved = resolveSketchKey(key, store.selection.length > 0);
      if (resolved === null) return;
      event.preventDefault();
      if (resolved.type === "constraint") {
        store.applyConstraint(resolved.action);
        return;
      }
      const tool = TOOL_SHORTCUTS[key];
      if (tool !== undefined) setTool(tool);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, finishSketch, setTool, toggleSnap]);

  // Leaving the workspace always leaves sketch mode.
  useEffect(() => () => useSketchStore.getState().exit(), []);

  // ---------------------------------------------------------------------
  // Extrude authoring + feature-tree interactions. Discrete user actions
  // (not the debounced sketch chain): each reads the freshest tree_version,
  // retries once on a stale-version race, then invalidates the tree + the
  // evaluate so the body updates through the #2 render path.
  // ---------------------------------------------------------------------
  const features = tree.data?.features ?? [];
  const sketchProfiles = useMemo(() => profileOptions(features), [features]);
  const [editor, setEditor] = useState<{
    mode: "create" | "edit";
    initial: ExtrudeForm;
    featureId?: string;
  } | null>(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(
    null,
  );
  const [extrudeSaving, setExtrudeSaving] = useState(false);
  const [extrudeError, setExtrudeError] = useState<string | null>(null);
  const [rollbackBusy, setRollbackBusy] = useState(false);

  /** Latest tree version, refetched if the query has none yet. */
  const freshTreeVersion = useCallback(async (): Promise<number> => {
    if (tree.data !== undefined) return tree.data.tree_version;
    return (await fetchFeatureTree(partId)).tree_version;
  }, [partId, tree.data]);

  const refreshTreeAndBody = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["features", partId] });
    await queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
    await queryClient.invalidateQueries({ queryKey: ["mesh", partId] });
  }, [partId, queryClient]);

  const openCreateExtrude = useCallback(() => {
    const profileId = defaultProfileId(tree.data?.features ?? []);
    if (profileId === "") return;
    setExtrudeError(null);
    setSelectedFeatureId(null);
    setEditor({ mode: "create", initial: defaultExtrudeForm(profileId) });
  }, [tree.data]);

  const selectFeature = useCallback((feature: FeatureResponse) => {
    setSelectedFeatureId(feature.id);
    if (feature.feature.type === "extrude") {
      setExtrudeError(null);
      setEditor({
        mode: "edit",
        featureId: feature.id,
        initial: formFromParams(feature.feature.params),
      });
    } else {
      setEditor(null);
    }
  }, []);

  const closeEditor = useCallback(() => {
    setEditor(null);
    setExtrudeError(null);
  }, []);

  const submitExtrude = useCallback(
    (params: Parameters<typeof extrudeFeatureCreate>[1]) => {
      const current = editor;
      if (current === null) return;
      setExtrudeSaving(true);
      setExtrudeError(null);
      void (async () => {
        try {
          const attempt = async (version: number) =>
            current.mode === "create"
              ? createFeature(
                  partId,
                  extrudeFeatureCreate(
                    `Extrude${
                      (tree.data?.features ?? []).filter(
                        (f) => f.feature.type === "extrude",
                      ).length + 1
                    }`,
                    params,
                    version,
                  ),
                )
              : updateFeature(
                  partId,
                  current.featureId as string,
                  extrudeFeatureUpdate(params, version),
                );
          let response;
          try {
            response = await attempt(await freshTreeVersion());
          } catch {
            response = await attempt(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          setSelectedFeatureId(response.feature.id);
          setEditor(null);
          await refreshTreeAndBody();
        } catch (error) {
          setExtrudeError(
            error instanceof Error
              ? error.message
              : "The extrude could not be saved.",
          );
        } finally {
          setExtrudeSaving(false);
        }
      })();
    },
    [editor, partId, tree.data, freshTreeVersion, refreshTreeAndBody],
  );

  const moveRollback = useCallback(
    (rollbackFeatureId: string | null) => {
      setRollbackBusy(true);
      void (async () => {
        try {
          const run = async (version: number) =>
            moveRollbackBar(partId, rollbackFeatureId, version);
          try {
            await run(await freshTreeVersion());
          } catch {
            await run((await fetchFeatureTree(partId)).tree_version);
          }
          await refreshTreeAndBody();
        } finally {
          setRollbackBusy(false);
        }
      })();
    },
    [partId, freshTreeVersion, refreshTreeAndBody],
  );

  // A solved sketch must exist before an extrude can consume one.
  const canExtrude =
    sketchProfiles.length > 0 &&
    (evaluation.data?.features.some(
      (f) => f.status === "ok" && f.data?.kind === "solved_sketch",
    ) ??
      false);

  // Sketch mode owns the viewport; leaving/entering it dismisses the editor.
  useEffect(() => {
    if (mode !== "off") setEditor(null);
  }, [mode]);

  // The body is the hero: once a solid renders, the profile sketch that
  // defined it recedes (it sits on the body's base face — coincident scribe
  // ink would only z-fight the solid). It returns, live, on sketch re-entry.
  const bodyPresent = body.data !== undefined;
  const solvedLayers = bodyPresent ? [] : solved;
  const bodyStatus: BodyStatus = regenFailed
    ? "error"
    : regenerating || (meshGlbId !== null && !bodyPresent && body.isFetching)
      ? "regenerating"
      : evaluation.isFetching
        ? "evaluating"
        : "up-to-date";
  // The inspector appears when there's a body to inspect and we're not
  // sketching — sketch mode keeps the viewport dominant (chrome recedes).
  const showInspector = mode === "off" && bodyProperties !== null;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="part-name">{part.data?.name ?? "Part"}</Chip>
      </TopBar>
      <main className="flex min-h-0 grow flex-col md:flex-row">
        <FeatureTreePanel
          tree={tree.data}
          treeError={tree.error}
          evaluation={evaluation.data}
          evaluating={evaluation.isFetching}
          sketchActive={mode !== "off"}
          onNewSketch={() => {
            lastSynced.current = 0;
            failedRevision.current = null;
            setSyncError(null);
            setEditor(null);
            setSelectedFeatureId(null);
            begin();
          }}
          canExtrude={canExtrude}
          onNewExtrude={openCreateExtrude}
          selectedFeatureId={selectedFeatureId}
          onSelectFeature={selectFeature}
          onMoveRollback={moveRollback}
          rollbackBusy={rollbackBusy}
        />
        <Viewport
          glb={body.data}
          rotateEnabled={mode !== "draw"}
          groundGrid={mode !== "draw"}
          hud={
            <>
              <SketchStrip
                onSave={finishSketch}
                saving={syncPending}
                saveError={syncError}
              />
              <SketchDro solving={syncPending || evaluation.isFetching} />
              <SolveDiagnostic />
              {mode === "off" && editor !== null ? (
                <ExtrudeEditor
                  mode={editor.mode}
                  profiles={sketchProfiles}
                  initial={editor.initial}
                  onSubmit={submitExtrude}
                  onCancel={closeEditor}
                  saving={extrudeSaving}
                  error={extrudeError}
                />
              ) : null}
              {regenerating ? (
                <div
                  role="status"
                  data-testid="body-regenerating"
                  className="absolute left-3 top-3 rounded-sm border border-hairline bg-anvil px-3 py-2"
                >
                  <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
                    Regenerating body
                  </span>
                  <span className="mt-1 block font-body text-xs text-mist">
                    The mesh expired from the cache — re-evaluating the tree.
                  </span>
                </div>
              ) : regenFailed ? (
                <div
                  role="alert"
                  data-testid="body-regen-failed"
                  className="absolute left-3 top-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
                >
                  <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                    Body unavailable
                  </span>
                  <span className="mt-1 block font-body text-xs text-mist">
                    The body mesh could not be regenerated.
                  </span>
                  <button
                    type="button"
                    onClick={retryBody}
                    className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                  >
                    Re-evaluate
                  </button>
                </div>
              ) : null}
            </>
          }
        >
          <SketchScene solved={solvedLayers} />
        </Viewport>
        {showInspector ? (
          <BodyInspector properties={bodyProperties} status={bodyStatus} />
        ) : null}
      </main>
    </div>
  );
}
