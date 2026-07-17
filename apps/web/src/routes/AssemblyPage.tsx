import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createInstance,
  createMate,
  deleteInstance,
  deleteMate,
  evaluateAssembly,
  fetchAssemblyGraph,
  type InstanceResponse,
  type LengthUnit,
  type Mate,
  type MateResponse,
  updateAssemblyUnit,
  updateInstance,
} from "../api/assemblies";
import { MeshNotFoundError, fetchBodyMesh } from "../api/mesh";
import { fetchOverlay, type OverlayResult } from "../api/measure";
import {
  fetchFeatureTree,
  type FeatureTreeResponse,
  type PartResponse,
} from "../api/parts";
import { AddInstancePanel } from "../components/AddInstancePanel";
import { AssemblyCommandBand } from "../components/AssemblyCommandBand";
import { AssemblyInspector } from "../components/AssemblyInspector";
import { Breadcrumb } from "../components/Breadcrumb";
import { AssemblyTreePanel } from "../components/AssemblyTreePanel";
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
import { isTypingTarget } from "../lib/isTypingTarget";
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

  // Keyboard-first: A opens the picker; F/N/K arm the mate tools; Escape
  // disarms the tool / closes the picker.
  const canMate = instances.length >= 2;
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
  }, [canMate, addOpen, setTool, toggleTool]);

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
            canAddPart={graph !== undefined}
            onAddPart={() => setAddOpen((open) => !open)}
            canMate={canMate}
            activeTool={tool}
            onToggleTool={toggleTool}
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
            />
          </Viewport>
          <FloatingPanel side="left" title="Components" id="tree">
            <AssemblyTreePanel
              graph={graph}
              graphError={graphQuery.error}
              evaluation={evaluation}
              selectedInstanceId={selectedInstanceId}
              onSelectInstance={selectInstance}
              onToggleGrounded={handleToggleGrounded}
              onDeleteInstance={handleDeleteInstance}
              onDeleteMate={handleDeleteMate}
              busy={busy}
            />
          </FloatingPanel>
          <FloatingPanel side="right" title="Solve" id="inspector">
            <AssemblyInspector
              evaluation={evaluation}
              evaluating={evalQuery.isFetching}
            />
          </FloatingPanel>
        </main>
      </div>
    </DocumentUnitProvider>
  );
}
