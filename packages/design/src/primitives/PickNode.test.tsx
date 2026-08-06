import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PickNode } from "./PickNode";

/**
 * SEL-1 A7 — the pick reticle RECEDES at rest, only at rest, and only where
 * something else took over the aiming.
 *
 * Why these assertions and not a pixel census. The acceptance criterion asks
 * for one (`docs/design/pre-selection.md` §6, A7, citing design mandate 3c),
 * and the repo's pixel probes cannot deliver it: `countTokenPixels` and every
 * other census in `e2e/support.ts` read the WebGL canvas
 * (`[data-testid="viewport"] canvas`), while a `PickNode` is a DOM node
 * projected over that canvas by drei `Html`. It contributes ZERO canvas pixels.
 *
 * That is not a footnote, it is the reason the "DOM-square blanket" survived so
 * long: every pixel gate we own is structurally blind to it, so no census could
 * ever have scored it, before or after. The honest instrument is the property
 * itself — the rendered class list that decides the opacity — which is exact,
 * cheap, and cannot be satisfied by making anything else on screen worse.
 *
 * THREE things have to hold together, and the third is the one the first cut
 * got wrong (code review, 2026-08-06): rest must drop, the addressed states
 * must not, and the drop must be OPT-IN. A7 argued the recession only became
 * safe once A2 made the drawn surface the hit-test — true of the sketch-plane
 * face pick and of nothing else. Measure, fillet/chamfer, shell/draft,
 * instance-mate and hole-point all still hang their only click handler on this
 * button, so a global dim would have dimmed the aim affordance on five
 * surfaces. `recede` is the scope, and `false` is the safe default.
 */

/** The reticle span — `aria-hidden`, so it is reached through the button. */
function reticleOf(container: HTMLElement): HTMLElement {
  const mark = container.querySelector<HTMLElement>("button > span");
  if (mark === null) throw new Error("no reticle rendered");
  return mark;
}

describe("PickNode — rest-state recession (SEL-1 A7)", () => {
  it("recedes at rest where the surface itself is the hit-test", () => {
    const { container } = render(
      <PickNode aria-label="Face at 0, 0, 10 mm" shape="face" recede />,
    );
    expect(reticleOf(container).className).toContain("opacity-60");
  });

  it("stays at FULL strength where it is still the only hit-test", () => {
    // The unconverted overlays (measure, edge pick, shell/draft, mate, hole
    // point) render exactly this. Dimming here would dim the thing you aim
    // with, which is the trade A7 exists to refuse — so the default is opaque
    // and the recession is something a converted surface has to ask for.
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" />,
    );
    const cls = reticleOf(container).className;
    expect(cls).toContain("opacity-100");
    expect(cls).not.toContain("opacity-60");
  });

  it("returns to full strength on hover and on keyboard focus", () => {
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" recede />,
    );
    const cls = reticleOf(container).className;
    // Addressing the node — by pointer or by Tab — restores it. Without these
    // the item would have shipped a mark that never answers.
    expect(cls).toContain("group-hover/pn:opacity-100");
    expect(cls).toContain("group-focus-visible/pn:opacity-100");
  });

  it("a chosen node stays at full strength", () => {
    const { container } = render(
      <PickNode
        aria-label="Face at 0, 0, 10 mm"
        shape="face"
        recede
        selected
      />,
    );
    const cls = reticleOf(container).className;
    expect(cls).toContain("opacity-100");
    expect(cls).not.toContain("opacity-60");
  });

  it("every shape recedes — the blanket was not one kind of mark", () => {
    for (const shape of ["vertex", "edge", "face", "center"] as const) {
      const { container, unmount } = render(
        <PickNode aria-label={`${shape} at 0, 0, 0 mm`} shape={shape} recede />,
      );
      expect(reticleOf(container).className, shape).toContain("opacity-60");
      unmount();
    }
  });

  it("never recedes past the WCAG 1.4.11 non-text floor", () => {
    // 60 %, not 50 %. The halo ring is the weaker half of the two-tone mark on
    // a light machined face, and `carbide` over `aluminum` measures 2.98:1 at
    // 50 % — under the 3:1 floor for a control's boundary — against 3.86:1 at
    // 60 %. Asserted as the literal class because that string IS the decision;
    // a test that re-derived the ratio would only be re-stating the arithmetic
    // in the comment above the class.
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" recede />,
    );
    const cls = reticleOf(container).className;
    expect(cls).toContain("opacity-60");
    expect(cls).not.toContain("opacity-50");
    expect(cls).not.toContain("opacity-40");
  });

  it("KEEPS the 24px target — this is a contrast cut, never a size cut", () => {
    // WCAG 2.5.8, and the floor FB-19 states for any density work. Shrinking
    // the hit area would trade "too many to see" for "cannot hit it", which on
    // a laptop trackpad is the worse defect.
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" recede />,
    );
    const button = screen.getByRole("button");
    expect(button.className).toContain("h-6");
    expect(button.className).toContain("w-6");
    // The reticle itself is unchanged at 12px; only its opacity moved.
    expect(reticleOf(container).className).toContain("h-3");
  });
});
