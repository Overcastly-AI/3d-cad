import { Chip, Panel } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchBodyMesh, MeshNotFoundError } from "../api/mesh";
import { fetchOverlay, measureTargets } from "../api/measure";
import { buildEvaluateTree, buildMeasureRequest } from "../measure/geometry";
import { useMeasureStore } from "../measure/store";
import { MeasureReadout } from "../components/MeasureReadout";
import { MeasureOverlay } from "../viewport/MeasureOverlay";
import {
  type ChamferParams,
  chamferFeatureCreate,
  chamferFeatureUpdate,
  createFeature,
  evaluatePart,
  type ExtrudeParams,
  extrudeFeatureCreate,
  extrudeFeatureUpdate,
  type FeatureCreate,
  type FeatureResponse,
  type FeatureTreeResponse,
  type FeatureUpdate,
  fetchFeatureTree,
  fetchPart,
  type FilletParams,
  filletFeatureCreate,
  filletFeatureUpdate,
  moveRollbackBar,
  type PatternParams,
  patternFeatureCreate,
  patternFeatureUpdate,
  type RevolveParams,
  revolveFeatureCreate,
  revolveFeatureUpdate,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  updateFeature,
} from "../api/parts";
import { BodyInspector, type BodyStatus } from "../components/BodyInspector";
import { ChamferEditor } from "../components/ChamferEditor";
import { CreateStrip } from "../components/CreateStrip";
import { ExtrudeEditor } from "../components/ExtrudeEditor";
import { FeatureTreePanel } from "../components/FeatureTreePanel";
import { FilletEditor } from "../components/FilletEditor";
import { PartExportControls } from "../components/PartExportControls";
import { PatternEditor } from "../components/PatternEditor";
import { RevolveEditor } from "../components/RevolveEditor";
import {
  defaultExtrudeForm,
  defaultProfileId,
  type ExtrudeForm,
  formFromParams,
  profileOptions,
} from "../features/extrude";
import {
  type AxisOption,
  axisOptions,
  defaultAxisId,
  defaultRevolveForm,
  formFromRevolveParams,
  type RevolveForm,
} from "../features/revolve";
import {
  defaultPatternForm,
  formFromPatternParams,
  type PatternForm,
} from "../features/pattern";
import {
  type ChamferForm,
  defaultChamferForm,
  defaultFilletForm,
  type FilletForm,
  formFromChamferParams,
  formFromFilletParams,
} from "../features/modify";
import { SketchDro } from "../components/SketchDro";
import { SketchStrip } from "../components/SketchStrip";
import { SolveDiagnostic } from "../components/SolveDiagnostic";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
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

  const hasBody = body.data !== undefined;

  // ---------------------------------------------------------------------
  // Measurement (inspect mode). The tool fetches the pickable overlay for the
  // current evaluated body, the user picks two vertices/edges, and the second
  // pick calls /measure for the exact nearest distance. State lives in the
  // shared measure store (the in-canvas overlay + the DOM readout both read
  // it); PartPage owns the two network effects and the mode plumbing.
  // ---------------------------------------------------------------------
  const measureActive = useMeasureStore((s) => s.active);
  const measurePicks = useMeasureStore((s) => s.picks);
  const measureResult = useMeasureStore((s) => s.result);
  const measureFailure = useMeasureStore((s) => s.measureError);
  const setMeasureOverlay = useMeasureStore((s) => s.setOverlay);
  const setMeasureOverlayError = useMeasureStore((s) => s.setOverlayError);
  const setMeasureResult = useMeasureStore((s) => s.setResult);
  const setMeasureFailure = useMeasureStore((s) => s.setMeasureError);

  const overlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: measureActive && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (measureActive && overlayQuery.data !== undefined) {
      setMeasureOverlay(overlayQuery.data);
    }
  }, [measureActive, overlayQuery.data, setMeasureOverlay]);

  useEffect(() => {
    if (measureActive && overlayQuery.error) {
      setMeasureOverlayError(
        overlayQuery.error instanceof Error
          ? overlayQuery.error.message
          : "The selection overlay could not be built.",
      );
    }
  }, [measureActive, overlayQuery.error, setMeasureOverlayError]);

  // The second pick resolves the measurement (once, per pair).
  const measureInFlight = useRef(false);
  useEffect(() => {
    if (!measureActive || measurePicks.length !== 2) return;
    if (measureResult !== null || measureFailure !== null) return;
    if (measureInFlight.current || tree.data === undefined) return;
    const currentTree = tree.data;
    const [a, b] = measurePicks;
    if (a === undefined || b === undefined) return;
    measureInFlight.current = true;
    void (async () => {
      try {
        const request = buildMeasureRequest(
          a,
          b,
          buildEvaluateTree(currentTree),
        );
        setMeasureResult(await measureTargets(request));
      } catch (error) {
        setMeasureFailure(
          error instanceof Error
            ? error.message
            : "The measurement could not be computed.",
        );
      } finally {
        measureInFlight.current = false;
      }
    })();
  }, [
    measureActive,
    measurePicks,
    measureResult,
    measureFailure,
    tree.data,
    setMeasureResult,
    setMeasureFailure,
  ]);

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
      if (resolved.type === "construction") {
        store.toggleConstruction();
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

  // Sketch mode owns the viewport — measurement never overlaps it.
  useEffect(() => {
    if (mode !== "off") useMeasureStore.getState().deactivate();
  }, [mode]);
  // Leaving the workspace tears the measurement overlay down.
  useEffect(() => () => useMeasureStore.getState().deactivate(), []);

  // ---------------------------------------------------------------------
  // Extrude authoring + feature-tree interactions. Discrete user actions
  // (not the debounced sketch chain): each reads the freshest tree_version,
  // retries once on a stale-version race, then invalidates the tree + the
  // evaluate so the body updates through the #2 render path.
  // ---------------------------------------------------------------------
  const features = tree.data?.features ?? [];
  const sketchProfiles = useMemo(() => profileOptions(features), [features]);
  // Axis line-entity choices per profile sketch — the revolve editor scopes its
  // axis picker to the selected profile's own lines.
  const axesByProfile = useMemo(() => {
    const map: Record<string, AxisOption[]> = {};
    for (const profile of sketchProfiles) {
      map[profile.id] = axisOptions(features, profile.id);
    }
    return map;
  }, [sketchProfiles, features]);
  // The authoring seat holds one editor at a time — an extrude OR a revolve —
  // so they share the saving/error state and the viewport top-left anchor.
  const [editor, setEditor] = useState<
    | {
        kind: "extrude";
        mode: "create" | "edit";
        initial: ExtrudeForm;
        featureId?: string;
      }
    | {
        kind: "revolve";
        mode: "create" | "edit";
        initial: RevolveForm;
        featureId?: string;
      }
    | {
        kind: "pattern";
        mode: "create" | "edit";
        initial: PatternForm;
        featureId?: string;
      }
    | {
        kind: "fillet";
        mode: "create" | "edit";
        initial: FilletForm;
        featureId?: string;
      }
    | {
        kind: "chamfer";
        mode: "create" | "edit";
        initial: ChamferForm;
        featureId?: string;
      }
    | null
  >(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(
    null,
  );
  const [editorSaving, setEditorSaving] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
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

  /** Enter sketch mode: reset the sync bookkeeping, drop any open editor. */
  const handleNewSketch = useCallback(() => {
    lastSynced.current = 0;
    failedRevision.current = null;
    setSyncError(null);
    setEditor(null);
    setSelectedFeatureId(null);
    useMeasureStore.getState().deactivate();
    begin();
  }, [begin]);

  /** Toggle the Measure tool; arming it drops any open feature editor. */
  const toggleMeasure = useCallback(() => {
    const store = useMeasureStore.getState();
    if (store.active) {
      store.deactivate();
      return;
    }
    setEditor(null);
    setSelectedFeatureId(null);
    store.activate();
  }, []);

  // Measure keyboard path (mode off): M toggles the tool; Escape clears the
  // picks, then exits — the same cascade grammar the sketcher uses.
  useEffect(() => {
    if (mode !== "off") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const store = useMeasureStore.getState();
      if (event.key === "Escape") {
        if (!store.active) return;
        event.preventDefault();
        if (
          store.picks.length > 0 ||
          store.result !== null ||
          store.measureError !== null
        ) {
          store.reset();
        } else {
          store.deactivate();
        }
        return;
      }
      if (event.key.toLowerCase() === "m") {
        event.preventDefault();
        if (store.active) {
          store.deactivate();
        } else if (hasBody) {
          setEditor(null);
          setSelectedFeatureId(null);
          store.activate();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, hasBody]);

  const openCreateExtrude = useCallback(() => {
    const profileId = defaultProfileId(tree.data?.features ?? []);
    if (profileId === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "extrude",
      mode: "create",
      initial: defaultExtrudeForm(profileId),
    });
  }, [tree.data]);

  const openCreateRevolve = useCallback(() => {
    const featureList = tree.data?.features ?? [];
    const profileId = defaultProfileId(featureList);
    if (profileId === "") return;
    const axes = axisOptions(featureList, profileId);
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "revolve",
      mode: "create",
      initial: defaultRevolveForm(profileId, defaultAxisId(axes)),
    });
  }, [tree.data]);

  // A pattern needs no sketch profile — it repeats the current BODY — so it
  // only requires a solid to exist (canModify), unlike extrude/revolve.
  const openCreatePattern = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "pattern",
      mode: "create",
      initial: defaultPatternForm(),
    });
  }, []);

  // Fillet/chamfer, like a pattern, act on the current BODY via a geometric
  // edge-selector predicate (no sketch profile) — they only need a solid to
  // exist (canModify), so they mirror openCreatePattern's guard.
  const openCreateFillet = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({ kind: "fillet", mode: "create", initial: defaultFilletForm() });
  }, []);

  const openCreateChamfer = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "chamfer",
      mode: "create",
      initial: defaultChamferForm(),
    });
  }, []);

  const selectFeature = useCallback((feature: FeatureResponse) => {
    useMeasureStore.getState().deactivate();
    setSelectedFeatureId(feature.id);
    setEditorError(null);
    if (feature.feature.type === "extrude") {
      setEditor({
        kind: "extrude",
        mode: "edit",
        featureId: feature.id,
        initial: formFromParams(feature.feature.params),
      });
    } else if (feature.feature.type === "revolve") {
      setEditor({
        kind: "revolve",
        mode: "edit",
        featureId: feature.id,
        initial: formFromRevolveParams(feature.feature.params),
      });
    } else if (feature.feature.type === "pattern") {
      setEditor({
        kind: "pattern",
        mode: "edit",
        featureId: feature.id,
        initial: formFromPatternParams(feature.feature.params),
      });
    } else if (feature.feature.type === "fillet") {
      setEditor({
        kind: "fillet",
        mode: "edit",
        featureId: feature.id,
        initial: formFromFilletParams(feature.feature.params),
      });
    } else if (feature.feature.type === "chamfer") {
      setEditor({
        kind: "chamfer",
        mode: "edit",
        featureId: feature.id,
        initial: formFromChamferParams(feature.feature.params),
      });
    } else {
      setEditor(null);
    }
  }, []);

  const closeEditor = useCallback(() => {
    setEditor(null);
    setEditorError(null);
  }, []);

  // The shared save path for either body-affecting feature: read the freshest
  // tree_version, retry once on a stale-version race, then invalidate the tree
  // + evaluate + mesh so the body updates through the #2 render path.
  const runFeatureSave = useCallback(
    (
      createEnvelope: (version: number) => FeatureCreate,
      updateEnvelope: (version: number) => FeatureUpdate,
      isCreate: boolean,
      featureId: string | undefined,
      fallbackMessage: string,
    ) => {
      setEditorSaving(true);
      setEditorError(null);
      void (async () => {
        try {
          const attempt = async (version: number) =>
            isCreate
              ? createFeature(partId, createEnvelope(version))
              : updateFeature(
                  partId,
                  featureId as string,
                  updateEnvelope(version),
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
          setEditorError(
            error instanceof Error ? error.message : fallbackMessage,
          );
        } finally {
          setEditorSaving(false);
        }
      })();
    },
    [partId, freshTreeVersion, refreshTreeAndBody],
  );

  const submitExtrude = useCallback(
    (params: ExtrudeParams) => {
      const current = editor;
      if (current === null || current.kind !== "extrude") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "extrude").length + 1;
      runFeatureSave(
        (version) =>
          extrudeFeatureCreate(`Extrude${nextIndex}`, params, version),
        (version) => extrudeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The extrude could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitRevolve = useCallback(
    (params: RevolveParams) => {
      const current = editor;
      if (current === null || current.kind !== "revolve") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "revolve").length + 1;
      runFeatureSave(
        (version) =>
          revolveFeatureCreate(`Revolve${nextIndex}`, params, version),
        (version) => revolveFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The revolve could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitPattern = useCallback(
    (params: PatternParams) => {
      const current = editor;
      if (current === null || current.kind !== "pattern") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "pattern").length + 1;
      runFeatureSave(
        (version) =>
          patternFeatureCreate(`Pattern${nextIndex}`, params, version),
        (version) => patternFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The pattern could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitFillet = useCallback(
    (params: FilletParams) => {
      const current = editor;
      if (current === null || current.kind !== "fillet") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "fillet").length + 1;
      runFeatureSave(
        (version) => filletFeatureCreate(`Fillet${nextIndex}`, params, version),
        (version) => filletFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The fillet could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitChamfer = useCallback(
    (params: ChamferParams) => {
      const current = editor;
      if (current === null || current.kind !== "chamfer") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "chamfer").length + 1;
      runFeatureSave(
        (version) =>
          chamferFeatureCreate(`Chamfer${nextIndex}`, params, version),
        (version) => chamferFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The chamfer could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const moveRollback = useCallback(
    (rollbackFeatureId: string | null) => {
      // Moving the bar rebuilds the body → the measure overlay refetches
      // against a different tree version; disarm the tool so a mid-measure
      // rollback can never resolve a stale pick index (matches every other
      // tree-mutating path: openCreate*, selectFeature, handleNewSketch).
      useMeasureStore.getState().deactivate();
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

  // A solved sketch must exist before an extrude or revolve can consume one.
  const hasSolvedSketch =
    sketchProfiles.length > 0 &&
    (evaluation.data?.features.some(
      (f) => f.status === "ok" && f.data?.kind === "solved_sketch",
    ) ??
      false);

  // Sketch mode owns the viewport; leaving/entering it dismisses the editor.
  useEffect(() => {
    if (mode !== "off") setEditor(null);
  }, [mode]);

  // Modify accelerator: P adds a pattern to the current body (mode off, a body
  // exists) — the same guard grammar as the Measure M accelerator.
  useEffect(() => {
    if (mode !== "off") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key.toLowerCase() !== "p" || !hasBody) return;
      event.preventDefault();
      openCreatePattern();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, hasBody, openCreatePattern]);

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
  // With a tree but no body (sketch-only / rolled back before the extrude),
  // still offer the EXPORT strip — disabled and honest about why.
  const showExportOnly =
    mode === "off" &&
    bodyProperties === null &&
    (tree.data?.features.length ?? 0) > 0;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="part-name">{part.data?.name ?? "Part"}</Chip>
      </TopBar>
      {/* The full-width command band, directly under the brand bar: the
          mode-aware CAD top-toolbar. Sketch tools while sketching, the
          feature-create tools otherwise — one edge-to-edge surface, the
          viewport below it. */}
      <TopToolbar>
        {mode === "off" ? (
          <CreateStrip
            treeReady={tree.data !== undefined}
            onNewSketch={handleNewSketch}
            canExtrude={hasSolvedSketch}
            onNewExtrude={openCreateExtrude}
            canRevolve={hasSolvedSketch}
            onNewRevolve={openCreateRevolve}
            canModify={hasBody}
            onFillet={openCreateFillet}
            onChamfer={openCreateChamfer}
            onPattern={openCreatePattern}
            canMeasure={hasBody}
            measuring={measureActive}
            onToggleMeasure={toggleMeasure}
          />
        ) : (
          <SketchStrip
            onSave={finishSketch}
            saving={syncPending}
            saveError={syncError}
          />
        )}
      </TopToolbar>
      <main className="flex min-h-0 grow flex-col md:flex-row">
        <FeatureTreePanel
          tree={tree.data}
          treeError={tree.error}
          evaluation={evaluation.data}
          evaluating={evaluation.isFetching}
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
              <SketchDro solving={syncPending || evaluation.isFetching} />
              <SolveDiagnostic />
              <MeasureReadout />
              {mode === "off" && editor !== null ? (
                editor.kind === "extrude" ? (
                  <ExtrudeEditor
                    mode={editor.mode}
                    profiles={sketchProfiles}
                    initial={editor.initial}
                    onSubmit={submitExtrude}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "revolve" ? (
                  <RevolveEditor
                    mode={editor.mode}
                    profiles={sketchProfiles}
                    axesByProfile={axesByProfile}
                    initial={editor.initial}
                    onSubmit={submitRevolve}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "pattern" ? (
                  <PatternEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    onSubmit={submitPattern}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "fillet" ? (
                  <FilletEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    onSubmit={submitFillet}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : (
                  <ChamferEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    onSubmit={submitChamfer}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                )
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
          <MeasureOverlay />
        </Viewport>
        {showInspector ? (
          <BodyInspector
            properties={bodyProperties}
            status={bodyStatus}
            partId={partId}
          />
        ) : showExportOnly ? (
          // No body yet (a sketch-only or rolled-back tree), but the part is
          // modeled enough to have a tree — offer the EXPORT strip in its
          // honest disabled state so the affordance is discoverable.
          <aside
            className="w-full shrink-0 p-3 md:w-inspector"
            aria-label="Part export"
            data-testid="part-export-idle"
          >
            <Panel>
              <PartExportControls partId={partId} hasBody={false} />
            </Panel>
          </aside>
        ) : null}
      </main>
    </div>
  );
}
