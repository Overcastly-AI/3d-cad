/**
 * The draw tools' guides, hung from the sketch strip into the viewport: the
 * Spline tool's fit-point count and the Project tool's pick guide. Split out
 * of `SketchStrip.tsx`; the strip decides when each shows.
 */
import { useEdgePickStore } from "../features/edgePickStore";
import { isProjected } from "../sketch/project";
import { useSketchStore } from "../sketch/store";

/**
 * The Project tool's guide, hung from the band into the viewport: what to
 * click, how many edges this sketch already follows, and the way out. Says
 * "Loading the body's edges" until the overlay arrives, so an armed tool with
 * nothing to click never looks broken.
 */
export function ProjectPrompt() {
  const count = useSketchStore(
    (state) => state.entities.filter(isProjected).length,
  );
  const loading = useEdgePickStore(
    (state) => state.purpose === "project" && state.overlay === null,
  );
  const error = useEdgePickStore((state) =>
    state.purpose === "project" ? state.overlayError : null,
  );
  return (
    <div
      role="status"
      data-testid="project-prompt"
      className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
    >
      {error !== null ? (
        <span className="text-flag">{error}</span>
      ) : loading ? (
        <span>Loading the body&rsquo;s edges…</span>
      ) : (
        <span>
          Click body edges to project them
          {count > 0 ? (
            <>
              {" · "}
              <span className="text-mist" data-testid="project-count">
                {count} projected
              </span>
            </>
          ) : null}
          {" · "}Esc to finish
        </span>
      )}
    </div>
  );
}

/**
 * The Spline tool's fit-point guide, hung from the band into the viewport. It
 * counts placed points and, once two are held, offers the keyboard-first finish
 * (Enter / double-click). Once committed, each fit point constrains like any
 * point (coincident / fixed / symmetric); the spline is also valid as part of a
 * closed extrude/revolve loop.
 */
export function SplinePrompt({ count }: { count: number }) {
  const ready = count >= 2;
  return (
    <div
      role="status"
      data-testid="spline-prompt"
      data-phase={ready ? "ready" : "collecting"}
      className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
    >
      {ready ? (
        <span>
          <span className="text-mist" data-testid="spline-count">
            {count} fit points
          </span>{" "}
          · Enter or double-click to finish · fit points constrain like any
          point
        </span>
      ) : (
        <span>
          Click to place fit points
          {count > 0 ? (
            <>
              {" · "}
              <span className="text-mist" data-testid="spline-count">
                {count} placed
              </span>
            </>
          ) : null}
        </span>
      )}
    </div>
  );
}
