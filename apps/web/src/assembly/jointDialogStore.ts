/**
 * The joint dialog's session (zustand): which joint it is shaping — a NEW one
 * between two picked origins, or a stored one re-opened from the tree — and
 * the draft of its fields. The dialog (DOM) and the server-solved preview both
 * read it; nothing here persists. OK sends one POST (create) or one PATCH
 * (edit); Cancel drops the draft and the parts return to their solve.
 */
import type { LengthUnit } from "@loft/design";
import { create } from "zustand";

import type { JointMate } from "../api/assemblies";
import {
  draftFromJoint,
  type JointDraft,
  type JointDraftAction,
  jointDraftReducer,
  type JointOriginPick,
  newJointDraft,
} from "./joints";

export type JointDialogTarget =
  | { mode: "create"; a: JointOriginPick; b: JointOriginPick }
  | { mode: "edit"; mateId: string; label: string; joint: JointMate };

export interface JointDialogState {
  target: JointDialogTarget | null;
  draft: JointDraft;
  /** A refusal from the server (e.g. a value past a limit), verbatim. */
  error: string | null;
  submitting: boolean;
  openCreate: (a: JointOriginPick, b: JointOriginPick) => void;
  openEdit: (
    mateId: string,
    label: string,
    joint: JointMate,
    unit: LengthUnit,
  ) => void;
  dispatch: (action: JointDraftAction) => void;
  setError: (error: string | null) => void;
  setSubmitting: (submitting: boolean) => void;
  close: () => void;
}

export const useJointDialogStore = create<JointDialogState>((set) => ({
  target: null,
  draft: newJointDraft(),
  error: null,
  submitting: false,
  openCreate: (a, b) =>
    set({
      target: { mode: "create", a, b },
      draft: newJointDraft(),
      error: null,
      submitting: false,
    }),
  openEdit: (mateId, label, joint, unit) =>
    set({
      target: { mode: "edit", mateId, label, joint },
      draft: draftFromJoint(joint, unit),
      error: null,
      submitting: false,
    }),
  // An edit clears a standing refusal: the user is answering it.
  dispatch: (action) =>
    set((state) => ({
      draft: jointDraftReducer(state.draft, action),
      error: null,
    })),
  setError: (error) => set({ error }),
  setSubmitting: (submitting) => set({ submitting }),
  close: () =>
    set({
      target: null,
      draft: newJointDraft(),
      error: null,
      submitting: false,
    }),
}));
