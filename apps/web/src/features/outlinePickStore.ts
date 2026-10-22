/**
 * The OUTLINE PICK (BUILDING-OUTLINE): the bridge between a custom feature's
 * dialog and the viewport, which are sibling subtrees (the same problem the
 * edge-pick store solves).
 *
 * The dialog owns the values; it publishes what the viewport may pick:
 *
 *  - `sketch`: the sketches an Outline field may name, each line of each one
 *    pickable, a click naming its sketch (Fusion's "select a profile", Revit's
 *    "pick lines");
 *  - `segments`: the lines of the picked outline, named by side, a click
 *    toggling one in (Revit's Defines Slope, an opening's wall).
 *
 * It also takes a click on a browser row while the dialog is open
 * (`treePick`), so an Outline or a Floor can be picked from the tree as
 * Fusion's selection fields take a browser pick.
 */
import { create } from "zustand";

import type { FeatureResponse } from "../api/parts";

export type Vec3Tuple = [number, number, number];

/** One pickable line, in scene space. */
export interface OutlinePickLine {
  /** What a click on it names: a sketch id (`sketch`) or a line id. */
  readonly key: string;
  /** The line's own sketch id (unique within an offer with its sketch). */
  readonly lineId: string;
  /** "Front", or the sketch's name: the mark's accessible name. */
  readonly label: string;
  /** Whether this line carries the key's mark (one mark per sketch). */
  readonly marked: boolean;
  readonly start: Vec3Tuple;
  readonly end: Vec3Tuple;
}

export interface OutlinePickOffer {
  readonly kind: "sketch" | "segments";
  /** The field the pick fills (its input name). */
  readonly input: string;
  readonly lines: readonly OutlinePickLine[];
  /** The keys picked now (drawn selected). */
  readonly selected: readonly string[];
  readonly onPick: (key: string) => void;
}

interface OutlinePickState {
  offer: OutlinePickOffer | null;
  /** The key under the pointer, or null. */
  hover: string | null;
  /** The dialog's handler for a browser row click: true when it took it. */
  treePick: ((feature: FeatureResponse) => boolean) | null;
  setOffer: (offer: OutlinePickOffer | null) => void;
  setHover: (key: string | null) => void;
  setTreePick: (pick: ((feature: FeatureResponse) => boolean) | null) => void;
}

export const useOutlinePickStore = create<OutlinePickState>((set) => ({
  offer: null,
  hover: null,
  treePick: null,
  setOffer: (offer) => set({ offer, hover: null }),
  setHover: (hover) => set({ hover }),
  setTreePick: (treePick) => set({ treePick }),
}));

/**
 * A browser row click while a custom feature's dialog is open: the dialog
 * takes it when one of its picks accepts that feature. False otherwise, and
 * the click goes on to open the feature as before.
 */
export function pickFromTree(feature: FeatureResponse): boolean {
  const pick = useOutlinePickStore.getState().treePick;
  return pick !== null && pick(feature);
}
