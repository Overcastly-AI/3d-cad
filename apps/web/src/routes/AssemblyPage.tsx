import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  checkInterference,
  createInstance,
  createMate,
  deleteInstance,
  deleteMate,
  evaluateAssembly,
  exportAssembly,
  fetchAssemblyGraph,
  type InstanceResponse,
  type InterferenceResult,
  type LengthUnit,
  type Mate,
  type MateResponse,
  redoAssembly,
  StaleAssemblyVersionError,
  undoAssembly,
  updateAssemblyUnit,
  updateInstance,
} from "../api/assemblies";
import type { ExportFormat } from "../api/exportPart";
import { fetchAssemblyBom } from "../api/bom";
import { MeshNotFoundError, fetchBodyMesh } from "../api/mesh";
import { fetchOverlay, type OverlayResult } from "../api/measure";
import {
  fetchFeatureTree,
  type FeatureTreeResponse,
  type PartResponse,
} from "../api/parts";
import { AddInstancePanel } from "../components/AddInstancePanel";
import { AssemblyCommandBand } from "../components/AssemblyCommandBand";
import {
  AssemblyInspectorPanel,
  type InspectorView,
} from "../components/AssemblyInspectorPanel";
import { Breadcrumb } from "../components/Breadcrumb";
import { AssemblyTreePanel } from "../components/AssemblyTreePanel";
import {
  HistoryErrorAlert,
  type HistoryStepError,
} from "../components/HistoryErrorAlert";
import { DocumentUnitSelect } from "../components/DocumentUnitSelect";
import { DocumentUnitProvider } from "../units/documentUnit";
import { MateHud } from "../components/MateHud";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import {
  buildEvaluateAssemblyRequest,
  uniquePartDocumentIds,
} from "../assembly/evaluateRequest";
import { buildMate, mateToolLabel } from "../assembly/mates";
import {
  isParametricMate,
  type MateTool,
  useMateAuthoringStore,
} from "../assembly/mateStore";
import { placementToScene } from "../assembly/placement";
import { buildEvaluateTree } from "../measure/geometry";
import { FloatingPanel } from "../components/FloatingPanel";
import { executeHistoryStep } from "../lib/historyStep";
import { isTypingTarget } from "../lib/isTypingTarget";
import { type HistoryStep, undoRedoStep } from "../lib/undoRedoShortcut";
import { useReducedMotion } from "../lib/useReducedMotion";
import { assemblyRoute } from "../router";
import {
  assemblyBounds,
  AssemblyScene,
  type SceneInstance,
} from "../viewport/AssemblyScene";
import { useInstanceGeometries } from "../viewport/useInstanceGeometries";
import { Viewport } from "../viewport/Viewport";

const IDENTITY_QUAT = { w: 1, x: 0, y: 0, z: 0 };

/**
 * The assembly workspace — the sibling of the part editor. The tree (left) is a
 * quiet title block of components + mates; the viewport (hero) draws every
 * instance's shared mesh at its solved pose; the inspector (right) is the solve
 * title block. A new part seeds APART from the others so that authoring a mate
 * and re-solving snaps them together in view — the signature moment.
 */
export function AssemblyPage() {
  const { assemblyId } = assemblyRoute.useParams();
  const queryClient = useQueryClient();
  const reducedMotion = useReducedMotion();

  const graphQuery = useQuery({
    queryKey: ["assembly", assemblyId],
    queryFn: () => fetchAssemblyGraph(assemblyId),
  });
  const graph = graphQuery.data;
  const docVersion = graph?.doc_version ?? 0;
  const lengthUnit = graph?.assembly.length_unit ?? "mm";
  const instances = useMemo(() => graph?.instances ?? [], [graph]);

  // The bill of materials — the flat, direct-instance read model (one line per
  // referenced document, quantity = shared count). Keyed on doc_version so it
  // refetches when instances are added/removed (which is what changes the
  // aggregate); switching the right panel to PARTS never refetches.
  const bomQuery = useQuery({
    queryKey: ["assembly-bom", assemblyId, docVersion],
    enabled: graph !== undefined,
    queryFn: () => fetchAssemblyBom(assemblyId),
  });
  const [inspectorView, setInspectorView] = useState<InspectorView>("solve");

  const partDocIds = useMemo(
    () => (graph ? uniquePartDocumentIds(graph) : []),
    [graph],
  );
  const partDocKey = partDocIds.join("|");

  // Each unique referenced part's feature tree, fetched once (instances sharing
  // a part share its tree) — the intent geometry evaluates.
  const partTreesQuery = useQuery({
    queryKey: ["assembly-part-trees", assemblyId, docVersion, partDocKey],
    enabled: partDocIds.length > 0,
    queryFn: async () => {
      const entries = await Promise.all(
        partDocIds.map(async (id) => [id, await fetchFeatureTree(id)] as const),
      );
      return new Map<string, FeatureTreeResponse>(entries);
    },
    staleTime: 30_000,
  });
  const partTrees = partTreesQuery.data;

  // Evaluate: one shared mesh per unique part + a solved pose per instance.
  const evalQuery = useQuery({
    queryKey: ["assembly-eval", assemblyId, docVersion],
    enabled:
      graph !== undefined && instances.length > 0 && partTrees !== undefined,
    queryFn: () =>
      evaluateAssembly(
        buildEvaluateAssemblyRequest(
          graph as NonNullable<typeof graph>,
          partTrees as Map<string, FeatureTreeResponse>,
        ),
      ),
    staleTime: Infinity,
    // Keep the prior evaluation visible while a doc_version bump refetches, so
    // solved geometry never blinks to null mid-refetch. Without this, every
    // mate/grounded/instance mutation empties evaluation → sceneFitKey collapses
    // to "" and back → CameraRig re-fits and teleports the camera away from the
    // view the user orbited to in order to author the mate.
    placeholderData: keepPreviousData,
  });
  const evaluation = evalQuery.data;

  // The evaluate request — the shared input to evaluate, export, and the
  // interference check (all three solve the identical world). Null until the
  // graph and every referenced part's tree have loaded.
  const evaluateRequest = useMemo(
    () =>
      graph !== undefined && partTrees !== undefined
        ? buildEvaluateAssemblyRequest(graph, partTrees)
        : null,
    [graph, partTrees],
  );

  // ---------------------------------------------------------------------
  // Interference (clash) check — the same solve as evaluate, scanned for
  // overlapping instance pairs. Held on the workspace so the result also drives
  // the tree badge + viewport highlight, not just the CLASH panel.
  // ---------------------------------------------------------------------
  const [clashResult, setClashResult] = useState<InterferenceResult | null>(
    null,
  );
  const [clashBusy, setClashBusy] = useState(false);
  const [clashError, setClashError] = useState<string | null>(null);

  // Any graph edit re-solves the assembly, so a prior clash report (and its
  // highlight) is stale — drop it on every doc_version change.
  useEffect(() => {
    setClashResult(null);
    setClashError(null);
  }, [docVersion]);

  const runInterference = useCallback(() => {
    if (evaluateRequest === null || clashBusy) return;
    setInspectorView("clash");
    setClashBusy(true);
    setClashError(null);
    void (async () => {
      try {
        setClashResult(await checkInterference(evaluateRequest));
      } catch (error) {
        setClashError(
          error instanceof Error
            ? error.message
            : "The interference check could not be run.",
        );
      } finally {
        setClashBusy(false);
      }
    })();
  }, [evaluateRequest, clashBusy]);

  // The instances flagged by the last check — badged in the tree and edge-lit
  // red in the viewport (one clash language across DOM + WebGL).
  const clashingInstanceIds = useMemo(() => {
    const set = new Set<string>();
    for (const clash of clashResult?.clashes ?? []) {
      set.add(clash.instance_a);
      set.add(clash.instance_b);
    }
    return set;
  }, [clashResult]);

  // Export the WHOLE solved assembly as one STEP/STL file. Bound to the shared
  // ExportRow (the same strip the part page exports from). Disabled until a
  // request exists and at least one instance produced a body.
  const exporter = useCallback(
    (format: ExportFormat) => {
      if (evaluateRequest === null) {
        return Promise.reject(new Error("The assembly is still loading."));
      }
      return exportAssembly(evaluateRequest, format);
    },
    [evaluateRequest],
  );
  const hasExportableBody = (evaluation?.instances ?? []).some(
    (instance) => instance.part_mesh_glb_id !== null,
  );
  const exportDisabledReason =
    evaluateRequest === null
      ? "No assembly"
      : hasExportableBody
        ? undefined
        : "No body";

  // Fetch each UNIQUE solved mesh once (dedup by content address); shared
  // instances reuse the one fetch. Keyed on the sorted id set so it only
  // refetches when the mesh set actually changes.
  const meshIds = useMemo(() => {
    const set = new Set<string>();
    for (const inst of evaluation?.instances ?? []) {
      if (inst.part_mesh_glb_id) set.add(inst.part_mesh_glb_id);
    }
    return [...set].sort();
  }, [evaluation]);
  const meshKey = meshIds.join("|");

  const meshesQuery = useQuery({
    queryKey: ["assembly-meshes", meshKey],
    enabled: meshIds.length > 0,
    queryFn: async () => {
      const entries = await Promise.all(
        meshIds.map(async (id) => [id, await fetchBodyMesh(id)] as const),
      );
      return new Map<string, ArrayBuffer>(entries);
    },
    staleTime: Infinity,
    retry: (count, error) => !(error instanceof MeshNotFoundError) && count < 2,
  });

  // A mesh evicted from the store (§7.8) → regenerate by re-evaluating, then
  // refetch. Guarded per mesh-set so an unservable mesh surfaces, never loops.
  const regeneratedFor = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!(meshesQuery.error instanceof MeshNotFoundError)) return;
    if (regeneratedFor.current.has(meshKey)) return;
    regeneratedFor.current.add(meshKey);
    void queryClient.invalidateQueries({
      queryKey: ["assembly-eval", assemblyId],
    });
    void queryClient.invalidateQueries({ queryKey: ["assembly-meshes"] });
  }, [meshesQuery.error, meshKey, assemblyId, queryClient]);

  const meshes = useMemo(
    () => meshesQuery.data ?? new Map<string, ArrayBuffer>(),
    [meshesQuery.data],
  );
  const { byMeshId } = useInstanceGeometries(meshes);

  // The scene instances: graph identity + solved pose + shared geometry.
  const solvedById = useMemo(
    () => new Map((evaluation?.instances ?? []).map((i) => [i.instance_id, i])),
    [evaluation],
  );
  const sceneInstances = useMemo<SceneInstance[]>(
    () =>
      instances.map((instance, index) => {
        const solved = solvedById.get(instance.id);
        const placement = solved?.placement ?? instance.placement;
        const meshGlbId = solved?.part_mesh_glb_id ?? null;
        return {
          id: instance.id,
          name: instance.name,
          balloon: index + 1,
          grounded: instance.grounded,
          transform: placementToScene(placement),
          geometry: meshGlbId ? (byMeshId.get(meshGlbId) ?? null) : null,
        };
      }),
    [instances, solvedById, byMeshId],
  );

  // ---------------------------------------------------------------------
  // Selection + mate authoring session.
  // ---------------------------------------------------------------------
  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(
    null,
  );
  const tool = useMateAuthoringStore((s) => s.tool);
  const picks = useMateAuthoringStore((s) => s.picks);
  const mateValue = useMateAuthoringStore((s) => s.value);
  const toggleTool = useMateAuthoringStore((s) => s.toggleTool);
  const resetPicks = useMateAuthoringStore((s) => s.resetPicks);
  const setTool = useMateAuthoringStore((s) => s.setTool);

  // Leaving the workspace disarms the mate session.
  useEffect(() => () => useMateAuthoringStore.getState().clear(), []);

  // Part overlays (faces/edges) — fetched once per unique part while a
  // face/axis mate tool is armed; mapped to each instance sharing that part.
  // Every mate but lock picks part geometry (faces for coincident / distance /
  // angle, axes for concentric), so all of them want the overlay fetched.
  const overlayActive = tool !== null && tool !== "lock";
  const overlaysQuery = useQuery({
    queryKey: ["assembly-overlays", assemblyId, docVersion, partDocKey],
    enabled: overlayActive && partTrees !== undefined && partDocIds.length > 0,
    queryFn: async () => {
      const trees = partTrees as Map<string, FeatureTreeResponse>;
      const entries = await Promise.all(
        partDocIds.map(async (id) => {
          const tree = trees.get(id);
          if (!tree) return [id, null] as const;
          return [id, await fetchOverlay(buildEvaluateTree(tree))] as const;
        }),
      );
      return new Map<string, OverlayResult | null>(entries);
    },
    staleTime: Infinity,
    retry: false,
  });
  const overlaysByInstance = useMemo(() => {
    const map = new Map<string, OverlayResult>();
    if (!overlayActive) return map;
    const byDoc = overlaysQuery.data;
    if (!byDoc) return map;
    for (const instance of instances) {
      const overlay = byDoc.get(instance.ref_document_id);
      if (overlay) map.set(instance.id, overlay);
    }
    return map;
  }, [overlayActive, overlaysQuery.data, instances]);

  // ---------------------------------------------------------------------
  // Mutations — each reads the freshest doc_version and invalidates the graph
  // (its new version cascades to part-trees + evaluate + meshes).
  // ---------------------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refreshGraph = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["assembly", assemblyId] }),
    [queryClient, assemblyId],
  );

  const runMutation = useCallback(
    async (fn: () => Promise<unknown>, fallback: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await fn();
        await refreshGraph();
      } catch (error) {
        setActionError(error instanceof Error ? error.message : fallback);
      } finally {
        setBusy(false);
      }
    },
    [refreshGraph],
  );

  // Document-unit change (docs/design/units.md §U2): a pure re-label under the
  // doc_version OCC. No stored mm value changes, so the assembly never
  // re-solves — every dimension echo simply re-formats on the next render.
  const [unitBusy, setUnitBusy] = useState(false);
  const changeUnit = useCallback(
    (next: LengthUnit) => {
      if (next === lengthUnit || unitBusy) return;
      setUnitBusy(true);
      void (async () => {
        try {
          await updateAssemblyUnit(assemblyId, next, docVersion);
          await refreshGraph();
        } catch {
          // A stale-version race (422) or transient failure leaves the unit as
          // it was; nothing stored changed and the user can retry.
        } finally {
          setUnitBusy(false);
        }
      })();
    },
    [lengthUnit, unitBusy, assemblyId, docVersion, refreshGraph],
  );

  // Add part: seed the Nth instance APART along +X so a later mate visibly
  // snaps it in; auto-ground the very first instance (the assembly anchor).
  const [addOpen, setAddOpen] = useState(false);
  const [addingPartId, setAddingPartId] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const handleAddPart = useCallback(
    (part: PartResponse) => {
      const index = instances.length;
      setAddingPartId(part.id);
      setAddError(null);
      void (async () => {
        try {
          await createInstance(assemblyId, {
            name: `${part.name} <${index + 1}>`,
            ref_document_id: part.id,
            ref_document_kind: "part",
            grounded: index === 0,
            placement: {
              position: { x: index * 80, y: 0, z: 0 },
              orientation: IDENTITY_QUAT,
            },
            expected_version: docVersion,
          });
          await refreshGraph();
        } catch (error) {
          setAddError(
            error instanceof Error
              ? error.message
              : "The part could not be added.",
          );
        } finally {
          setAddingPartId(null);
        }
      })();
    },
    [assemblyId, instances.length, docVersion, refreshGraph],
  );

  const handleToggleGrounded = useCallback(
    (instance: InstanceResponse) =>
      runMutation(
        () =>
          updateInstance(assemblyId, instance.id, {
            expected_version: docVersion,
            grounded: !instance.grounded,
          }),
        "The instance could not be updated.",
      ),
    [assemblyId, docVersion, runMutation],
  );

  const handleDeleteInstance = useCallback(
    (instance: InstanceResponse) => {
      if (selectedInstanceId === instance.id) setSelectedInstanceId(null);
      return runMutation(
        () => deleteInstance(assemblyId, instance.id, docVersion),
        "The instance could not be removed.",
      );
    },
    [assemblyId, docVersion, runMutation, selectedInstanceId],
  );

  const handleDeleteMate = useCallback(
    (mate: MateResponse) =>
      runMutation(
        () => deleteMate(assemblyId, mate.id, docVersion),
        "The mate could not be removed.",
      ),
    [assemblyId, docVersion, runMutation],
  );

  // POST a built mate, re-solve (the snap), keep the tool armed to chain
  // another. A nonce guards a double-fire (React strict mode / re-render).
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const submitNonce = useRef(0);
  const submitMate = useCallback(
    (mate: Mate) => {
      if (submitting) return;
      const nonce = submitNonce.current + 1;
      submitNonce.current = nonce;
      setSubmitting(true);
      setSubmitError(null);
      void (async () => {
        try {
          await createMate(assemblyId, {
            expected_version: docVersion,
            mate,
          });
          resetPicks();
          await refreshGraph();
        } catch (error) {
          setSubmitError(
            error instanceof Error
              ? error.message
              : "The mate could not be added.",
          );
          resetPicks();
        } finally {
          if (submitNonce.current === nonce) setSubmitting(false);
        }
      })();
    },
    [submitting, assemblyId, docVersion, resetPicks, refreshGraph],
  );

  // Complete-pair watcher for the value-free mates (coincident / concentric /
  // lock): a complete pair auto-commits. Parametric mates (distance / angle)
  // hold at a complete pair for the value edit and commit explicitly below.
  useEffect(() => {
    if (tool === null || isParametricMate(tool)) return;
    if (picks.length !== 2 || submitting) return;
    const mate = buildMate(tool, picks);
    if (mate === null) return;
    submitMate(mate);
  }, [tool, picks, submitting, submitMate]);

  // Explicit commit for a parametric mate: build with the edited value.
  const commitMate = useCallback(() => {
    if (tool === null || !isParametricMate(tool)) return;
    const mate = buildMate(tool, picks, mateValue);
    if (mate === null) return;
    submitMate(mate);
  }, [tool, picks, mateValue, submitMate]);

  // ---------------------------------------------------------------------
  // Undo/redo (docs/design/undo-redo.md §UR3). History is SERVER-side snapshot
  // state: the graph GET's can_undo/can_redo gate the controls, and a step is
  // a document edit under the same doc_version OCC as every other write. A
  // restored graph re-renders through the SAME refreshGraph invalidation every
  // mutation uses (new doc_version cascades to part-trees → evaluate → meshes,
  // so the solved placements re-render) — never a second pipeline.
  // ---------------------------------------------------------------------
  const canUndo = graph?.can_undo ?? false;
  const canRedo = graph?.can_redo ?? false;
  /** Any graph mutation in flight — history must never race its version. */
  const mutationInFlight =
    busy || submitting || unitBusy || addingPartId !== null;
  /** Which step is in flight (drives the honest hold caption), or null. */
  const [historyStep, setHistoryStep] = useState<HistoryStep | null>(null);
  const historyInFlight = useRef(false);
  /** A non-stale undo/redo failure, surfaced in the viewport HUD. */
  const [historyError, setHistoryError] = useState<HistoryStepError | null>(
    null,
  );

  const runHistoryStep = useCallback(
    (step: HistoryStep) => {
      // One graph rewrite at a time: repeats (held chord / double click) AND
      // any in-flight mutation are ignored until the write settles.
      if (historyInFlight.current || mutationInFlight || graph === undefined) {
        return;
      }
      historyInFlight.current = true;
      setHistoryStep(step);
      setHistoryError(null);
      void (async () => {
        try {
          const outcome = await executeHistoryStep(step, {
            // Mirror every other assembly mutation: echo the cached graph's
            // token as the expected version.
            version: () => docVersion,
            run: (s, expected) =>
              s === "undo"
                ? undoAssembly(assemblyId, expected)
                : redoAssembly(assemblyId, expected),
            versionOf: (g) => g.doc_version,
            // Boundary no-op (clean 200): adopt the echoed graph (fresh
            // can_undo/can_redo) — doc_version is unchanged, so no downstream
            // query refetches and no re-solve fires.
            adoptNoOp: (g) =>
              queryClient.setQueryData(["assembly", assemblyId], g),
            onRestored: async () => {
              // A REAL restore: the graph changed under the session — drop
              // the mate-authoring picks/pending value and the selection (the
              // assembly analog of the part page's measure-disarm hygiene,
              // only after the version-changed discriminator confirms it),
              // then resync through the shared invalidation path.
              useMateAuthoringStore.getState().clear();
              setSelectedInstanceId(null);
              await refreshGraph();
            },
            isStale: (error) => error instanceof StaleAssemblyVersionError,
            // Someone else moved the graph: the design doc's soft reload —
            // resync quietly; the user re-issues against what they now see.
            resync: () => refreshGraph(),
          });
          if (outcome.kind === "failed") {
            setHistoryError({ step, message: outcome.message });
          }
        } finally {
          historyInFlight.current = false;
          setHistoryStep(null);
        }
      })();
    },
    [
      mutationInFlight,
      graph,
      docVersion,
      assemblyId,
      queryClient,
      refreshGraph,
    ],
  );

  const triggerUndo = useCallback(() => {
    if (canUndo) runHistoryStep("undo");
  }, [canUndo, runHistoryStep]);
  const triggerRedo = useCallback(() => {
    if (canRedo) runHistoryStep("redo");
  }, [canRedo, runHistoryStep]);

  // Keyboard-first: A opens the picker; I runs the clash check; F/N/K arm the
  // mate tools; Escape disarms the tool / closes the picker.
  const canMate = instances.length >= 2;
  const canCheckInterference = evaluateRequest !== null && canMate;
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (event.key === "Escape") {
        if (useMateAuthoringStore.getState().tool !== null) {
          event.preventDefault();
          setTool(null);
        } else if (addOpen) {
          event.preventDefault();
          setAddOpen(false);
        }
        return;
      }
      if (key === "a") {
        event.preventDefault();
        setAddOpen((open) => !open);
        return;
      }
      if (key === "i" && canCheckInterference) {
        event.preventDefault();
        runInterference();
        return;
      }
      if (!canMate) return;
      const map: Record<string, MateTool> = {
        f: "coincident",
        n: "concentric",
        k: "lock",
        d: "distance",
        g: "angle",
      };
      const next = map[key];
      if (next !== undefined) {
        event.preventDefault();
        toggleTool(next);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    canMate,
    canCheckInterference,
    runInterference,
    addOpen,
    setTool,
    toggleTool,
  ]);

  // One predicate owns "who holds Ctrl+Z right now": an armed mate tool or the
  // open part picker. Both the keyboard effect below and the band's disabled
  // reason read THIS value, so the keys and the buttons can never disagree (a
  // third owning state added to one and not the other was the drift risk).
  const historyLockReason: string | null =
    tool !== null
      ? `Finish the ${mateToolLabel(tool)} mate first`
      : addOpen
        ? "Close the part picker first"
        : null;

  // Undo/redo keyboard grammar: Ctrl/⌘+Z, Ctrl/⌘+Shift+Z, Ctrl+Y — assembly
  // idle only. An armed mate tool owns the session (a mid-pick Ctrl+Z must
  // never yank the graph out from under the picks) and the open part picker
  // owns the keys the same way, matching the band's History lock. A focused
  // text field (the mate value input, the picker's filter) keeps its NATIVE
  // undo — the typing-target guard is resolved inside the pure grammar helper.
  useEffect(() => {
    if (historyLockReason !== null) return;
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
  }, [historyLockReason, triggerUndo, triggerRedo]);

  const selectInstance = useCallback((id: string) => {
    setSelectedInstanceId((current) => (current === id ? null : id));
  }, []);

  // Camera fit inputs for the shared Viewport rig. The fit key is the set of
  // instances whose mesh has LOADED — the fit fires when geometry actually
  // lands (fixing the add-instance race where the fit read stale/partial
  // bounds) and never on a re-solve of the same set (the mate snap-together
  // motion plays without the camera jumping).
  const sceneBounds = useMemo(
    () => assemblyBounds(sceneInstances),
    [sceneInstances],
  );
  const sceneFitKey = useMemo(
    () =>
      sceneInstances
        .filter((instance) => instance.geometry !== null)
        .map((instance) => instance.id)
        .sort()
        .join("|"),
    [sceneInstances],
  );

  return (
    <DocumentUnitProvider unit={lengthUnit}>
      <div className="flex h-full flex-col">
        <TopBar>
          <Breadcrumb
            register="assemblies"
            documentName={graph?.assembly.name ?? "Assembly"}
            documentTestId="assembly-name"
            mode={
              tool !== null ? mateToolLabel(tool) : addOpen ? "Add part" : null
            }
          />
          <DocumentUnitSelect
            value={lengthUnit}
            onChange={changeUnit}
            busy={unitBusy}
          />
        </TopBar>
        <TopToolbar>
          <AssemblyCommandBand
            historyReady={graph !== undefined}
            canUndo={canUndo}
            canRedo={canRedo}
            historyHold={historyStep}
            historyHoldReason={
              mutationInFlight ? "Waiting for the current edit…" : null
            }
            historyLockReason={historyLockReason ?? undefined}
            onUndo={triggerUndo}
            onRedo={triggerRedo}
            canAddPart={graph !== undefined}
            onAddPart={() => setAddOpen((open) => !open)}
            canMate={canMate}
            activeTool={tool}
            onToggleTool={toggleTool}
            canCheckInterference={canCheckInterference}
            interferenceBusy={clashBusy}
            onCheckInterference={runInterference}
          />
        </TopToolbar>
        {/* Full-bleed scene; tree + inspector float over it (Batch 1, P0-4). */}
        <main className="relative min-h-0 grow">
          <Viewport
            worldBounds={sceneBounds}
            fitKey={sceneFitKey}
            hud={
              <>
                <MateHud
                  submitError={submitError}
                  submitting={submitting}
                  onCommit={commitMate}
                />
                {addOpen ? (
                  <AddInstancePanel
                    addingPartId={addingPartId}
                    error={addError}
                    onAdd={handleAddPart}
                    onClose={() => setAddOpen(false)}
                  />
                ) : null}
                <HistoryErrorAlert
                  error={historyError}
                  onDismiss={() => setHistoryError(null)}
                />
                {actionError ? (
                  <div
                    role="alert"
                    data-testid="assembly-action-error"
                    className="absolute bottom-3 left-3 max-w-sm border border-flag bg-anvil px-3 py-2"
                  >
                    <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
                      Action failed
                    </span>
                    <span className="mt-1 block font-body text-xs text-mist">
                      {actionError}
                    </span>
                    <button
                      type="button"
                      onClick={() => setActionError(null)}
                      className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                    >
                      Dismiss
                    </button>
                  </div>
                ) : null}
                {instances.length === 0 ? (
                  <div
                    data-testid="assembly-hint"
                    // Inline pointer-events beats the HUD's `[&>*]:pointer-events-auto`
                    // so this centred hint never intercepts a click on the add
                    // panel / balloons beneath it.
                    style={{ pointerEvents: "none" }}
                    className="absolute inset-0 flex items-center justify-center"
                  >
                    <p className="max-w-xs text-center font-body text-sm text-gauge">
                      Add a part to begin. Ground the first one, then mate the
                      rest to bolt them together.
                    </p>
                  </div>
                ) : null}
              </>
            }
          >
            <AssemblyScene
              instances={sceneInstances}
              reducedMotion={reducedMotion}
              selectedInstanceId={selectedInstanceId}
              onSelectInstance={selectInstance}
              overlaysByInstance={overlaysByInstance}
              clashingInstanceIds={clashingInstanceIds}
            />
          </Viewport>
          <FloatingPanel side="left" title="Components" id="tree">
            <AssemblyTreePanel
              graph={graph}
              graphError={graphQuery.error}
              evaluation={evaluation}
              selectedInstanceId={selectedInstanceId}
              clashingInstanceIds={clashingInstanceIds}
              onSelectInstance={selectInstance}
              onToggleGrounded={handleToggleGrounded}
              onDeleteInstance={handleDeleteInstance}
              onDeleteMate={handleDeleteMate}
              // The panel's writes also hold while a history step restores
              // (the mutual exclusion's visible half — runHistoryStep guards
              // the other direction).
              busy={busy || historyStep !== null}
            />
          </FloatingPanel>
          <FloatingPanel side="right" title="Inspect" id="inspector">
            <AssemblyInspectorPanel
              view={inspectorView}
              onViewChange={setInspectorView}
              evaluation={evaluation}
              evaluating={evalQuery.isFetching}
              bom={bomQuery.data}
              bomLoading={bomQuery.isLoading}
              bomError={bomQuery.error}
              instances={instances}
              clashResult={clashResult}
              clashBusy={clashBusy}
              clashError={clashError}
              exporter={exporter}
              exportDisabledReason={exportDisabledReason}
            />
          </FloatingPanel>
        </main>
      </div>
    </DocumentUnitProvider>
  );
}
