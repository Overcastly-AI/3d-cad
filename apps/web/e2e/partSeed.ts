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
