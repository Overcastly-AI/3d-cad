/**
 * The four snap marks name WHICH snap the sketcher is about to take, at ~20px,
 * over a live drawing. Their whole job is being told apart at a glance, so the
 * legibility constraint is the contract: each is drawn from a DIFFERENT set of
 * primitives, and none of them relies on a fill to carry the difference.
 *
 * That rule is not stylistic. The eye set's first cut distinguished its three
 * states by a filled-vs-hollow pupil and measured ILLEGIBLE at 16px
 * (`docs/design/ui-wave-tool-grade.md` Surface 2, as-built correction 2), so
 * these are asserted rather than eyeballed.
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  SnapCenterIcon,
  SnapEndpointIcon,
  SnapIntersectionIcon,
  SnapMidpointIcon,
  SnapOnCurveIcon,
  SnapOriginIcon,
  SnapXAxisIcon,
  SnapYAxisIcon,
} from "./icons";

/**
 * The mark's shape signature — which primitives it is built from, and for a
 * path how many SEPARATE strokes it has, whether it closes, and which drawing
 * verbs it uses. Element tags alone are too coarse: a closed triangle and two
 * crossing diagonals are both "a path", and they are the two forms most at
 * risk of converging under a well-meaning simplification.
 */
function signature(node: Element): string {
  return [...node.querySelectorAll("rect, circle, path")]
    .map((el) => {
      if (el.tagName.toLowerCase() !== "path") return el.tagName.toLowerCase();
      const d = el.getAttribute("d") ?? "";
      const strokes = (d.match(/M/gi) ?? []).length;
      const verbs = [
        ...new Set((d.match(/[a-z]/gi) ?? []).map((c) => c.toUpperCase())),
      ]
        .sort()
        .join("");
      return `path(${strokes}${/z/i.test(d) ? "-closed" : ""}:${verbs})`;
    })
    .sort()
    .join("+");
}

const MARKS = {
  endpoint: <SnapEndpointIcon />,
  midpoint: <SnapMidpointIcon />,
  center: <SnapCenterIcon />,
  intersection: <SnapIntersectionIcon />,
  // The sketch PLANE's own frame joined the set once the sheet got a visible,
  // snappable origin. They compete in the same ranked list as the four object
  // snaps and are drawn at the same size in the same place, so they are held to
  // the same contract — and the pair most at risk of converging is X-axis vs
  // Y-axis, which differ ONLY by rotation. That is a whole-stroke difference in
  // a line's direction (the one axis a 90° rotation cannot hide), not a fill.
  origin: <SnapOriginIcon />,
  "x-axis": <SnapXAxisIcon />,
  "y-axis": <SnapYAxisIcon />,
  // The SELECT tool names its winning candidate with the same vocabulary
  // (SEL-2), which puts one more mark in the set: the on-curve pick tick. It is
  // held to the same contract because it is drawn at the same size in the same
  // place as the rest, and the mark it is most at risk of converging with is the
  // centre mark — both a curve plus a straight stroke. They differ by whole
  // strokes: a CLOSED circle crossed twice through its middle, against an OPEN
  // arc with one tick across it.
  "on-curve": <SnapOnCurveIcon />,
} as const;

describe("sketch snap marks", () => {
  it("draws every mark from a distinct set of strokes", () => {
    const signatures = Object.entries(MARKS).map(([kind, element]) => {
      const { container } = render(element);
      const svg = container.querySelector("svg");
      expect(svg, `${kind} renders an svg`).not.toBeNull();
      return [kind, signature(svg as Element)] as const;
    });
    // endpoint = one rect · midpoint = one closed path · centre = circle +
    // cross · intersection = one two-stroke path · origin = one bent corner ·
    // the two axes = three-stroke centrelines, level vs upright. The set must
    // be pairwise distinct, or two snaps look the same and the mark stops being
    // honest.
    const distinct = new Set(signatures.map(([, sig]) => sig));
    expect(distinct.size, JSON.stringify(signatures)).toBe(signatures.length);
  });

  it("never carries meaning in a fill — a fill difference is not a difference at 16px", () => {
    for (const [kind, element] of Object.entries(MARKS)) {
      const { container } = render(element);
      const svg = container.querySelector("svg");
      expect(svg?.getAttribute("fill"), kind).toBe("none");
      for (const shape of svg?.querySelectorAll("rect, circle, path") ?? []) {
        expect(shape.getAttribute("fill"), `${kind} shape fill`).toBeNull();
      }
    }
  });

  it("inherits its ink from the caller (one palette, no per-icon colour)", () => {
    const { container } = render(<SnapCenterIcon />);
    expect(container.querySelector("svg")).toHaveAttribute(
      "stroke",
      "currentColor",
    );
  });
});
