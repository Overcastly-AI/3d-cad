import { describe, expect, it } from "vitest";

import type { MirrorParams } from "../api/parts";
import type { DatumPlaneOption } from "../sketch/plane";
import {
  buildMirrorParams,
  defaultMirrorForm,
  formFromMirrorParams,
  mirrorPlaneChoices,
  planeRefKey,
  selectedChoice,
} from "./mirror";

/** A reusable in-tree datum option (an offset datum, "XY +30"). */
const DATUM_OPTION: DatumPlaneOption = {
  id: "d1",
  name: "Datum1",
  spec: {
    kind: "offset",
    base: "XY",
    offsetMm: 30,
    flip: false,
    datumFeatureId: "d1",
  },
};

describe("mirrorPlaneChoices", () => {
  it("offers the three origin datums first, then in-tree datums", () => {
    const choices = mirrorPlaneChoices([DATUM_OPTION]);
    expect(choices.map((c) => c.key)).toEqual([
      "origin:XY",
      "origin:XZ",
      "origin:YZ",
      "datum:d1",
    ]);
    expect(choices[3]?.testId).toBe("mirror-plane-datum-d1");
    expect(choices[0]?.testId).toBe("mirror-plane-XY");
  });

  it("offers only the origins when the tree has no datums", () => {
    expect(mirrorPlaneChoices([]).map((c) => c.key)).toEqual([
      "origin:XY",
      "origin:XZ",
      "origin:YZ",
    ]);
  });
});

describe("buildMirrorParams", () => {
  const WHOLE_BODY = { scope: "body", scopeFeatures: [] } as const;

  it("builds a DatumPlaneRef for an origin datum", () => {
    const params = buildMirrorParams(
      { kind: "origin", base: "XZ" },
      WHOLE_BODY,
    );
    expect(params).toEqual<MirrorParams>({
      plane: { kind: "datum_plane", plane: "XZ" },
      scope: { kind: "body" },
    });
  });

  it("builds a FeatureRef for an in-tree datum", () => {
    expect(
      buildMirrorParams(DATUM_OPTION.spec, WHOLE_BODY),
    ).toEqual<MirrorParams>({
      plane: { kind: "feature", feature_id: "d1" },
      scope: { kind: "body" },
    });
  });

  // The scope is ALWAYS on the wire (pattern-scope §7.1). An omitted key means
  // "the whole body" forever, so a selection that failed to serialise would be
  // a silently ignored feature rather than an error.
  it("names the selected features when the scope is a selection", () => {
    expect(
      buildMirrorParams(
        { kind: "origin", base: "XY" },
        {
          scope: "features",
          scopeFeatures: [{ id: "h1", name: "Hole1", subtractive: true }],
        },
      ),
    ).toEqual<MirrorParams>({
      plane: { kind: "datum_plane", plane: "XY" },
      scope: {
        kind: "features",
        features: [{ kind: "feature", feature_id: "h1" }],
      },
    });
  });

  // `min_length=1` server-side: an empty selection is authoring nonsense, not a
  // no-op mirror, so the form gate refuses before the round-trip.
  it("refuses a features scope that names nothing", () => {
    expect(
      buildMirrorParams(
        { kind: "origin", base: "XY" },
        { scope: "features", scopeFeatures: [] },
      ),
    ).toBeNull();
  });
});

describe("planeRefKey", () => {
  it("maps an origin ref to its choice key", () => {
    expect(planeRefKey({ kind: "datum_plane", plane: "YZ" })).toBe("origin:YZ");
  });

  it("maps a feature ref to its choice key", () => {
    expect(planeRefKey({ kind: "feature", feature_id: "d1" })).toBe("datum:d1");
  });
});

describe("selectedChoice", () => {
  const choices = mirrorPlaneChoices([DATUM_OPTION]);

  it("defaults a new form (no plane) to the first origin (XY)", () => {
    expect(selectedChoice(choices, defaultMirrorForm())?.key).toBe("origin:XY");
  });

  it("selects the persisted origin plane when editing", () => {
    const form = formFromMirrorParams({
      plane: { kind: "datum_plane", plane: "XZ" },
    });
    expect(selectedChoice(choices, form)?.key).toBe("origin:XZ");
  });

  it("selects the persisted in-tree datum when editing", () => {
    const form = formFromMirrorParams({
      plane: { kind: "feature", feature_id: "d1" },
    });
    expect(selectedChoice(choices, form)?.key).toBe("datum:d1");
  });

  it("falls back to the first choice when the persisted datum is gone", () => {
    // A form referencing a datum no longer in the tree — the picker must still
    // land on a valid choice rather than an empty selection.
    const form = formFromMirrorParams({
      plane: { kind: "feature", feature_id: "deleted" },
    });
    expect(selectedChoice(choices, form)?.key).toBe("origin:XY");
  });
});
