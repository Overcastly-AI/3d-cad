/**
 * Healing a re-anchored reference. The dangerous failure here is silent: a heal
 * that writes the WRONG edge into the stored dimension moves the annotation onto
 * geometry the user never picked, and the sheet would go on looking correct. So
 * these pin (a) that only a `durable` tier offers anything to confirm, (b) that
 * each dimension type takes the signature the anchor's contract assigns it
 * (primary = the measured edge / circle / `edge_a` / the first endpoint's edge),
 * (c) that the authored PLACEMENT survives untouched, and (d) that a half-filled
 * anchor heals NOTHING rather than half of a two-edge dimension.
 */
import { describe, expect, it } from "vitest";

import type {
  DimensionAnchor,
  DimensionParams,
  EdgeSignature,
  MeasuredDimension,
} from "../api/drawings";
import { healDimensionParams, reanchoredAnchor } from "./anchorHeal";

function sig(x: number): EdgeSignature {
  return {
    subshape_type: "edge",
    curve: "line",
    end_a: { x: 0, y: 0, z: 0 },
    end_b: { x, y: 0, z: 0 },
    midpoint: { x: x / 2, y: 0, z: 0 },
    length_mm: x,
  };
}

const OLD = sig(100);
const NEW_A = sig(120);
const NEW_B = sig(60);

function anchor(
  tier: DimensionAnchor["tier"],
  primary: EdgeSignature | null = NEW_A,
  secondary: EdgeSignature | null = NEW_B,
): DimensionAnchor {
  return { tier, primary, secondary };
}

function measured(a: DimensionAnchor | null): MeasuredDimension {
  return {
    value: 120,
    unit: "mm",
    foreshortened: false,
    error: null,
    anchor: a,
  };
}

describe("reanchoredAnchor", () => {
  it("says nothing for an exact match — the everyday case", () => {
    expect(reanchoredAnchor(measured(anchor("exact")))).toBeNull();
  });

  it("says nothing when there is no anchor at all", () => {
    expect(reanchoredAnchor(measured(null))).toBeNull();
    expect(reanchoredAnchor(undefined)).toBeNull();
  });

  it("reports a durable re-anchor", () => {
    const a = anchor("durable");
    expect(reanchoredAnchor(measured(a))).toEqual(a);
  });
});

describe("healDimensionParams", () => {
  const placement = { offset_mm: 11, text_pos: { x_mm: 5, y_mm: 6 } };

  it("heals a linear edge-length onto the primary signature", () => {
    const params: DimensionParams = {
      type: "linear",
      measurement: { mode: "edge_length", edge: OLD },
      placement,
    };
    const healed = healDimensionParams(params, anchor("durable"));
    expect(healed).toEqual({
      type: "linear",
      measurement: { mode: "edge_length", edge: NEW_A },
      placement,
    });
    // The authored placement is preserved by identity, not merely by value.
    expect(healed?.placement).toBe(placement);
  });

  it("heals a point-to-point linear on BOTH endpoints, keeping which end", () => {
    const params: DimensionParams = {
      type: "linear",
      measurement: {
        mode: "point_to_point",
        a: { signature: OLD, endpoint: "end_b" },
        b: { signature: OLD, endpoint: "end_a" },
      },
      placement,
    };
    const healed = healDimensionParams(params, anchor("durable"));
    expect(healed).toEqual({
      type: "linear",
      measurement: {
        mode: "point_to_point",
        a: { signature: NEW_A, endpoint: "end_b" },
        b: { signature: NEW_B, endpoint: "end_a" },
      },
      placement,
    });
  });

  it("heals a diameter and a radius onto the primary signature", () => {
    for (const type of ["diameter", "radius"] as const) {
      const healed = healDimensionParams(
        { type, edge: OLD, placement },
        anchor("durable"),
      );
      expect(healed).toEqual({ type, edge: NEW_A, placement });
    }
  });

  it("heals an angular onto primary/secondary in edge_a/edge_b order", () => {
    const healed = healDimensionParams(
      { type: "angular", edge_a: OLD, edge_b: OLD, placement },
      anchor("durable"),
    );
    expect(healed).toEqual({
      type: "angular",
      edge_a: NEW_A,
      edge_b: NEW_B,
      placement,
    });
  });

  it("refuses a half-filled anchor rather than writing half a reference", () => {
    const noSecondary = anchor("durable", NEW_A, null);
    expect(
      healDimensionParams(
        { type: "angular", edge_a: OLD, edge_b: OLD, placement },
        noSecondary,
      ),
    ).toBeNull();
    expect(
      healDimensionParams(
        {
          type: "linear",
          measurement: {
            mode: "point_to_point",
            a: { signature: OLD, endpoint: "end_a" },
            b: { signature: OLD, endpoint: "end_b" },
          },
          placement,
        },
        noSecondary,
      ),
    ).toBeNull();
    // ...but a single-edge dimension needs only the primary.
    expect(
      healDimensionParams(
        { type: "radius", edge: OLD, placement },
        noSecondary,
      ),
    ).not.toBeNull();
  });

  it("refuses when the anchor names no edge at all", () => {
    expect(
      healDimensionParams(
        { type: "radius", edge: OLD, placement },
        anchor("durable", null, null),
      ),
    ).toBeNull();
  });
});
