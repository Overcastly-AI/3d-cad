/**
 * Component patterns in the assembly workspace (ASM-A3-PATTERN): the dialog's
 * state and writes, the tree section and the band's Pattern button, owned here
 * so the workspace page only mounts what this returns.
 *
 * A pattern is created or replaced with ONE write and deleted with one, each
 * an undo step; the workspace then re-reads the graph, whose new version
 * re-solves the assembly and draws the copies. A viewport edge pick (the
 * direction, axis or seed hole) goes through `usePatternPickStore`.
 */
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import type {
  EvaluateAssemblyResult,
  InstanceResponse,
} from "../api/assemblies";
import {
  createPattern,
  deletePattern,
  type PatternCount,
  type PatternResponse,
  updatePattern,
} from "../api/patterns";
import { PatternPanel } from "../components/PatternPanel";
import { PatternTreeSection } from "../components/PatternTreeSection";
import {
  buildPattern,
  formFromPattern,
  newPatternForm,
  type PatternForm,
} from "./patterns";
import { usePatternPickStore } from "./patternStore";

export interface UsePatternsInput {
  assemblyId: string;
  docVersion: number;
  patterns: readonly PatternResponse[];
  instances: readonly InstanceResponse[];
  evaluation: EvaluateAssemblyResult | undefined;
  /** The solve on screen is superseded: counts are not claimed. */
  stale: boolean;
  selectedInstanceId: string | null;
  nameOf: (instanceId: string) => string;
  refreshGraph: () => Promise<unknown>;
  onError: (message: string) => void;
  /** Another write is in flight: the tree's actions hold. */
  busy: boolean;
}

interface DialogState {
  mode: "create" | "edit";
  patternId: string | null;
  form: PatternForm;
}

export interface Patterns {
  /** The dialog is open (the page's other tools stand down). */
  open: boolean;
  /** A pattern write is in flight. */
  writing: boolean;
  /** A viewport edge pick is armed (the page fetches overlays for it). */
  picking: boolean;
  /** The band's Pattern button. */
  band: { active: boolean; blocker: string | null; onToggle: () => void };
  hud: ReactNode;
  treeSection: ReactNode;
}

export function usePatterns(input: UsePatternsInput): Patterns {
  const {
    assemblyId,
    docVersion,
    patterns,
    instances,
    evaluation,
    selectedInstanceId,
    refreshGraph,
    onError,
  } = input;
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picking = usePatternPickStore((s) => s.picking);
  const picked = usePatternPickStore((s) => s.picked);
  const arm = usePatternPickStore((s) => s.arm);
  const clearPick = usePatternPickStore((s) => s.clear);

  // A finished viewport pick lands in the form.
  useEffect(() => {
    if (picked === null) return;
    const edge = { instanceId: picked.instanceId, signature: picked.signature };
    setDialog((current) =>
      current === null
        ? current
        : {
            ...current,
            form:
              picked.target === "axis"
                ? { ...current.form, axis: "edge", edge }
                : { ...current.form, hole: edge, alsoOn: [] },
          },
    );
    clearPick();
  }, [picked, clearPick]);

  // Leaving the workspace drops any armed pick.
  useEffect(() => () => usePatternPickStore.getState().clear(), []);

  const close = useCallback(() => {
    setDialog(null);
    setError(null);
    clearPick();
  }, [clearPick]);

  const openCreate = useCallback(() => {
    setError(null);
    setDialog({
      mode: "create",
      patternId: null,
      form: newPatternForm(
        selectedInstanceId === null ? [] : [selectedInstanceId],
      ),
    });
  }, [selectedInstanceId]);

  const openEdit = useCallback((pattern: PatternResponse) => {
    setError(null);
    setDialog({
      mode: "edit",
      patternId: pattern.id,
      form: formFromPattern(pattern.pattern),
    });
  }, []);

  const submit = useCallback(() => {
    if (dialog === null || writing) return;
    const built = buildPattern(dialog.form);
    if ("error" in built) {
      setError(built.error);
      return;
    }
    setWriting(true);
    setError(null);
    void (async () => {
      try {
        if (dialog.patternId === null) {
          await createPattern(assemblyId, built.pattern, docVersion);
        } else {
          await updatePattern(
            assemblyId,
            dialog.patternId,
            built.pattern,
            docVersion,
          );
        }
        await refreshGraph();
        close();
      } catch (failure) {
        setError(
          failure instanceof Error
            ? failure.message
            : "The pattern could not be saved.",
        );
      } finally {
        setWriting(false);
      }
    })();
  }, [dialog, writing, assemblyId, docVersion, refreshGraph, close]);

  const remove = useCallback(
    (pattern: PatternResponse) => {
      setWriting(true);
      void (async () => {
        try {
          await deletePattern(assemblyId, pattern.id, docVersion);
          await refreshGraph();
        } catch (failure) {
          onError(
            failure instanceof Error
              ? failure.message
              : "The pattern could not be removed.",
          );
        } finally {
          setWriting(false);
        }
      })();
    },
    [assemblyId, docVersion, refreshGraph, onError],
  );

  const states = useMemo(
    () =>
      new Map<string, PatternCount>(
        (evaluation?.pattern_states ?? []).map((s) => [s.pattern_id, s]),
      ),
    [evaluation],
  );

  const blocker = instances.length === 0 ? "Add a part first" : null;
  return {
    open: dialog !== null,
    writing,
    picking: picking !== null,
    band: {
      active: dialog !== null,
      blocker,
      onToggle: () => (dialog !== null ? close() : openCreate()),
    },
    hud:
      dialog === null ? null : (
        <PatternPanel
          mode={dialog.mode}
          form={dialog.form}
          onChange={(form) => setDialog({ ...dialog, form })}
          instances={instances}
          nameOf={input.nameOf}
          picking={picking}
          onPick={arm}
          submitting={writing}
          error={error}
          onSubmit={submit}
          onCancel={close}
        />
      ),
    treeSection: (
      <PatternTreeSection
        patterns={patterns}
        instances={instances}
        states={states}
        stale={input.stale}
        busy={input.busy || writing}
        onEdit={openEdit}
        onDelete={remove}
      />
    ),
  };
}
