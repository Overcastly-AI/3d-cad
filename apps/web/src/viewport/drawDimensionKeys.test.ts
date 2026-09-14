import { describe, expect, it } from "vitest";

import {
  bufferDrawKey,
  bufferHasText,
  bufferedText,
  type DrawKeyBuffer,
} from "./drawDimensionKeys";

const OPTIONS = { draftId: "a,b,c,d", fieldCount: 2 };

/** Type a whole sequence from nothing, the way the burst arrives. */
function type(keys: string[], options = OPTIONS): DrawKeyBuffer | null {
  let buffer: DrawKeyBuffer | null = null;
  for (const key of keys) {
    const outcome = bufferDrawKey(buffer, key, options);
    if (outcome.kind === "buffered") buffer = outcome.buffer;
  }
  return buffer;
}

describe("bufferDrawKey", () => {
  it("keeps the audit's plate: 100 Tab 50 Enter, typed into nothing", () => {
    const buffer = type(["1", "0", "0", "Tab", "5", "0", "Enter"]);
    expect(buffer).not.toBeNull();
    expect(bufferedText(buffer!, 0)).toBe("100");
    expect(bufferedText(buffer!, 1)).toBe("50");
    expect(buffer!.apply).toBe(true);
  });

  it("takes a decimal point, so 12.5 survives the window as well as 12", () => {
    expect(bufferedText(type(["1", "2", ".", "5"])!, 0)).toBe("12.5");
  });

  it("leaves every other key to the canvas", () => {
    for (const key of ["r", "l", "g", "Escape", "ArrowLeft", "F5", " "]) {
      expect(bufferDrawKey(null, key, OPTIONS).kind).toBe("ignored");
    }
  });

  it("does not eat Backspace when there is nothing to correct", () => {
    expect(bufferDrawKey(null, "Backspace", OPTIONS).kind).toBe("ignored");
    expect(bufferedText(type(["1", "0", "Backspace"])!, 0)).toBe("1");
  });

  it("wraps on Tab, so the pair is a loop and not a dead end", () => {
    expect(type(["Tab"])!.index).toBe(1);
    expect(type(["Tab", "Tab"])!.index).toBe(0);
    const back = bufferDrawKey(null, "Tab", { ...OPTIONS, shiftKey: true });
    expect(back.kind === "buffered" && back.buffer.index).toBe(1);
  });

  it("routes a one-cell shape's Tab back to its only cell", () => {
    const circle = { draftId: "circle", fieldCount: 1 };
    expect(type(["Tab", "7"], circle)!.text).toEqual(["7"]);
  });

  it("accepts a bare Enter as 'the shape is right as drawn'", () => {
    const buffer = type(["Enter"]);
    expect(buffer!.apply).toBe(true);
    expect(bufferHasText(buffer!)).toBe(false);
  });

  it("closes on Enter — what follows a commit is not this shape's size", () => {
    const buffer = type(["1", "0", "Enter", "9", "9"]);
    expect(bufferedText(buffer!, 0)).toBe("10");
  });

  /**
   * The leak this guard exists for: draw, type into the void, draw again. A
   * buffer that outlived its shape would write the first rectangle's width
   * into the second one — a wrong size arriving from nowhere, which is a worse
   * defect than the dropped keystroke it would be fixing.
   */
  it("never lets one shape's typing reach the next", () => {
    const first = type(["1", "0", "0"])!;
    const outcome = bufferDrawKey(first, "5", {
      draftId: "e,f,g,h",
      fieldCount: 2,
    });
    expect(outcome.kind === "buffered" && outcome.buffer.draftId).toBe(
      "e,f,g,h",
    );
    expect(outcome.kind === "buffered" && bufferedText(outcome.buffer, 0)).toBe(
      "5",
    );
  });

  it("refuses a draft with no cells rather than inventing one", () => {
    expect(bufferDrawKey(null, "1", { draftId: "x", fieldCount: 0 }).kind).toBe(
      "ignored",
    );
  });
});
