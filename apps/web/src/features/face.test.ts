import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type {
  FeatureResponse,
  OverlayFace,
  PlanarFaceSignature,
} from "../api/parts";
import {
  BODY_AFFECTING_FEATURE_TYPES,
  faceLabel,
  faceOrdinalOfSignature,
  faceSignatureKey,
  faceSubshapeRef,
  isFacePicked,
  isPickableFace,
  lastBodyFeatureId,
  onFaceDatumParams,
  toggleFace,
} from "./face";

/**
 * The py-kit module the client set mirrors. The path is deliberate: if the
 * module moves, this test fails loudly rather than silently stopping guarding
 * anything (the idiom `thread.test.ts` uses for the kernel's pitch table).
 */
const PY_KIT_FEATURES = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../packages/py-kit/src/py_kit/schemas/features.py",
);

/**
 * Parse `BODY_AFFECTING_FEATURE_TYPES` out of the py-kit module — THE source of
 * truth for the set (`packages/py-kit/src/py_kit/schemas/features.py`).
 *
 * Comments are stripped before the string literals are read, because the
 * comments inside that frozenset quote prose (`"sketch on an imported part's
 * face"`) that would otherwise parse as a member.
 *
 * The OpenAPI schema cannot express "body-affecting" (it is a semantic subset,
 * not a field), so the set cannot come from the generated contract today —
 * exposing it as a generated enum in `packages/contracts` would retire this
 * parse entirely, and is filed as a follow-up.
 */
function pyKitBodyAffecting(source: string): string[] {
  const marker = "\nBODY_AFFECTING_FEATURE_TYPES = frozenset(";
  const start = source.indexOf(marker);
  expect(
    start,
    "py-kit BODY_AFFECTING_FEATURE_TYPES not found",
  ).toBeGreaterThan(-1);
  const open = source.indexOf("{", start);
  const close = source.indexOf("\n)", open);
  const types: string[] = [];
  for (const line of source.slice(open + 1, close).split("\n")) {
    const code = line.split("#")[0] ?? "";
    const match = /"([a-z_]+)"\s*,/.exec(code);
    if (match !== null) types.push(match[1] as string);
  }
  return types;
}

/**
 * A minimal feature row whose `feature.type` is set from `type` — the ONLY
 * field `lastBodyFeatureId` reads. A sketch envelope is the cheapest valid
 * shape; the type is then overridden in place.
 */
function typed(id: string, type: string, rolled_back = false): FeatureResponse {
  const row: FeatureResponse = {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
    rolled_back,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [],
        constraints: [],
      },
    },
  };
  (row.feature as { type: string }).type = type;
  return row;
}

const SIGNATURE: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 10, y: 10, z: 10 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};

describe("faceSubshapeRef", () => {
  it("echoes the signature into a stage-1 face reference", () => {
    expect(faceSubshapeRef("feat-1", SIGNATURE)).toEqual({
      kind: "subshape",
      feature_id: "feat-1",
      subshape_type: "face",
      selector: { selector_version: 1, signature: SIGNATURE },
    });
  });

  it("passes the signature through unchanged (full precision)", () => {
    const ref = faceSubshapeRef("feat-1", SIGNATURE);
    expect(ref.selector.signature).toBe(SIGNATURE);
  });
});

describe("onFaceDatumParams", () => {
  it("wraps the reference with a default on-face (offset 0) datum", () => {
    expect(onFaceDatumParams("feat-1", SIGNATURE)).toEqual({
      kind: "on_face",
      face: faceSubshapeRef("feat-1", SIGNATURE),
      offset_mm: 0,
    });
  });

  it("carries a signed offset along the face normal", () => {
    expect(onFaceDatumParams("feat-1", SIGNATURE, 5).offset_mm).toBe(5);
  });
});

describe("lastBodyFeatureId", () => {
  it("returns the last non-rolled-back body-affecting feature", () => {
    const tree = [
      typed("s1", "sketch"),
      typed("e1", "extrude"),
      typed("s2", "sketch"),
      typed("e2", "extrude"),
    ];
    expect(lastBodyFeatureId(tree)).toBe("e2");
  });

  it("skips rolled-back features (uses the current body)", () => {
    const tree = [
      typed("e1", "extrude"),
      typed("e2", "extrude", true), // rolled back — not in the current body
    ];
    expect(lastBodyFeatureId(tree)).toBe("e1");
  });

  it("treats a datum as NOT body-affecting", () => {
    const tree = [typed("e1", "extrude"), typed("d1", "datum")];
    expect(lastBodyFeatureId(tree)).toBe("e1");
  });

  it("returns null when no body-affecting feature exists", () => {
    expect(lastBodyFeatureId([typed("s1", "sketch")])).toBeNull();
    expect(lastBodyFeatureId([])).toBeNull();
  });

  // "recognises every body-affecting op" moved into the drift-guard block
  // below, where the list comes from py-kit instead of a hand-copy.
});

describe("BODY_AFFECTING_FEATURE_TYPES — backend drift guard", () => {
  const source = readFileSync(PY_KIT_FEATURES, "utf8");

  it("mirrors py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES exactly", () => {
    // A REAL drift guard (AUDIT-ENGINEERING J5): this reads the py-kit module
    // and compares the client set to what it actually declares, so adding a
    // body-affecting feature server-side and forgetting the client fails here.
    // Until 2026-07-30 it compared a hand-copy in this file to a hand-copy in
    // `face.ts` — BOTH inside apps/web — so backend drift could not fail it,
    // while the comment claimed "a member added on ONE side fails here".
    const pyKit = pyKitBodyAffecting(source);
    // Non-vacuity: a regex that silently matched nothing (or a set that stopped
    // being a frozenset literal) would make the equality below vacuously true.
    expect(pyKit.length).toBeGreaterThan(15);
    expect(new Set(pyKit).size).toBe(pyKit.length);
    // Order-independent set equality: a member added on ONE side fails here.
    expect([...BODY_AFFECTING_FEATURE_TYPES].sort()).toEqual([...pyKit].sort());
  });

  it("recognises every body-affecting type py-kit declares", () => {
    // The pick-anchor consequence, stated as behaviour: `lastBodyFeatureId`
    // must anchor to EACH of them, or a later face/edge pick lands on the wrong
    // body (subshape_unresolved / a bad write-time dependency).
    for (const type of pyKitBodyAffecting(source)) {
      expect(lastBodyFeatureId([typed("x", type)])).toBe("x");
    }
  });

  it("excludes the types py-kit deliberately leaves out", () => {
    const pyKit = pyKitBodyAffecting(source);
    expect(pyKit).not.toContain("sketch");
    expect(pyKit).not.toContain("datum");
  });

  it("excludes the non-body-affecting types", () => {
    expect(BODY_AFFECTING_FEATURE_TYPES.has("sketch")).toBe(false);
    expect(BODY_AFFECTING_FEATURE_TYPES.has("datum")).toBe(false);
  });

  it("includes hole + boolean (the just-fixed drift)", () => {
    expect(BODY_AFFECTING_FEATURE_TYPES.has("hole")).toBe(true);
    expect(BODY_AFFECTING_FEATURE_TYPES.has("boolean")).toBe(true);
  });

  it("includes mirror (body-affecting — reflection unioned into the chain)", () => {
    expect(BODY_AFFECTING_FEATURE_TYPES.has("mirror")).toBe(true);
  });
});

describe("isPickableFace", () => {
  const planar: OverlayFace = { index: 0, planar: true, signature: SIGNATURE };
  const curved: OverlayFace = { index: 1, planar: false, signature: null };

  it("accepts a planar face carrying a signature", () => {
    expect(isPickableFace(planar)).toBe(true);
  });

  it("rejects a non-planar face (no signature)", () => {
    expect(isPickableFace(curved)).toBe(false);
  });
});

// A second, distinct planar face (a different normal + centroid + area).
const SIGNATURE_B: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: -1 },
  centroid: { x: 10, y: 10, z: 0 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};

describe("faceLabel", () => {
  it("names a face from its 1-based index + rounded centroid", () => {
    expect(faceLabel(0, SIGNATURE)).toBe(
      "Planar face 1, centred at 10, 10, 10 millimetres",
    );
  });
});

describe("faceSignatureKey", () => {
  it("distinguishes two distinct faces", () => {
    expect(faceSignatureKey(SIGNATURE)).not.toBe(faceSignatureKey(SIGNATURE_B));
  });

  it("is stable for an equal signature (a fresh object)", () => {
    expect(faceSignatureKey({ ...SIGNATURE })).toBe(
      faceSignatureKey(SIGNATURE),
    );
  });
});

describe("toggleFace", () => {
  it("adds an unpicked face, preserving order", () => {
    expect(toggleFace([SIGNATURE], SIGNATURE_B)).toEqual([
      SIGNATURE,
      SIGNATURE_B,
    ]);
  });

  it("removes an already-picked face (a repeat click)", () => {
    expect(toggleFace([SIGNATURE, SIGNATURE_B], SIGNATURE)).toEqual([
      SIGNATURE_B,
    ]);
  });

  it("matches by identity, not reference (an equal fresh object toggles off)", () => {
    expect(toggleFace([SIGNATURE], { ...SIGNATURE })).toEqual([]);
  });
});

describe("isFacePicked", () => {
  it("reports membership by signature identity", () => {
    expect(isFacePicked([SIGNATURE], { ...SIGNATURE })).toBe(true);
    expect(isFacePicked([SIGNATURE], SIGNATURE_B)).toBe(false);
  });
});

describe("faceOrdinalOfSignature", () => {
  // `OverlayFace.index` IS the mesh's face ordinal, and it is NOT the array
  // position — the overlay lists only the faces it can describe, so a fixture
  // whose indices matched their slots could not tell the two apart.
  const faces: OverlayFace[] = [
    { index: 4, planar: true, signature: SIGNATURE },
    { index: 7, planar: false, signature: null },
    { index: 9, planar: true, signature: SIGNATURE_B },
  ];

  it("resolves the ordinal the overlay carries, not the array slot", () => {
    expect(faceOrdinalOfSignature(SIGNATURE, faces)).toBe(4);
    expect(faceOrdinalOfSignature(SIGNATURE_B, faces)).toBe(9);
  });

  it("matches by signature identity, not by object reference", () => {
    expect(faceOrdinalOfSignature({ ...SIGNATURE }, faces)).toBe(4);
  });

  it("answers null when nothing is asked, or nothing is loaded", () => {
    expect(faceOrdinalOfSignature(null, faces)).toBeNull();
    expect(faceOrdinalOfSignature(SIGNATURE, null)).toBeNull();
    expect(faceOrdinalOfSignature(null, null)).toBeNull();
  });

  it("answers null for a signature no listed face carries", () => {
    const other: PlanarFaceSignature = { ...SIGNATURE, area_mm2: 999 };
    expect(faceOrdinalOfSignature(other, faces)).toBeNull();
  });

  it("skips an unpickable face even if it somehow carries the signature", () => {
    // Defence in depth against the null-signature branch: a face the overlay
    // marked non-planar is not a placement target whatever else it says.
    const odd: OverlayFace[] = [
      { index: 2, planar: false, signature: SIGNATURE },
    ];
    expect(faceOrdinalOfSignature(SIGNATURE, odd)).toBeNull();
  });
});
