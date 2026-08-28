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

import {
  PROJECTION_SHORTCUT,
  useViewCommandStore,
} from "../viewport/viewCommands";

/**
 * The projection cell — the rail's one WORD, and deliberately a word.
 *
 * A drawing states its projection convention in the title block, in engraved
 * caps, because the reader has to know which one they are measuring against;
 * this rail cell is the same statement about the live view. It is a readout AND
 * the control that changes it: the projection moves on its own when a named
 * view is asked for (`viewCommands.orients`), so a plain icon toggle would
 * leave the modeller guessing which mode a snap had just put them in. The word
 * always says which. Brass = parallel, i.e. what you see is what you can
 * measure; mist = perspective, the free look.
 *
 * Typeset with `ToolButton`'s own label classes so the cell is
 * indistinguishable from a labelled tool — no new primitive, no second visual
 * language in a six-button rail.
 */
function ProjectionMark({ parallel }: { parallel: boolean }) {
  return (
    <span className="font-display text-2xs uppercase tracking-[0.12em]">
      {parallel ? "Ortho" : "Persp"}
    </span>
  );
}

export function ViewBar() {
  const request = useViewCommandStore((state) => state.request);
  const projection = useViewCommandStore((state) => state.projection);
  const toggleProjection = useViewCommandStore(
    (state) => state.toggleProjection,
  );
  const parallel = projection === "orthographic";
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
      <span aria-hidden className="my-1 w-px bg-hairline" />
      <ToolButton
        icon={<ProjectionMark parallel={parallel} />}
        // The tooltip names the state; the caption names the action, so the
        // button never has to be both at once.
        label={parallel ? "Orthographic" : "Perspective"}
        caption={parallel ? "Switch to perspective" : "Switch to orthographic"}
        shortcut={PROJECTION_SHORTCUT}
        active={parallel}
        tooltipSide="top"
        data-testid="view-projection"
        aria-label={
          parallel ? "Projection: orthographic" : "Projection: perspective"
        }
        onClick={toggleProjection}
      />
    </div>
  );
}
