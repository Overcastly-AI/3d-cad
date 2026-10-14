/**
 * A solved sketch feature, ready to render. Split out of `SketchScene.tsx`
 * (check-file-size) and re-exported there, so every import is unchanged.
 */
import type { PlaneBasis } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";

/** One solved sketch feature, ready to render (on its resolved plane basis). */
export interface SolvedSketchLayer {
  featureId: string;
  basis: PlaneBasis;
  entities: SketchEntity[];
  /**
   * The curves the geometry service builds this sketch's profile from
   * (`profile_entities`); absent means every non-construction curve. Previews
   * stitch only these, so they agree with the commit (QA-PROJECTED-PROFILE).
   */
  profileEntityIds?: readonly string[];
}
