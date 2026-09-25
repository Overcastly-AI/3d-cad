/**
 * Toolbar primitives — the grouped-icon layer that carries Loft's growing
 * tool count (frontend-design plan, docs/design/toolbar-system.md). Built ON
 * the existing machine-shop token system, not beside it: square corners,
 * hairline rules, scribed icons, and brass spent only on the active scribe —
 * never a filled button. Chrome recedes; the viewport keeps the pixels.
 *
 * Keyboard is still the primary surface (the global sketch key handler is
 * untouched); these buttons are the DISCOVERABLE surface, and each teaches its
 * accelerator through a `Kbd` chip in the tooltip — icons for the eye, letters
 * for the hands.
 */
import { useId } from "react";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  MouseEvent,
  ReactNode,
} from "react";

import { cx } from "../cx";
import { color } from "../tokens";

/** A shortcut chip — a small stamped key, brass on the carbide ground. */
export function Kbd({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cx(
        "inline-flex min-w-4 items-center justify-center rounded-sm border border-hairline",
        "bg-carbide px-1 py-px font-data text-2xs not-italic leading-none text-brass",
        className,
      )}
      {...rest}
    />
  );
}

/**
 * The stamped tooltip a band control wears — the accelerator engraved beside
 * the name, with a quiet caption (count / reason) on a second line so the
 * resting control stays a single icon-thin row.
 *
 * Extracted from `ToolButton` when `Flyout` became its second real user
 * (DRY: extract on the second use, not the first imagined one). A flyout
 * trigger that has shed its label under the band's measured tier is otherwise
 * an unnamed pictograph, which is the "chrome that only decorates" defect in a
 * different costume — the tooltip is what keeps the shed state honest.
 *
 * `data-tooltip` is the QA hook for z-order/occlusion asserts, and the node is
 * always mounted (it hides by opacity, never unmount) so `aria-describedby`
 * can point at the caption.
 */
export function ToolStamp({
  label,
  shortcut,
  caption,
  captionId,
  side = "bottom",
}: {
  label: ReactNode;
  shortcut?: string | undefined;
  caption?: ReactNode | undefined;
  captionId?: string | undefined;
  side?: "bottom" | "top" | undefined;
}) {
  return (
    <span
      aria-hidden
      data-tooltip
      className={cx(
        "pointer-events-none absolute left-1/2 z-30 -translate-x-1/2",
        side === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5",
        "flex flex-col gap-0.5 whitespace-nowrap border border-hairline bg-anvil px-2 py-1",
        "font-body text-2xs text-mist opacity-0",
        "group-hover/tt:opacity-100 group-focus-visible/tt:opacity-100",
        "motion-safe:transition-opacity motion-safe:duration-fast",
      )}
    >
      <span className="flex items-center gap-1.5">
        {label}
        {shortcut ? <Kbd>{shortcut}</Kbd> : null}
      </span>
      {caption ? (
        <span id={captionId} className="font-data text-2xs text-gauge">
          {caption}
        </span>
      ) : null}
    </span>
  );
}

/**
 * How a band tool wears the NEXT-STEP OFFER (FLOW-B3), or undefined when it is
 * not the proposed tool.
 *
 *  - `"resting"` — the anchor dot alone. The full offer (leader + stamp) comes
 *    up on hover and on keyboard focus, exactly where the plain tooltip would.
 *  - `"announced"` — the full offer is up UNPROMPTED. The caller decides when
 *    a proposal is new enough to say out loud and for how long; this primitive
 *    only knows how it looks.
 */
export type ToolProposal = "resting" | "announced";

/**
 * Band-density geometry of the offer, in CSS px. Explicit numbers rather than
 * spacing utilities for the same reason the dot always was raw SVG: the
 * theme's spacing scale is CLOSED, Tailwind emits nothing at all for a step it
 * cannot generate, and this repo has shipped three zero-area marks that way.
 * Everything is derived from the dot, so the leader cannot drift off it.
 */
const OFFER = {
  /** The dot's box and its inset from the tool's top-right corner. */
  dot: 6,
  dotInset: 4,
  /** The leader: a two-tone hairline, carbide casing under a brass core. */
  casing: 3,
  core: 1,
  /** Gap between the tool's bottom edge and the stamp — the tooltip's `mt-1.5`. */
  drop: 6,
} as const;
/** The dot's centre, measured in from the tool's top and right edges. */
const DOT_CENTRE = OFFER.dotInset + OFFER.dot / 2;
/**
 * The leader's brass core occupies the whole-pixel column whose LEFT edge is
 * `DOT_CENTRE` in from the tool's right edge — within half a pixel of the
 * dot's centre, and never on a half pixel (a fractional 1px line is smeared
 * across two device pixels at half strength, and reads as a smudge). The casing
 * straddles the core by a pixel either side, and the stamp's left border sits
 * on the same column, so the line runs unbroken from dot to chip corner.
 */
const CASING_RIGHT = DOT_CENTRE - OFFER.core - (OFFER.casing - OFFER.core) / 2;

/**
 * THE BAND'S NEXT-STEP OFFER — `viewport/ProposalNote`'s one-mark grammar
 * (anchor dot, leader, stamped chip) at the band's density, rather than a
 * second look for the same idea.
 *
 * At rest only the ANCHOR is drawn: the 6px brass dot at the tool's top-right
 * corner, zero width, and deliberately not the active scribe (`aria-pressed`
 * + bottom line already mean "this tool is ON", and a proposal is not a
 * state). On hover, on keyboard focus, and while `announced`, the rest of the
 * note comes up: a leader drops from the dot past the tool's bottom edge and
 * lands on the near corner of a stamp that names the offer — `NEXT` + the
 * tool's own name + its key — over the proposal's caption.
 *
 * It REPLACES the tool's ordinary tooltip rather than stacking beside it: two
 * stamps hanging from one tool would be the "three dialects" failure drawn on
 * screen. Same box semantics as `ToolStamp` (`data-tooltip`, always mounted,
 * hidden by opacity, the caption node carries `captionId`), so every consumer
 * of the tooltip contract — `aria-describedby`, the z-order probes — keeps
 * working on the proposed tool too.
 *
 * WHY IT CANNOT STEAL A CLICK OR A KEY. Every node is `pointer-events: none`
 * and `aria-hidden`, and nothing here binds a key: the offer names the button,
 * it does not accept on its behalf. A click at the tool lands on the tool, and
 * `Enter` belongs to whatever holds focus (W2 review — a proposal note once
 * took `Enter` from the focused control, and this one has no handler to do
 * it with). Every node is ABSOLUTE, so the band's self-measurement, which sheds
 * labels by reading its row's width at 1280x800, never sees it.
 *
 * No motion beyond the tooltip's own opacity fade, and that only under
 * `motion-safe`: under `prefers-reduced-motion` the offer simply appears.
 */
export function ToolOffer({
  label,
  shortcut,
  caption,
  captionId,
  announced,
}: {
  label: ReactNode;
  shortcut?: string | undefined;
  caption?: ReactNode | undefined;
  captionId?: string | undefined;
  announced: boolean;
}) {
  // One visibility rule for the leader and the stamp, so the two halves of the
  // note can never be on screen without each other. The two branches are
  // exclusive rather than layered: `opacity-0` and `opacity-100` on one node
  // would leave the outcome to the order two utilities happen to occupy in the
  // generated stylesheet.
  const shown = announced
    ? "opacity-100"
    : "opacity-0 group-hover/tt:opacity-100 group-focus-visible/tt:opacity-100";
  const fade = "motion-safe:transition-opacity motion-safe:duration-fast";
  return (
    <>
      {/* THE ANCHOR — the resting mark, and the only part drawn at rest. The
          fill is the `color` token so DOM and WebGL keep one palette. */}
      <svg
        aria-hidden="true"
        data-testid="next-step-dot"
        width={OFFER.dot}
        height={OFFER.dot}
        viewBox="0 0 6 6"
        className="pointer-events-none absolute"
        style={{ top: OFFER.dotInset, right: OFFER.dotInset }}
      >
        <circle cx={3} cy={3} r={2.5} fill={color.brass} />
      </svg>

      {/* THE LEADER — from the dot's centre down past the tool's bottom edge to
          the stamp's near corner. TWO-TONE exactly as the viewport's leader,
          so the one mark is drawn the same way at both densities; the carbide
          casing also keeps the core distinct from the hovered cell's own
          carbide ground. Spans, not SVG — the tool's glyph is its only other
          SVG, and specs identify it as such. */}
      <span
        aria-hidden
        data-next-step-leader
        className={cx("pointer-events-none absolute z-30", shown, fade)}
        style={{
          top: DOT_CENTRE,
          bottom: -OFFER.drop,
          right: CASING_RIGHT,
          width: OFFER.casing,
          // The viewport casing's 0.55 opacity, carried in the colour's alpha
          // (0x8C) so it cannot fight the visibility rule for `opacity`.
          backgroundColor: `${color.carbide}8C`,
        }}
      >
        <span
          className="absolute inset-y-0"
          style={{
            left: (OFFER.casing - OFFER.core) / 2,
            width: OFFER.core,
            backgroundColor: color.brass,
          }}
        />
      </span>

      {/* THE STAMP — the viewport chip's material (anvil, hairline, float
          shadow), carrying words instead of being a control. The leader lands
          on its top-left corner, the corner nearest the anchor.

          OPAQUE, deliberately without the chip's `backdrop-blur`: this node is
          ALWAYS MOUNTED on the proposed tool (hidden by opacity, like every
          tooltip, so `aria-describedby` can resolve), so a backdrop filter
          here would sit over the WebGL canvas for as long as the proposal
          stands, on a node that is invisible nearly all of that time. The
          viewport chip is mounted only while it is on screen, so it pays for
          its blur only then; this node takes the tooltip's opaque ground
          instead. Not measured to cost a frame — simply not a risk worth
          taking for a 90 % tint. */}
      <span
        aria-hidden
        data-tooltip
        data-testid="next-step-label"
        data-announced={announced ? "true" : "false"}
        className={cx(
          "pointer-events-none absolute z-30 top-full",
          "flex flex-col gap-0.5 whitespace-nowrap border border-hairline",
          "bg-anvil px-2 py-1 shadow-float",
          shown,
          fade,
        )}
        style={{
          marginTop: OFFER.drop,
          left: `calc(100% - ${DOT_CENTRE}px)`,
        }}
      >
        <span className="flex items-center gap-1.5 font-display text-2xs uppercase tracking-[0.16em]">
          <span className="text-gauge">Next</span>
          <span className="text-brass">{label}</span>
          {shortcut ? <Kbd>{shortcut}</Kbd> : null}
        </span>
        {caption ? (
          <span id={captionId} className="font-data text-2xs text-mist">
            {caption}
          </span>
        ) : null}
      </span>
    </>
  );
}

export interface ToolButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
> {
  /** Scribed glyph (an icon component's element). Rendered aria-hidden. */
  icon: ReactNode;
  /** Human name — the tooltip title and the default accessible name. */
  label: string;
  /** Keyboard accelerator, shown as a `Kbd` chip in the tooltip. */
  shortcut?: string;
  /** Toggle/selected state — sets `aria-pressed` and the brass scribe. */
  active?: boolean;
  /**
   * Show the `label` text beside the icon. Inside a `CommandBand`, labels are
   * a MEASURED tier, not a constant: the band probes the row's natural width
   * and sheds labels a `ToolGroup.labelPriority` level at a time until what
   * remains fits, writing `data-labels` on each group. This label collapses
   * via ancestor-attribute CSS when its own group is shed (icon + group
   * eyebrow + tooltip carry the name), so the no-wrap band can never clip or
   * hide a tool group at any width, including when future groups land. No
   * viewport-breakpoint arithmetic to go stale (the 2026-07-24 audit P0 was
   * exactly that staleness). Outside a band the label simply shows.
   */
  showLabel?: boolean;
  /**
   * Quiet supplement — engraved in the tooltip, not stacked, and ALWAYS the
   * button's accessible description (see the component doc below). Two things
   * legitimately ride it: why the tool is gated ("Solve a sketch first") and
   * what a click would do ("marks the file partial"). Write it as the second
   * line of a sentence the button's name starts, in either case.
   */
  caption?: ReactNode;
  /**
   * Where the tooltip hangs. Top-anchored strips drop it BELOW (default);
   * bottom-anchored surfaces (the viewport's view rail) raise it ABOVE so the
   * window edge never clips it.
   */
  tooltipSide?: "bottom" | "top";
  /**
   * This tool is the band's NEXT-STEP OFFER (see {@link ToolOffer}): it wears
   * the anchor dot, and its tooltip becomes the offer's leader note. Undefined
   * for every other tool. Additive to `caption`, never instead of it — the
   * proposal's words ride `caption` exactly as before, so the accessible
   * description is the same sentence whether or not the note is on screen.
   */
  proposal?: ToolProposal | undefined;
  /** Override the computed accessible name (label + shortcut otherwise). */
  "aria-label"?: string;
}

/**
 * One tool. Icon-forward and dense; the label rides along only where the
 * surface has room (`showLabel`). The tooltip appears on hover AND keyboard
 * focus (a11y), sits BELOW the button so the top-anchored strip never clips
 * it, and is aria-hidden so the accessible name isn't announced twice.
 *
 * A gated tool uses `aria-disabled`, NOT the native `disabled` attribute, so a
 * disabled tool still HOVERS and FOCUSES — and therefore still shows its
 * tooltip + reason `caption` ("Solve a sketch first") to both mouse and
 * keyboard (UI-REVIEW 2026-07-16, Track C P1). It's inert on activation:
 * clicks and Enter/Space are swallowed. Playwright's `toBeDisabled()` /
 * `toBeEnabled()` honor `aria-disabled`, so existing gate assertions still hold.
 *
 * The caption also reaches SCREEN READERS: whenever one is rendered, the
 * button's `aria-describedby` points at the caption node (always in the DOM —
 * the tooltip hides by opacity, not unmount). Directly-referenced nodes are
 * exempt from `aria-hidden` in the accessible name/description computation, so
 * the visual tooltip behavior is untouched (BACKLOG P2, UR2 QA 2026-07-17).
 *
 * That wiring used to be gated on `disabled`, which read as a deliberate design
 * and was a defect (A11Y-TOOLBTN-1). The caption carries two different things —
 * a GATE REASON while disabled ("Solve a sketch first": why you cannot) and a
 * QUALIFIER while enabled ("marks the file partial": what happens if you do) —
 * and only the first was ever announced, so an enabled-but-qualified tool told
 * a sighted user on hover what a screen-reader user was never told at all.
 *
 * Both now get the SAME treatment, deliberately, for three reasons. (a) They
 * are one node: the tooltip renders them identically, so announcing only one
 * would make the spoken UI and the drawn UI disagree about what the caption is.
 * (b) The distinction is already carried by `aria-disabled`, which every screen
 * reader announces before the description — prefixing the text would re-encode
 * state the state attribute already owns. (c) A rule of the form "captions
 * announce sometimes" is the defect itself; "the caption always describes the
 * button" is the only version a consumer can rely on without reading this file.
 *
 * Consequence for CONSUMERS: do not fold a caption's words into `aria-label` to
 * force them out — that makes the accessible NAME change as state changes, so
 * the same control answers to two names through one flow. Pass the sentence as
 * `caption` and let it describe.
 */
export function ToolButton({
  icon,
  label,
  shortcut,
  active,
  showLabel,
  caption,
  tooltipSide = "bottom",
  proposal,
  className,
  type,
  disabled,
  onClick,
  "aria-describedby": describedByProp,
  ...rest
}: ToolButtonProps) {
  const accessibleName =
    rest["aria-label"] ?? (shortcut ? `${label} — ${shortcut}` : label);
  const isDisabled = disabled === true;
  // Caption description (see the doc comment above): the caption node describes
  // the button whenever there is one — gate reason or qualifier, disabled or
  // enabled. A consumer-provided `aria-describedby` is preserved alongside it,
  // never clobbered.
  const captionId = useId();
  // Truthiness deliberately mirrors the caption render condition below, so the
  // id is only referenced when the caption node actually exists in the DOM.
  // NOT `isDisabled && …`: that was A11Y-TOOLBTN-1, and it silenced every
  // enabled qualifier in every command band.
  const hasCaption = Boolean(caption);
  const describedBy =
    [describedByProp, hasCaption ? captionId : undefined]
      .filter(Boolean)
      .join(" ") || undefined;
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (isDisabled) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };

  return (
    <button
      type={type ?? "button"}
      aria-pressed={active}
      aria-disabled={isDisabled || undefined}
      aria-describedby={describedBy}
      aria-label={accessibleName}
      onClick={handleClick}
      className={cx(
        "group/tt relative inline-flex select-none items-center rounded-sm py-1.5",
        // Padding + gap follow the label tier: icon-only spacing when the
        // enclosing CommandBand has measured itself into the icon tier. EVERY
        // tool gets the same comfortable ≥32px target (`min-h-8`), labelled or
        // not, so one band row has one hover geometry; icon-only tools are
        // square (`min-w-8`). This promise was made in 2026-07 and unmet until
        // 2026-07-30, when `py-1.5` turned out to be a class the closed spacing
        // scale never emitted, leaving every band tool 16px tall.
        "min-h-8",
        // The enclosing group's `data-labels` is the ONE mechanism that hides
        // a label. There used to be a second, keyed on the band's own
        // `data-band-tier=icon` — with graduated shedding that selector is
        // actively harmful, not merely redundant: the band passes THROUGH the
        // icon tier while it buys labels back, so a band-level rule would keep
        // every label hidden during the probe, report that each tranche
        // "fits", and then show all of them at once when the final tier lands.
        // Measured exactly that on the part band: 2650.88px of row in a 1280px
        // frame, tier reported "mixed", every group labeled.
        showLabel
          ? "gap-2 px-3 [[data-labels=off]_&]:px-2"
          : "min-w-8 justify-center px-2",
        "transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        isDisabled ? "cursor-not-allowed opacity-40" : "hover:bg-carbide",
        active ? "text-brass" : "text-mist",
        className,
      )}
      {...rest}
    >
      <span className="flex shrink-0 items-center">{icon}</span>
      {showLabel ? (
        <span className="block min-w-0 truncate text-left font-display text-2xs uppercase tracking-[0.12em] [[data-labels=off]_&]:hidden">
          {label}
        </span>
      ) : null}

      {/* Active scribe — the accent is a line, never a fill. */}
      {active ? (
        <span
          aria-hidden
          // QA hook: the signature accent is a LINE, so its size is the
          // assertion. It measured 0x0 for months because the `inset-x-1.5` /
          // `h-px` steps were missing from the closed spacing scale, and a 0x0
          // element is invisible in a screenshot review (UI-REVIEW 2026-07-30).
          data-scribe
          className="pointer-events-none absolute inset-x-1.5 bottom-0.5 h-px bg-brass"
        />
      ) : null}

      {/* Tooltip: an anvil stamp with the accelerator engraved. The z-30 is
          LOCAL to the enclosing stacking context; page-level ordering (band
          above panels, so this stamp never hides behind the feature tree)
          comes from the `zLayer` scale on the band itself. */}
      {proposal === undefined ? (
        <ToolStamp
          label={label}
          shortcut={shortcut}
          caption={caption}
          captionId={captionId}
          side={tooltipSide}
        />
      ) : (
        <ToolOffer
          label={label}
          shortcut={shortcut}
          caption={caption}
          captionId={captionId}
          announced={proposal === "announced"}
        />
      )}
    </button>
  );
}

export interface ToolGroupProps extends HTMLAttributes<HTMLDivElement> {
  /** Tracked-caps cluster name (encodes the real taxonomy, not decoration). */
  eyebrow?: string;
  /**
   * How hard this group holds on to its labels when the band runs out of room
   * — HIGHER keeps its words longer (`CommandBand` guarantee #3). Groups that
   * share a value are shed together, so peers are never half-dressed.
   *
   * The scale is per-band and means nothing on its own; what it encodes is
   * INFORMATION PER PIXEL. A label earns its width when the glyph cannot carry
   * the identity — a format code like "3MF" is an identifier no picture can
   * spell, while "Extrude" merely repeats a glyph the eyebrow and tooltip
   * already name. Rank accordingly, and say why at the call site.
   *
   * Left at the default, every group on a surface shares one level and the
   * band flips as a unit — the two-tier behaviour that predates this.
   */
  labelPriority?: number;
}

/**
 * A labeled cluster of tools — the Fusion-style "group" rendered in
 * Plasticity density. The eyebrow names the family (Geometric / Dimensional /
 * Relational / Create); the members sit in a tight row beneath it.
 *
 * `data-labels` is written by the enclosing `CommandBand` after it measures,
 * never rendered here: React would fight the imperative probe for it, and a
 * group that has not been measured yet must default to showing its labels so
 * the band's first measurement sees the widest configuration.
 */
export function ToolGroup({
  eyebrow,
  labelPriority = 0,
  className,
  children,
  ...rest
}: ToolGroupProps) {
  return (
    <div
      role="group"
      aria-label={eyebrow}
      data-label-priority={labelPriority}
      className={cx("flex flex-col justify-center px-1.5 py-1", className)}
      {...rest}
    >
      {eyebrow ? (
        <span className="px-1 pb-0.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
          {eyebrow}
        </span>
      ) : null}
      <div className="flex items-stretch gap-0.5">{children}</div>
    </div>
  );
}
