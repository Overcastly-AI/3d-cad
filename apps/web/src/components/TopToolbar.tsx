import type { ReactNode } from "react";

/**
 * The full-width command band — a conventional CAD top-toolbar spanning the
 * window edge-to-edge, directly beneath the brand bar (Fusion/Plasticity both
 * anchor the command surface here). It is mode-aware by composition: the
 * workspace feeds it the sketch tools while sketching and the feature-create
 * tools otherwise, so the top band is always THE command surface and the
 * viewport below keeps every pixel it can.
 *
 * `relative` so a strip's transient overlays (constraint hint / save error)
 * can hang from `top-full` into the viewport without thickening the band; the
 * band itself stays a single thin instrument row.
 */
export function TopToolbar({ children }: { children: ReactNode }) {
  return (
    <div
      data-testid="top-toolbar"
      className="relative z-10 flex h-band shrink-0 items-stretch overflow-visible border-b border-hairline bg-anvil"
    >
      {children}
    </div>
  );
}
