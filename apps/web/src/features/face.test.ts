import { describe, expect, it } from "vitest";

import { readWireModule } from "../test/wireSource";

import type {
  FeatureResponse,
  OverlayFace,
  PlanarFaceSignature,
} from "../api/parts";
import {
  anchorBodyFeatureId,
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
 * Parse `BODY_AFFECTING_FEATURE_TYPES` out of the wire module — THE source of
 * truth for the set (`packages/loft-wire/src/loft_wire/features.py`, located by
 * `src/test/wireSource.ts`, which owns that path for every guard that reads it).
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
function wireBodyAffecting(source: string): string[] {
  const marker = "\nBODY_AFFECTING_FEATURE_TYPES = frozenset(";
  const start = source.indexOf(marker);
  expect(
    start,
    "loft_wire BODY_AFFECTING_FEATURE_TYPES not found",
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
  // below, where the list comes from loft_wire instead of a hand-copy.
});

describe("anchorBodyFeatureId — PICK-1 (M16)", () => {
  /** extrude · fillet · extrude — the fillet's anchor is NEVER the tip. */
  const MID_TREE = [
    typed("s1", "sketch"),
    typed("e1", "extrude"),
    typed("f1", "fillet"),
    typed("s2", "sketch"),
    typed("e2", "extrude"),
  ];

  it("creating (no feature under edit) anchors on the tip", () => {
    expect(anchorBodyFeatureId(MID_TREE, null)).toBe("e2");
    expect(anchorBodyFeatureId(MID_TREE, null)).toBe(
      lastBodyFeatureId(MID_TREE),
    );
  });

  it("editing a MID-TREE feature anchors on the body BEFORE it, not the tip", () => {
    // The whole defect: "e2" is the tip and is LATER than "f1", so documents
    // rejects it with `reference_not_earlier` (422) and no non-tip feature can
    // be re-saved at all.
    expect(anchorBodyFeatureId(MID_TREE, "f1")).toBe("e1");
  });

  it("editing the TIP never names the feature itself", () => {
    // M10 in one line: a fillet at the tip re-stamped with `lastBodyFeatureId`
    // references ITSELF, so its radius could never be changed. The answer walks
    // back one body-affecting feature — here the fillet, not the extrude.
    expect(lastBodyFeatureId(MID_TREE)).toBe("e2");
    expect(anchorBodyFeatureId(MID_TREE, "e2")).toBe("f1");
  });

  it("skips a rolled-back feature on the earlier side too", () => {
    const tree = [
      typed("e1", "extrude"),
      typed("e2", "extrude", true), // rolled back — not in the current body
      typed("f1", "fillet"),
    ];
    expect(anchorBodyFeatureId(tree, "f1")).toBe("e1");
  });

  it("ignores a non-body-affecting neighbour when walking back", () => {
    const tree = [
      typed("e1", "extrude"),
      typed("d1", "datum"),
      typed("s1", "sketch"),
      typed("h1", "hole"),
    ];
    expect(anchorBodyFeatureId(tree, "h1")).toBe("e1");
  });

  it("returns null when nothing body-affecting precedes the edited feature", () => {
    const tree = [typed("s1", "sketch"), typed("e1", "extrude")];
    expect(anchorBodyFeatureId(tree, "e1")).toBeNull();
  });

  it("falls back to the create answer for an id not in the tree", () => {
    expect(anchorBodyFeatureId(MID_TREE, "not-in-this-tree")).toBe("e2");
  });
});

describe("BODY_AFFECTING_FEATURE_TYPES — backend drift guard", () => {
  // LAZY, and that is the whole point (2026-09-15). This used to read the file
  // in the describe body, so when `14f6e14` moved the schemas out of py-kit the
  // throw happened at COLLECTION: the file never loaded, the suite reported
  // 2516 passing AND exit 1, and no assertion anywhere named the cause. A guard
  // that becomes unloadable when the thing it guards moves stops guarding and
  // stops explaining in the same instant. Reading per test makes a moved module
  // one legible failure.
  const source = (): string => readWireModule("features");

  it("mirrors loft_wire.features.BODY_AFFECTING_FEATURE_TYPES exactly", () => {
    // A REAL drift guard (AUDIT-ENGINEERING J5): this reads the wire module
    // and compares the client set to what it actually declares, so adding a
    // body-affecting feature server-side and forgetting the client fails here.
    // Until 2026-07-30 it compared a hand-copy in this file to a hand-copy in
    // `face.ts` — BOTH inside apps/web — so backend drift could not fail it,
    // while the comment claimed "a member added on ONE side fails here".
    const wire = wireBodyAffecting(source());
    // Non-vacuity: a regex that silently matched nothing (or a set that stopped
    // being a frozenset literal) would make the equality below vacuously true.
    expect(wire.length).toBeGreaterThan(15);
    expect(new Set(wire).size).toBe(wire.length);
    // Order-independent set equality: a member added on ONE side fails here.
    expect([...BODY_AFFECTING_FEATURE_TYPES].sort()).toEqual([...wire].sort());
  });

  it("recognises every body-affecting type loft_wire declares", () => {
    // The pick-anchor consequence, stated as behaviour: `lastBodyFeatureId`
    // must anchor to EACH of them, or a later face/edge pick lands on the wrong
    // body (subshape_unresolved / a bad write-time dependency).
    for (const type of wireBodyAffecting(source())) {
      expect(lastBodyFeatureId([typed("x", type)])).toBe("x");
    }
  });

  it("excludes the types loft_wire deliberately leaves out", () => {
    const wire = wireBodyAffecting(source());
    expect(wire).not.toContain("sketch");
    expect(wire).not.toContain("datum");
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
