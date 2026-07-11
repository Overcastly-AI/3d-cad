import { Chip } from "@loft/design";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import {
  createFeature,
  evaluatePart,
  fetchFeatureTree,
  fetchPart,
  sketchFeatureCreate,
} from "../api/parts";
import { FeatureTreePanel } from "../components/FeatureTreePanel";
import { SketchDro } from "../components/SketchDro";
import { SketchStrip } from "../components/SketchStrip";
import { TopBar } from "../components/TopBar";
import { useSketchStore } from "../sketch/store";
import { TOOL_SHORTCUTS } from "../sketch/tools";
import { partRoute } from "../router";
import { SketchScene, type SolvedSketchLayer } from "../viewport/SketchScene";
import { Viewport } from "../viewport/Viewport";

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
 * the sketcher renders what the solver says, never its own input echo.
 */
export function PartPage() {
  const { partId } = partRoute.useParams();
  const queryClient = useQueryClient();

  const mode = useSketchStore((state) => state.mode);
  const begin = useSketchStore((state) => state.begin);
  const escape = useSketchStore((state) => state.escape);
  const setTool = useSketchStore((state) => state.setTool);
  const toggleSnap = useSketchStore((state) => state.toggleSnap);
  const exit = useSketchStore((state) => state.exit);

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

  /** Solved sketch layers: tree feature (plane) × evaluate result (geometry). */
  const solved = useMemo<SolvedSketchLayer[]>(() => {
    if (tree.data === undefined || evaluation.data === undefined) return [];
    const results = new Map(
      evaluation.data.features.map((f) => [f.feature_id, f]),
    );
    const layers: SolvedSketchLayer[] = [];
    for (const feature of tree.data.features) {
      if (feature.feature.type !== "sketch") continue;
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
  }, [tree.data, evaluation.data]);

  const save = useMutation({
    mutationFn: async () => {
      const { plane, entities } = useSketchStore.getState();
      if (
        plane === null ||
        entities.length === 0 ||
        treeVersion === undefined
      ) {
        throw new Error("Nothing to save yet — draw at least one entity.");
      }
      const sketchCount = (tree.data?.features ?? []).filter(
        (f) => f.feature.type === "sketch",
      ).length;
      return createFeature(
        partId,
        sketchFeatureCreate(
          `Sketch${sketchCount + 1}`,
          plane,
          entities,
          treeVersion,
        ),
      );
    },
    onSuccess: () => {
      exit();
      // New tree version → the evaluate query re-keys and re-solves.
      void queryClient.invalidateQueries({ queryKey: ["features", partId] });
    },
  });

  // Keyboard-first: Escape cascade always; tools + snap while drawing.
  useEffect(() => {
    if (mode === "off") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key === "Escape") {
        event.preventDefault();
        escape();
        return;
      }
      if (mode !== "draw") return;
      const key = event.key.toLowerCase();
      if (key === "g") {
        event.preventDefault();
        toggleSnap();
        return;
      }
      const tool = TOOL_SHORTCUTS[key];
      if (tool !== undefined) {
        event.preventDefault();
        setTool(tool);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, escape, setTool, toggleSnap]);

  // Leaving the workspace always leaves sketch mode.
  useEffect(() => () => exit(), [exit]);

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
            save.reset();
            begin();
          }}
        />
        <Viewport
          rotateEnabled={mode !== "draw"}
          groundGrid={mode !== "draw"}
          hud={
            <>
              <SketchStrip
                onSave={() => save.mutate()}
                saving={save.isPending}
                saveError={save.error ? save.error.message : null}
              />
              <SketchDro />
            </>
          }
        >
          <SketchScene solved={solved} />
        </Viewport>
      </main>
    </div>
  );
}
