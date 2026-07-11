/**
 * Sketch-mode state (zustand) — plane pick, tool sequence, the local entity
 * buffer, and the constraint/selection layer. All geometry and constraint
 * transitions are the pure functions of `tools.ts` / `pick.ts` /
 * `constraints.ts`; this store only holds state.
 *
 * Persistence model (the live parametric loop): entities/constraints edits
 * bump `revision`; once the sketch is bound to a persisted feature
 * (`featureId`), `PartPage` debounce-saves every revision and feeds the
 * solved evaluate payload back through `adoptSolved` — which does NOT bump
 * `revision`, so the loop terminates.
 */
import { create } from "zustand";

import {
  applyConstraintAction,
  type ConstraintAction,
  type DimensionEditorTarget,
  type SketchConstraint,
  type SolveInfo,
} from "./constraints";
import type { DatumPlaneName, Point2D } from "./plane";
import { snapPoint } from "./plane";
import { pickCandidates, toggleSelection, type SketchPick } from "./pick";
import {
  escapeAction,
  placePoint,
  type SketchEntity,
  type SketchTool,
} from "./tools";

/** Default grid snap (mm) — toggled with G, not adjustable yet. */
export const SNAP_STEP_MM = 1;

export type SketchMode = "off" | "plane" | "draw";

export interface SketchState {
  mode: SketchMode;
  /** Chosen datum plane (set on entering `draw`). */
  plane: DatumPlaneName | null;
  tool: SketchTool;
  /** Points of the in-progress placement sequence (plane mm, snapped). */
  pending: Point2D[];
  /** Locally buffered entities; adopt solved positions once persisted. */
  entities: SketchEntity[];
  /** Constraints authored this session (persisted with the entities). */
  constraints: SketchConstraint[];
  /** Next sketch-local id index (`e1`, `e2`, …). */
  nextIdIndex: number;
  snapEnabled: boolean;
  /** Pointer position in plane mm, already snapped; null when off-plane. */
  cursor: Point2D | null;
  /** Plane under the pointer / focused cell during plane pick. */
  hoveredPlane: DatumPlaneName | null;
  /** Current selection (select tool): entities and defining points. */
  selection: SketchPick[];
  /** Pick under the pointer (select tool) — hover highlight. */
  hoverPick: SketchPick | null;
  /** Selected constraint glyph (index into `constraints`), for Delete. */
  selectedConstraint: number | null;
  /** Open inline dimension editor, or null. */
  dimensionEdit: DimensionEditorTarget | null;
  /** Persisted feature this session is bound to (null = unsaved). */
  featureId: string | null;
  /** Monotonic edit counter — the sync loop persists every bump. */
  revision: number;
  /** Latest solve feedback for the bound feature (DRO + diagnostics). */
  solve: SolveInfo | null;
  /** Transient strip hint (invalid constraint action, duplicates, …). */
  hint: string | null;

  /** Enter sketch mode at the plane-pick step. */
  begin: () => void;
  choosePlane: (plane: DatumPlaneName) => void;
  setTool: (tool: SketchTool) => void;
  setHoveredPlane: (plane: DatumPlaneName | null) => void;
  setCursor: (point: Point2D | null) => void;
  toggleSnap: () => void;
  /** Apply the current snap setting to a raw plane-space point. */
  snap: (point: Point2D) => Point2D;
  /** Place the next point of the active tool's sequence. */
  placeAt: (point: Point2D) => void;
  /** Select-tool click at a raw (unsnapped) plane point. */
  selectAt: (point: Point2D, toleranceMm: number) => void;
  setHoverPick: (pick: SketchPick | null) => void;
  clearSelection: () => void;
  /** Apply a constraint verb to the selection (H/V/X/C add; D/R edit). */
  applyConstraint: (action: ConstraintAction) => void;
  /** Open the editor for an existing dimension constraint (glyph click). */
  editDimension: (constraintIndex: number) => void;
  /** Commit the open dimension editor with a validated value (mm). */
  commitDimension: (valueMm: number) => void;
  cancelDimension: () => void;
  selectConstraint: (index: number | null) => void;
  removeConstraint: (index: number) => void;
  /** Bind the session to its persisted feature (first save). */
  bind: (featureId: string) => void;
  /** Feed solved geometry + diagnosis back in (never bumps `revision`). */
  adoptSolved: (
    entities: readonly SketchEntity[] | null,
    solve: SolveInfo | null,
  ) => void;
  /** Escape cascade: editor → placement → tool → selection → exit. */
  escape: () => void;
  /** Leave sketch mode, discarding the local buffer. */
  exit: () => void;
}

const INITIAL = {
  mode: "off" as SketchMode,
  plane: null,
  tool: "select" as SketchTool,
  pending: [],
  entities: [],
  constraints: [],
  nextIdIndex: 1,
  snapEnabled: true,
  cursor: null,
  hoveredPlane: null,
  selection: [],
  hoverPick: null,
  selectedConstraint: null,
  dimensionEdit: null,
  featureId: null,
  revision: 0,
  solve: null,
  hint: null,
};

export const useSketchStore = create<SketchState>()((set, get) => ({
  ...INITIAL,

  begin: () => set({ ...INITIAL, mode: "plane" }),
  choosePlane: (plane) =>
    set({ mode: "draw", plane, hoveredPlane: null, cursor: null }),
  setTool: (tool) =>
    set({
      tool,
      pending: [],
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      dimensionEdit: null,
      hint: null,
    }),
  setHoveredPlane: (hoveredPlane) => set({ hoveredPlane }),
  setCursor: (cursor) => set({ cursor }),
  toggleSnap: () => set((state) => ({ snapEnabled: !state.snapEnabled })),
  snap: (point) => snapPoint(point, get().snapEnabled ? SNAP_STEP_MM : 0),

  placeAt: (point) => {
    const { tool, pending, nextIdIndex, entities, revision } = get();
    const result = placePoint(tool, pending, point, nextIdIndex);
    set({
      pending: result.pending,
      nextIdIndex: result.nextIdIndex,
      entities:
        result.entities.length > 0
          ? [...entities, ...result.entities]
          : entities,
      revision: result.entities.length > 0 ? revision + 1 : revision,
    });
  },

  selectAt: (point, toleranceMm) => {
    const { entities, selection } = get();
    const candidates = pickCandidates(entities, point, toleranceMm);
    set({
      selection: toggleSelection(selection, candidates),
      selectedConstraint: null,
      hint: null,
    });
  },

  setHoverPick: (hoverPick) => set({ hoverPick }),
  clearSelection: () => set({ selection: [], selectedConstraint: null }),

  applyConstraint: (action) => {
    const { selection, entities, constraints, revision } = get();
    const result = applyConstraintAction(
      action,
      selection,
      entities,
      constraints,
    );
    switch (result.outcome) {
      case "added":
        set({
          constraints: [...constraints, ...result.constraints],
          revision: revision + 1,
          selection: [],
          hint: null,
        });
        return;
      case "editor":
        set({ dimensionEdit: result.target, hint: null });
        return;
      case "hint":
        set({ hint: result.hint });
        return;
    }
  },

  editDimension: (constraintIndex) => {
    const constraint = get().constraints[constraintIndex];
    if (constraint?.kind !== "distance" && constraint?.kind !== "radius") {
      return;
    }
    set({
      dimensionEdit: {
        kind: constraint.kind,
        entity: constraint.entity,
        initialMm: constraint.value_mm,
        constraintIndex,
      },
      selectedConstraint: null,
      hint: null,
    });
  },

  commitDimension: (valueMm) => {
    const { dimensionEdit, constraints, revision } = get();
    if (dimensionEdit === null || !(valueMm > 0)) return;
    const constraint: SketchConstraint = {
      kind: dimensionEdit.kind,
      entity: dimensionEdit.entity,
      value_mm: valueMm,
    };
    const next =
      dimensionEdit.constraintIndex === null
        ? [...constraints, constraint]
        : constraints.map((c, i) =>
            i === dimensionEdit.constraintIndex ? constraint : c,
          );
    set({
      constraints: next,
      revision: revision + 1,
      dimensionEdit: null,
      selection: [],
      hint: null,
    });
  },

  cancelDimension: () => set({ dimensionEdit: null }),

  selectConstraint: (selectedConstraint) =>
    set({ selectedConstraint, selection: [], hint: null }),

  removeConstraint: (index) => {
    const { constraints, revision, selectedConstraint } = get();
    if (index < 0 || index >= constraints.length) return;
    set({
      constraints: constraints.filter((_, i) => i !== index),
      revision: revision + 1,
      selectedConstraint:
        selectedConstraint === index
          ? null
          : selectedConstraint !== null && selectedConstraint > index
            ? selectedConstraint - 1
            : selectedConstraint,
      dimensionEdit: null,
    });
  },

  bind: (featureId) => set({ featureId }),

  adoptSolved: (entities, solve) => {
    if (entities === null) {
      set({ solve });
      return;
    }
    const solvedById = new Map(entities.map((e) => [e.id, e]));
    set((state) => ({
      solve,
      entities: state.entities.map((e) => solvedById.get(e.id) ?? e),
    }));
  },

  escape: () => {
    const { tool, pending, selection, dimensionEdit } = get();
    switch (
      escapeAction(
        tool,
        pending.length,
        selection.length > 0,
        dimensionEdit !== null,
      )
    ) {
      case "close-editor":
        set({ dimensionEdit: null });
        return;
      case "cancel-placement":
        set({ pending: [] });
        return;
      case "reset-tool":
        set({ tool: "select", pending: [] });
        return;
      case "clear-selection":
        set({ selection: [], selectedConstraint: null, hint: null });
        return;
      case "exit":
        set({ ...INITIAL });
        return;
    }
  },

  exit: () => set({ ...INITIAL }),
}));
