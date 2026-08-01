import {
  CloseIcon,
  ContextMenu,
  type ContextMenuSection,
  DatumIcon,
  formatLength,
  MeasureIcon,
  Panel,
  SketchIcon,
  SuppressIcon,
  ViewFitIcon,
  ViewFrontIcon,
  ViewHomeIcon,
  ViewIsoIcon,
  ViewRightIcon,
  ViewTopIcon,
} from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  fetchMaterials,
  type MaterialAssignment,
  type MaterialKey,
  updatePartMaterials,
} from "../api/materials";
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
  type BooleanParams,
  booleanFeatureCreate,
  type ChamferParams,
  chamferFeatureCreate,
  chamferFeatureUpdate,
  createFeature,
  type DatumOffsetParams,
  type DatumParams,
  datumFeatureCreate,
  datumFeatureUpdate,
  datumOnFaceFeatureCreate,
  type DraftParams,
  draftFeatureCreate,
  draftFeatureUpdate,
  deleteFeature,
  renameFeature,
  type EdgeSignature,
  evaluatePart,
  type ExtrudeParams,
  extrudeFeatureCreate,
  extrudeFeatureUpdate,
  type FeatureCreate,
  type FeatureResponse,
  type FeatureTreeResponse,
  type FeatureUpdate,
  type FeatureDependent,
  fetchFeatureDependents,
  fetchFeatureTree,
  FeatureHasDependentsError,
  fetchPart,
  importStep,
  type OverlayFace,
  type PlanarFaceSignature,
  type FilletParams,
  filletFeatureCreate,
  filletFeatureUpdate,
  type HoleParams,
  holeFeatureCreate,
  holeFeatureUpdate,
  type Vec3,
  type LoftParams,
  loftFeatureCreate,
  loftFeatureUpdate,
  type MirrorParams,
  mirrorFeatureCreate,
  mirrorFeatureUpdate,
  moveRollbackBar,
  redoPart,
  StaleTreeVersionError,
  undoPart,
  type PatternParams,
  patternFeatureCreate,
  patternFeatureUpdate,
  type RevolveParams,
  revolveFeatureCreate,
  revolveFeatureUpdate,
  type ShellParams,
  shellFeatureCreate,
  shellFeatureUpdate,
  type SheetMetalBaseFlangeParams,
  baseFlangeFeatureCreate,
  baseFlangeFeatureUpdate,
  type SheetMetalEdgeFlangeParams,
  edgeFlangeFeatureCreate,
  edgeFlangeFeatureUpdate,
  type SheetMetalHemParams,
  hemFeatureCreate,
  hemFeatureUpdate,
  type SheetMetalCornerReliefParams,
  cornerReliefFeatureCreate,
  cornerReliefFeatureUpdate,
  type SweepParams,
  sweepFeatureCreate,
  sweepFeatureUpdate,
  sketchFeatureCreate,
  sketchFeatureUpdate,
  suppressFeature,
  updateFeature,
  updatePartUnit,
  type LengthUnit,
} from "../api/parts";
import { BodyInspector } from "../components/BodyInspector";
import { Breadcrumb } from "../components/Breadcrumb";
import { DocumentUnitSelect } from "../components/DocumentUnitSelect";
import { DocumentUnitProvider } from "../units/documentUnit";
import { BodiesPanel } from "../components/BodiesPanel";
import { ChamferEditor } from "../components/ChamferEditor";
import { CombineEditor } from "../components/CombineEditor";
import { CreateStrip } from "../components/CreateStrip";
import { FloatingPanel } from "../components/FloatingPanel";
import { DatumEditor } from "../components/DatumEditor";
import { DraftEditor } from "../components/DraftEditor";
import { ExtrudeEditor } from "../components/ExtrudeEditor";
import { HoleEditor } from "../components/HoleEditor";
import { BaseFlangeEditor } from "../components/BaseFlangeEditor";
import { EdgeFlangeEditor } from "../components/EdgeFlangeEditor";
import { HemEditor } from "../components/HemEditor";
import { CornerReliefEditor } from "../components/CornerReliefEditor";
import { FeatureDeleteConfirm } from "../components/FeatureDeleteConfirm";
import { FeatureTreePanel } from "../components/FeatureTreePanel";
import { FilletEditor } from "../components/FilletEditor";
import { LoftEditor } from "../components/LoftEditor";
import { MirrorEditor } from "../components/MirrorEditor";
import { PartExportControls } from "../components/PartExportControls";
import { PatternEditor } from "../components/PatternEditor";
import { RevolveEditor } from "../components/RevolveEditor";
import { ShellEditor } from "../components/ShellEditor";
import { SweepEditor } from "../components/SweepEditor";
import {
  defaultDatumForm,
  type DatumFacePick,
  type DatumFaceSlot,
  type DatumForm,
  formFromDatumParams,
} from "../features/datum";
import {
  defaultExtrudeForm,
  defaultProfileId,
  type ExtrudeForm,
  type ExtrudePreviewState,
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
import { computeBodies } from "../features/bodies";
import {
  bodyMaterialRows,
  withBodyMaterial,
  withDefaultMaterial,
} from "../features/materials";
import { derivePartBuild, partialBodySentence } from "../features/partBuild";
import {
  type BaseFlangeForm,
  canAuthorCornerRelief,
  type CornerReliefForm,
  cornerReliefBendHighlights,
  defaultBaseFlangeForm,
  defaultCornerReliefForm,
  defaultEdgeFlangeForm,
  defaultHemForm,
  type EdgeFlangeForm,
  type EdgeFlangeSpanPreview,
  edgeFlangeOptions,
  formFromBaseFlangeParams,
  formFromCornerReliefParams,
  formFromEdgeFlangeParams,
  formFromHemParams,
  type HemForm,
  isSheetMetalPart,
  pickedFromEdgeFlangeParams,
  pickedFromHemParams,
  sheetMetalDefaults,
} from "../features/sheetMetal";
import { BendHighlightOverlay } from "../viewport/BendHighlightOverlay";
import { FlangeSpanOverlay } from "../viewport/FlangeSpanOverlay";
import { type CombineForm, defaultCombineForm } from "../features/boolean";
import {
  defaultMirrorForm,
  formFromMirrorParams,
  type MirrorForm,
} from "../features/mirror";
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
import { useCommandActionStore } from "../features/commandActions";
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
import { HolePointOverlay } from "../viewport/HolePointOverlay";
import {
  defaultHoleForm,
  formFromHoleParams,
  type HoleFacePick,
  type HoleForm,
  type HolePickTarget,
  type HolePointPick,
  type HolePreview,
} from "../features/hole";
import {
  preselectedEdges,
  preselectedFace,
  preselectedFaces,
  usePreselectStore,
} from "../features/preselect";
import { SketchDro } from "../components/SketchDro";
import { SketchStrip } from "../components/SketchStrip";
import { SolveDiagnostic } from "../components/SolveDiagnostic";
import { TimelineStrip } from "../components/TimelineStrip";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import { resolveSketchKey, type SolveInfo } from "../sketch/constraints";
import {
  type AnyDatumParams,
  faceSpecFromDatum,
  offsetSpecFromDatum,
  originBasis,
  planeRefFromSpec,
  type PlaneBasis,
  resolveDatumBasis,
  resolveDatumPlaneOptions,
} from "../sketch/plane";
import {
  faceSignatureKey,
  isPickableFace,
  lastBodyFeatureId,
  onFaceDatumParams,
} from "../features/face";
import { isTypingTarget } from "../lib/isTypingTarget";
import { executeHistoryStep } from "../lib/historyStep";
import {
  HistoryErrorAlert,
  type HistoryStepError,
} from "../components/HistoryErrorAlert";
import { type HistoryStep, undoRedoStep } from "../lib/undoRedoShortcut";
import { FacePickOverlay } from "../viewport/FacePickOverlay";
import { useSketchStore } from "../sketch/store";
import { escapeAction, TOOL_SHORTCUTS } from "../sketch/tools";
import {
  KEY_MEASURE,
  KEY_SNAP,
  PART_CREATE_SHORTCUTS,
} from "../shortcuts/registry";
import { partRoute } from "../router";
import { useNavigate } from "@tanstack/react-router";
import {
  createDrawing,
  createSheet,
  createView,
  DrawingNameTakenError,
} from "../api/drawings";
import { sheetDimensions } from "../drawing/layout";
import { SketchScene, type SolvedSketchLayer } from "../viewport/SketchScene";
import { ExtrudePreview } from "../viewport/ExtrudePreview";
import { useViewCommandStore } from "../viewport/viewCommands";
import { Viewport } from "../viewport/Viewport";

/** Constraint/dimension edits persist after this quiet gap (the live loop). */
const SYNC_DEBOUNCE_MS = 400;

/**
 * The one open feature editor (the authoring seat holds a single editor at a
 * time). Hoisted to a named union so `COMMAND_LABEL` can be keyed on
 * `OpenEditor["kind"]` — a future editor kind missing from the map is a
 * COMPILE error, never a silently unlocked band with unregistered keys.
 */
type OpenEditor =
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
      kind: "hole";
      mode: "create" | "edit";
      initial: HoleForm;
      featureId?: string;
    }
  | {
      kind: "mirror";
      mode: "create" | "edit";
      initial: MirrorForm;
      featureId?: string;
    }
  | {
      kind: "datum";
      mode: "create" | "edit";
      initial: DatumForm;
      featureId?: string;
    }
  | {
      kind: "baseFlange";
      mode: "create" | "edit";
      initial: BaseFlangeForm;
      featureId?: string;
    }
  | {
      kind: "edgeFlange";
      mode: "create" | "edit";
      initial: EdgeFlangeForm;
      initialPicked: EdgeSignature[];
      featureId?: string;
    }
  | {
      kind: "hem";
      mode: "create" | "edit";
      initial: HemForm;
      initialPicked: EdgeSignature[];
      featureId?: string;
    }
  | {
      kind: "cornerRelief";
      mode: "create" | "edit";
      initial: CornerReliefForm;
      featureId?: string;
    }
  | {
      kind: "combine";
      mode: "create";
      initial: CombineForm;
      featureId?: string;
    };

/** Editor kind → the command name shown in the breadcrumb + band lock reason. */
const COMMAND_LABEL: Record<OpenEditor["kind"], string> = {
  extrude: "Extrude",
  revolve: "Revolve",
  sweep: "Sweep",
  loft: "Loft",
  pattern: "Pattern",
  fillet: "Fillet",
  chamfer: "Chamfer",
  shell: "Shell",
  draft: "Draft",
  hole: "Hole",
  mirror: "Mirror",
  datum: "Datum plane",
  baseFlange: "Base flange",
  edgeFlange: "Edge flange",
  hem: "Hem",
  cornerRelief: "Corner relief",
  combine: "Combine",
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
  const navigate = useNavigate();

  const part = useQuery({
    queryKey: ["part", partId],
    queryFn: () => fetchPart(partId),
    // NOT `staleTime: Infinity` (it was, until 2026-07-30). The part row is five
    // scalars — id/name/unit/`tree_version`/`eval_state` — and one of them is the
    // DENOMINATOR of the staleness comparison the STATUS cell now reports
    // (`features/partBuild.ts`). A version the client never refreshes cannot
    // detect the case that motivated the readout: another session edits the tree,
    // nothing here invalidates, and the workspace would keep asserting currency
    // indefinitely (UI-REVIEW 2026-07-30 F2). Re-reading five scalars when the
    // tab regains focus is cheap; being confidently wrong is not.
    staleTime: 5_000,
  });
  // The document display unit (docs/design/units.md §U2). Edit-form seeds render
  // their canonical mm in this unit; the DocumentUnitProvider carries it to
  // every dimension cell + readout below. Falls back to mm until the part loads.
  const lengthUnit = part.data?.length_unit ?? "mm";
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

  // Datum-editor face picking: the DatumEditor arms a pick for one slot (the
  // on_face base, or either midplane side); a clicked face is folded into that
  // slot's form field. Reuses the SAME FacePickOverlay + overlay fetch the
  // sketch-on-face flow uses — one enumeration, pick side and resolve side.
  const [datumFacePick, setDatumFacePick] = useState<DatumFaceSlot | null>(
    null,
  );
  const [datumFacePicked, setDatumFacePicked] = useState<DatumFacePick | null>(
    null,
  );
  const [datumFacePickError, setDatumFacePickError] = useState<string | null>(
    null,
  );
  const datumFacePickNonce = useRef(0);

  // Hole authoring pick session: the HoleEditor arms a FACE pick (the planar
  // placement face) then a POINT pick (a point ON it). Both reuse the SAME
  // overlay fetch + DOM-in-canvas pick affordances the datum/measure flows use
  // — one enumeration, pick side and resolve side. `holePreview` mirrors the
  // editor's live face + position up so the point overlay draws ON the face.
  const [holePick, setHolePick] = useState<HolePickTarget | null>(null);
  const [holeFacePicked, setHoleFacePicked] = useState<HoleFacePick | null>(
    null,
  );
  const [holePointPicked, setHolePointPicked] = useState<HolePointPick | null>(
    null,
  );
  const [holePickError, setHolePickError] = useState<string | null>(null);
  const [holePreview, setHolePreview] = useState<HolePreview | null>(null);
  const holePickNonce = useRef(0);

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

  /** All datum feature params by id — the datum-plane resolution table. */
  const datumById = useMemo(() => {
    const map = new Map<string, AnyDatumParams>();
    for (const feature of tree.data?.features ?? []) {
      if (feature.feature.type === "datum") {
        map.set(feature.id, feature.feature.params);
      }
    }
    return map;
  }, [tree.data]);

  /**
   * Every datum feature's placed sketch basis, resolved client-side by the SAME
   * math the kernel evaluates (offset / offset-from-a-datum / midplane over
   * origin + datum sides — one plane-math source, two renderers). An `on_face`
   * datum (or a face-picked midplane side) resolves server-side only, so it is
   * absent here and simply not offered as a reusable preview plane.
   */
  const datumBasisById = useMemo(() => {
    const map = new Map<string, PlaneBasis>();
    for (const id of datumById.keys()) {
      const basis = resolveDatumBasis(id, datumById);
      if (basis !== null) map.set(id, basis);
    }
    return map;
  }, [datumById]);

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
        basis = datumBasisById.get(plane.feature_id) ?? null;
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
  }, [tree.data, evaluation.data, mode, featureId, datumBasisById]);

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
      if (key === KEY_SNAP) {
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
  // The part's body set, replayed from the tree (multi-body §MB-1) — drives the
  // Bodies panel and the Combine tool's target/tool pickers. One body is the
  // common case; a `merge: false` add (or an import) starts a second.
  const bodies = useMemo(() => computeBodies(features), [features]);
  // Per-body lump count from the evaluate wire (§MB-4c): a disjoint-union /
  // multi-solid-import body reports `lumps > 1`, which the Bodies panel flags.
  // Keyed by the body's base feature id (its §MB-0 identity) so a row maps to its
  // count; absent for a tree with no body-affecting feature (the panel shows none).
  const lumpsByFeature = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of evaluation.data?.bodies ?? []) {
      map.set(entry.base_feature_id, entry.lumps);
    }
    return map;
  }, [evaluation.data?.bodies]);
  // Sheet-metal state: the part is sheet metal once it has a base flange, and
  // that base flange's gauge / bend-radius / K become the defaults every edge
  // flange inherits (sheet-metal.md §4.2). Edge flange + Flat pattern light up
  // from `isSheetMetal`; the edge-flange editor shows `smDefaults`.
  const smDefaults = useMemo(() => sheetMetalDefaults(features), [features]);
  const isSheetMetal = useMemo(() => isSheetMetalPart(features), [features]);
  // Corner relief references TWO edge-flange FEATURES (not an edge pick), so it
  // lights up only with ≥2 edge flanges, and the editor lists them by name.
  const edgeFlangeOpts = useMemo(() => edgeFlangeOptions(features), [features]);
  const canCornerRelief = useMemo(
    () => canAuthorCornerRelief(features),
    [features],
  );
  // Datum features already in the tree, offered as reusable sketch planes in
  // the plane picker (a standalone datum seats many sketches — DRY). The SAME
  // derivation the section-view author reads (`resolveDatumPlaneOptions`), so a
  // datum FeatureRef means exactly the same plane in both flows (one source).
  const datumPlaneOptions = useMemo(
    () => resolveDatumPlaneOptions(features),
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
  // (The union lives in `OpenEditor` above, which also keys COMMAND_LABEL.)
  const [editor, setEditor] = useState<OpenEditor | null>(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(
    null,
  );
  const [editorSaving, setEditorSaving] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
  // UX audit #20e — a feature can SAVE cleanly yet fail to REBUILD (the create
  // 200s, then the tree re-evaluation flags the feature). That error lands in
  // the tree while the eye is still on the editor seat, so we mirror it right
  // there. Keyed to the last-saved feature so merely selecting an old broken
  // feature never nags; dismissible, and re-armed by the next save.
  const [lastSavedFeatureId, setLastSavedFeatureId] = useState<string | null>(
    null,
  );
  const [rebuildNoticeDismissed, setRebuildNoticeDismissed] = useState(false);
  const [rollbackBusy, setRollbackBusy] = useState(false);
  // Live extrude ghost (UI-REVIEW #8): the open extrude editor projects its
  // form here on every keystroke; the viewport sweeps the profile at this
  // distance before Save. Cleared the moment the editor closes.
  const [extrudePreview, setExtrudePreview] =
    useState<ExtrudePreviewState | null>(null);

  // Earlier datum features offered to the datum editor as references (the
  // offset-from base + the midplane sides). Create authors at the tip, so every
  // existing datum is earlier; an edit sees only the datums strictly before it
  // (the strict-backward rule — a datum can't reference itself or a later one).
  const datumEditorRefs = useMemo(() => {
    if (editor?.kind !== "datum") return [];
    const editingId = editor.featureId;
    const foundAt = editingId
      ? features.findIndex((f) => f.id === editingId)
      : -1;
    const bound = foundAt < 0 ? features.length : foundAt;
    return features
      .filter((f, i) => f.feature.type === "datum" && i < bound)
      .map((f) => ({ id: f.id, name: f.name }));
  }, [editor, features]);
  // STEP import (a discrete toolbar action, no editor panel): busy + the server
  // envelope's own message on rejection, surfaced in the viewport HUD.
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  // Flat pattern (a discrete action, no editor panel): unfolding the sheet body
  // creates a drawing + a lone flat-pattern view referencing this part, then
  // navigates to it. Busy + the server envelope's own message on rejection.
  const [flatPatternBusy, setFlatPatternBusy] = useState(false);
  const [flatPatternError, setFlatPatternError] = useState<string | null>(null);
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

  // The pickable face overlay while the datum editor is armed for a slot —
  // same request/key (one cache entry, faces line up with the rendered body).
  const datumFacesQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled:
      datumFacePick !== null && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const datumPickableFaces =
    datumFacePick !== null ? (datumFacesQuery.data?.faces ?? null) : null;

  // The pickable overlay for the WHOLE hole command — same request/key as every
  // other overlay (one cache entry, faces + vertices + edges line up with the
  // rendered body). `.faces` feeds the face pick; `.vertices` feed the point
  // pick's face-corner snaps; `.edges` feed the coordinate cells' live material
  // check and the concentric snaps (QA3-1), which is why this is no longer
  // gated on a pick being armed — typing a coordinate needs the geometry too.
  const holeEditing = editor?.kind === "hole";
  const holeOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: holeEditing && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const holePickableFaces =
    holePick === "face" ? (holeOverlayQuery.data?.faces ?? null) : null;
  const holeOverlayVertices = holeOverlayQuery.data?.vertices ?? null;
  const holeOverlayEdges = holeOverlayQuery.data?.edges ?? null;

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

  // ---------------------------------------------------------------------
  // Feature-localized selection (FINDINGS #9). Selecting a feature in the tree
  // highlights ONLY the faces that feature owns — the studio matcap stays on
  // the rest of the body (never a whole-body clay swap). The overlay carries
  // per-face `feature_id` provenance; the selected feature's faces are every
  // OverlayFace whose `feature_id` matches it, and each face's `index` is its
  // GLB primitive ordinal — the mesh face set to tint. Fetched through the SAME
  // request/key as every other overlay (one cache entry, faces line up with the
  // rendered body). Mirrors `bodySelected` exactly (selecting a feature opens
  // its editor, so it must NOT gate on `editor === null`) — it localizes the
  // same warm the body already shows, refining whole-body → this feature's faces.
  // ---------------------------------------------------------------------
  const selectionActive =
    mode === "off" && selectedFeatureId !== null && !measureActive;
  const selectionOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: selectionActive && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const selectedFaceIndices = useMemo<number[] | null>(() => {
    if (!selectionActive || selectedFeatureId === null) return null;
    const faces = selectionOverlayQuery.data?.faces;
    if (faces === undefined) return null;
    const owned = faces
      .filter((face) => face.feature_id === selectedFeatureId)
      .map((face) => face.index);
    return owned.length > 0 ? owned : null;
  }, [selectionActive, selectedFeatureId, selectionOverlayQuery.data]);

  // ---------------------------------------------------------------------
  // Pre-selection highlight (UI-W3). A selection you cannot see is a trap: the
  // next command would prefill itself from something invisible. So the faces
  // the cursor has picked STAY lit after the editor that picked them closes —
  // the same feature-localized brass a tree selection lights, on the same
  // cached overlay (the pick already fetched it, so this costs no request).
  // A tree selection wins while one is active: one highlight, one meaning.
  // ---------------------------------------------------------------------
  const preselectedFaceSet = usePreselectStore((s) => s.faces);
  const livePreselectedFaces = useMemo(
    () => preselectedFaces({ faces: preselectedFaceSet }, bodyFeatureId),
    [preselectedFaceSet, bodyFeatureId],
  );
  const preselectHighlightActive =
    mode === "off" &&
    !measureActive &&
    selectedFeatureId === null &&
    livePreselectedFaces.length > 0;
  const preselectOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled:
      preselectHighlightActive && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const preselectedFaceIndices = useMemo<number[] | null>(() => {
    if (!preselectHighlightActive) return null;
    const faces = preselectOverlayQuery.data?.faces;
    if (faces === undefined) return null;
    const keys = new Set(
      livePreselectedFaces.map((face) => faceSignatureKey(face.signature)),
    );
    const lit = faces
      .filter(
        (face) =>
          isPickableFace(face) && keys.has(faceSignatureKey(face.signature)),
      )
      .map((face) => face.index);
    return lit.length > 0 ? lit : null;
  }, [
    preselectHighlightActive,
    livePreselectedFaces,
    preselectOverlayQuery.data,
  ]);

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

  // Document-unit change (docs/design/units.md §U2): a pure re-label. It PATCHes
  // the part's `length_unit` under the tree-version OCC and refreshes the part +
  // tree — NO stored mm value is touched, so the body never re-solves; every
  // dimension cell + readout simply re-formats into the new unit on the next
  // render (the DocumentUnitProvider feeds them the new value).
  const [unitBusy, setUnitBusy] = useState(false);
  const changeUnit = useCallback(
    (next: LengthUnit) => {
      if (next === lengthUnit || unitBusy) return;
      setUnitBusy(true);
      void (async () => {
        try {
          const version = await freshTreeVersion();
          await updatePartUnit(partId, next, version);
          await queryClient.invalidateQueries({ queryKey: ["part", partId] });
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
        } catch {
          // A stale-version race (422) or transient failure leaves the unit as
          // it was; the selector reverts to the loaded value and the user can
          // retry. Nothing stored changed.
        } finally {
          setUnitBusy(false);
        }
      })();
    },
    [lengthUnit, unitBusy, partId, freshTreeVersion, queryClient],
  );

  // MATERIAL (docs/design/materials.md). The library is SERVED, never typed
  // client-side — a density is a physical constant with one home, and a second
  // copy in TS would silently drift. It is a fixed table, so one fetch per
  // session; a failure disables the picker and says why rather than guessing.
  const materialLibrary = useQuery({
    queryKey: ["materials"],
    queryFn: () => fetchMaterials(),
    staleTime: Infinity,
    retry: false,
  });
  // A stored NULL reads back as the EMPTY assignment (§4), so the panel has ONE
  // shape to render and never has to tell null from empty.
  const assignment = useMemo<MaterialAssignment>(
    () => part.data?.materials ?? { default_material: null, bodies: [] },
    [part.data?.materials],
  );
  // One row per body: the tree's names/ordinals joined to the evaluation's
  // RESOLVED material + mass. Resolution is the server's single function
  // (`resolve_body_material`); nothing here re-derives it.
  const materialRows = useMemo(
    () => bodyMaterialRows(bodies, evaluation.data?.bodies ?? [], assignment),
    [bodies, evaluation.data?.bodies, assignment],
  );
  const [materialBusy, setMaterialBusy] = useState(false);
  const [materialError, setMaterialError] = useState<string | null>(null);
  // Assignment is a WHOLESALE replacement under the tree-version OCC guard
  // (§2): the request states the full intended state, so two concurrent edits
  // cannot interleave into an assignment neither of them sent. Unlike a rename
  // or a unit change this really does invalidate the recorded evaluate — mass
  // was derived from the material — so the tree refetch bumps `tree_version`,
  // which re-keys the evaluate query and rebuilds with the new density.
  const assignMaterials = useCallback(
    (next: MaterialAssignment) => {
      if (materialBusy) return;
      setMaterialBusy(true);
      setMaterialError(null);
      void (async () => {
        try {
          // Retry ONCE on a stale-version race, the way every other discrete
          // edit here does: a user who re-units the document and immediately
          // picks a material would otherwise hit a 422 for a conflict that
          // isn't one (nobody else edited anything — the cached version simply
          // hadn't caught up yet).
          try {
            await updatePartMaterials(partId, next, await freshTreeVersion());
          } catch {
            await updatePartMaterials(
              partId,
              next,
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({ queryKey: ["part", partId] });
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
          await queryClient.invalidateQueries({
            queryKey: ["evaluate", partId],
          });
        } catch (error) {
          setMaterialError(
            error instanceof Error
              ? error.message
              : "The material could not be assigned.",
          );
        } finally {
          setMaterialBusy(false);
        }
      })();
    },
    [materialBusy, partId, freshTreeVersion, queryClient],
  );
  const assignDefaultMaterial = useCallback(
    (material: MaterialKey | null) =>
      assignMaterials(withDefaultMaterial(assignment, material)),
    [assignMaterials, assignment],
  );
  const assignBodyMaterial = useCallback(
    (baseFeatureId: string, material: MaterialKey | null) =>
      assignMaterials(withBodyMaterial(assignment, baseFeatureId, material)),
    [assignMaterials, assignment],
  );
  const materialControls = useMemo(
    () => ({
      library: materialLibrary.data ?? [],
      libraryError:
        materialLibrary.error instanceof Error
          ? materialLibrary.error.message
          : null,
      assignment,
      rows: materialRows,
      busy: materialBusy,
      error: materialError,
      onAssignDefault: assignDefaultMaterial,
      onAssignBody: assignBodyMaterial,
    }),
    [
      materialLibrary.data,
      materialLibrary.error,
      assignment,
      materialRows,
      materialBusy,
      materialError,
      assignDefaultMaterial,
      assignBodyMaterial,
    ],
  );

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
  // picks, then exits — the same cascade grammar the sketcher uses. Locked while
  // a feature editor is open (M would `setEditor(null)` and discard its picks).
  useEffect(() => {
    if (mode !== "off" || editor !== null) return;
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
      if (event.key.toLowerCase() === KEY_MEASURE) {
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
  }, [mode, editor, hasBody]);

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
  // Both seed from the edges the cursor already has selected (UI-W3): picking
  // three edges and then choosing Fillet is how a modeller works, and until
  // now that selection was thrown away at the door. A seeded editor opens in
  // "pick" mode — the picks ARE the selector — and an empty one keeps the
  // all-edges rule default.
  const openCreateFillet = useCallback(() => {
    const picked = preselectedEdges(
      usePreselectStore.getState(),
      bodyFeatureId,
    );
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "fillet",
      mode: "create",
      initial: {
        ...defaultFilletForm(),
        ...(picked.length > 0 ? { mode: "pick" as const } : {}),
      },
      initialPicked: [...picked],
    });
  }, [bodyFeatureId]);

  const openCreateChamfer = useCallback(() => {
    const picked = preselectedEdges(
      usePreselectStore.getState(),
      bodyFeatureId,
    );
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "chamfer",
      mode: "create",
      initial: {
        ...defaultChamferForm(),
        ...(picked.length > 0 ? { mode: "pick" as const } : {}),
      },
      initialPicked: [...picked],
    });
  }, [bodyFeatureId]);

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
      // The faces the cursor already has selected are the faces to leave open
      // (UI-W3) — an empty selection still means a sealed hollow.
      initialPickedFaces: preselectedFaces(
        usePreselectStore.getState(),
        bodyFeatureId,
      ).map((face) => face.signature),
    });
  }, [bodyFeatureId]);

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
      // Seeded from the cursor selection (UI-W3); Apply stays gated until at
      // least one face is chosen either way.
      initialPickedFaces: preselectedFaces(
        usePreselectStore.getState(),
        bodyFeatureId,
      ).map((face) => face.signature),
    });
  }, [bodyFeatureId]);

  // A hole, like fillet/shell/draft, modifies the current BODY (no sketch
  // profile) — it only needs a solid to exist (canModify), so it mirrors their
  // guard.
  //
  // UI-W3, and the reason this item exists: the hole opens PLACED on whatever
  // face the cursor already had selected (drill point seeded to its centre), so
  // the anchor block reads as confirmation and the modeller types a diameter
  // and hits Enter. With nothing selected the face pick is ARMED on open, so
  // clicking a face just takes it — no arming step, which is the other half of
  // the "must select the same face twice" complaint.
  const openCreateHole = useCallback(() => {
    const seed = preselectedFace(usePreselectStore.getState(), bodyFeatureId);
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "hole",
      mode: "create",
      initial: defaultHoleForm(seed, lengthUnit),
    });
    setHolePickError(null);
    setHolePick(seed === null ? "face" : null);
  }, [bodyFeatureId, lengthUnit]);

  // A mirror, like pattern/fillet/shell, reflects the current BODY about a
  // plane (no sketch profile) — it only needs a solid to exist (canModify), so
  // it mirrors those guards. v1 needs only a plane choice: no face/point pick.
  const openCreateMirror = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({ kind: "mirror", mode: "create", initial: defaultMirrorForm() });
  }, []);

  // A datum plane needs no sketch/body — it's a construction plane parallel to
  // an origin datum. Available as soon as the tree exists (its own feature row).
  const openCreateDatum = useCallback(() => {
    const seed = preselectedFace(usePreselectStore.getState(), bodyFeatureId);
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    // A selected face means "a plane on THIS" (UI-W3) — the datum opens as an
    // on_face datum sitting on it, instead of the generic 30 mm-above-XY form.
    setEditor({
      kind: "datum",
      mode: "create",
      initial: defaultDatumForm(seed),
    });
  }, [bodyFeatureId]);

  // A base flange thickens a sketch profile to gauge — the sheet-metal part's
  // first body (sheet-metal.md §4.1). Like extrude it needs a solved sketch to
  // consume, so it mirrors openCreateExtrude's profile guard.
  const openCreateBaseFlange = useCallback(() => {
    const profileId = defaultProfileId(tree.data?.features ?? []);
    if (profileId === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "baseFlange",
      mode: "create",
      initial: defaultBaseFlangeForm(profileId),
    });
  }, [tree.data]);

  // An edge flange folds a leg off ONE picked straight edge of the sheet body
  // (sheet-metal.md §4.2). It picks like fillet/chamfer (single-select), so it
  // only needs a sheet body to exist.
  const openCreateEdgeFlange = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "edgeFlange",
      mode: "create",
      initial: defaultEdgeFlangeForm(),
      // ONE edge folds a flange, so a multi-edge selection seeds its most
      // recent member rather than an arbitrary one (UI-W3).
      initialPicked: [
        ...preselectedEdges(usePreselectStore.getState(), bodyFeatureId, 1),
      ],
    });
  }, [bodyFeatureId]);

  // A closed hem folds ONE picked straight edge 180° back onto the sheet
  // (parity §2). It picks like an edge flange (single-select), so it only needs
  // a sheet body to exist.
  const openCreateHem = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "hem",
      mode: "create",
      initial: defaultHemForm(),
      initialPicked: [
        ...preselectedEdges(usePreselectStore.getState(), bodyFeatureId, 1),
      ],
    });
  }, [bodyFeatureId]);

  // A corner relief notches the shared corner of two edge flanges (parity §4.4).
  // It references two edge-flange FEATURES (not an edge pick), so it seeds the
  // first two edge flanges in tree order; the user retargets either in the form.
  const openCreateCornerRelief = useCallback(() => {
    const opts = edgeFlangeOptions(tree.data?.features ?? []);
    const a = opts[0]?.id ?? "";
    const b = opts[1]?.id ?? "";
    if (a === "" || b === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "cornerRelief",
      mode: "create",
      initial: defaultCornerReliefForm(a, b),
    });
  }, [tree.data]);

  // Flat pattern (sheet-metal.md §7): unfold the sheet body onto a lone drawing
  // sheet, so the model → flatten loop is click-through from the part. It
  // creates a drawing named after the part (a numeric suffix dodges a name
  // clash), a sheet, and a single flat_pattern view, then opens the drawing —
  // where the reused flat-pattern renderer draws the blank + bend table. A
  // non-sheet-metal part composes an honest `flat_pattern_not_sheet_metal` view
  // there, never a crash.
  const openFlatPattern = useCallback(() => {
    if (flatPatternBusy) return;
    setFlatPatternBusy(true);
    setFlatPatternError(null);
    void (async () => {
      try {
        const baseName = `${part.data?.name ?? "Part"} — flat pattern`;
        let drawing = null;
        for (let attempt = 0; attempt < 6 && drawing === null; attempt += 1) {
          const name = attempt === 0 ? baseName : `${baseName} ${attempt + 1}`;
          try {
            drawing = await createDrawing(name);
          } catch (error) {
            if (error instanceof DrawingNameTakenError) continue;
            throw error;
          }
        }
        if (drawing === null) {
          throw new Error("A drawing for this flat pattern already exists.");
        }
        const sheet = await createSheet(drawing.id, {
          name: "Sheet 1",
          size: "A4",
          orientation: "landscape",
          projection: "third_angle",
          expected_version: drawing.doc_version,
        });
        const dims = sheetDimensions("A4", "landscape");
        await createView(drawing.id, sheet.sheet.id, {
          projection: "flat_pattern",
          ref_document_id: partId,
          ref_document_kind: "part",
          scale: { numerator: 1, denominator: 1 },
          position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
          auto_place: true,
          expected_version: sheet.doc_version,
        });
        await navigate({
          to: "/drawings/$drawingId",
          params: { drawingId: drawing.id },
        });
      } catch (error) {
        setFlatPatternError(
          error instanceof Error
            ? error.message
            : "The flat pattern could not be opened.",
        );
      } finally {
        setFlatPatternBusy(false);
      }
    })();
  }, [flatPatternBusy, part.data, partId, navigate]);

  // Combine needs ≥2 bodies to fuse (a boolean union names two of them). It
  // seeds the first two bodies in tree order; the user retargets either.
  const openCreateCombine = useCallback(() => {
    if (bodies.length < 2) return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "combine",
      mode: "create",
      initial: defaultCombineForm(bodies),
    });
  }, [bodies]);

  const selectFeature = useCallback(
    (feature: FeatureResponse) => {
      useMeasureStore.getState().deactivate();
      setSelectedFeatureId(feature.id);
      setEditorError(null);
      if (feature.feature.type === "extrude") {
        setEditor({
          kind: "extrude",
          mode: "edit",
          featureId: feature.id,
          initial: formFromParams(feature.feature.params, lengthUnit),
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
          initial: formFromPatternParams(feature.feature.params, lengthUnit),
        });
      } else if (feature.feature.type === "fillet") {
        setEditor({
          kind: "fillet",
          mode: "edit",
          featureId: feature.id,
          initial: formFromFilletParams(feature.feature.params, lengthUnit),
          initialPicked: pickedFromFilletParams(feature.feature.params),
        });
      } else if (feature.feature.type === "chamfer") {
        setEditor({
          kind: "chamfer",
          mode: "edit",
          featureId: feature.id,
          initial: formFromChamferParams(feature.feature.params, lengthUnit),
          initialPicked: pickedFromChamferParams(feature.feature.params),
        });
      } else if (feature.feature.type === "shell") {
        setEditor({
          kind: "shell",
          mode: "edit",
          featureId: feature.id,
          initial: formFromShellParams(feature.feature.params, lengthUnit),
          initialPickedFaces: pickedFacesFromShellParams(
            feature.feature.params,
          ),
        });
      } else if (feature.feature.type === "draft") {
        setEditor({
          kind: "draft",
          mode: "edit",
          featureId: feature.id,
          initial: formFromDraftParams(feature.feature.params, lengthUnit),
          initialPickedFaces: pickedFacesFromDraftParams(
            feature.feature.params,
          ),
        });
      } else if (feature.feature.type === "hole") {
        setEditor({
          kind: "hole",
          mode: "edit",
          featureId: feature.id,
          initial: formFromHoleParams(feature.feature.params, lengthUnit),
        });
      } else if (feature.feature.type === "mirror") {
        setEditor({
          kind: "mirror",
          mode: "edit",
          featureId: feature.id,
          initial: formFromMirrorParams(feature.feature.params),
        });
      } else if (feature.feature.type === "sheet_metal_base_flange") {
        setEditor({
          kind: "baseFlange",
          mode: "edit",
          featureId: feature.id,
          initial: formFromBaseFlangeParams(feature.feature.params, lengthUnit),
        });
      } else if (feature.feature.type === "sheet_metal_edge_flange") {
        setEditor({
          kind: "edgeFlange",
          mode: "edit",
          featureId: feature.id,
          initial: formFromEdgeFlangeParams(feature.feature.params, lengthUnit),
          initialPicked: pickedFromEdgeFlangeParams(feature.feature.params),
        });
      } else if (feature.feature.type === "sheet_metal_hem") {
        setEditor({
          kind: "hem",
          mode: "edit",
          featureId: feature.id,
          initial: formFromHemParams(feature.feature.params, lengthUnit),
          initialPicked: pickedFromHemParams(feature.feature.params),
        });
      } else if (feature.feature.type === "sheet_metal_corner_relief") {
        setEditor({
          kind: "cornerRelief",
          mode: "edit",
          featureId: feature.id,
          initial: formFromCornerReliefParams(
            feature.feature.params,
            lengthUnit,
          ),
        });
      } else if (feature.feature.type === "datum") {
        // Every datum kind is editable here — offset / offset-from / midplane /
        // on_face. A face-referencing datum (on_face or a midplane FACE-side)
        // seeds its picked face(s) from the stored signature; the editor arms a
        // re-pick through the same FacePickOverlay it authored them with.
        setEditor({
          kind: "datum",
          mode: "edit",
          featureId: feature.id,
          initial: formFromDatumParams(feature.feature.params, lengthUnit),
        });
      } else {
        setEditor(null);
      }
    },
    [lengthUnit],
  );

  // Re-pick repair for a `subshape_unresolved` feature error (FINDINGS #3). The
  // kernel re-matches a same-face reference resiliently, so this fires only for a
  // GENUINELY lost face; the one-click fix opens the feature's editor and re-arms
  // its FACE pick, so the user re-attaches the reference through the same overlay
  // that authored it. Batched with selectFeature: the hole pick-session effect
  // only clears `holePick` when the open editor is NOT a hole, and after this
  // render the editor IS the hole, so the armed pick survives.
  const repickFace = useCallback(
    (feature: FeatureResponse) => {
      selectFeature(feature);
      if (feature.feature.type === "hole") {
        setHolePickError(null);
        setHolePick("face");
      }
    },
    [selectFeature],
  );

  const closeEditor = useCallback(() => {
    setEditor(null);
    setEditorError(null);
    setExtrudePreview(null);
  }, []);

  // Global cancel for an open feature editor (FINDINGS #11). The command band
  // advertises "CANCEL ESC", so Escape MUST disarm the editor from any focus —
  // the per-editor onKeyDown only fires when focus is inside the panel, so with
  // focus in the viewport the band's own promise was dead and the toolbar stayed
  // locked. This window-level handler is the ONE cancel path every editor's
  // Cancel cell also routes through (`closeEditor`); the editors no longer carry
  // their own Escape branch (DRY). It stands down while a hole/datum face pick is
  // armed — those pick handlers own Escape then (first Escape disarms the pick,
  // staying in the editor), exactly the cascade the Hole/Datum editors deferred
  // to before. Not registered in sketch mode (the sketch cascade owns Escape).
  useEffect(() => {
    if (mode !== "off" || editor === null) return;
    if (datumFacePick !== null || holePick !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      event.preventDefault();
      closeEditor();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, editor, datumFacePick, holePick, closeEditor]);

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
    } else if (
      editor !== null &&
      (editor.kind === "edgeFlange" || editor.kind === "hem")
    ) {
      // An edge flange / hem always picks (a lone straight edge to fold) —
      // single-select: a click replaces the pick rather than accumulating a set.
      store.open(editor.initialPicked, true, true);
    } else {
      store.close();
    }
  }, [editor]);
  // Leaving the workspace tears the edge-pick session down.
  useEffect(() => () => useEdgePickStore.getState().close(), []);

  // Corner-relief bend highlight (SM-relief-ui-1): the editor mirrors its live
  // Bend A / Bend B selection up, PartPage resolves each id to its flange's
  // stored fold-edge signature, and the viewport draws the bend line + tag
  // (`BendHighlightOverlay`) — the in-scene answer to which select option is
  // which physical corner. Cleared whenever the corner-relief editor closes.
  const [reliefBends, setReliefBends] = useState<{
    a: string;
    b: string;
  } | null>(null);
  const onReliefBendsChange = useCallback(
    (a: string, b: string) => setReliefBends({ a, b }),
    [],
  );
  useEffect(() => {
    if (editor === null || editor.kind !== "cornerRelief") {
      setReliefBends(null);
    }
  }, [editor]);
  const reliefBendHighlights = useMemo(() => {
    if (editor?.kind !== "cornerRelief" || reliefBends === null) return [];
    return cornerReliefBendHighlights(features, reliefBends.a, reliefBends.b);
  }, [editor, reliefBends, features]);

  // Edge-flange width-extent preview (§4.5.1): the editor mirrors its live
  // Full / Centered / Offset span up, and the viewport draws it ON the picked
  // edge (`FlangeSpanOverlay`) — the in-scene answer to the chosen extent.
  // Cleared whenever the edge-flange editor closes.
  const [edgeFlangeSpan, setEdgeFlangeSpan] =
    useState<EdgeFlangeSpanPreview | null>(null);
  const onEdgeFlangeSpanChange = useCallback(
    (span: EdgeFlangeSpanPreview | null) => setEdgeFlangeSpan(span),
    [],
  );
  useEffect(() => {
    if (editor?.kind !== "edgeFlange") setEdgeFlangeSpan(null);
  }, [editor]);
  const edgeFlangeSpanLabel = useMemo(
    () =>
      edgeFlangeSpan === null
        ? ""
        : formatLength(edgeFlangeSpan.spanMm, lengthUnit, { unitSuffix: true }),
    [edgeFlangeSpan, lengthUnit],
  );

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

  // ---------------------------------------------------------------------
  // Pre-selection mirror (UI-W3). The in-canvas overlays write their picks to
  // the edge/face pick stores, which are SESSION state — closing the editor
  // wipes them. These two effects copy the live picks out to the pre-selection
  // while a session is open, so the selection survives the command that made
  // it and the next command opens seeded. Guarded on `active`, so the store's
  // own teardown (`close()` → picked: []) never erases what it just published.
  // ---------------------------------------------------------------------
  const shellPickedFaces = useFacePickStore((s) => s.picked);
  const shellSessionOpen = useFacePickStore((s) => s.active);
  useEffect(() => {
    if (!shellSessionOpen || bodyFeatureId === null) return;
    usePreselectStore.getState().rememberFaces(
      shellPickedFaces.map((signature) => ({
        signature,
        anchorId: bodyFeatureId,
      })),
    );
  }, [shellSessionOpen, shellPickedFaces, bodyFeatureId]);

  const edgePickedEdges = useEdgePickStore((s) => s.picked);
  const edgeSessionOpen = useEdgePickStore((s) => s.active);
  useEffect(() => {
    if (!edgeSessionOpen) return;
    usePreselectStore.getState().rememberEdges(edgePickedEdges, bodyFeatureId);
  }, [edgeSessionOpen, edgePickedEdges, bodyFeatureId]);

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
          setLastSavedFeatureId(response.feature.id);
          setRebuildNoticeDismissed(false);
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

  const submitMirror = useCallback(
    (params: MirrorParams) => {
      const current = editor;
      if (current === null || current.kind !== "mirror") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "mirror").length + 1;
      runFeatureSave(
        (version) => mirrorFeatureCreate(`Mirror${nextIndex}`, params, version),
        (version) => mirrorFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The mirror could not be saved.",
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

  const submitHole = useCallback(
    (params: HoleParams) => {
      const current = editor;
      if (current === null || current.kind !== "hole") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "hole").length + 1;
      runFeatureSave(
        (version) => holeFeatureCreate(`Hole${nextIndex}`, params, version),
        (version) => holeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The hole could not be saved.",
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

  const submitBaseFlange = useCallback(
    (params: SheetMetalBaseFlangeParams) => {
      const current = editor;
      if (current === null || current.kind !== "baseFlange") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_base_flange")
          .length + 1;
      runFeatureSave(
        (version) =>
          baseFlangeFeatureCreate(`Base flange${nextIndex}`, params, version),
        (version) => baseFlangeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The base flange could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitEdgeFlange = useCallback(
    (params: SheetMetalEdgeFlangeParams) => {
      const current = editor;
      if (current === null || current.kind !== "edgeFlange") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_edge_flange")
          .length + 1;
      runFeatureSave(
        (version) =>
          edgeFlangeFeatureCreate(`Edge flange${nextIndex}`, params, version),
        (version) => edgeFlangeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The edge flange could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitHem = useCallback(
    (params: SheetMetalHemParams) => {
      const current = editor;
      if (current === null || current.kind !== "hem") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_hem").length + 1;
      runFeatureSave(
        (version) => hemFeatureCreate(`Hem${nextIndex}`, params, version),
        (version) => hemFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The hem could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitCornerRelief = useCallback(
    (params: SheetMetalCornerReliefParams) => {
      const current = editor;
      if (current === null || current.kind !== "cornerRelief") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_corner_relief")
          .length + 1;
      runFeatureSave(
        (version) =>
          cornerReliefFeatureCreate(
            `Corner relief${nextIndex}`,
            params,
            version,
          ),
        (version) => cornerReliefFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The corner relief could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitCombine = useCallback(
    (params: BooleanParams) => {
      const current = editor;
      if (current === null || current.kind !== "combine") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "boolean").length + 1;
      runFeatureSave(
        (version) =>
          booleanFeatureCreate(`Combine${nextIndex}`, params, version),
        // A boolean is create-only in MB-1 (its operands are fixed at authoring);
        // the update arm is never taken but keeps runFeatureSave's shape.
        (version) => ({
          expected_tree_version: version,
          feature: { type: "boolean", version: 1, params },
        }),
        true,
        undefined,
        "The bodies could not be combined.",
      );
    },
    [editor, features, runFeatureSave],
  );

  // Guided recovery for a `boolean_disjoint` rebuild error (MB-4c): re-run the
  // failing boolean with `allow_disjoint` on, so its disconnected pieces become
  // ONE multi-lump body instead of a dead-end error. An in-place PATCH of the
  // existing boolean feature (never a second boolean) — freshest tree version,
  // retry once on a stale-version race, then refresh the tree + body.
  const [disjointRecovering, setDisjointRecovering] = useState(false);
  const keepAsOneBody = useCallback(
    (feature: FeatureResponse) => {
      if (feature.feature.type !== "boolean") return;
      const params: BooleanParams = {
        ...feature.feature.params,
        allow_disjoint: true,
      };
      setDisjointRecovering(true);
      void (async () => {
        try {
          const attempt = (version: number) =>
            updateFeature(partId, feature.id, {
              expected_tree_version: version,
              feature: { type: "boolean", version: 1, params },
            });
          try {
            await attempt(await freshTreeVersion());
          } catch {
            await attempt((await fetchFeatureTree(partId)).tree_version);
          }
          setSelectedFeatureId(feature.id);
          await refreshTreeAndBody();
        } catch {
          // A hard failure leaves the boolean_disjoint error row in place — the
          // recovery button reappears so the user can retry. Nothing changed.
        } finally {
          setDisjointRecovering(false);
        }
      })();
    },
    [partId, freshTreeVersion, refreshTreeAndBody],
  );

  // Suppress toggle (feature-tree.md §4.3a): flip a feature's suppress flag so a
  // rebuild SKIPS it (the body builds off the non-suppressed prefix) — the row
  // stays in the tree, just dimmed. A minimal, param-untouching mutation; like
  // every tree write it takes the freshest tree version and refreshes the tree +
  // body. On a stale-version race (422) it refetches the fresh version and
  // retries once (OCC soft-resync, matching moveRollback / keepAsOneBody) so the
  // toggle can never leave the UI out of sync.
  const [suppressingId, setSuppressingId] = useState<string | null>(null);
  const toggleSuppress = useCallback(
    (feature: FeatureResponse) => {
      if (suppressingId !== null) return;
      const next = !(feature.feature.suppressed ?? false);
      // Rebuilding the body invalidates a mid-measure pick index — disarm the
      // tool, as every other tree-mutating path does.
      useMeasureStore.getState().deactivate();
      setSuppressingId(feature.id);
      void (async () => {
        try {
          const attempt = (version: number) =>
            suppressFeature(partId, feature.id, next, version);
          try {
            await attempt(await freshTreeVersion());
          } catch (error) {
            if (error instanceof StaleTreeVersionError) {
              await attempt((await fetchFeatureTree(partId)).tree_version);
            } else {
              throw error;
            }
          }
          setSelectedFeatureId(feature.id);
          await refreshTreeAndBody();
        } catch {
          // A hard failure leaves the feature as it was; the toggle stays put so
          // the user can retry. Nothing changed.
        } finally {
          setSuppressingId(null);
        }
      })();
    },
    [partId, suppressingId, freshTreeVersion, refreshTreeAndBody],
  );

  // Select a body from the Bodies panel: select its base feature — lights the
  // brass rule in both panels and opens that feature's editor (the same select
  // a tree row does). Per-body viewport highlight is MB-4.
  const selectBody = useCallback(
    (baseFeatureId: string) => {
      const feature = features.find((f) => f.id === baseFeatureId);
      if (feature !== undefined) selectFeature(feature);
    },
    [features, selectFeature],
  );

  // ---------------------------------------------------------------------
  // Right-click context menus (UI-REVIEW 2026-07-24 #10). Two surfaces, one
  // reusable primitive: the viewport menu (view snaps, tools, selection) and
  // the feature-tree row menu (edit / suppress / rename / delete). Both hold
  // only WIRED actions — a decorative menu row is a defect (mandate 3a).
  // ---------------------------------------------------------------------
  const [viewportMenu, setViewportMenu] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [treeMenu, setTreeMenu] = useState<{
    x: number;
    y: number;
    feature: FeatureResponse;
  } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [treeActionError, setTreeActionError] = useState<string | null>(null);

  /**
   * ASK BEFORE DESTROYING (UI-REVIEW F3). Delete used to fire straight off the
   * context menu with no confirmation and no dependency check; a user found out
   * what it broke when the extrude turned red on the next evaluate.
   *
   * The ask is a real question to the SERVER — `GET …/dependents`, answered by
   * the same query the delete's 409 is built from — so the confirmation names
   * the features and drawings that break, and when there are any the delete is
   * not offered at all (the server would refuse it, and a button that cannot
   * work is worse than no button). While the ask is in flight nothing is shown
   * and nothing is destroyed.
   */
  const [deleteIntent, setDeleteIntent] = useState<{
    feature: FeatureResponse;
    dependents: FeatureDependent[];
  } | null>(null);

  const requestDeleteFeature = useCallback(
    (feature: FeatureResponse) => {
      if (deletingId !== null) return;
      useMeasureStore.getState().deactivate();
      setTreeActionError(null);
      void (async () => {
        try {
          const dependents = await fetchFeatureDependents(partId, feature.id);
          setDeleteIntent({ feature, dependents });
        } catch (error) {
          setTreeActionError(
            error instanceof Error
              ? error.message
              : "What depends on this feature could not be read.",
          );
        }
      })();
    },
    [partId, deletingId],
  );

  // Delete a feature (OCC, stale-version retry once) — the same write grammar
  // suppress uses; a hard failure surfaces the server's message, never silent.
  const deleteFeatureAction = useCallback(
    (feature: FeatureResponse) => {
      if (deletingId !== null) return;
      useMeasureStore.getState().deactivate();
      setDeletingId(feature.id);
      setTreeActionError(null);
      void (async () => {
        try {
          const attempt = (version: number) =>
            deleteFeature(partId, feature.id, version);
          try {
            await attempt(await freshTreeVersion());
          } catch (error) {
            if (error instanceof StaleTreeVersionError) {
              await attempt((await fetchFeatureTree(partId)).tree_version);
            } else {
              throw error;
            }
          }
          if (selectedFeatureId === feature.id) {
            setSelectedFeatureId(null);
            closeEditor();
          }
          if (renamingId === feature.id) setRenamingId(null);
          setDeleteIntent(null);
          await refreshTreeAndBody();
        } catch (error) {
          // A clean pre-check is not a promise: another client could have added
          // a reference in between, and the delete re-checks under the row lock.
          // Re-open the confirmation with the names the REFUSAL carried, rather
          // than reducing them to an error string.
          if (error instanceof FeatureHasDependentsError) {
            setDeleteIntent({ feature, dependents: error.dependents });
          } else {
            setDeleteIntent(null);
            setTreeActionError(
              error instanceof Error
                ? error.message
                : "The feature could not be deleted.",
            );
          }
        } finally {
          setDeletingId(null);
        }
      })();
    },
    [
      partId,
      deletingId,
      selectedFeatureId,
      renamingId,
      freshTreeVersion,
      refreshTreeAndBody,
      closeEditor,
    ],
  );

  // Commit an inline rename: a no-op when unchanged/blank (the field just
  // closes); otherwise a minimal name-only PATCH (never touches params).
  const commitRename = useCallback(
    (feature: FeatureResponse, nextName: string) => {
      const name = nextName.trim();
      setRenamingId(null);
      if (name === "" || name === feature.name) return;
      setTreeActionError(null);
      void (async () => {
        try {
          const attempt = (version: number) =>
            renameFeature(partId, feature.id, name, version);
          try {
            await attempt(await freshTreeVersion());
          } catch (error) {
            if (error instanceof StaleTreeVersionError) {
              await attempt((await fetchFeatureTree(partId)).tree_version);
            } else {
              throw error;
            }
          }
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
        } catch (error) {
          setTreeActionError(
            error instanceof Error
              ? error.message
              : "The feature could not be renamed.",
          );
        }
      })();
    },
    [partId, freshTreeVersion, queryClient],
  );

  // Viewport right-click: open the menu at the pointer, but only when the view
  // rig owns the camera (mode off) — sketch/plane modes own their own gestures.
  const openViewportMenu = useCallback(
    (event: ReactMouseEvent) => {
      if (mode !== "off") return;
      event.preventDefault();
      setTreeMenu(null);
      setViewportMenu({ x: event.clientX, y: event.clientY });
    },
    [mode],
  );

  // Feature-row right-click: open the row menu at the pointer.
  const openTreeMenu = useCallback(
    (feature: FeatureResponse, x: number, y: number) => {
      setViewportMenu(null);
      setTreeMenu({ x, y, feature });
    },
    [],
  );

  // "Sketch on face" from the viewport menu: begin a sketch and arm the
  // face-pick step (the same flow the sketch strip's "Pick face" button drives).
  const startSketchOnFace = useCallback(() => {
    handleNewSketch();
    setFacePicking(true);
    setFacePlaneError(null);
  }, [handleNewSketch]);

  // The inline "sketch at a height" path: author a datum feature, then enter
  // the sketcher on it. One extra field, not a separate multi-step ritual —
  // the datum write returns the feature id the sketch's plane FeatureRef needs.
  const authorOffsetPlane = useCallback(
    (params: DatumOffsetParams) => {
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
    (
      face: { signature: PlanarFaceSignature; index?: number },
      options: { remember?: boolean } = {},
    ) => {
      const featureList = tree.data?.features ?? [];
      const anchorId = lastBodyFeatureId(featureList);
      if (anchorId === null) {
        setFacePlaneError(
          "Add a feature that creates a body before sketching on a face.",
        );
        return;
      }
      const { signature } = face;
      // A face clicked in the viewport is remembered for the next command
      // (UI-W3); a face that CAME from the pre-selection is not re-remembered.
      if (options.remember !== false) {
        usePreselectStore.getState().rememberFaces([{ signature, anchorId }]);
      }
      const nextIndex =
        featureList.filter((f) => f.feature.type === "datum").length + 1;
      setFacePlaneBusy(true);
      setPendingFaceIndex(face.index ?? null);
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

  /**
   * New sketch — ON the pre-selected face when there is one (UI-W3).
   *
   * Selecting a face and asking for a sketch is an unambiguous instruction, and
   * making the user re-pick the face they just picked is exactly the friction
   * the founder reported. With nothing selected this is the plane picker as
   * before; the picker is the fallback, not the toll booth.
   */
  const startSketch = useCallback(() => {
    const seed = preselectedFace(usePreselectStore.getState(), bodyFeatureId);
    handleNewSketch();
    if (seed !== null) {
      authorFacePlane({ signature: seed.signature }, { remember: false });
    }
  }, [bodyFeatureId, handleNewSketch, authorFacePlane]);

  // Datum-editor face picking. Arming a slot highlights the body's planar faces
  // in the viewport (the shared FacePickOverlay); a click resolves to a
  // full-precision signature the editor folds into that slot. The anchor is the
  // last body-affecting feature — the same rule sketch-on-face uses.
  const toggleDatumFacePick = useCallback(
    (slot: DatumFaceSlot) => {
      if (!hasBody) {
        setDatumFacePickError(
          "Add a feature that creates a body before picking a face.",
        );
        return;
      }
      setDatumFacePickError(null);
      setDatumFacePick((current) => (current === slot ? null : slot));
    },
    [hasBody],
  );

  const pickDatumFace = useCallback(
    (face: OverlayFace & { signature: PlanarFaceSignature }) => {
      const slot = datumFacePick;
      if (slot === null) return;
      const anchorId = lastBodyFeatureId(tree.data?.features ?? []);
      if (anchorId === null) {
        setDatumFacePickError(
          "Add a feature that creates a body before picking a face.",
        );
        setDatumFacePick(null);
        return;
      }
      datumFacePickNonce.current += 1;
      setDatumFacePicked({
        nonce: datumFacePickNonce.current,
        slot,
        face: { signature: face.signature, anchorId },
      });
      // Remembered for the next command (UI-W3).
      usePreselectStore
        .getState()
        .rememberFaces([{ signature: face.signature, anchorId }]);
      setDatumFacePick(null);
    },
    [datumFacePick, tree.data],
  );

  // The datum face-pick session ends whenever the datum editor closes (or the
  // seat holds a different editor) — drop the armed slot, the pending pick, and
  // any pick error so a reopened editor starts clean (the nonce guard already
  // stops a stale pick re-folding, but a cleared session is the honest state).
  useEffect(() => {
    if (editor?.kind !== "datum") {
      setDatumFacePick(null);
      setDatumFacePicked(null);
      setDatumFacePickError(null);
    }
  }, [editor]);

  // Escape disarms an armed datum face pick (staying in the editor) — the most
  // local cancel, mirroring the sketch-on-face Escape. Registered only while a
  // pick is armed; the editor's own Escape (cancel) stands down in that window.
  useEffect(() => {
    if (datumFacePick === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setDatumFacePick(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [datumFacePick]);

  // Hole authoring picks. Arming a target highlights the body (faces for the
  // placement face, points on the face for the drill point); a click resolves
  // to a full-precision signature / world point the editor folds in. The face
  // anchor is the last body-affecting feature — the same rule sketch-on-face and
  // the datum picker use.
  const toggleHolePick = useCallback(
    (target: HolePickTarget) => {
      if (!hasBody) {
        setHolePickError(
          "Add a feature that creates a body before drilling a hole.",
        );
        return;
      }
      setHolePickError(null);
      setHolePick((current) => (current === target ? null : target));
    },
    [hasBody],
  );

  const pickHoleFace = useCallback(
    (face: OverlayFace & { signature: PlanarFaceSignature }) => {
      const anchorId = lastBodyFeatureId(tree.data?.features ?? []);
      if (anchorId === null) {
        setHolePickError(
          "Add a feature that creates a body before drilling a hole.",
        );
        setHolePick(null);
        return;
      }
      holePickNonce.current += 1;
      setHoleFacePicked({
        nonce: holePickNonce.current,
        face: { signature: face.signature, anchorId },
      });
      // The pick outlives this editor (UI-W3): cancel the hole and invoke
      // Datum, or Sketch, and the face is already chosen.
      usePreselectStore
        .getState()
        .rememberFaces([{ signature: face.signature, anchorId }]);
      // A face chosen → disarm (the editor seeds the point to the centre); the
      // user arms the POINT pick next to refine the placement.
      setHolePick(null);
    },
    [tree.data],
  );

  const pickHolePoint = useCallback((point: Vec3) => {
    holePickNonce.current += 1;
    setHolePointPicked({ nonce: holePickNonce.current, position: point });
    setHolePick(null);
  }, []);

  const onHolePreviewChange = useCallback(
    (preview: HolePreview | null) => setHolePreview(preview),
    [],
  );

  // The hole pick session ends whenever the hole editor closes (or the seat
  // holds a different editor) — drop the armed target, pending picks, preview,
  // and any error so a reopened editor starts clean.
  useEffect(() => {
    if (editor?.kind !== "hole") {
      setHolePick(null);
      setHoleFacePicked(null);
      setHolePointPicked(null);
      setHolePickError(null);
      setHolePreview(null);
    }
  }, [editor]);

  // Escape disarms an armed hole pick (staying in the editor) — the most local
  // cancel, mirroring the datum face pick. Registered only while a pick is armed.
  useEffect(() => {
    if (holePick === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setHolePick(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [holePick]);

  // ---------------------------------------------------------------------
  // Undo/redo (docs/design/undo-redo.md §UR2). History is SERVER-side snapshot
  // state: the tree GET's can_undo/can_redo gate the controls, and a step is a
  // document edit under the same tree-version OCC as every other write. The
  // restored tree re-renders through the SAME post-mutation refresh path all
  // feature saves use — never a second pipeline.
  // ---------------------------------------------------------------------
  const canUndo = tree.data?.can_undo ?? false;
  const canRedo = tree.data?.can_redo ?? false;
  /** Which step is in flight (drives the honest hold caption), or null. */
  const [historyStep, setHistoryStep] = useState<HistoryStep | null>(null);
  const historyInFlight = useRef(false);
  /** A non-stale undo/redo failure, surfaced in the viewport HUD. */
  const [historyError, setHistoryError] = useState<HistoryStepError | null>(
    null,
  );

  const runHistoryStep = useCallback(
    (step: HistoryStep) => {
      // One tree rewrite at a time: repeats (held key / double click) AND an
      // in-flight rollback-bar move are ignored until the write settles —
      // history and the bar mutually exclude (both rewrite the tree; the OCC
      // would 422 the loser, but the bar's blind retry must never run against
      // a freshly restored tree).
      if (historyInFlight.current || rollbackBusy) return;
      historyInFlight.current = true;
      setHistoryStep(step);
      setHistoryError(null);
      void (async () => {
        try {
          // The shared engine (lib/historyStep, also driving the assembly
          // workspace) runs the sequence; only the part-tree seams live here.
          const outcome = await executeHistoryStep(step, {
            version: freshTreeVersion,
            run: (s, expected) =>
              s === "undo"
                ? undoPart(partId, expected)
                : redoPart(partId, expected),
            versionOf: (tree) => tree.tree_version,
            // Boundary no-op (clean 200): nothing changed — adopt the echoed
            // tree (fresh can_undo/can_redo) without a re-evaluate cycle.
            adoptNoOp: (restored) =>
              queryClient.setQueryData(["features", partId], restored),
            onRestored: async () => {
              // A REAL restore happened: only now disarm measure and drop the
              // selection (the tree is known to have changed under them),
              // then resync through the shared invalidation path.
              useMeasureStore.getState().deactivate();
              setSelectedFeatureId(null);
              await refreshTreeAndBody();
            },
            isStale: (error) => error instanceof StaleTreeVersionError,
            // Someone else moved the tree: the design doc's soft reload —
            // resync quietly; the user re-issues against what they now see.
            resync: () => refreshTreeAndBody(),
          });
          if (outcome.kind === "failed") {
            // The tree is unchanged server-side — say so through the HUD (the
            // import-error affordance), never a silent busy flash.
            setHistoryError({ step, message: outcome.message });
          }
        } finally {
          historyInFlight.current = false;
          setHistoryStep(null);
        }
      })();
    },
    [partId, rollbackBusy, freshTreeVersion, refreshTreeAndBody, queryClient],
  );

  const triggerUndo = useCallback(() => {
    if (canUndo) runHistoryStep("undo");
  }, [canUndo, runHistoryStep]);
  const triggerRedo = useCallback(() => {
    if (canRedo) runHistoryStep("redo");
  }, [canRedo, runHistoryStep]);

  const moveRollback = useCallback(
    (rollbackFeatureId: string | null) => {
      // Mutual exclusion with undo/redo (and drag re-entry): both rewrite the
      // tree, and the bar's blind stale-retry must never land on a tree a
      // history step just restored.
      if (rollbackBusy || historyInFlight.current) return;
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
    [partId, rollbackBusy, freshTreeVersion, refreshTreeAndBody],
  );

  // The last-saved feature's rebuild error (UX audit #20e), surfaced at the
  // editor seat so it reads where the user just clicked Create/Save — not only
  // in the tree across the screen. Dismissible; the next save re-arms it.
  const rebuildNotice = useMemo<string | null>(() => {
    if (lastSavedFeatureId === null || rebuildNoticeDismissed) return null;
    const result = evaluation.data?.features.find(
      (f) => f.feature_id === lastSavedFeatureId,
    );
    return result !== undefined &&
      result.status === "error" &&
      result.error != null
      ? result.error.message
      : null;
  }, [lastSavedFeatureId, rebuildNoticeDismissed, evaluation.data]);

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
  //
  // These are LOCKED behind an open editor exactly like the pointer band is: an
  // open command owns the picks, and firing another opener would `setEditor(...)`
  // over the top, silently discarding the in-progress selection (the keyboard
  // twin of the fillet→extrude pick-loss the pointer lock closes).
  useEffect(() => {
    if (mode !== "off" || editor !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      // The keys come from `shortcuts/registry` — the SAME table the key card
      // prints (UI-REVIEW F4), so a re-keyed verb cannot leave the reference
      // teaching a letter nothing listens for.
      const key = event.key.toLowerCase();
      const openers: Record<string, { open: () => void; enabled: boolean }> = {
        p: { open: openCreatePattern, enabled: hasBody },
        s: { open: openCreateSweep, enabled: canSweep },
        l: { open: openCreateLoft, enabled: canLoft },
        h: { open: openCreateShell, enabled: hasBody },
        d: { open: openCreateDraft, enabled: hasBody },
        o: { open: openCreateHole, enabled: hasBody },
        i: { open: openCreateMirror, enabled: hasBody },
      };
      const opener = PART_CREATE_SHORTCUTS.some((entry) => entry.key === key)
        ? openers[key]
        : undefined;
      if (opener !== undefined && opener.enabled) {
        event.preventDefault();
        opener.open();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    mode,
    editor,
    hasBody,
    canSweep,
    canLoft,
    openCreatePattern,
    openCreateSweep,
    openCreateLoft,
    openCreateShell,
    openCreateDraft,
    openCreateHole,
    openCreateMirror,
  ]);

  // Undo/redo keyboard grammar: Ctrl/⌘+Z, Ctrl/⌘+Shift+Z, Ctrl+Y — model idle
  // only. Sketch mode owns its own buffer (sketch-internal undo is a later,
  // finer-grained layer — docs/design/undo-redo.md "out of v1"), and an open
  // editor locks the band's History tools, so the keys hold to the same gate.
  // A focused text field keeps its NATIVE undo (the typing-target guard is
  // resolved inside the pure grammar helper).
  useEffect(() => {
    if (mode !== "off" || editor !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const step = undoRedoStep(event, isTypingTarget(event.target));
      if (step === null) return;
      // The chord is ours in the workspace even at a history bound — swallow
      // it so the browser never runs its own undo behind the tool.
      event.preventDefault();
      if (step === "undo") triggerUndo();
      else triggerRedo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, editor, triggerUndo, triggerRedo]);

  // The body is the hero: once a solid renders, the profile sketch that
  // defined it recedes (it sits on the body's base face — coincident scribe
  // ink would only z-fight the solid). It returns, live, on sketch re-entry.
  //
  // That rule now lives in the SCENE (`SketchScene`, via `viewport/partView`),
  // as the DEFAULT of a per-sketch view stop rather than as a law the modeler
  // cannot answer back to — UI-W2, founder: "what about the ability to enable
  // planes, sketches and bodies?". The full solved set is handed down and the
  // scene decides which layers draw, so the browser's Sketches rows and the ink
  // on screen read one derivation.
  const bodyPresent = body.data !== undefined;
  // The extrude ghost's profile layer (UI-REVIEW #8): the SOLVED sketch the
  // open extrude editor points at, resolved from the full `solved` set so the
  // ghost shows whether or not a body already exists. Absent until the editor
  // projects a valid form.
  const extrudeGhostLayer = useMemo<SolvedSketchLayer | null>(() => {
    if (extrudePreview === null) return null;
    return (
      solved.find((l) => l.featureId === extrudePreview.profileFeatureId) ??
      null
    );
  }, [extrudePreview, solved]);
  const showExtrudeGhost =
    mode === "off" &&
    editor?.kind === "extrude" &&
    extrudePreview !== null &&
    extrudeGhostLayer !== null;
  // THE ONE SET OF FACTS about the body on screen. The feature tree's SOLVE
  // cell, the inspector's STATUS cell, the EXPORT gate, the SKIP rows and the
  // partial-body notice below all read this object — they used to compute three
  // separate answers, and on a part with a broken feature the same screen said
  // "Failed", "Up to date" and "Ready" at once (AUDIT-ENGINEERING J2).
  const build = useMemo(
    () =>
      derivePartBuild({
        tree: tree.data,
        evaluation: evaluation.data,
        part: part.data,
        evaluating: evaluation.isFetching,
        treeFetching: tree.isFetching,
        regenerating,
        regenFailed,
        meshPending: meshGlbId !== null && !bodyPresent && body.isFetching,
      }),
    [
      tree.data,
      tree.isFetching,
      evaluation.data,
      evaluation.isFetching,
      part.data,
      regenerating,
      regenFailed,
      meshGlbId,
      bodyPresent,
      body.isFetching,
    ],
  );
  // The inspector appears when there's a body to inspect and we're not
  // sketching — sketch mode keeps the viewport dominant (chrome recedes).
  const showInspector = mode === "off" && bodyProperties !== null;
  // With a tree but no body (sketch-only / rolled back before the extrude),
  // still offer the EXPORT strip — disabled and honest about why.
  const showExportOnly =
    mode === "off" &&
    bodyProperties === null &&
    (tree.data?.features.length ?? 0) > 0;

  // A blank part — the tree has loaded with nothing in it and we're at rest.
  // The empty scene gets a first-run call to action (item 13); the grid +
  // atmosphere (Batch 1) already keep it from being a black void.
  const isEmptyPart =
    mode === "off" &&
    editor === null &&
    !measureActive &&
    tree.data !== undefined &&
    features.length === 0;

  // The open command scopes the band + names the mode (breadcrumb + lock).
  // No runtime fallback: COMMAND_LABEL is total over OpenEditor["kind"], so
  // an unmapped editor kind cannot compile, let alone unlock the band.
  const activeCommand = editor === null ? null : COMMAND_LABEL[editor.kind];

  // Context-menu section builders (UI-REVIEW #10). Built on open (cheap), so
  // every item reads the freshest state; each row is a WIRED action.
  const requestView = (
    kind: "fit" | "home" | "front" | "top" | "right" | "iso",
  ) => useViewCommandStore.getState().request(kind);

  const buildViewportSections = (): ContextMenuSection[] => {
    const selected =
      selectedFeatureId === null
        ? undefined
        : features.find((f) => f.id === selectedFeatureId);
    const sections: ContextMenuSection[] = [
      {
        key: "view",
        label: "View",
        items: [
          {
            key: "fit",
            label: "Fit to view",
            icon: <ViewFitIcon />,
            shortcut: "0",
            onSelect: () => requestView("fit"),
            "data-testid": "ctx-view-fit",
          },
          {
            key: "home",
            label: "Home",
            icon: <ViewHomeIcon />,
            shortcut: "Home",
            onSelect: () => requestView("home"),
            "data-testid": "ctx-view-home",
          },
          {
            key: "front",
            label: "Front",
            icon: <ViewFrontIcon />,
            shortcut: "1",
            onSelect: () => requestView("front"),
            "data-testid": "ctx-view-front",
          },
          {
            key: "top",
            label: "Top",
            icon: <ViewTopIcon />,
            shortcut: "2",
            onSelect: () => requestView("top"),
            "data-testid": "ctx-view-top",
          },
          {
            key: "right",
            label: "Right",
            icon: <ViewRightIcon />,
            shortcut: "3",
            onSelect: () => requestView("right"),
            "data-testid": "ctx-view-right",
          },
          {
            key: "iso",
            label: "Isometric",
            icon: <ViewIsoIcon />,
            shortcut: "4",
            onSelect: () => requestView("iso"),
            "data-testid": "ctx-view-iso",
          },
        ],
      },
      {
        key: "tools",
        label: "Tools",
        items: [
          {
            key: "new-sketch",
            label: "New sketch",
            icon: <SketchIcon />,
            onSelect: startSketch,
            "data-testid": "ctx-new-sketch",
          },
          {
            key: "sketch-on-face",
            label: "Sketch on face",
            icon: <DatumIcon />,
            disabled: !hasBody,
            onSelect: startSketchOnFace,
            "data-testid": "ctx-sketch-on-face",
          },
          {
            key: "measure",
            label: measureActive ? "Stop measuring" : "Measure",
            icon: <MeasureIcon />,
            shortcut: "M",
            disabled: !hasBody,
            onSelect: toggleMeasure,
            "data-testid": "ctx-measure",
          },
        ],
      },
    ];
    if (selected !== undefined) {
      const suppressed = selected.feature.suppressed ?? false;
      sections.push({
        key: "selected",
        label: selected.name,
        items: [
          {
            key: "suppress",
            label: suppressed ? "Unsuppress" : "Suppress",
            icon: <SuppressIcon />,
            onSelect: () => toggleSuppress(selected),
            "data-testid": "ctx-selected-suppress",
          },
          {
            key: "delete",
            label: "Delete",
            icon: <CloseIcon />,
            danger: true,
            disabled: deletingId === selected.id,
            onSelect: () => requestDeleteFeature(selected),
            "data-testid": "ctx-selected-delete",
          },
        ],
      });
    }
    return sections;
  };

  const buildTreeSections = (
    feature: FeatureResponse,
  ): ContextMenuSection[] => {
    const suppressed = feature.feature.suppressed ?? false;
    return [
      {
        key: "feature",
        label: feature.name,
        items: [
          {
            key: "edit",
            label: "Edit",
            onSelect: () => selectFeature(feature),
            "data-testid": "tree-ctx-edit",
          },
          {
            key: "rename",
            label: "Rename",
            icon: <SketchIcon />,
            onSelect: () => {
              setSelectedFeatureId(feature.id);
              setRenamingId(feature.id);
            },
            "data-testid": "tree-ctx-rename",
          },
          {
            key: "suppress",
            label: suppressed ? "Unsuppress" : "Suppress",
            icon: <SuppressIcon />,
            onSelect: () => toggleSuppress(feature),
            "data-testid": "tree-ctx-suppress",
          },
          {
            key: "delete",
            label: "Delete",
            icon: <CloseIcon />,
            danger: true,
            disabled: deletingId === feature.id,
            onSelect: () => requestDeleteFeature(feature),
            "data-testid": "tree-ctx-delete",
          },
        ],
      },
    ];
  };

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
    <DocumentUnitProvider unit={lengthUnit}>
      <div className="flex h-full flex-col">
        <TopBar>
          <Breadcrumb
            register="parts"
            documentName={part.data?.name ?? "Part"}
            documentTestId="part-name"
            mode={workspaceMode}
          />
          <DocumentUnitSelect
            value={lengthUnit}
            onChange={changeUnit}
            busy={unitBusy}
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
              canUndo={canUndo}
              canRedo={canRedo}
              historyHold={
                historyStep ?? (rollbackBusy ? ("rollback" as const) : null)
              }
              onUndo={triggerUndo}
              onRedo={triggerRedo}
              onNewSketch={startSketch}
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
              onHole={openCreateHole}
              onMirror={openCreateMirror}
              canBaseFlange={hasSolvedSketch}
              onNewBaseFlange={openCreateBaseFlange}
              canEdgeFlange={isSheetMetal}
              onNewEdgeFlange={openCreateEdgeFlange}
              canHem={isSheetMetal}
              onNewHem={openCreateHem}
              canCornerRelief={canCornerRelief}
              onNewCornerRelief={openCreateCornerRelief}
              canFlatPattern={isSheetMetal}
              flatteningPattern={flatPatternBusy}
              onFlatPattern={openFlatPattern}
              canCombine={bodies.length >= 2}
              onCombine={openCreateCombine}
              canMeasure={hasBody}
              measuring={measureActive}
              onToggleMeasure={toggleMeasure}
              activeCommand={activeCommand}
              onCommandOk={() =>
                useCommandActionStore.getState().requestSubmit()
              }
              onCommandCancel={closeEditor}
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
            onContextMenu={openViewportMenu}
            rotateEnabled={mode !== "draw"}
            groundGrid={mode !== "draw"}
            viewNav={mode === "off"}
            bodyInteractive={
              mode === "off" && editor === null && !measureActive
            }
            bodySelected={
              mode === "off" &&
              !measureActive &&
              (selectedFeatureId !== null || preselectedFaceIndices !== null)
            }
            bodySelectedFaces={selectedFaceIndices ?? preselectedFaceIndices}
            hud={
              <>
                <SketchDro solving={syncPending || evaluation.isFetching} />
                <SolveDiagnostic />
                <MeasureReadout />
                {/* Inert DOM signal that the live extrude ghost is on screen
                    (the ghost itself is WebGL) — a raster-independent hook QA
                    drives the "preview responds before Save" assertion from. */}
                {showExtrudeGhost && extrudePreview !== null ? (
                  <span
                    hidden
                    data-testid="extrude-preview-active"
                    data-distance-mm={extrudePreview.distanceMm}
                    data-direction={extrudePreview.direction}
                    data-operation={extrudePreview.operation}
                  />
                ) : null}
                {isEmptyPart ? (
                  <div
                    data-testid="empty-viewport-hint"
                    className="pointer-events-none absolute left-1/2 top-[42%] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 text-center"
                  >
                    <span className="font-display text-2xs uppercase tracking-[0.24em] text-gauge">
                      Empty part
                    </span>
                    <span className="font-body text-sm text-mist">
                      Start with a <span className="text-brass">Sketch</span> —
                      pick a plane, then draw.
                    </span>
                    <span className="font-body text-xs text-gauge">
                      Or Import a STEP solid as the base body.
                    </span>
                  </div>
                ) : null}
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
                      onPreviewChange={setExtrudePreview}
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
                  ) : editor.kind === "hole" ? (
                    <HoleEditor
                      mode={editor.mode}
                      initial={editor.initial}
                      onSubmit={submitHole}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                      canPickFace={hasBody}
                      activePick={holePick}
                      onTogglePick={toggleHolePick}
                      facePick={holeFacePicked}
                      pointPick={holePointPicked}
                      pickError={holePickError}
                      edges={holeOverlayEdges}
                      onPreviewChange={onHolePreviewChange}
                    />
                  ) : editor.kind === "baseFlange" ? (
                    <BaseFlangeEditor
                      mode={editor.mode}
                      profiles={sketchProfiles}
                      initial={editor.initial}
                      onSubmit={submitBaseFlange}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                    />
                  ) : editor.kind === "edgeFlange" ? (
                    <EdgeFlangeEditor
                      mode={editor.mode}
                      initial={editor.initial}
                      bodyFeatureId={bodyFeatureId}
                      defaults={smDefaults}
                      onSubmit={submitEdgeFlange}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                      onSpanChange={onEdgeFlangeSpanChange}
                    />
                  ) : editor.kind === "hem" ? (
                    <HemEditor
                      mode={editor.mode}
                      initial={editor.initial}
                      bodyFeatureId={bodyFeatureId}
                      defaults={smDefaults}
                      onSubmit={submitHem}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                    />
                  ) : editor.kind === "cornerRelief" ? (
                    <CornerReliefEditor
                      mode={editor.mode}
                      initial={editor.initial}
                      edgeFlanges={edgeFlangeOpts}
                      defaults={smDefaults}
                      onSubmit={submitCornerRelief}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                      onBendsChange={onReliefBendsChange}
                    />
                  ) : editor.kind === "mirror" ? (
                    <MirrorEditor
                      mode={editor.mode}
                      initial={editor.initial}
                      datumPlanes={datumPlaneOptions}
                      onSubmit={submitMirror}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                    />
                  ) : editor.kind === "datum" ? (
                    <DatumEditor
                      mode={editor.mode}
                      initial={editor.initial}
                      datumRefs={datumEditorRefs}
                      onSubmit={submitDatum}
                      onCancel={closeEditor}
                      saving={editorSaving}
                      error={editorError}
                      canPickFace={hasBody}
                      activeFacePickSlot={datumFacePick}
                      onToggleFacePick={toggleDatumFacePick}
                      facePick={datumFacePicked}
                      facePickError={datumFacePickError}
                    />
                  ) : (
                    <CombineEditor
                      bodies={bodies}
                      initial={editor.initial}
                      onSubmit={submitCombine}
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
                {flatPatternBusy ? (
                  <div
                    role="status"
                    data-testid="flat-pattern-status"
                    className="absolute bottom-3 left-3 rounded-sm border border-hairline bg-anvil px-3 py-2"
                  >
                    <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
                      Unfolding flat pattern
                    </span>
                    <span className="mt-1 block font-body text-xs text-mist">
                      Laying the blank onto a drawing sheet.
                    </span>
                  </div>
                ) : flatPatternError !== null ? (
                  <div
                    role="alert"
                    data-testid="flat-pattern-error"
                    className="absolute bottom-3 left-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
                  >
                    <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                      Flat pattern failed
                    </span>
                    <span className="mt-1 block font-body text-xs text-mist">
                      {flatPatternError}
                    </span>
                    <button
                      type="button"
                      onClick={() => setFlatPatternError(null)}
                      data-testid="flat-pattern-dismiss"
                      className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                    >
                      Dismiss
                    </button>
                  </div>
                ) : null}
                <HistoryErrorAlert
                  error={historyError}
                  onDismiss={() => setHistoryError(null)}
                />
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
                ) : editor === null && rebuildNotice !== null ? (
                  <div
                    role="alert"
                    data-testid="rebuild-notice"
                    className="absolute left-editor top-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
                  >
                    <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                      This feature couldn't build
                    </span>
                    <span className="mt-1 block font-body text-xs text-mist">
                      {rebuildNotice}
                    </span>
                    <button
                      type="button"
                      onClick={() => setRebuildNoticeDismissed(true)}
                      data-testid="rebuild-notice-dismiss"
                      className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                    >
                      Dismiss
                    </button>
                  </div>
                ) : editor === null && build.failed && build.hasBody ? (
                  // WHAT YOU ARE LOOKING AT (AUDIT-PRODUCT N3). The strict-prefix
                  // rule renders the last-good PREFIX, so one bad pick can turn a
                  // modelled bracket into a bare brick — and until now nothing on
                  // screen said the solid was not the part. `last_good_feature_id`
                  // was on the wire and unused; it names the state being shown.
                  // NOT dismissible: it describes a live condition, and it leaves
                  // when the condition does.
                  <div
                    role="status"
                    data-testid="partial-body-notice"
                    className="absolute left-editor top-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
                  >
                    <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                      Partial body
                    </span>
                    <span className="mt-1 block font-body text-xs text-mist">
                      {partialBodySentence(build)}
                    </span>
                    {build.failure !== null ? (
                      <button
                        type="button"
                        onClick={() => {
                          const failed = features.find(
                            (f) => f.id === build.failure?.id,
                          );
                          if (failed !== undefined) selectFeature(failed);
                        }}
                        data-testid="partial-body-show-failure"
                        className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                      >
                        Show {build.failure.name}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </>
            }
          >
            <SketchScene solved={solved} facePicking={facePicking} />
            {showExtrudeGhost &&
            extrudeGhostLayer !== null &&
            extrudePreview ? (
              <ExtrudePreview
                layer={extrudeGhostLayer}
                distanceMm={extrudePreview.distanceMm}
                direction={extrudePreview.direction}
                operation={extrudePreview.operation}
              />
            ) : null}
            <MeasureOverlay />
            {mode === "off" && edgePicking ? <EdgePickOverlay /> : null}
            {mode === "off" && reliefBendHighlights.length > 0 ? (
              <BendHighlightOverlay bends={reliefBendHighlights} />
            ) : null}
            {mode === "off" &&
            editor?.kind === "edgeFlange" &&
            edgeFlangeSpan !== null ? (
              <FlangeSpanOverlay
                span={edgeFlangeSpan}
                label={edgeFlangeSpanLabel}
              />
            ) : null}
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
            {mode === "off" &&
            editor?.kind === "datum" &&
            datumFacePick !== null ? (
              <FacePickOverlay
                faces={datumPickableFaces}
                onPick={pickDatumFace}
                pendingIndex={null}
              />
            ) : null}
            {mode === "off" &&
            editor?.kind === "hole" &&
            holePick === "face" ? (
              <FacePickOverlay
                faces={holePickableFaces}
                onPick={pickHoleFace}
                pendingIndex={null}
              />
            ) : null}
            {/* The placement overlay shows from the moment a face exists, not
                only while the point pick is armed: the datum crosshair is what
                says where the editor's X/Y cells count from, and it has to be
                on screen while they are being typed (QA3-1). */}
            {mode === "off" &&
            editor?.kind === "hole" &&
            holePreview?.signature != null ? (
              <HolePointOverlay
                signature={holePreview.signature}
                vertices={holeOverlayVertices}
                edges={holeOverlayEdges}
                position={holePreview.position}
                armed={holePick === "point"}
                onPick={pickHolePoint}
              />
            ) : null}
          </Viewport>
          <FloatingPanel side="left" title="Feature tree" id="tree">
            <div className="flex flex-col gap-3">
              <FeatureTreePanel
                tree={tree.data}
                treeError={tree.error}
                evaluation={evaluation.data}
                build={build}
                selectedFeatureId={selectedFeatureId}
                onSelectFeature={selectFeature}
                onKeepAsOneBody={keepAsOneBody}
                recoveringDisjoint={disjointRecovering}
                onRepickFace={repickFace}
                onToggleSuppress={toggleSuppress}
                suppressingId={suppressingId}
                onRowContextMenu={openTreeMenu}
                renamingId={renamingId}
                onCommitRename={commitRename}
                onCancelRename={() => setRenamingId(null)}
              />
              {bodies.length > 0 ? (
                <BodiesPanel
                  bodies={bodies}
                  lumpsByFeature={lumpsByFeature}
                  selectedFeatureId={selectedFeatureId}
                  onSelectBody={selectBody}
                />
              ) : null}
            </div>
          </FloatingPanel>
          {showInspector ? (
            // The EXPORT strip is PINNED under the panel, not trailing the
            // scrolling readouts: the panel's height is clamped (it clears the
            // reference cube), so whatever sits last in the column is whatever
            // goes under the fold — and on a 1366x768 frame that was the strip
            // plus the sentence warning that the file will be marked *partial*
            // (UI-REVIEW 2026-07-30 P1, a regression of the 48px timeline).
            // Mass properties scroll; the actions never move.
            <FloatingPanel
              side="right"
              title="Inspector"
              id="inspector"
              footer={
                <Panel className="border-t-0">
                  <PartExportControls partId={partId} build={build} />
                </Panel>
              }
            >
              <BodyInspector
                properties={bodyProperties}
                build={build}
                material={materialControls}
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
                  <PartExportControls partId={partId} build={build} />
                </Panel>
              </aside>
            </FloatingPanel>
          ) : null}
          {/* What breaks if this feature goes — asked before it does (F3). */}
          {deleteIntent !== null ? (
            <FeatureDeleteConfirm
              featureName={deleteIntent.feature.name}
              dependents={deleteIntent.dependents}
              pending={deletingId === deleteIntent.feature.id}
              onCancel={() => setDeleteIntent(null)}
              onConfirm={() => deleteFeatureAction(deleteIntent.feature)}
            />
          ) : null}
          {/* Tree-action failure (rename/delete) — honest, dismissible chrome. */}
          {treeActionError !== null ? (
            <div
              role="alert"
              data-testid="tree-action-error"
              className="absolute bottom-3 left-3 z-hud max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
            >
              <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                Action failed
              </span>
              <span className="mt-1 block font-body text-xs text-mist">
                {treeActionError}
              </span>
              <button
                type="button"
                onClick={() => setTreeActionError(null)}
                data-testid="tree-action-error-dismiss"
                className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
              >
                Dismiss
              </button>
            </div>
          ) : null}
        </main>
        {/* THE TIMELINE — docked along the bottom of the frame, the way the
            build travels (UI-W1, founder-directed). In flow, not floating: the
            bottom of the viewport already carries the HUD lane, the reference
            cube and the status banners, and a fourth floating occupant would
            fight all three. */}
        <TimelineStrip
          tree={tree.data}
          evaluation={evaluation.data}
          selectedFeatureId={selectedFeatureId}
          onSelectFeature={selectFeature}
          onMoveRollback={moveRollback}
          // The stop also holds while a history step is restoring (the mutual
          // exclusion's visible half — runHistoryStep guards it).
          busy={rollbackBusy || historyStep !== null}
          onChipContextMenu={openTreeMenu}
        />
      </div>
      {/* Right-click menus (UI-REVIEW #10) — one primitive, two surfaces. */}
      {viewportMenu !== null ? (
        <ContextMenu
          open
          x={viewportMenu.x}
          y={viewportMenu.y}
          aria-label="Viewport actions"
          data-testid="viewport-context-menu"
          sections={buildViewportSections()}
          onClose={() => setViewportMenu(null)}
        />
      ) : null}
      {treeMenu !== null ? (
        <ContextMenu
          open
          x={treeMenu.x}
          y={treeMenu.y}
          aria-label={`Actions for ${treeMenu.feature.name}`}
          data-testid="tree-context-menu"
          sections={buildTreeSections(treeMenu.feature)}
          onClose={() => setTreeMenu(null)}
        />
      ) : null}
    </DocumentUnitProvider>
  );
}
