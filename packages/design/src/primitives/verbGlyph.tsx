/**
 * THE verb → glyph map. One source of truth for "which scribed icon means
 * `extrude`", read by every surface that has to draw a modeling verb: the
 * command band's Create/Modify tools and the bottom timeline's op chips (and
 * anything that lands next — a history list, a search palette).
 *
 * Why it lives here and not in the app: the glyph set is a design decision, and
 * the two consumers already existed with the choice inlined at each call site
 * (`icon={<ExtrudeIcon />}` in `CreateStrip`, and a second copy needed for the
 * timeline). That is the second real use, which is exactly when the DRY rule
 * says to extract — a band tool and a timeline chip for the same verb must never
 * be able to disagree.
 *
 * Keys are the WIRE feature types (`extrude`, `sheet_metal_hem`, …) so a tree
 * feature maps with no translation table, plus the handful of band verbs that
 * are commands rather than features (`import_step`, `flat_pattern`, `measure`).
 * An unknown key falls back to `StockIcon` — a generic blank, never a wrong
 * verb, and never nothing (a missing glyph would silently reflow the chip).
 */
import type { ComponentType } from "react";

import {
  BaseFlangeIcon,
  ChamferIcon,
  CombineIcon,
  CornerReliefIcon,
  DatumIcon,
  DraftIcon,
  EdgeFlangeIcon,
  ExtrudeIcon,
  FilletIcon,
  FlatPatternIcon,
  HemIcon,
  HoleIcon,
  type IconProps,
  ImportStepIcon,
  LoftIcon,
  MeasureIcon,
  MirrorIcon,
  PatternIcon,
  RevolveIcon,
  ShellIcon,
  SketchIcon,
  StockIcon,
  SweepIcon,
} from "./icons";

/** Every verb the product can draw, keyed by its wire name. */
export const VERB_GLYPHS: Readonly<Record<string, ComponentType<IconProps>>> = {
  // Feature types (the `feature.type` discriminator).
  sketch: SketchIcon,
  datum: DatumIcon,
  extrude: ExtrudeIcon,
  revolve: RevolveIcon,
  sweep: SweepIcon,
  loft: LoftIcon,
  fillet: FilletIcon,
  chamfer: ChamferIcon,
  shell: ShellIcon,
  draft: DraftIcon,
  hole: HoleIcon,
  mirror: MirrorIcon,
  pattern: PatternIcon,
  boolean: CombineIcon,
  import: ImportStepIcon,
  sheet_metal_base_flange: BaseFlangeIcon,
  sheet_metal_edge_flange: EdgeFlangeIcon,
  sheet_metal_hem: HemIcon,
  sheet_metal_corner_relief: CornerReliefIcon,
  // Band commands that are not feature types.
  import_step: ImportStepIcon,
  flat_pattern: FlatPatternIcon,
  measure: MeasureIcon,
};

export interface VerbGlyphProps extends IconProps {
  /** Wire verb name — a `feature.type` or a band command key. */
  verb: string;
}

/** The scribed glyph for a modeling verb (generic blank if the verb is new). */
export function VerbGlyph({ verb, ...rest }: VerbGlyphProps) {
  const Glyph = VERB_GLYPHS[verb] ?? StockIcon;
  return <Glyph {...rest} />;
}
