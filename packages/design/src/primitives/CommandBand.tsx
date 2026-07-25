/**
 * CommandBand — the full-width command surface under the brand bar (the
 * conventional CAD anchor; Fusion/Plasticity both put the tools here). One
 * primitive owns the two guarantees the 2026-07-24 hard audit demanded:
 *
 * 1. **The band can never widen the app frame.** `overflow-x: clip` (X only —
 *    overflow-y stays `visible`, so tooltips/flyouts/transient sheets still
 *    hang below the band) removes the band's content from the page's
 *    scrollable overflow entirely: no root horizontal scrollbar, and
 *    hovering/focusing a tool can never scroll the app sideways (clip forbids
 *    even programmatic scroll).
 *
 * 2. **Label tiers are MEASURED, never breakpoint arithmetic.** The old
 *    `showLabel` tier ("labeled band ≈ 1315px natural → fits ≥1360") went
 *    stale the moment the Sheet-metal + Inspect groups landed and silently
 *    hid whole tool groups at 1440–1600 (audit P0). Instead the band probes
 *    its own content: it stamps `data-band-tier="labeled"`, reads the row's
 *    natural (max-content) width, and keeps labels only if that row fits the
 *    band — otherwise it steps to the icon tier (`data-band-tier="icon"`,
 *    which `ToolButton` reads via ancestor-attribute CSS). The probe re-runs
 *    on band resize AND on any content change (mode swaps, new tool groups),
 *    so a future group can never re-introduce the stale-arithmetic defect —
 *    the widest tier that fits is chosen, categorically. If one day even the
 *    icon tier cannot fit a surface at the 1280 responsive floor, grow an
 *    explicit "more" flyout — never let the band clip silently (the
 *    regression spec `e2e/toolbar-overflow.spec.ts` enforces this).
 *
 * The band also owns its page-level stacking layer (`z-band`, above the
 * floating panels): its tooltips and flyout menus hang into the viewport and
 * must never render behind a panel (audit P1). The band itself never
 * geometrically overlaps a panel, so panels lose nothing.
 */
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import type { HTMLAttributes } from "react";

import { cx } from "../cx";

/** The label tier the band measured itself into. */
export type CommandBandTier = "labeled" | "icon";

/** Sub-pixel slack: rect widths are fractional, clientWidth is an integer. */
const FIT_SLACK_PX = 0.5;

export type CommandBandProps = HTMLAttributes<HTMLDivElement>;

export function CommandBand({
  className,
  children,
  ...rest
}: CommandBandProps) {
  const bandRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);
  const [tier, setTier] = useState<CommandBandTier>("labeled");

  const measure = useCallback(() => {
    const band = bandRef.current;
    const row = rowRef.current;
    if (band === null || row === null) return;
    // Probe the labeled tier: flipping the attribute is a pure CSS reflow
    // (labels are hidden/shown by ancestor-attribute selectors), and the
    // browser never paints mid-task, so the probe is invisible. The row is
    // `w-max` (max-content), so its rect width IS the tier's natural width.
    band.dataset.bandTier = "labeled";
    const fitsLabeled =
      row.getBoundingClientRect().width <= band.clientWidth + FIT_SLACK_PX;
    const next: CommandBandTier = fitsLabeled ? "labeled" : "icon";
    band.dataset.bandTier = next;
    setTier(next);
  }, []);

  useLayoutEffect(() => {
    measure();
    const band = bandRef.current;
    if (band === null) return;
    const teardowns: Array<() => void> = [];
    // Re-measure when the band's own width changes (window resize) …
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(measure);
      ro.observe(band);
      teardowns.push(() => ro.disconnect());
    }
    // … and when its CONTENT changes (mode swap, a group mounting, a label
    // text change) — attribute churn (hover/pressed states) never moves
    // widths, so it is deliberately not observed.
    if (typeof MutationObserver !== "undefined") {
      const mo = new MutationObserver(measure);
      mo.observe(band, { childList: true, characterData: true, subtree: true });
      teardowns.push(() => mo.disconnect());
    }
    return () => {
      for (const teardown of teardowns) teardown();
    };
  }, [measure]);

  return (
    <div
      ref={bandRef}
      data-band-tier={tier}
      className={cx(
        // `relative` anchors transient sheets (`top-full` overlays) below the
        // band; `overflow-x-clip` is guarantee #1 above (X only — Y stays
        // visible so those sheets and the tooltips are never cut off).
        "relative z-band flex h-band shrink-0 items-stretch overflow-x-clip",
        "border-b border-hairline bg-anvil",
        className,
      )}
      {...rest}
    >
      {/* The measured row: max-content wide (so the probe reads the natural
          width), stretched to the band when content is narrower (min-w-full,
          so right-anchored cells like the in-command OK/Cancel still reach
          the edge), and never flex-shrunk under it (shrink-0 — shrinking
          would hide the very overflow the probe must see). */}
      <div
        ref={rowRef}
        className="flex w-max min-w-full shrink-0 items-stretch"
      >
        {children}
      </div>
    </div>
  );
}
