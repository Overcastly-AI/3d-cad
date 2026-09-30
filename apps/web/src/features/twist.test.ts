import { describe, expect, it } from "vitest";

import type { SketchEntity } from "../api/parts";
import { readRepoSource } from "../test/wireSource";
import {
  MAX_TWIST_DEG,
  MIN_TWIST_DEG,
  parseTwistDeg,
  storedTwistInput,
  TWIST_COST_LIMIT_S,
  twistCostUpperS,
  twistError,
  twistHand,
} from "./twist";

/**
 * Review N1: MAX_TWIST_DEG / MIN_TWIST_DEG restate the wire model's bounds,
 * which the generated TS client carries as types only (no `maximum`). The
 * committed OpenAPI contract is generated from the same pydantic model and CI
 * fails on its drift, so it is the source these constants are held to.
 */
describe("the twist bounds match the contract (review N1)", () => {
  /** The contract's twist property, read LAZILY (see `wireSource.ts`). */
  function contractTwist():
    | {
        anyOf?: { maximum?: number; minimum?: number }[];
        description?: string;
      }
    | undefined {
    const contract = JSON.parse(
      readRepoSource("packages/contracts/gateway.openapi.json", {
        declaredIn: "contractTwist in apps/web/src/features/twist.test.ts",
        guards: "the twisted sweep's wire bounds (MAX/MIN_TWIST_DEG)",
      }),
    ) as {
      components: {
        schemas: Record<
          string,
          {
            properties?: Record<
              string,
              {
                anyOf?: { maximum?: number; minimum?: number }[];
                description?: string;
              }
            >;
          }
        >;
      };
    };
    return contract.components.schemas["SweepParamsV1"]?.properties?.[
      "twist_angle_deg"
    ];
  }

  it("MAX_TWIST_DEG is the schema's maximum and minus its minimum", () => {
    const bounded = contractTwist()?.anyOf?.find(
      (s) => s.maximum !== undefined,
    );
    expect(bounded?.maximum).toBe(MAX_TWIST_DEG);
    expect(bounded?.minimum).toBe(-MAX_TWIST_DEG);
  });

  it("MIN_TWIST_DEG is the threshold the contract normalises to no twist", () => {
    // Stated in prose on the wire model ("any |twist| below 1e-9 deg is NO
    // twist"); held to the text so a changed threshold cannot drift silently.
    expect(contractTwist()?.description).toContain(
      `below ${MIN_TWIST_DEG.toExponential()} deg`,
    );
  });
});

/**
 * Review S9, after the kernel's F4 cost guard (4c49218): the note keys on the
 * upper bound design note §6.1 publishes for the UI. The EXPECTED crossings
 * are the note's own "rough reach" figures, not recomputed from the formula.
 */
describe("twistCostUpperS (design note §6.1)", () => {
  function polygon(n: number): SketchEntity[] {
    return Array.from({ length: n }, (_, i) => {
      const a = (i / n) * 2 * Math.PI;
      const b = ((i + 1) / n) * 2 * Math.PI;
      return {
        id: `e${i}`,
        kind: "line" as const,
        start: { x: 10 * Math.cos(a), y: 10 * Math.sin(a) },
        end: { x: 10 * Math.cos(b), y: 10 * Math.sin(b) },
        construction: false,
      };
    });
  }
  const circle: SketchEntity[] = [
    {
      id: "c",
      kind: "circle",
      center: { x: 0, y: 0 },
      radius: 10,
      construction: false,
    },
  ];
  const deg = (turns: number) => turns * 360;

  it("passes the kernel's limit where the note says: square 10.2, hexagon 8.2, 12-gon 5.6, circle 9.0 turns", () => {
    for (const [entities, below, above] of [
      [polygon(4), 10.1, 10.3],
      [polygon(6), 8.1, 8.3],
      [polygon(12), 5.5, 5.7],
      [circle, 8.9, 9.1],
    ] as const) {
      expect(twistCostUpperS(deg(below), entities)).toBeLessThan(
        TWIST_COST_LIMIT_S,
      );
      expect(twistCostUpperS(deg(above), entities)).toBeGreaterThan(
        TWIST_COST_LIMIT_S,
      );
    }
  });

  it("counts profile edges only, and is signed-twist symmetric", () => {
    const withConstruction = [
      ...polygon(4),
      { ...polygon(1)[0]!, id: "k", construction: true },
      {
        id: "p",
        kind: "point" as const,
        at: { x: 0, y: 0 },
        construction: false,
      },
    ] as SketchEntity[];
    expect(twistCostUpperS(1800, withConstruction)).toBeCloseTo(
      twistCostUpperS(1800, polygon(4)),
      12,
    );
    expect(twistCostUpperS(-1800, polygon(4))).toBe(
      twistCostUpperS(1800, polygon(4)),
    );
  });

  it("TWIST_COST_LIMIT_S is the kernel's own limit", () => {
    const source = readRepoSource(
      "services/geometry/src/geometry/kernel/twist.py",
      {
        declaredIn:
          "twistCostUpperS tests in apps/web/src/features/twist.test.ts",
        guards: "the kernel's twist cost limit (TWIST_COST_LIMIT_S)",
      },
    );
    const match = /^TWIST_COST_LIMIT_S = ([\d.]+)/m.exec(source);
    expect(Number(match?.[1])).toBe(TWIST_COST_LIMIT_S);
  });
});

describe("the twist field (TWIST-TO-SWEEP)", () => {
  it("parses a signed twist; empty and vanishing are no twist; beyond ten turns is wrong", () => {
    expect(parseTwistDeg("")).toBe(0);
    expect(parseTwistDeg("  ")).toBe(0);
    expect(parseTwistDeg("12.358")).toBe(12.358);
    expect(parseTwistDeg("-30")).toBe(-30);
    expect(parseTwistDeg("1e-12")).toBe(0);
    expect(parseTwistDeg("3600")).toBe(3600);
    expect(parseTwistDeg("3600.1")).toBeNull();
    expect(parseTwistDeg("twelve")).toBeNull();
    expect(parseTwistDeg("NaN")).toBeNull();
    expect(parseTwistDeg("Infinity")).toBeNull();
    expect(twistError("-3600")).toBeNull();
    expect(twistError("4000")).toMatch(/3600/);
  });

  it("names the hand the way an engineer says it", () => {
    expect(twistHand(15)).toBe("Right-hand");
    expect(twistHand(-15)).toBe("Left-hand");
    expect(twistHand(0)).toBeNull();
  });

  it("seeds a stored twist EXACTLY, so a no-op Save sends it back (review B1)", () => {
    for (const angle of [31.280937437761875, -0.1 - 0.2, 12.358, 3600]) {
      expect(parseTwistDeg(storedTwistInput(angle))).toBe(angle);
    }
  });
});
