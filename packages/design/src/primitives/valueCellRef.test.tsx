// @vitest-environment jsdom
/**
 * THE VALUE CELLS HAND BACK THEIR INPUT (DIM-1).
 *
 * These primitives own the `<input>`, so a screen that wants the BROWSER to own
 * the text — uncontrolled, because a controlled cell inside the r3f canvas
 * drops keystrokes at human typing speed — can only read what was typed through
 * a ref. Without one the caller's alternatives are all worse: a controlled
 * value (the defect), or a hand-rolled `<input>` in app code (restyling a raw
 * element, which the design rule forbids).
 *
 * Pinned here rather than in the app because the FIX BELONGS TO THE PRIMITIVE:
 * a `ref` silently dropped from the props spread type-checks at the definition
 * and fails only at the third caller, at runtime, as a null commit.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { ExpressionField } from "./ExpressionField";
import { NumberField } from "./NumberField";

afterEach(cleanup);

describe("value cells forward a ref to their input", () => {
  it("ExpressionField — the dimension cell", () => {
    const ref = createRef<HTMLInputElement>();
    render(
      <ExpressionField
        label="Distance"
        unit="mm"
        ref={ref}
        defaultValue="43"
      />,
    );
    expect(ref.current).toBe(screen.getByLabelText("Distance"));
    // What a commit reads: the node's own text, not a rendered prop. Typing is
    // simulated at the DOM level exactly as the browser does it.
    ref.current!.value = "125";
    expect(ref.current?.value).toBe("125");
  });

  it("NumberField — the offset/corner cells, both layouts", () => {
    const stacked = createRef<HTMLInputElement>();
    const inline = createRef<HTMLInputElement>();
    render(
      <>
        <NumberField label="Offset" unit="mm" ref={stacked} defaultValue="2" />
        <NumberField
          label="Radius"
          unit="mm"
          layout="inline"
          ref={inline}
          defaultValue="2"
        />
      </>,
    );
    // `inline` routes the cell through FieldRow — a different return path, and
    // the one a ref would most easily be lost on.
    expect(stacked.current).toBe(screen.getByLabelText("Offset"));
    expect(inline.current).toBe(screen.getByLabelText("Radius"));
  });
});
