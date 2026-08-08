import type { Page } from "@playwright/test";

/**
 * Shared API-level part seeding for the e2e suite — build a real tree through
 * the real gateway without driving the sketcher, so a spec whose subject is
 * somewhere else (a register column, a tree row, a target size) pays browser
 * time only for its own surface.
 *
 * Extracted on the third identical copy: `fillet-chamfer.spec.ts` and
 * `feature-suppress.spec.ts` each carried a byte-identical `SQUARE_20` +
 * `createFeature`, and `p2-register-health.spec.ts` needed the same pair plus
 * an evaluate (DRY rule — a divergence between two specs' idea of "a 20 mm
 * cube" is a debugging trap, not a saving).
 */

/** A 20×20 rectangle fixed at the origin on XY — a clean 20 mm cube when extruded. */
export const SQUARE_20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 20, y: 0 } },
    { id: "e2", kind: "line", start: { x: 20, y: 0 }, end: { x: 20, y: 20 } },
    { id: "e3", kind: "line", start: { x: 20, y: 20 }, end: { x: 0, y: 20 } },
    { id: "e4", kind: "line", start: { x: 0, y: 20 }, end: { x: 0, y: 0 } },
  ],
  constraints: [
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e3", point: "end" },
      b: { entity: "e4", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e4", point: "end" },
      b: { entity: "e1", point: "start" },
    },
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 20 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

export async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Sketch + extrude a 20 mm cube; resolves with the resulting tree version. */
export async function seedCube(
  page: Page,
  token: string,
  partId: string,
): Promise<number> {
  const sketch = await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return extrude.tree_version;
}

/**
 * A fillet over every edge — `radius_mm: 50` on the 20 mm cube is the cheapest
 * genuine KERNEL FAILURE the API can author (OCCT cannot build it), which is
 * how a spec gets a truthfully broken part rather than a mocked one.
 */
export async function seedAllEdgeFillet(
  page: Page,
  token: string,
  partId: string,
  radiusMm: number,
  expectedTreeVersion: number,
): Promise<number> {
  const fillet = await createFeature(page, token, partId, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: radiusMm },
    },
    expected_tree_version: expectedTreeVersion,
  });
  return fillet.tree_version;
}

/**
 * A 60 mm plate with SEVEN bores on a Ø40 bolt circle — the dense-hole fixture
 * spec A2 names (`docs/design/pre-selection.md` §6) and the shipped SEL-1 gate
 * did not have.
 *
 * Why it has to exist: a six-face box cannot show a MIS-RESOLVED ordinal. Every
 * face of a box is metres apart in ordinal space and centimetres apart on
 * screen, so a pick model that quietly answers "the face next door" scores
 * perfectly on it. Seven bores put ~14 circular edges and 7 snap centres within
 * a few millimetres of one another, which is where a widened pick corridor
 * either stays a corridor or becomes a blanket.
 *
 * Two features, not eight: ONE sketch carries all seven circles and ONE cut
 * extrude drills them, so the fixture costs two kernel evaluations. The circles
 * are deliberately NON-overlapping (17.4 mm apart on a Ø40 circle, Ø6 bores) —
 * overlapping profiles would fuse into a single face and destroy the very
 * ordinal crowding the fixture exists to create.
 */
export function boltCircleSketch(
  count: number,
  centre: { x: number; y: number },
  pitchRadiusMm: number,
  boreRadiusMm: number,
) {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: Array.from({ length: count }, (_unused, i) => {
      const angle = (2 * Math.PI * i) / count;
      return {
        id: `c${i + 1}`,
        kind: "circle",
        center: {
          x: centre.x + pitchRadiusMm * Math.cos(angle),
          y: centre.y + pitchRadiusMm * Math.sin(angle),
        },
        radius: boreRadiusMm,
      };
    }),
    constraints: [],
  };
}

/** Sketch + extrude the plate, then sketch + cut the bolt circle. */
export async function seedDenseHolePlate(
  page: Page,
  token: string,
  partId: string,
): Promise<number> {
  const plate = await createFeature(page, token, partId, {
    name: "Plate",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 60, 60),
    },
    expected_tree_version: 0,
  });
  const solid = await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: plate.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: plate.tree_version,
  });
  const bores = await createFeature(page, token, partId, {
    name: "Bolt circle",
    feature: {
      type: "sketch",
      version: 1,
      params: boltCircleSketch(7, { x: 30, y: 30 }, 20, 3),
    },
    expected_tree_version: solid.tree_version,
  });
  const cut = await createFeature(page, token, partId, {
    name: "Bores",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: bores.feature.id },
        distance_mm: 10,
        operation: "cut",
        direction: "normal",
      },
    },
    expected_tree_version: bores.tree_version,
  });
  return cut.tree_version;
}

/**
 * TWO BODIES, ONE BEHIND THE OTHER in the FRONT view — the fixture for "hide a
 * body to reach the geometry behind it".
 *
 * Body 1 (the blocker) is a 40×20 wall standing 40 mm tall at y∈[0,20];
 * body 2 (the target) is a 60×20 plate 10 mm thick at y∈[30,50], so the two
 * never touch (`merge: false` starts the second body). `occtToSceneTuple` maps
 * OCCT y to scene −z and the front view puts the camera on scene +z, so SMALLER
 * OCCT y is NEARER: the wall stands directly in front of the plate, and the
 * plate's top-front edge — mid-span at OCCT (30, 30, 10) — is squarely behind
 * it, with the wall's own nearest edge 10 mm away in the view plane.
 *
 * A one-body fixture cannot pose this question at all: the occlusion test is
 * only wrong when the material in front is material the modeller has switched
 * OFF, which takes two bodies and a visibility toggle.
 */
export async function seedOccludedEdgePlate(
  page: Page,
  token: string,
  partId: string,
): Promise<number> {
  const wall = await createFeature(page, token, partId, {
    name: "Wall sketch",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(10, 0, 40, 20),
    },
    expected_tree_version: 0,
  });
  const wallSolid = await createFeature(page, token, partId, {
    name: "Wall",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: wall.feature.id },
        distance_mm: 40,
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
    expected_tree_version: wall.tree_version,
  });
  const plate = await createFeature(page, token, partId, {
    name: "Plate sketch",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 30, 60, 20),
    },
    expected_tree_version: wallSolid.tree_version,
  });
  const plateSolid = await createFeature(page, token, partId, {
    name: "Plate",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: plate.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
        merge: false,
      },
    },
    expected_tree_version: plate.tree_version,
  });
  return plateSolid.tree_version;
}

/**
 * Park the travel stop on `featureId` (null = tip) through the gateway — the
 * API half of the timeline's drag, for specs that need a part whose evaluate
 * genuinely covers only a PREFIX. Resolves with the new tree version.
 */
export async function setRollbackViaApi(
  page: Page,
  token: string,
  partId: string,
  featureId: string | null,
  expectedTreeVersion: number,
): Promise<number> {
  const response = await page.request.put(`/api/v1/parts/${partId}/rollback`, {
    data: {
      rollback_feature_id: featureId,
      expected_tree_version: expectedTreeVersion,
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e rollback failed: ${response.status()} ${await response.text()}`,
    );
  }
  return ((await response.json()) as { tree_version: number }).tree_version;
}

/** Evaluate the tree through the gateway; resolves with the feature statuses. */
export async function evaluateViaApi(
  page: Page,
  token: string,
  partId: string,
): Promise<string[]> {
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e evaluate failed: ${response.status()} ${await response.text()}`,
    );
  }
  const body = (await response.json()) as {
    features: { status: string }[];
  };
  return body.features.map((f) => f.status);
}

/**
 * A fully-constrained axis-aligned rectangle at (x0,y0), w×h, on XY — the
 * general form of {@link SQUARE_20}, for specs that need a SECOND body offset
 * from the first. Extracted on the third use (multibody-union,
 * multibody-disjoint, materials) per the DRY rule.
 */
export function rectangleSketch(x0: number, y0: number, w: number, h: number) {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      {
        id: "e1",
        kind: "line",
        start: { x: x0, y: y0 },
        end: { x: x0 + w, y: y0 },
      },
      {
        id: "e2",
        kind: "line",
        start: { x: x0 + w, y: y0 },
        end: { x: x0 + w, y: y0 + h },
      },
      {
        id: "e3",
        kind: "line",
        start: { x: x0 + w, y: y0 + h },
        end: { x: x0, y: y0 + h },
      },
      {
        id: "e4",
        kind: "line",
        start: { x: x0, y: y0 + h },
        end: { x: x0, y: y0 },
      },
    ],
    constraints: [
      {
        kind: "coincident",
        a: { entity: "e1", point: "end" },
        b: { entity: "e2", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e2", point: "end" },
        b: { entity: "e3", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e3", point: "end" },
        b: { entity: "e4", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e4", point: "end" },
        b: { entity: "e1", point: "start" },
      },
      { kind: "horizontal", entity: "e1" },
      { kind: "vertical", entity: "e2" },
      { kind: "horizontal", entity: "e3" },
      { kind: "vertical", entity: "e4" },
      { kind: "distance", entity: "e1", value_mm: w },
      { kind: "distance", entity: "e2", value_mm: h },
      { kind: "fixed", point: { entity: "e1", point: "start" } },
    ],
  };
}
