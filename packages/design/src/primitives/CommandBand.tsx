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
 *    its own content: it reads the row's natural (max-content) width and
 *    keeps the widest set of labels that actually fits. The probe re-runs on
 *    band resize AND on any content change (mode swaps, new tool groups), so
 *    a future group can never re-introduce the stale-arithmetic defect. If
 *    one day even the icon tier cannot fit a surface at the 1280 responsive
 *    floor, grow an explicit "more" flyout — never let the band clip silently
 *    (the regression spec `e2e/toolbar-overflow.spec.ts` enforces this).
 *
 * 3. **Labels are shed GROUP BY GROUP, in a declared order — not all at once.**
 *    The tier used to be a two-position switch: 30 labels or none. That does
 *    not scale, and EXPORT-1 proved it. Measured on the part band: the fully
 *    labeled row needs **2650.9px** and the icon row **1047.5px**, so after a
 *    sixth group landed there was no display in the mainstream range
 *    (1280–2560) that could show a single label — the "labeled" tier had
 *    become chrome only a synthetic test viewport ever saw, which design
 *    mandate 3a(c) calls a defect. Meanwhile the band sat on 233px of unused
 *    width at 1280 and 1513px at 2560 with no way to spend it, because the
 *    only alternative cost 1603px in one step.
 *
 *    So each `ToolGroup` declares a `labelPriority` (higher keeps its words
 *    longer) and the band buys labels back one PRIORITY LEVEL at a time until
 *    the next level would not fit. Peers share a level, so groups of equal
 *    standing never disagree and the band is never half-dressed among equals;
 *    the result is a prefix of the declared order, so it is a function of the
 *    order and the width alone — never of enumeration order or of which group
 *    happens to be cheapest. The old behaviour is the degenerate case: a
 *    surface whose groups all take the default priority still flips as one.
 *
 *    `data-band-tier` reports the outcome — `labeled` (every group), `icon`
 *    (none), `mixed` (a prefix) — and each group carries `data-labels` so a
 *    test, and the CSS in `ToolButton`, can read the decision per group.
 *
 * The band also owns its page-level stacking layer (`z-band`, above the
 * floating panels): its tooltips and flyout menus hang into the viewport and
 * must never render behind a panel (audit P1). The band itself never
 * geometrically overlaps a panel, so panels lose nothing.
 */
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import type { HTMLAttributes } from "react";

import { cx } from "../cx";

/**
 * The label tier the band measured itself into: every group labeled, none of
 * them, or a prefix of the declared priority order.
 */
export type CommandBandTier = "labeled" | "icon" | "mixed";

/** Sub-pixel slack: rect widths are fractional, clientWidth is an integer. */
const FIT_SLACK_PX = 0.5;

/**
 * Groups opt into the graduated tier by carrying this attribute — `ToolGroup`
 * always emits it, so every group on every band participates automatically and
 * a new one cannot silently escape the fit probe.
 */
const PRIORITY_ATTR = "data-label-priority";

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

    // Flipping these attributes is a pure CSS reflow (labels are hidden/shown
    // by ancestor-attribute selectors) and the browser never paints mid-task,
    // so the whole probe is invisible. The row is `w-max` (max-content), so
    // its rect width IS the natural width of whatever is currently shown.
    const groups = Array.from(
      band.querySelectorAll<HTMLElement>(`[${PRIORITY_ATTR}]`),
    );
    const fits = (): boolean =>
      row.getBoundingClientRect().width <= band.clientWidth + FIT_SLACK_PX;
    const show = (only: readonly HTMLElement[], state: "on" | "off"): void => {
      for (const group of only) group.dataset.labels = state;
    };

    // Widest configuration first — if every label fits, nothing else to decide.
    show(groups, "on");
    if (fits()) {
      band.dataset.bandTier = "labeled";
      setTier("labeled");
      return;
    }

    // Otherwise strip the band bare and buy labels back a priority level at a
    // time, stopping at the first level that does not fit. Stopping (rather
    // than skipping ahead to a cheaper level) is what makes the outcome a
    // prefix of the declared order instead of a knapsack result nobody can
    // predict from the source.
    //
    // `data-band-tier` is deliberately NOT written until the probe is over: it
    // reports the outcome and must never be an input to it. Writing "icon"
    // here — while any rule keyed on it can still hide a label — is what made
    // the first version of this measure every tranche as fitting.
    show(groups, "off");
    const priorityOf = (group: HTMLElement): number =>
      Number(group.dataset.labelPriority) || 0;
    const levels = [...new Set(groups.map(priorityOf))].sort((a, b) => b - a);
    let labeled = 0;
    for (const level of levels) {
      const tranche = groups.filter((group) => priorityOf(group) === level);
      show(tranche, "on");
      if (!fits()) {
        show(tranche, "off");
        break;
      }
      labeled += tranche.length;
    }

    const next: CommandBandTier = labeled === 0 ? "icon" : "mixed";
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
