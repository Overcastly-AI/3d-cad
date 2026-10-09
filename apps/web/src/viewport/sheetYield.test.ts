import { describe, expect, it } from "vitest";

import { bodyTakesRay, PLANE_PICK_BODY_ID } from "./sheetYield";

const hit = (pickId?: string) => ({
  object: { userData: pickId === undefined ? {} : { pickId } },
});

describe("bodyTakesRay (SKETCH-PLANE-PICK)", () => {
  it("gives the ray to the body when it strikes the body, nearer or not", () => {
    expect(
      bodyTakesRay({ intersections: [hit(), hit(PLANE_PICK_BODY_ID)] }),
    ).toBe(true);
    expect(
      bodyTakesRay({ intersections: [hit(PLANE_PICK_BODY_ID), hit()] }),
    ).toBe(true);
  });

  it("leaves the ray to the sheet off the body's silhouette", () => {
    expect(bodyTakesRay({ intersections: [hit()] })).toBe(false);
    expect(bodyTakesRay({ intersections: [hit("mate-instance")] })).toBe(false);
  });
});
