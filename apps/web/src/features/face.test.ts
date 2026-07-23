import { describe, expect, it } from "vitest";

import type {
  FeatureResponse,
  OverlayFace,
  PlanarFaceSignature,
} from "../api/parts";
import {
  BODY_AFFECTING_FEATURE_TYPES,
  faceLabel,
  faceSignatureKey,
  faceSubshapeRef,
  isFacePicked,
  isPickableFace,
  lastBodyFeatureId,
  onFaceDatumParams,
  toggleFace,
} from "./face";

/**
 * The EXACT membership of `py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES`
 * (`packages/py-kit/src/py_kit/schemas/features.py`) — hand-mirrored so a single-
 * side edit (add a body-affecting feature server-side, forget the client) fails
 * this guard loudly. `datum`/`sketch` are NOT body-affecting and must stay out.
 * The set anchors EVERY face/edge pick (`lastBodyFeatureId`), so a missing entry
 * mis-anchors a later pick to the wrong body (subshape_unresolved / bad dep).
 *
 * Follow-up (true DRY): the OpenAPI schema can't express the "body-affecting"
 * subset (it's a semantic flag, not a field), so this can't be derived from the
 * generated contract today. Exposing the set as a generated enum in
 * `packages/contracts` would kill the drift class — filed as a follow-up.
 */
const EXPECTED_BODY_AFFECTING = [
  "extrude",
  "revolve",
  "sweep",
  "loft",
  "fillet",
  "chamfer",
  "shell",
  "draft",
  "hole",
  "pattern",
  "import",
  "sheet_metal_base_flange",
  "sheet_metal_edge_flange",
  "sheet_metal_hem",
  "sheet_metal_corner_relief",
  "boolean",
] as const;

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

  it("recognises every body-affecting op", () => {
    for (const type of EXPECTED_BODY_AFFECTING) {
      expect(lastBodyFeatureId([typed("x", type)])).toBe("x");
    }
  });
});

describe("BODY_AFFECTING_FEATURE_TYPES — backend drift guard", () => {
  it("mirrors py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES exactly", () => {
    // Order-independent set equality: a member added on ONE side fails here.
    expect([...BODY_AFFECTING_FEATURE_TYPES].sort()).toEqual(
      [...EXPECTED_BODY_AFFECTING].sort(),
    );
  });

  it("excludes the non-body-affecting types", () => {
    expect(BODY_AFFECTING_FEATURE_TYPES.has("sketch")).toBe(false);
    expect(BODY_AFFECTING_FEATURE_TYPES.has("datum")).toBe(false);
  });

  it("includes hole + boolean (the just-fixed drift)", () => {
    expect(BODY_AFFECTING_FEATURE_TYPES.has("hole")).toBe(true);
    expect(BODY_AFFECTING_FEATURE_TYPES.has("boolean")).toBe(true);
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
