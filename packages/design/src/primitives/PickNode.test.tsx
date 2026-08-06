import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PickNode } from "./PickNode";

/**
 * SEL-1 A7 — the pick reticle RECEDES at rest, and only at rest.
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
 * The pairing is what matters: rest must drop AND the three addressed states
 * must not. A change that dimmed everything would close the complaint by
 * breaking the control, which is the trade this explicitly refuses.
 */

/** The reticle span — `aria-hidden`, so it is reached through the button. */
function reticleOf(container: HTMLElement): HTMLElement {
  const mark = container.querySelector<HTMLElement>("button > span");
  if (mark === null) throw new Error("no reticle rendered");
  return mark;
}

describe("PickNode — rest-state recession (SEL-1 A7)", () => {
  it("is dimmed at rest", () => {
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" />,
    );
    expect(reticleOf(container).className).toContain("opacity-50");
  });

  it("returns to full strength on hover and on keyboard focus", () => {
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" />,
    );
    const cls = reticleOf(container).className;
    // Addressing the node — by pointer or by Tab — restores it. Without these
    // the item would have shipped a mark that never answers.
    expect(cls).toContain("group-hover/pn:opacity-100");
    expect(cls).toContain("group-focus-visible/pn:opacity-100");
  });

  it("a chosen node stays at full strength", () => {
    const { container } = render(
      <PickNode aria-label="Face at 0, 0, 10 mm" shape="face" selected />,
    );
    const cls = reticleOf(container).className;
    expect(cls).toContain("opacity-100");
    expect(cls).not.toContain("opacity-50");
  });

  it("every shape recedes — the blanket was not one kind of mark", () => {
    for (const shape of ["vertex", "edge", "face", "center"] as const) {
      const { container, unmount } = render(
        <PickNode aria-label={`${shape} at 0, 0, 0 mm`} shape={shape} />,
      );
      expect(reticleOf(container).className, shape).toContain("opacity-50");
      unmount();
    }
  });

  it("KEEPS the 24px target — this is a contrast cut, never a size cut", () => {
    // WCAG 2.5.8, and the floor FB-19 states for any density work. Shrinking
    // the hit area would trade "too many to see" for "cannot hit it", which on
    // a laptop trackpad is the worse defect.
    const { container } = render(
      <PickNode aria-label="Vertex at 0, 0, 0 mm" />,
    );
    const button = screen.getByRole("button");
    expect(button.className).toContain("h-6");
    expect(button.className).toContain("w-6");
    // The reticle itself is unchanged at 12px; only its opacity moved.
    expect(reticleOf(container).className).toContain("h-3");
  });
});
