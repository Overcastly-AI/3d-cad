/**
 * The open 3D sketch (SKETCH-3D), shared by the editor panel and the viewport
 * layer: the panel types points and relations, the viewport draws the draft
 * and places snapped points. A store rather than props because the two sit
 * on opposite sides of the r3f Canvas.
 */
import { create } from "zustand";

import type { Sketch3DSnap, Vec3 } from "../api/parts";
import {
  continueTo,
  emptySketch3DForm,
  placePoint,
  type Sketch3DForm,
} from "./sketch3d";

interface Sketch3DStore {
  /** The form of the open 3D sketch editor, or null when none is open. */
  form: Sketch3DForm | null;
  /** The feature being edited (its own lines are not snap targets). */
  featureId: string | null;
  open: (form: Sketch3DForm, featureId: string | null) => void;
  close: () => void;
  update: (next: (form: Sketch3DForm) => Sketch3DForm) => void;
  /** A snap clicked in the viewport: place (or reuse) a point there. */
  snap: (position: Vec3, snap: Sketch3DSnap | null) => void;
  /** One of this sketch's own points clicked: continue the chain to it. */
  continueAt: (pointId: string) => void;
}

export const useSketch3DStore = create<Sketch3DStore>((set) => ({
  form: null,
  featureId: null,
  open: (form, featureId) => set({ form, featureId }),
  close: () => set({ form: null, featureId: null }),
  update: (next) => set((s) => ({ form: next(s.form ?? emptySketch3DForm()) })),
  snap: (position, snap) =>
    set((s) =>
      s.form === null ? s : { form: placePoint(s.form, position, snap) },
    ),
  continueAt: (pointId) =>
    set((s) => (s.form === null ? s : { form: continueTo(s.form, pointId) })),
}));
