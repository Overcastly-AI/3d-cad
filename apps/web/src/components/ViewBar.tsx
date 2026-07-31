/**
 * The view rail (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-2) — persistent
 * view navigation at the bottom of the scene, the Fusion nav-bar position.
 * Every button fires a REAL camera command through the view command store
 * (nothing decorates); the numeric accelerators are engraved in the
 * tooltips. The in-canvas reference cube is its 3D counterpart.
 */
import {
  ToolButton,
  ViewFitIcon,
  ViewFrontIcon,
  ViewHomeIcon,
  ViewIsoIcon,
  ViewRightIcon,
  ViewTopIcon,
} from "@loft/design";

import { useViewCommandStore } from "../viewport/viewCommands";

export function ViewBar() {
  const request = useViewCommandStore((state) => state.request);
  return (
    <div
      data-testid="view-bar"
      role="toolbar"
      aria-label="View navigation"
      // Docks over the scene, so "Fit model" must frame the part ABOVE it —
      // the rail is one of the things the founder's part was hiding under
      // (`fitFraming.ts`).
      data-viewport-chrome="view-bar"
      className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-stretch border border-hairline bg-anvil shadow-float"
    >
      <ToolButton
        icon={<ViewHomeIcon />}
        label="Home view"
        shortcut="Home"
        tooltipSide="top"
        data-testid="view-home"
        onClick={() => request("home")}
      />
      <ToolButton
        icon={<ViewFitIcon />}
        label="Fit model"
        shortcut="0"
        tooltipSide="top"
        data-testid="view-fit"
        onClick={() => request("fit")}
      />
      <span aria-hidden className="my-1 w-px bg-hairline" />
      <ToolButton
        icon={<ViewFrontIcon />}
        label="Front view"
        shortcut="1"
        tooltipSide="top"
        data-testid="view-front"
        onClick={() => request("front")}
      />
      <ToolButton
        icon={<ViewTopIcon />}
        label="Top view"
        shortcut="2"
        tooltipSide="top"
        data-testid="view-top"
        onClick={() => request("top")}
      />
      <ToolButton
        icon={<ViewRightIcon />}
        label="Right view"
        shortcut="3"
        tooltipSide="top"
        data-testid="view-right"
        onClick={() => request("right")}
      />
      <ToolButton
        icon={<ViewIsoIcon />}
        label="Isometric view"
        shortcut="4"
        tooltipSide="top"
        data-testid="view-iso"
        onClick={() => request("iso")}
      />
    </div>
  );
}
