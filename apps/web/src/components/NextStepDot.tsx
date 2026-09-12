/**
 * FLOW-B3 — the band's proposal mark: a 6px brass dot at the accented tool's
 * top-right corner.
 *
 * IT IS THE LEADER NOTE'S ANCHOR DOT, at the band's density. The viewport's
 * proposal (`viewport/SketchProposal.tsx`) draws an r=2 brass dot with a
 * carbide halo on the exact point its note is about; a 32px band cell has no
 * room for the leader and the stamped chip that follow it, so the band keeps
 * the anchor and drops the rest. One mark, two densities — NOT a second visual
 * language for the same idea, which is the failure the W2 direction brief
 * exists to prevent.
 *
 * RAW SVG, NOT TAILWIND SIZING, and this is not a style preference. The theme's
 * spacing scale is CLOSED (it ends at 12) and Tailwind emits nothing at all for
 * a utility it cannot generate — no warning, no error, just a rule that never
 * exists. This repo has shipped three separate zero-area defects that way, each
 * with a different cause and all three presenting identically as "the mark is
 * in the DOM and cannot be seen": an SVG stroke `getBoundingClientRect` ignores,
 * an `sr-only` element clipped out of frame, and a `w-32` that was never
 * generated. An explicit `width`/`height` on the element cannot fail that way.
 * The fill comes from the `color` token so the DOM and the WebGL viewport keep
 * one palette (CLAUDE.md DRY rule) — never a hex literal here.
 *
 * ABSOLUTE, so it costs ZERO WIDTH: the band measures itself and sheds labels
 * when it runs out of room, so a mark that widened a tool could push a whole
 * group into the icon tier at the 1280x800 floor. It positions against
 * `ToolButton`'s own `relative` box, which is why it rides in the `icon` slot
 * rather than wrapping the button.
 *
 * It is deliberately NOT the active scribe (`bottom-0.5 h-px bg-brass` +
 * `aria-pressed`) and does NOT turn the glyph brass: both of those already mean
 * "this tool is ON", and a proposal is not a state.
 *
 * SILENT to assistive tech. The proposal reaches a screen-reader user as the
 * accented tool's `caption`, which `ToolButton` routes through
 * `aria-describedby` — words, in the place words already live. A decorative
 * mark announcing itself would be chatter.
 */
import { color } from "@loft/design";

export function NextStepDot() {
  return (
    <svg
      aria-hidden="true"
      data-testid="next-step-dot"
      width={6}
      height={6}
      viewBox="0 0 6 6"
      className="pointer-events-none absolute right-1 top-1"
    >
      <circle cx={3} cy={3} r={2.5} fill={color.brass} />
    </svg>
  );
}
