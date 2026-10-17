/**
 * Mirror components in the assembly workspace (ASM-MIRROR-COMPONENT): the
 * dialog's state and writes, the tree section and the band's Mirror button,
 * owned here so the workspace page only mounts what this returns.
 *
 * A mirror is created or replaced with ONE write and deleted with one, each an
 * undo step; the workspace then re-reads the graph, whose new version re-solves
 * the assembly and draws the twins. A viewport face pick (the mirror plane)
 * goes through `usePatternPickStore`'s "plane" target.
 */
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  createMirror,
  deleteMirror,
  type MirrorResponse,
  type MirrorState,
  updateMirror,
} from "../api/mirrors";
import { MirrorPanel } from "../components/MirrorPanel";
import { MirrorTreeSection } from "../components/MirrorTreeSection";
import {
  buildMirror,
  formFromMirror,
  type MirrorForm,
  newMirrorForm,
} from "./mirrors";
import { usePatternPickStore } from "./patternStore";
import type { UsePatternsInput } from "./usePatterns";

export type UseMirrorsInput = Omit<UsePatternsInput, "patterns"> & {
  mirrors: readonly MirrorResponse[];
};

interface DialogState {
  mirrorId: string | null;
  form: MirrorForm;
}

export interface Mirrors {
  /** A mirror write is in flight. */
  writing: boolean;
  /** The band's Mirror button. */
  band: { active: boolean; blocker: string | null; onToggle: () => void };
  hud: ReactNode;
  treeSection: ReactNode;
}

export function useMirrors(input: UseMirrorsInput): Mirrors {
  const {
    assemblyId,
    docVersion,
    mirrors,
    instances,
    evaluation,
    selectedInstanceId,
    refreshGraph,
    onError,
  } = input;
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picking = usePatternPickStore((s) => s.picking === "plane");
  const pickedFace = usePatternPickStore((s) => s.pickedFace);
  const arm = usePatternPickStore((s) => s.arm);
  const clearPick = usePatternPickStore((s) => s.clear);

  // A finished viewport pick lands in the form.
  useEffect(() => {
    if (pickedFace === null) return;
    setDialog((current) =>
      current === null
        ? current
        : { ...current, form: { ...current.form, face: pickedFace } },
    );
    clearPick();
  }, [pickedFace, clearPick]);

  const close = useCallback(() => {
    setDialog(null);
    setError(null);
    clearPick();
  }, [clearPick]);

  const openCreate = useCallback(() => {
    setError(null);
    setDialog({
      mirrorId: null,
      form: newMirrorForm(
        selectedInstanceId === null ? [] : [selectedInstanceId],
      ),
    });
  }, [selectedInstanceId]);

  const openEdit = useCallback((mirror: MirrorResponse) => {
    setError(null);
    setDialog({ mirrorId: mirror.id, form: formFromMirror(mirror.mirror) });
  }, []);

  const submit = useCallback(() => {
    if (dialog === null || writing) return;
    const built = buildMirror(dialog.form);
    if ("error" in built) {
      setError(built.error);
      return;
    }
    setWriting(true);
    setError(null);
    void (async () => {
      try {
        if (dialog.mirrorId === null) {
          await createMirror(assemblyId, built.mirror, docVersion);
        } else {
          await updateMirror(
            assemblyId,
            dialog.mirrorId,
            built.mirror,
            docVersion,
          );
        }
        await refreshGraph();
        close();
      } catch (failure) {
        setError(
          failure instanceof Error
            ? failure.message
            : "The mirror could not be saved.",
        );
      } finally {
        setWriting(false);
      }
    })();
  }, [dialog, writing, assemblyId, docVersion, refreshGraph, close]);

  const remove = useCallback(
    (mirror: MirrorResponse) => {
      setWriting(true);
      void (async () => {
        try {
          await deleteMirror(assemblyId, mirror.id, docVersion);
          await refreshGraph();
        } catch (failure) {
          onError(
            failure instanceof Error
              ? failure.message
              : "The mirror could not be removed.",
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
      new Map<string, MirrorState>(
        (evaluation?.mirror_states ?? []).map((s) => [s.mirror_id, s]),
      ),
    [evaluation],
  );

  const blocker = instances.length === 0 ? "Add a part first" : null;
  return {
    writing,
    band: {
      active: dialog !== null,
      blocker,
      onToggle: () => (dialog !== null ? close() : openCreate()),
    },
    hud:
      dialog === null ? null : (
        <MirrorPanel
          mode={dialog.mirrorId === null ? "create" : "edit"}
          form={dialog.form}
          onChange={(form) => setDialog({ ...dialog, form })}
          instances={instances}
          nameOf={input.nameOf}
          picking={picking}
          onPick={(armed) => arm(armed ? "plane" : null)}
          submitting={writing}
          error={error}
          onSubmit={submit}
          onCancel={close}
        />
      ),
    treeSection: (
      <MirrorTreeSection
        mirrors={mirrors}
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
