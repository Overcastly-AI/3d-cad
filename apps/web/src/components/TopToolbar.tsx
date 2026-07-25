import { CommandBand } from "@loft/design";
import type { ReactNode } from "react";

/**
 * The full-width command band — a conventional CAD top-toolbar spanning the
 * window edge-to-edge, directly beneath the brand bar (Fusion/Plasticity both
 * anchor the command surface here). It is mode-aware by composition: the
 * workspace feeds it the sketch tools while sketching and the feature-create
 * tools otherwise, so the top band is always THE command surface and the
 * viewport below keeps every pixel it can.
 *
 * All band behavior lives in the `CommandBand` primitive (fix the primitive,
 * not the instance): the measured label tier (`data-band-tier`), the
 * overflow clamp (the band can never widen the app frame or hide a tool
 * group), and the `z-band` stacking layer that keeps its tooltips/flyouts
 * above the floating panels. Strips' transient overlays (constraint hint /
 * save error) still hang from `top-full` into the viewport without
 * thickening the band — the band stays a single thin instrument row.
 */
export function TopToolbar({ children }: { children: ReactNode }) {
  return <CommandBand data-testid="top-toolbar">{children}</CommandBand>;
}
