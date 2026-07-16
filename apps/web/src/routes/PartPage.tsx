import { Panel } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchBodyMesh, MeshNotFoundError } from "../api/mesh";
import { fetchOverlay, measureTargets } from "../api/measure";
import {
  cornerSketch,
  editSketch,
  mirrorSketch,
  offsetSketch,
  SketchEditError,
} from "../api/sketchEdit";
import { buildEvaluateTree, buildMeasureRequest } from "../measure/geometry";
import { useMeasureStore } from "../measure/store";
import { MeasureReadout } from "../components/MeasureReadout";
import { MeasureOverlay } from "../viewport/MeasureOverlay";
import {
  type ChamferParams,
  chamferFeatureCreate,
  chamferFeatureUpdate,
  createFeature,
  type DatumParams,
  datumFeatureCreate,
  datumFeatureUpdate,
  datumOnFaceFeatureCreate,
  type DraftParams,
  draftFeatureCreate,
  draftFeatureUpdate,
  type EdgeSignature,
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
  importStep,
  type OverlayFace,
  type PlanarFaceSignature,
  type FilletParams,
  filletFeatureCreate,
  filletFeatureUpdate,
  type LoftParams,
  loftFeatureCreate,
  loftFeatureUpdate,
  moveRollbackBar,
  type PatternParams,
  patternFeatureCreate,
  patternFeatureUpdate,
  type RevolveParams,
  revolveFeatureCreate,
  revolveFeatureUpdate,
  type ShellParams,
  shellFeatureCreate,
  shellFeatureUpdate,
  type SweepParams,
  sweepFeatureCreate,
  sweepFeatureUpdate,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  updateFeature,
} from "../api/parts";
import { BodyInspector, type BodyStatus } from "../components/BodyInspector";
import { Breadcrumb } from "../components/Breadcrumb";
import { ChamferEditor } from "../components/ChamferEditor";
import { CreateStrip } from "../components/CreateStrip";
import { FloatingPanel } from "../components/FloatingPanel";
import { DatumEditor } from "../components/DatumEditor";
import { DraftEditor } from "../components/DraftEditor";
import { ExtrudeEditor } from "../components/ExtrudeEditor";
import { FeatureTreePanel } from "../components/FeatureTreePanel";
import { FilletEditor } from "../components/FilletEditor";
import { LoftEditor } from "../components/LoftEditor";
import { PartExportControls } from "../components/PartExportControls";
import { PatternEditor } from "../components/PatternEditor";
import { RevolveEditor } from "../components/RevolveEditor";
import { ShellEditor } from "../components/ShellEditor";
import { SweepEditor } from "../components/SweepEditor";
import {
  defaultDatumForm,
  type DatumForm,
  formFromDatumParams,
} from "../features/datum";
import {
  defaultExtrudeForm,
  defaultProfileId,
  type ExtrudeForm,
  formFromParams,
  profileOptions,
} from "../features/extrude";
import { precheckStepFile, stepFeatureName } from "../features/import";
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
  defaultSweepForm,
  defaultSweepPathId,
  defaultSweepProfileId,
  formFromSweepParams,
  pathOptions,
  type ProfileOption,
  type SweepForm,
} from "../features/sweep";
import {
  defaultLoftForm,
  defaultLoftSections,
  formFromLoftParams,
  type LoftForm,
} from "../features/loft";
import {
  type ChamferForm,
  defaultChamferForm,
  defaultFilletForm,
  type FilletForm,
  formFromChamferParams,
  formFromFilletParams,
  pickedFromChamferParams,
  pickedFromFilletParams,
} from "../features/modify";
import { useEdgePickStore } from "../features/edgePickStore";
import { EdgePickOverlay } from "../viewport/EdgePickOverlay";
import {
  defaultShellForm,
  type ShellForm,
  formFromShellParams,
  pickedFacesFromShellParams,
} from "../features/shell";
import {
  defaultDraftForm,
  type DraftForm,
  formFromDraftParams,
  pickedFacesFromDraftParams,
} from "../features/draft";
import { useFacePickStore } from "../features/facePickStore";
import { ShellFaceOverlay } from "../viewport/ShellFaceOverlay";
import { SketchDro } from "../components/SketchDro";
import { SketchStrip } from "../components/SketchStrip";
import { SolveDiagnostic } from "../components/SolveDiagnostic";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import { resolveSketchKey, type SolveInfo } from "../sketch/constraints";
import {
  faceSpecFromDatum,
  offsetBasis,
  offsetSpecFromDatum,
  originBasis,
  planeRefFromSpec,
  type PlaneBasis,
} from "../sketch/plane";
import { lastBodyFeatureId, onFaceDatumParams } from "../features/face";
import { isTypingTarget } from "../lib/isTypingTarget";
import { FacePickOverlay } from "../viewport/FacePickOverlay";
import { useSketchStore } from "../sketch/store";
import { escapeAction, TOOL_SHORTCUTS } from "../sketch/tools";
import { partRoute } from "../router";
import { SketchScene, type SolvedSketchLayer } from "../viewport/SketchScene";
import { Viewport } from "../viewport/Viewport";

/** Constraint/dimension edits persist after this quiet gap (the live loop). */
const SYNC_DEBOUNCE_MS = 400;

/** Editor kind → the command name shown in the breadcrumb + band lock reason. */
const COMMAND_LABEL: Record<string, string> = {
  extrude: "Extrude",
  revolve: "Revolve",
  sweep: "Sweep",
  loft: "Loft",
  pattern: "Pattern",
  fillet: "Fillet",
  chamfer: "Chamfer",
  shell: "Shell",
  draft: "Draft",
  datum: "Datum plane",
};

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
  const edit = useSketchStore((state) => state.edit);
  const offset = useSketchStore((state) => state.offset);
  const mirrorRequest = useSketchStore((state) => state.mirrorRequest);
  const cornerRequest = useSketchStore((state) => state.cornerRequest);
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

  // Face-pick (the plane-pick "Pick a face" path): arm → highlight the body's
  // planar faces → click one → author an on_face datum → seat the sketch.
  // Declared up here because the sketch keyboard effect (Escape cancels the
  // pick) reads `facePicking`.
  const [facePicking, setFacePicking] = useState(false);
  const [facePlaneBusy, setFacePlaneBusy] = useState(false);
  const [facePlaneError, setFacePlaneError] = useState<string | null>(null);
  const [pendingFaceIndex, setPendingFaceIndex] = useState<number | null>(null);

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
      chain.current = chain.current.then(async () => {
        const planeRef = planeRefFromSpec(payload.plane);
        // Default sketch name numbers off the FRESHEST tree, never a stale query
        // — so the first sketch is "Sketch1", the next "Sketch2", never a dupe.
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
        try {
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
        } finally {
          if (isCreate) {
            creatingRef.current = false;
            pendingExitRef.current = false;
          }
          inFlight.current -= 1;
          if (inFlight.current === 0) setSyncPending(false);
        }
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
      // The per-dimension readouts line each glyph up with its authored
      // constraint (a driving dim's evaluated value / a driven dim's measured).
      store.adoptSolved(
        result.data.entities,
        info,
        result.data.dimensions ?? [],
      );
      return;
    }
    if (result.status === "error" && result.error != null) {
      // A bad expression / cycle / unknown-or-driven ref / div-by-zero comes
      // back as `sketch_invalid` — surface the server's message in the
      // diagnostic stamp (never swallow it), keeping the last-good geometry.
      if (result.error.code === "sketch_invalid") {
        store.adoptSolved(null, {
          status: "invalid",
          dof: null,
          conflicting: [],
          redundant: [],
          message: result.error.message,
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

  /** Datum feature params by id — the sketch→datum plane resolution table. */
  const datumParamsById = useMemo(() => {
    const map = new Map<string, DatumParams>();
    for (const feature of tree.data?.features ?? []) {
      // Offset datums drive client-side plane preview math; on-face datums
      // resolve against the body server-side (the later face-picker slice).
      if (
        feature.feature.type === "datum" &&
        feature.feature.params.kind === "offset"
      ) {
        map.set(feature.id, feature.feature.params);
      }
    }
    return map;
  }, [tree.data]);

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
      // Resolve the plane ref to a placed basis: an origin datum draws at the
      // world frame; a datum FeatureRef draws at that datum's offset (so a
      // sketch on XY+30 renders its solved ink at z=30). Mirrors the kernel's
      // resolve_sketch_plane so overlay + body agree.
      const plane = feature.feature.params.plane;
      let basis: PlaneBasis | null = null;
      if (plane.kind === "datum_plane") {
        basis = originBasis(plane.plane);
      } else {
        const datum = datumParamsById.get(plane.feature_id);
        if (datum !== undefined) {
          basis = offsetBasis(datum.base, datum.offset_mm, datum.flip);
        }
      }
      if (basis === null) continue; // unresolved plane (rolled back / deleted)
      const result = results.get(feature.id);
      if (result?.status !== "ok" || result.data?.kind !== "solved_sketch") {
        continue;
      }
      layers.push({
        featureId: feature.id,
        basis,
        entities: result.data.entities,
      });
    }
    return layers;
  }, [tree.data, evaluation.data, mode, featureId, datumParamsById]);

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
        // Face-pick has its own most-local cancel: disarm the mode, staying in
        // the plane-pick step (a second Escape then exits the sketch).
        if (facePicking) {
          setFacePicking(false);
          setFacePlaneError(null);
          return;
        }
        // Mirror and the corner tools run their own cascades (mirror: axis →
        // targets → drop tool; corner: close editor / clear picks → drop tool)
        // and never exit the sketch mid-flow.
        if (store.mirror !== null || store.corner !== null) {
          store.escape();
          return;
        }
        const action = escapeAction(
          store.tool,
          store.pending.length,
          store.selection.length > 0 || store.selectedConstraint !== null,
          store.dimensionEdit !== null || store.offsetDraft !== null,
        );
        if (action === "exit") finishSketch();
        else store.escape();
        return;
      }
      if (mode !== "draw") return;
      // Enter advances the mirror draft from collecting targets to the axis
      // pick — the keyboard-first path the "Choose axis" button mirrors.
      if (event.key === "Enter") {
        if (store.mirror?.phase === "targets") {
          event.preventDefault();
          store.advanceMirror();
          return;
        }
        // Enter commits an open spline (≥ 2 fit points) — the keyboard-first
        // finish the double-click mirrors.
        if (store.tool === "spline" && store.pending.length >= 2) {
          event.preventDefault();
          store.finishPlacement();
        }
        return;
      }
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
  }, [mode, finishSketch, setTool, toggleSnap, facePicking]);

  // Trim/extend: the scene arms an edit on a target click; this effect owns
  // the one network hop (the store stays side-effect-free). On success the
  // result's entity set is adopted and constraints are reconciled in the store
  // (dangling refs dropped) — the revision bump then re-solves through the
  // live loop for a bound sketch; an unbound buffer just re-renders locally.
  // The nonce guards against a double fire (React strict mode / re-render).
  const editNonceRef = useRef(0);
  useEffect(() => {
    if (edit === null || edit.nonce === editNonceRef.current) return;
    editNonceRef.current = edit.nonce;
    const { op, target, pick } = edit;
    void (async () => {
      try {
        const result = await editSketch(op, {
          entities: useSketchStore.getState().entities,
          target,
          pick,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyEditResult(op, result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failEdit(
            error instanceof SketchEditError
              ? error.message
              : "The edit could not be applied — try a different spot.",
          );
      }
    })();
  }, [edit]);

  // Offset: the scene arms a signed-distance offset once the inline editor
  // confirms; this effect owns the one network hop and APPENDS the returned
  // offset entity/entities (source unchanged — offset adds, never rewrites).
  // The revision bump then re-solves through the live loop for a bound sketch;
  // an unbound buffer just re-renders locally. The nonce guards a double fire.
  const offsetNonceRef = useRef(0);
  useEffect(() => {
    if (offset === null || offset.nonce === offsetNonceRef.current) return;
    offsetNonceRef.current = offset.nonce;
    const { target, distance } = offset;
    void (async () => {
      try {
        const result = await offsetSketch({
          entities: useSketchStore.getState().entities,
          target,
          distance,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyOffsetResult(result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failOffset(
            error instanceof SketchEditError
              ? error.message
              : "The offset could not be applied — try a different distance.",
          );
      }
    })();
  }, [offset]);

  // Mirror: the axis pick arms a mirror request; this effect owns the one
  // network hop and APPENDS the reflected copies (sources unchanged — mirror
  // adds, never rewrites). Like offset, the revision bump then re-solves a
  // bound sketch; an unbound buffer just re-renders. The nonce guards a double
  // fire (React strict mode / re-render).
  const mirrorNonceRef = useRef(0);
  useEffect(() => {
    if (
      mirrorRequest === null ||
      mirrorRequest.nonce === mirrorNonceRef.current
    )
      return;
    mirrorNonceRef.current = mirrorRequest.nonce;
    const { targets, axis } = mirrorRequest;
    void (async () => {
      try {
        const result = await mirrorSketch({
          entities: useSketchStore.getState().entities,
          targets,
          axis,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyMirrorResult(result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failMirror(
            error instanceof SketchEditError
              ? error.message
              : "The mirror could not be applied — try a different axis.",
          );
      }
    })();
  }, [mirrorRequest]);

  // Fillet/Chamfer: the value editor arms a corner request; this effect owns
  // the one network hop and SWAPS the whole rewritten set in (the two source
  // lines trimmed in place, ids preserved, plus the appended bridge) — like
  // trim/extend, unlike the additive offset/mirror. The store reconciles
  // constraints; the revision bump then re-solves through the live loop. The
  // nonce guards a double fire (React strict mode / re-render).
  const cornerNonceRef = useRef(0);
  useEffect(() => {
    if (
      cornerRequest === null ||
      cornerRequest.nonce === cornerNonceRef.current
    )
      return;
    cornerNonceRef.current = cornerRequest.nonce;
    const { op, a, b, value } = cornerRequest;
    void (async () => {
      try {
        const result = await cornerSketch(op, {
          entities: useSketchStore.getState().entities,
          a,
          b,
          value,
        });
        const store = useSketchStore.getState();
        if (store.mode === "draw") store.applyCornerResult(result.entities);
      } catch (error) {
        useSketchStore
          .getState()
          .failCorner(
            error instanceof SketchEditError
              ? error.message
              : "The corner could not be broken — try a smaller value.",
          );
      }
    })();
  }, [cornerRequest]);

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
  // Datum features already in the tree, offered as reusable sketch planes in
  // the plane picker (a standalone datum seats many sketches — DRY).
  const datumPlaneOptions = useMemo(
    () =>
      features.flatMap((f) =>
        // Offset datums are offerable as reusable sketch planes today; on-face
        // datums (a picked face SubshapeRef) are selectable via the later
        // face-picker slice — the offset plane math does not describe them.
        f.feature.type === "datum" && f.feature.params.kind === "offset"
          ? [{ id: f.id, name: f.name, params: f.feature.params }]
          : [],
      ),
    [features],
  );
  // Axis line-entity choices per profile sketch — the revolve editor scopes its
  // axis picker to the selected profile's own lines.
  const axesByProfile = useMemo(() => {
    const map: Record<string, AxisOption[]> = {};
    for (const profile of sketchProfiles) {
      map[profile.id] = axisOptions(features, profile.id);
    }
    return map;
  }, [sketchProfiles, features]);
  // Path choices per profile sketch — the sweep editor scopes its path picker
  // to every OTHER sketch (a sketch fills one slot: closed profile OR open path).
  const pathsByProfile = useMemo(() => {
    const map: Record<string, ProfileOption[]> = {};
    for (const profile of sketchProfiles) {
      map[profile.id] = pathOptions(features, profile.id);
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
        kind: "sweep";
        mode: "create" | "edit";
        initial: SweepForm;
        featureId?: string;
      }
    | {
        kind: "loft";
        mode: "create" | "edit";
        initial: LoftForm;
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
        initialPicked: EdgeSignature[];
        featureId?: string;
      }
    | {
        kind: "chamfer";
        mode: "create" | "edit";
        initial: ChamferForm;
        initialPicked: EdgeSignature[];
        featureId?: string;
      }
    | {
        kind: "shell";
        mode: "create" | "edit";
        initial: ShellForm;
        initialPickedFaces: PlanarFaceSignature[];
        featureId?: string;
      }
    | {
        kind: "draft";
        mode: "create" | "edit";
        initial: DraftForm;
        initialPickedFaces: PlanarFaceSignature[];
        featureId?: string;
      }
    | {
        kind: "datum";
        mode: "create" | "edit";
        initial: DatumForm;
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
  // STEP import (a discrete toolbar action, no editor panel): busy + the server
  // envelope's own message on rejection, surfaced in the viewport HUD.
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  // Inline offset-plane authoring (the plane-pick "+ Offset plane" path).
  const [offsetPlaneBusy, setOffsetPlaneBusy] = useState(false);
  const [offsetPlaneError, setOffsetPlaneError] = useState<string | null>(null);

  // The pickable face overlay for the current evaluated body — fetched exactly
  // as measurement fetches its overlay (same request/key: one cache entry, and
  // the faces line up with the body the viewport renders). Only while arming a
  // face pick and a body exists.
  const facesQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: facePicking && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const pickableFaces = facePicking ? (facesQuery.data?.faces ?? null) : null;

  // ---------------------------------------------------------------------
  // Fillet/Chamfer edge picking. The anchor for a picked edge's `SubshapeRef`
  // is the last body-affecting feature (the body the edges belong to) — the
  // same rule face picking uses. The edge-pick store bridges the editor and
  // the in-canvas overlay; PartPage owns the overlay fetch and the session
  // lifecycle (open on a fillet/chamfer editor, close otherwise).
  // ---------------------------------------------------------------------
  const bodyFeatureId = useMemo(
    () => lastBodyFeatureId(tree.data?.features ?? []),
    [tree.data],
  );
  const edgePicking = useEdgePickStore((s) => s.active && s.picking);
  const setEdgeOverlay = useEdgePickStore((s) => s.setOverlay);
  const setEdgeOverlayError = useEdgePickStore((s) => s.setOverlayError);

  const edgeOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: edgePicking && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (edgePicking && edgeOverlayQuery.data !== undefined) {
      setEdgeOverlay(edgeOverlayQuery.data);
    }
  }, [edgePicking, edgeOverlayQuery.data, setEdgeOverlay]);

  useEffect(() => {
    if (edgePicking && edgeOverlayQuery.error) {
      setEdgeOverlayError(
        edgeOverlayQuery.error instanceof Error
          ? edgeOverlayQuery.error.message
          : "The edge overlay could not be built.",
      );
    }
  }, [edgePicking, edgeOverlayQuery.error, setEdgeOverlayError]);

  // Face picking (shell + draft). A shell OR draft editor arms a face-pick
  // session on the SAME store (only one editor is open at a time); the pickable
  // face overlay for the current body is fetched exactly as the edge/measure
  // overlays are (same request/key — one cache entry, faces line up with the
  // rendered body). The anchor for a picked face's `SubshapeRef` is the same
  // `bodyFeatureId` fillet/chamfer use (the last body-affecting feature).
  const shellPicking = useFacePickStore((s) => s.active);
  const setShellOverlay = useFacePickStore((s) => s.setOverlay);
  const setShellOverlayError = useFacePickStore((s) => s.setOverlayError);

  const shellOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: shellPicking && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (shellPicking && shellOverlayQuery.data !== undefined) {
      setShellOverlay(shellOverlayQuery.data);
    }
  }, [shellPicking, shellOverlayQuery.data, setShellOverlay]);

  useEffect(() => {
    if (shellPicking && shellOverlayQuery.error) {
      setShellOverlayError(
        shellOverlayQuery.error instanceof Error
          ? shellOverlayQuery.error.message
          : "The face overlay could not be built.",
      );
    }
  }, [shellPicking, shellOverlayQuery.error, setShellOverlayError]);

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
    setImportError(null);
    useMeasureStore.getState().deactivate();
    begin();
  }, [begin]);

  // STEP import: read the chosen file's bytes and POST them to the import route
  // as the base body (§2b). Client-side size/extension pre-checks give instant
  // feedback, but the server is the source of truth — its envelope message
  // (import_too_large / import_empty / import_not_step / import_with_prior_body)
  // is surfaced verbatim. On success the tree + evaluate + mesh refetch so the
  // imported body appears in BOTH the feature tree and the viewport (the #2
  // render path every other feature creation uses).
  const handleImportStep = useCallback(
    (file: File) => {
      useMeasureStore.getState().deactivate();
      setEditor(null);
      setSelectedFeatureId(null);
      setImportError(null);
      const preError = precheckStepFile(file);
      if (preError !== null) {
        setImportError(preError);
        return;
      }
      setImporting(true);
      void (async () => {
        try {
          const bytes = await file.arrayBuffer();
          const response = await importStep(
            partId,
            bytes,
            stepFeatureName(file.name),
            await freshTreeVersion(),
          );
          setSelectedFeatureId(response.feature.id);
          await refreshTreeAndBody();
        } catch (error) {
          setImportError(
            error instanceof Error
              ? error.message
              : "The STEP file could not be imported.",
          );
        } finally {
          setImporting(false);
        }
      })();
    },
    [partId, freshTreeVersion, refreshTreeAndBody],
  );

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

  // A sweep references TWO earlier sketches (a closed profile + an open path),
  // so it seeds both slots from the tree — the first sketch as the profile, the
  // first other sketch as the path — and the user retargets either in the form.
  const openCreateSweep = useCallback(() => {
    const featureList = tree.data?.features ?? [];
    const profileId = defaultSweepProfileId(featureList);
    const pathId = defaultSweepPathId(featureList, profileId);
    if (profileId === "" || pathId === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "sweep",
      mode: "create",
      initial: defaultSweepForm(profileId, pathId),
    });
  }, [tree.data]);

  // A loft references an ORDERED LIST of ≥2 earlier sketches (its sections),
  // so it seeds the first two sketches in build order as the initial stack; the
  // user retargets, reorders, or adds more sections in the editor.
  const openCreateLoft = useCallback(() => {
    const featureList = tree.data?.features ?? [];
    const initialSections = defaultLoftSections(featureList);
    if (initialSections.length < 2) return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "loft",
      mode: "create",
      initial: defaultLoftForm(initialSections),
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
    setEditor({
      kind: "fillet",
      mode: "create",
      initial: defaultFilletForm(),
      initialPicked: [],
    });
  }, []);

  const openCreateChamfer = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "chamfer",
      mode: "create",
      initial: defaultChamferForm(),
      initialPicked: [],
    });
  }, []);

  // A shell, like fillet/chamfer/pattern, hollows the current BODY (no sketch
  // profile) — it only needs a solid to exist (canModify), so it mirrors their
  // guard. It opens with zero picked faces: a sealed hollow is a valid default.
  const openCreateShell = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "shell",
      mode: "create",
      initial: defaultShellForm(),
      initialPickedFaces: [],
    });
  }, []);

  // A draft, like shell, tapers the current BODY's picked faces (no sketch
  // profile) — it only needs a solid to exist (canModify), so it mirrors the
  // shell guard. It opens with zero picked faces; Apply stays disabled until at
  // least one face is picked (a draft with no faces is `no_draft_faces`).
  const openCreateDraft = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "draft",
      mode: "create",
      initial: defaultDraftForm(),
      initialPickedFaces: [],
    });
  }, []);

  // A datum plane needs no sketch/body — it's a construction plane parallel to
  // an origin datum. Available as soon as the tree exists (its own feature row).
  const openCreateDatum = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({ kind: "datum", mode: "create", initial: defaultDatumForm() });
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
    } else if (feature.feature.type === "sweep") {
      setEditor({
        kind: "sweep",
        mode: "edit",
        featureId: feature.id,
        initial: formFromSweepParams(feature.feature.params),
      });
    } else if (feature.feature.type === "loft") {
      setEditor({
        kind: "loft",
        mode: "edit",
        featureId: feature.id,
        initial: formFromLoftParams(feature.feature.params),
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
        initialPicked: pickedFromFilletParams(feature.feature.params),
      });
    } else if (feature.feature.type === "chamfer") {
      setEditor({
        kind: "chamfer",
        mode: "edit",
        featureId: feature.id,
        initial: formFromChamferParams(feature.feature.params),
        initialPicked: pickedFromChamferParams(feature.feature.params),
      });
    } else if (feature.feature.type === "shell") {
      setEditor({
        kind: "shell",
        mode: "edit",
        featureId: feature.id,
        initial: formFromShellParams(feature.feature.params),
        initialPickedFaces: pickedFacesFromShellParams(feature.feature.params),
      });
    } else if (feature.feature.type === "draft") {
      setEditor({
        kind: "draft",
        mode: "edit",
        featureId: feature.id,
        initial: formFromDraftParams(feature.feature.params),
        initialPickedFaces: pickedFacesFromDraftParams(feature.feature.params),
      });
    } else if (
      feature.feature.type === "datum" &&
      feature.feature.params.kind === "offset"
    ) {
      setEditor({
        kind: "datum",
        mode: "edit",
        featureId: feature.id,
        initial: formFromDatumParams(feature.feature.params),
      });
    } else {
      setEditor(null);
    }
  }, []);

  const closeEditor = useCallback(() => {
    setEditor(null);
    setEditorError(null);
  }, []);

  // Edge-pick session lifecycle: a fillet/chamfer editor opens a session
  // (seeded with its persisted picks + mode); anything else closes it. Keyed on
  // `editor` identity, which only changes on an open/select/close, so the store
  // never churns mid-edit. The overlay fetch + render gate on the store.
  useEffect(() => {
    const store = useEdgePickStore.getState();
    if (
      editor !== null &&
      (editor.kind === "fillet" || editor.kind === "chamfer")
    ) {
      store.open(editor.initialPicked, editor.initial.mode === "pick");
    } else {
      store.close();
    }
  }, [editor]);
  // Leaving the workspace tears the edge-pick session down.
  useEffect(() => () => useEdgePickStore.getState().close(), []);

  // Face-pick session lifecycle: a shell OR draft editor opens a session
  // (seeded with its persisted picked faces), anything else closes it. Keyed on
  // `editor` identity (only changes on open/select/close), so the store never
  // churns mid-edit. The overlay fetch + render gate on the store.
  useEffect(() => {
    const store = useFacePickStore.getState();
    if (
      editor !== null &&
      (editor.kind === "shell" || editor.kind === "draft")
    ) {
      store.open(editor.initialPickedFaces);
    } else {
      store.close();
    }
  }, [editor]);
  // Leaving the workspace tears the face-pick session down.
  useEffect(() => () => useFacePickStore.getState().close(), []);

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

  const submitSweep = useCallback(
    (params: SweepParams) => {
      const current = editor;
      if (current === null || current.kind !== "sweep") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sweep").length + 1;
      runFeatureSave(
        (version) => sweepFeatureCreate(`Sweep${nextIndex}`, params, version),
        (version) => sweepFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The sweep could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitLoft = useCallback(
    (params: LoftParams) => {
      const current = editor;
      if (current === null || current.kind !== "loft") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "loft").length + 1;
      runFeatureSave(
        (version) => loftFeatureCreate(`Loft${nextIndex}`, params, version),
        (version) => loftFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The loft could not be saved.",
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

  const submitShell = useCallback(
    (params: ShellParams) => {
      const current = editor;
      if (current === null || current.kind !== "shell") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "shell").length + 1;
      runFeatureSave(
        (version) => shellFeatureCreate(`Shell${nextIndex}`, params, version),
        (version) => shellFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The shell could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitDraft = useCallback(
    (params: DraftParams) => {
      const current = editor;
      if (current === null || current.kind !== "draft") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "draft").length + 1;
      runFeatureSave(
        (version) => draftFeatureCreate(`Draft${nextIndex}`, params, version),
        (version) => draftFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The draft could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitDatum = useCallback(
    (params: DatumParams) => {
      const current = editor;
      if (current === null || current.kind !== "datum") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "datum").length + 1;
      runFeatureSave(
        (version) => datumFeatureCreate(`Plane${nextIndex}`, params, version),
        (version) => datumFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The datum plane could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  // The inline "sketch at a height" path: author a datum feature, then enter
  // the sketcher on it. One extra field, not a separate multi-step ritual —
  // the datum write returns the feature id the sketch's plane FeatureRef needs.
  const authorOffsetPlane = useCallback(
    (params: DatumParams) => {
      const nextIndex =
        features.filter((f) => f.feature.type === "datum").length + 1;
      setOffsetPlaneBusy(true);
      setOffsetPlaneError(null);
      void (async () => {
        try {
          const create = (version: number) =>
            createFeature(
              partId,
              datumFeatureCreate(`Plane${nextIndex}`, params, version),
            );
          let response;
          try {
            response = await create(await freshTreeVersion());
          } catch {
            response = await create(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
          useSketchStore
            .getState()
            .choosePlaneSpec(offsetSpecFromDatum(response.feature.id, params));
        } catch (error) {
          setOffsetPlaneError(
            error instanceof Error
              ? error.message
              : "The offset plane could not be created.",
          );
        } finally {
          setOffsetPlaneBusy(false);
        }
      })();
    },
    [partId, features, freshTreeVersion, queryClient],
  );

  // The "Pick a face" path: author an `on_face` datum from the clicked face's
  // stage-1 signature, then seat this sketch on it — the datum-node route
  // (datum-planes §7), so the sketch's plane is the SAME FeatureRef slot an
  // offset datum uses. The face's plane basis is reconstructed client-side from
  // the signature (origin + deterministic x-axis), matching the kernel's
  // `resolve_sketch_plane` exactly, so the ink lands on the rendered face.
  const authorFacePlane = useCallback(
    (face: OverlayFace & { signature: PlanarFaceSignature }) => {
      const featureList = tree.data?.features ?? [];
      const anchorId = lastBodyFeatureId(featureList);
      if (anchorId === null) {
        setFacePlaneError(
          "Add a feature that creates a body before sketching on a face.",
        );
        return;
      }
      const { signature } = face;
      const nextIndex =
        featureList.filter((f) => f.feature.type === "datum").length + 1;
      setFacePlaneBusy(true);
      setPendingFaceIndex(face.index);
      setFacePlaneError(null);
      void (async () => {
        try {
          const params = onFaceDatumParams(anchorId, signature, 0);
          const create = (version: number) =>
            createFeature(
              partId,
              datumOnFaceFeatureCreate(`Plane${nextIndex}`, params, version),
            );
          let response;
          try {
            response = await create(await freshTreeVersion());
          } catch {
            response = await create(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
          useSketchStore
            .getState()
            .choosePlaneSpec(
              faceSpecFromDatum(response.feature.id, signature, 0),
            );
          setFacePicking(false);
        } catch (error) {
          setFacePlaneError(
            error instanceof Error
              ? error.message
              : "The sketch could not be placed on that face.",
          );
        } finally {
          setFacePlaneBusy(false);
          setPendingFaceIndex(null);
        }
      })();
    },
    [partId, tree.data, freshTreeVersion, queryClient],
  );

  /** Arm/disarm the face-pick mode (clears any stale error on toggle). */
  const togglePickFace = useCallback(() => {
    setFacePlaneError(null);
    setFacePicking((armed) => !armed);
  }, []);

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
  // A sweep needs TWO sketch features to reference (a profile + a path), both
  // solved so their wires exist — hence ≥2 sketches AND a solve has landed.
  const canSweep = sketchProfiles.length >= 2 && hasSolvedSketch;
  // A loft blends through ≥2 ordered section sketches — the same gate as sweep
  // (two sketch features must exist and a solve must have produced their wires).
  const canLoft = sketchProfiles.length >= 2 && hasSolvedSketch;

  // Sketch mode owns the viewport; leaving/entering it dismisses the editor.
  useEffect(() => {
    if (mode !== "off") setEditor(null);
  }, [mode]);

  // Face-pick belongs to the plane-pick step only: a chosen plane (→ draw) or a
  // sketch exit (→ off) disarms it, so the face overlay never lingers.
  useEffect(() => {
    if (mode !== "plane") {
      setFacePicking(false);
      setFacePlaneError(null);
    }
  }, [mode]);

  // Create/Modify accelerators (mode off): P patterns the current body (needs a
  // body); S sweeps a profile along a path (needs two solved sketches) — the
  // same guard grammar as the Measure M accelerator.
  useEffect(() => {
    if (mode !== "off") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "p" && hasBody) {
        event.preventDefault();
        openCreatePattern();
      } else if (key === "s" && canSweep) {
        event.preventDefault();
        openCreateSweep();
      } else if (key === "l" && canLoft) {
        event.preventDefault();
        openCreateLoft();
      } else if (key === "h" && hasBody) {
        event.preventDefault();
        openCreateShell();
      } else if (key === "d" && hasBody) {
        event.preventDefault();
        openCreateDraft();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    mode,
    hasBody,
    canSweep,
    canLoft,
    openCreatePattern,
    openCreateSweep,
    openCreateLoft,
    openCreateShell,
    openCreateDraft,
  ]);

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

  // The open command scopes the band + names the mode (breadcrumb + lock).
  const activeCommand =
    editor === null ? null : (COMMAND_LABEL[editor.kind] ?? null);
  // The breadcrumb's mode leaf: sketch step / measure / open command / model.
  const workspaceMode =
    mode === "draw"
      ? "Sketch"
      : mode === "plane"
        ? "Pick a plane"
        : measureActive
          ? "Measure"
          : activeCommand;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Breadcrumb
          register="parts"
          documentName={part.data?.name ?? "Part"}
          documentTestId="part-name"
          mode={workspaceMode}
        />
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
            canImportStep={bodyFeatureId === null}
            importingStep={importing}
            onImportStep={handleImportStep}
            onNewDatum={openCreateDatum}
            canExtrude={hasSolvedSketch}
            onNewExtrude={openCreateExtrude}
            canRevolve={hasSolvedSketch}
            onNewRevolve={openCreateRevolve}
            canSweep={canSweep}
            onNewSweep={openCreateSweep}
            canLoft={canLoft}
            onNewLoft={openCreateLoft}
            canModify={hasBody}
            onFillet={openCreateFillet}
            onChamfer={openCreateChamfer}
            onPattern={openCreatePattern}
            onShell={openCreateShell}
            onDraft={openCreateDraft}
            canMeasure={hasBody}
            measuring={measureActive}
            onToggleMeasure={toggleMeasure}
            activeCommand={activeCommand}
          />
        ) : (
          <SketchStrip
            onSave={finishSketch}
            saving={syncPending}
            saveError={syncError}
            datumPlanes={datumPlaneOptions}
            onChoosePlaneSpec={(spec) =>
              useSketchStore.getState().choosePlaneSpec(spec)
            }
            onAuthorOffsetPlane={authorOffsetPlane}
            authoringOffset={offsetPlaneBusy}
            offsetPlaneError={offsetPlaneError}
            onTogglePickFace={togglePickFace}
            canPickFace={hasBody}
            facePicking={facePicking}
            authoringFace={facePlaneBusy}
            facePickError={facePlaneError}
          />
        )}
      </TopToolbar>
      {/* Full-bleed scene: the canvas owns the frame; the tree + inspector
          FLOAT over it as collapsible instruments (Batch 1 makeover, P0-4) —
          no more columns subtracted from the viewport. */}
      <main className="relative min-h-0 grow">
        <Viewport
          glb={body.data}
          rotateEnabled={mode !== "draw"}
          groundGrid={mode !== "draw"}
          viewNav={mode === "off"}
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
                ) : editor.kind === "sweep" ? (
                  <SweepEditor
                    mode={editor.mode}
                    profiles={sketchProfiles}
                    pathsByProfile={pathsByProfile}
                    initial={editor.initial}
                    onSubmit={submitSweep}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "loft" ? (
                  <LoftEditor
                    mode={editor.mode}
                    sections={sketchProfiles}
                    initial={editor.initial}
                    onSubmit={submitLoft}
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
                    bodyFeatureId={bodyFeatureId}
                    onSubmit={submitFillet}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "chamfer" ? (
                  <ChamferEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    bodyFeatureId={bodyFeatureId}
                    onSubmit={submitChamfer}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "shell" ? (
                  <ShellEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    bodyFeatureId={bodyFeatureId}
                    onSubmit={submitShell}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : editor.kind === "draft" ? (
                  <DraftEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    bodyFeatureId={bodyFeatureId}
                    onSubmit={submitDraft}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                ) : (
                  <DatumEditor
                    mode={editor.mode}
                    initial={editor.initial}
                    onSubmit={submitDatum}
                    onCancel={closeEditor}
                    saving={editorSaving}
                    error={editorError}
                  />
                )
              ) : null}
              {importing ? (
                <div
                  role="status"
                  data-testid="import-step-status"
                  className="absolute bottom-3 left-3 rounded-sm border border-hairline bg-anvil px-3 py-2"
                >
                  <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
                    Importing STEP
                  </span>
                  <span className="mt-1 block font-body text-xs text-mist">
                    Reading the solid and building the base body.
                  </span>
                </div>
              ) : importError !== null ? (
                <div
                  role="alert"
                  data-testid="import-step-error"
                  className="absolute bottom-3 left-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
                >
                  <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                    Import failed
                  </span>
                  <span className="mt-1 block font-body text-xs text-mist">
                    {importError}
                  </span>
                  <button
                    type="button"
                    onClick={() => setImportError(null)}
                    data-testid="import-step-dismiss"
                    className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                  >
                    Dismiss
                  </button>
                </div>
              ) : null}
              {regenerating ? (
                <div
                  role="status"
                  data-testid="body-regenerating"
                  className="absolute left-editor top-3 rounded-sm border border-hairline bg-anvil px-3 py-2"
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
                  className="absolute left-editor top-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
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
          <SketchScene solved={solvedLayers} facePicking={facePicking} />
          <MeasureOverlay />
          {mode === "off" && edgePicking ? <EdgePickOverlay /> : null}
          {mode === "off" && shellPicking ? (
            <ShellFaceOverlay
              testIdPrefix={
                editor?.kind === "draft" ? "draft-face" : "shell-face"
              }
            />
          ) : null}
          {mode === "plane" && facePicking ? (
            <FacePickOverlay
              faces={pickableFaces}
              onPick={authorFacePlane}
              pendingIndex={pendingFaceIndex}
            />
          ) : null}
        </Viewport>
        <FloatingPanel side="left" title="Feature tree" id="tree">
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
        </FloatingPanel>
        {showInspector ? (
          <FloatingPanel side="right" title="Inspector" id="inspector">
            <BodyInspector
              properties={bodyProperties}
              status={bodyStatus}
              partId={partId}
            />
          </FloatingPanel>
        ) : showExportOnly ? (
          // No body yet (a sketch-only or rolled-back tree), but the part is
          // modeled enough to have a tree — offer the EXPORT strip in its
          // honest disabled state so the affordance is discoverable.
          <FloatingPanel side="right" title="Export" id="inspector">
            <aside
              className="w-full"
              aria-label="Part export"
              data-testid="part-export-idle"
            >
              <Panel>
                <PartExportControls partId={partId} hasBody={false} />
              </Panel>
            </aside>
          </FloatingPanel>
        ) : null}
      </main>
    </div>
  );
}
