import { Chip } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createFeature,
  evaluatePart,
  fetchFeatureTree,
  fetchPart,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  updateFeature,
} from "../api/parts";
import { FeatureTreePanel } from "../components/FeatureTreePanel";
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
            begin();
          }}
        />
        <Viewport
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
            </>
          }
        >
          <SketchScene solved={solved} />
        </Viewport>
      </main>
    </div>
  );
}
