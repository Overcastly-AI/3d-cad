/**
 * THE CUT-SHEET REGION — a scroll container that ADMITS it is one.
 *
 * Why this is a primitive and not a `div` (AUDIT-PRODUCT T-18, three passes).
 * The inspector's readouts were already inside an `overflow-y-auto` div, and at
 * the documented 1280x800 floor a finished part needs 674 px of title block in
 * a 478 px column. So the container worked and the product still failed: the
 * clip landed MID-ROW — `Max 150, 80, 8` sliced through the digits by the
 * pinned EXPORT strip — with no scrollbar, no rule, no mark of any kind. The
 * auditor's reading was the only one available from the pixels: "there is no
 * scroll container, and Min / Max / TOPOLOGY / STATUS are unreachable."
 * `document.elementFromPoint` at the Min row returned `SPAN:"Export"`, because
 * the row was laid out below the fold and the strip owned those pixels.
 *
 * An overflow that is invisible is not a scroll container, it is a truncation.
 * Two things fix that, and both speak the title block's own language rather
 * than adding a new one (the signature stays with the ruled card):
 *
 * - **The break rule.** A drawing that continues past a cut says so. A clipped
 *   edge here carries the panel's own hairline with a short fade of the anvil
 *   ground above it, so a half-sliced row dissolves into the sheet and
 *   terminates on a rule instead of a guillotine cut. It appears ONLY on an
 *   edge that is actually hiding content, top or bottom, so it is a readout —
 *   never decoration (mandate 3a: chrome that only decorates is a defect).
 * - **The travel mark.** Slim, square-cornered, `etch` on `anvil`: how much
 *   sheet there is and where you are on it. It is drawn by this component and
 *   not left to the platform because the platform cannot be relied on to say
 *   anything — measured in this project's own capture environment, Chromium
 *   renders OVERLAY scrollbars (gutter 0 px, painted only mid-scroll), so a
 *   panel hiding four sections looks identical to one showing everything. On
 *   an engine that DOES draw a classic bar the mark stands down rather than
 *   doubling it, and `scrollbar-instrument` (the Tailwind preset, same tokens)
 *   dresses that bar in the same ink.
 *
 * Keyboard: a scrollable region that the keyboard cannot reach is a trap for
 * anyone not using a mouse (axe `scrollable-region-focusable`). While — and
 * only while — there is something to scroll, the viewport takes `tabindex=0`,
 * `role="region"` and the given name, so Tab lands on it and the arrow keys
 * work, with the same inset brass focus ring the rest of the panel uses. No
 * tab stop is added when everything already fits.
 *
 * Motion: none. There is no smooth-scroll and no fade transition to gate, so
 * `prefers-reduced-motion` has nothing to suppress.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { cx } from "../cx";

/** Which edges are currently hiding content — the region's own readout. */
export type ScrollEdges = "none" | "top" | "bottom" | "both";

export interface ScrollRegionProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "children" | "role"
> {
  /**
   * Accessible name for the region, used only once it is actually scrollable
   * (at which point it becomes a focusable `role="region"`).
   */
  label: string;
  children: ReactNode;
  /** Classes for the OUTER box — sizing and ground live here. */
  className?: string;
  /**
   * Classes for the CONTENT box inside the viewport. It exists so the region
   * has exactly one element whose size is the content's size: a ResizeObserver
   * on the viewport fires when the COLUMN resizes, never when the content
   * grows inside it, so without this the break rule would go stale the moment
   * a material assignment added two rows.
   */
  contentClassName?: string;
}

/** Sub-pixel slack: a 0.4 px rounding must not light the break rule. */
const EDGE_EPSILON_PX = 1;

/** Shortest travel thumb (%), so a very long sheet still shows one. */
const MIN_THUMB_PERCENT = 12;

function edgesOf(el: HTMLElement): ScrollEdges {
  const above = el.scrollTop > EDGE_EPSILON_PX;
  const below =
    el.scrollTop + el.clientHeight < el.scrollHeight - EDGE_EPSILON_PX;
  if (above && below) return "both";
  if (above) return "top";
  if (below) return "bottom";
  return "none";
}

/** Where we are in the sheet, as `{ height, top }` percentages of the track. */
interface Travel {
  heightPercent: number;
  topPercent: number;
}

function travelOf(el: HTMLElement): Travel {
  const ratio = el.clientHeight / el.scrollHeight;
  const heightPercent = Math.max(MIN_THUMB_PERCENT, ratio * 100);
  const range = el.scrollHeight - el.clientHeight;
  const progress = range <= 0 ? 0 : el.scrollTop / range;
  return { heightPercent, topPercent: progress * (100 - heightPercent) };
}

export function ScrollRegion({
  label,
  children,
  className,
  contentClassName,
  ...rest
}: ScrollRegionProps) {
  const viewport = useRef<HTMLDivElement | null>(null);
  const content = useRef<HTMLDivElement | null>(null);
  const [edges, setEdges] = useState<ScrollEdges>("none");
  const [scrollable, setScrollable] = useState(false);
  const [travel, setTravel] = useState<Travel | null>(null);

  const measure = useCallback(() => {
    const el = viewport.current;
    if (el === null) return;
    const next = edgesOf(el);
    // Only re-render on a real transition — this runs on every scroll event.
    setEdges((current) => (current === next ? current : next));
    const canScroll = el.scrollHeight - el.clientHeight > EDGE_EPSILON_PX;
    setScrollable((current) => (current === canScroll ? current : canScroll));
    // The platform's own bar, WHERE IT HAS ONE. A classic scrollbar takes
    // layout width, so this gutter is a direct measurement of whether the user
    // is already being shown their position — and where they are, the travel
    // mark below would just be a second bar beside the first.
    const nativeGutter = el.offsetWidth - el.clientWidth > EDGE_EPSILON_PX;
    setTravel(canScroll && !nativeGutter ? travelOf(el) : null);
  }, []);

  // The content grows and shrinks under the region (a material assignment adds
  // two rows; a rebuild changes the topology counts), and the column itself
  // resizes with the frame. Observe BOTH: measuring only on scroll would leave
  // the rule lit on a region that no longer overflows.
  useEffect(() => {
    const el = viewport.current;
    if (el === null || typeof ResizeObserver === "undefined") {
      measure();
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    if (content.current !== null) observer.observe(content.current);
    measure();
    return () => observer.disconnect();
  }, [measure]);

  const showTop = edges === "top" || edges === "both";
  const showBottom = edges === "bottom" || edges === "both";

  return (
    <div
      className={cx("relative flex min-h-0 flex-col", className)}
      data-scroll-edges={edges}
      {...rest}
    >
      <div
        ref={viewport}
        onScroll={measure}
        // A focusable region ONLY while there is something to reach — see the
        // module header. `undefined` (not `-1`) so nothing is added otherwise.
        tabIndex={scrollable ? 0 : undefined}
        role={scrollable ? "region" : undefined}
        aria-label={scrollable ? label : undefined}
        className={cx(
          "scrollbar-instrument min-h-0 overflow-y-auto",
          "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        )}
      >
        <div ref={content} className={contentClassName}>
          {children}
        </div>
      </div>
      {/* THE TRAVEL MARK — how much sheet there is and where you are on it.
          It exists because the platform bar cannot be relied on to say so:
          measured in this project's own capture environment, Chromium renders
          OVERLAY scrollbars, which take no layout width and are painted only
          while a scroll is in flight — so a panel hiding four sections looks
          identical to one showing everything. Where the engine DOES draw a
          classic bar (a measurable gutter) this stands down rather than
          doubling it. Wired to `scrollTop`/`scrollHeight`, so it is a readout,
          not an ornament (mandate 3a); dragging is deliberately not offered,
          because the wheel, the arrow keys and the platform bar already move
          the sheet and a third mover would be three ways to do one thing. */}
      {travel !== null ? (
        <div
          aria-hidden
          data-testid="scroll-travel"
          className="pointer-events-none absolute inset-y-0 right-0 w-1.5 border-l border-hairline bg-anvil"
        >
          <div
            data-testid="scroll-travel-thumb"
            className="absolute inset-x-0 bg-etch"
            style={{
              height: `${travel.heightPercent}%`,
              top: `${travel.topPercent}%`,
            }}
          />
        </div>
      ) : null}
      {/* Break rules. `aria-hidden` + `pointer-events-none`: they report, they
          are not operable, and a click must reach the row underneath. */}
      {showTop ? (
        <div
          aria-hidden
          data-testid="scroll-edge-top"
          className="pointer-events-none absolute inset-x-0 top-0 h-6 border-t border-hairline bg-gradient-to-b from-anvil to-transparent"
        />
      ) : null}
      {showBottom ? (
        <div
          aria-hidden
          data-testid="scroll-edge-bottom"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-6 border-b border-hairline bg-gradient-to-t from-anvil to-transparent"
        />
      ) : null}
    </div>
  );
}
