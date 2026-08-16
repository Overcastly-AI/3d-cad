import type { Request } from "@playwright/test";

import { expect, test, type Page } from "./fixtures";
import { createPartViaApi, seedSession } from "./support";

/**
 * PICK-1 (M16) — a subshape reference must be anchored to the body the kernel
 * will actually match it against: the last body-affecting feature STRICTLY
 * EARLIER than the feature being written. Stamping the TIP is right only while
 * CREATING at the tip; on an EDIT of a mid-tree feature it names a feature that
 * is later than (or IS) the feature under edit, and `documents` correctly
 * refuses it with `reference_not_earlier` (services/documents/features.py —
 * `target.order_index >= order_index`).
 *
 * Every fixture here is built so the TIP IS NOT THE ANSWER: the feature under
 * edit sits mid-tree with further body-affecting features after it, so an
 * implementation that keeps stamping the tip cannot pass by coincidence.
 */

/** A 20x20 rectangle fixed at the origin on XY — a clean 20 mm cube extruded. */
const SQUARE_20 = {
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

/** A 10x10 rectangle inset at (5,5) on XY — a column that unions into the cube. */
const SQUARE_10_INSET = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 5, y: 5 }, end: { x: 15, y: 5 } },
    { id: "e2", kind: "line", start: { x: 15, y: 5 }, end: { x: 15, y: 15 } },
    { id: "e3", kind: "line", start: { x: 15, y: 15 }, end: { x: 5, y: 15 } },
    { id: "e4", kind: "line", start: { x: 5, y: 15 }, end: { x: 5, y: 5 } },
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
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 10 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

/** The cube's top edge along +X at y=0 — a signature seeded without a raycast. */
const TOP_EDGE_Y0 = {
  subshape_type: "edge",
  curve: "line",
  end_a: { x: 0, y: 0, z: 20 },
  end_b: { x: 20, y: 0, z: 20 },
  midpoint: { x: 10, y: 0, z: 20 },
  length_mm: 20,
};

/** The cube's TOP face (z = 20) — the shell's open face, seeded directly. */
const TOP_FACE = {
  subshape_type: "face",
  surface: "plane",
  area_mm2: 400,
  centroid: { x: 10, y: 10, z: 20 },
  normal: { x: 0, y: 0, z: 1 },
};

interface Created {
  feature: { id: string };
  tree_version: number;
}

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<Created> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as Created;
}

interface Fixture {
  partId: string;
  /** The correct anchor: the last body-affecting feature BEFORE the edited one. */
  ownerId: string;
  /** The feature the spec edits (mid-tree). */
  subjectId: string;
  /** The tip — a LATER body-affecting feature, i.e. the wrong answer. */
  tipId: string;
}

/**
 * Seed a part whose picked-subshape feature sits MID-tree:
 *
 *   0 Sketch1 · 1 Extrude1 (cube) · 2 <subject> · 3 Sketch2 · 4 Extrude2 (tip)
 *
 * `Extrude1` is the only valid anchor for the subject's picks; `Extrude2` is
 * the tip and is STRICTLY LATER than the subject, so a tip-stamped reference is
 * rejected with `reference_not_earlier`.
 */
async function seedMidTreeSubject(
  page: Page,
  partName: string,
  subject: (extrudeId: string) => { name: string; feature: unknown },
): Promise<Fixture> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, partName);
  const sketch1 = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const extrude1 = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch1.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch1.tree_version,
  });
  const spec = subject(extrude1.feature.id);
  const subjectFeature = await createFeature(page, account.token, part.id, {
    name: spec.name,
    feature: spec.feature,
    expected_tree_version: extrude1.tree_version,
  });
  const sketch2 = await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: SQUARE_10_INSET },
    expected_tree_version: subjectFeature.tree_version,
  });
  const extrude2 = await createFeature(page, account.token, part.id, {
    name: "Extrude2",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch2.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch2.tree_version,
  });
  return {
    partId: part.id,
    ownerId: extrude1.feature.id,
    subjectId: subjectFeature.feature.id,
    tipId: extrude2.feature.id,
  };
}

/**
 * The `feature_id` every subshape reference in a captured PATCH body carries.
 * Reads the request the CLIENT sent, so the assertion is about the stamp, not
 * about whatever the server made of it.
 */
function stampedAnchors(request: Request): string[] {
  const body = request.postDataJSON() as {
    feature?: { params?: Record<string, unknown> };
  };
  const params = body.feature?.params ?? {};
  const found: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (node === null || typeof node !== "object") return;
    const record = node as Record<string, unknown>;
    if (record.kind === "subshape" && typeof record.feature_id === "string") {
      found.push(record.feature_id);
    }
    Object.values(record).forEach(walk);
  };
  walk(params);
  return found;
}

/**
 * Name the ids by their ROLE so a failure reads "Extrude2 (the tip)" instead of
 * two indistinguishable uuids — the whole defect is *which* feature was named.
 */
function roleOf(fx: Fixture, id: string): string {
  if (id === fx.ownerId) return "Extrude1 (owns the sub-shape)";
  if (id === fx.subjectId) return "the feature under edit (itself)";
  if (id === fx.tipId) return "Extrude2 (the TIP)";
  return `unknown feature ${id}`;
}

/**
 * Click the pickable planar face with the greatest z — the cube's top face —
 * chosen from the overlay node's accessible name so the pick never depends on a
 * screen projection. (The hole spec's own local twin; kept here rather than
 * imported because `support.ts` is off-limits to this change.)
 */
async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/**
 * The next feature PATCH the page issues while `act` runs, and what the server
 * did with it. The STATUS is asserted rather than the absence of an error panel:
 * `toHaveCount(0)` on an error that has not rendered yet passes for the wrong
 * reason, and a 422 that arrives a tick later would sail past it.
 */
async function capturePatch(
  page: Page,
  partId: string,
  act: () => Promise<void>,
): Promise<{ request: Request; status: number; body: string }> {
  const isPatch = (url: string, method: string): boolean =>
    method === "PATCH" && url.includes(`/parts/${partId}/features/`);
  const pending = page.waitForResponse(
    (response) => isPatch(response.url(), response.request().method()),
    { timeout: 30_000 },
  );
  await act();
  const response = await pending;
  return {
    request: response.request(),
    status: response.status(),
    body: await response.text(),
  };
}

test.describe("PICK-1 — a subshape pick is anchored to its own body, not the tip", () => {
  test("editing a mid-tree picked-edge fillet stamps the owning feature and rebuilds", async ({
    page,
  }) => {
    const fx = await seedMidTreeSubject(page, "Anchor fillet", (extrudeId) => ({
      name: "Fillet1",
      feature: {
        type: "fillet",
        version: 1,
        params: {
          radius_mm: 4,
          edges: {
            kind: "edges",
            refs: [
              {
                kind: "subshape",
                feature_id: extrudeId,
                subshape_type: "edge",
                selector: { selector_version: 1, signature: TOP_EDGE_Y0 },
              },
            ],
          },
        },
      },
    }));

    await page.goto(`/parts/${fx.partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("feature-row")).toHaveCount(5);

    // Re-open Fillet1 (row index 2) and change its radius — the everyday edit.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );
    await page.getByTestId("fillet-radius").fill("3");

    const patch = await capturePatch(page, fx.partId, async () => {
      await page.getByTestId("fillet-submit").click();
    });

    // THE STAMP: the extrude that owns the edge — never the tip, never itself.
    expect(stampedAnchors(patch.request).map((id) => roleOf(fx, id))).toEqual([
      "Extrude1 (owns the sub-shape)",
    ]);

    // And the edit actually LANDS: the server accepts it (it used to answer 422
    // `reference_not_earlier`), the editor closes, the tree rebuilds.
    expect(patch.status, patch.body).toBe(200);
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
  });

  test("editing a mid-tree picked-face shell stamps the owning feature and rebuilds", async ({
    page,
  }) => {
    const fx = await seedMidTreeSubject(page, "Anchor shell", (extrudeId) => ({
      name: "Shell1",
      feature: {
        type: "shell",
        version: 1,
        params: {
          thickness_mm: 2,
          faces: {
            kind: "faces",
            refs: [
              {
                kind: "subshape",
                feature_id: extrudeId,
                subshape_type: "face",
                selector: { selector_version: 1, signature: TOP_FACE },
              },
            ],
          },
        },
      },
    }));

    await page.goto(`/parts/${fx.partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("feature-row")).toHaveCount(5);

    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill("3");

    const patch = await capturePatch(page, fx.partId, async () => {
      await page.getByTestId("shell-submit").click();
    });

    expect(stampedAnchors(patch.request).map((id) => roleOf(fx, id))).toEqual([
      "Extrude1 (owns the sub-shape)",
    ]);

    expect(patch.status, patch.body).toBe(200);
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
  });

  /**
   * THE FLOW THIS TICKET EXISTS FOR (M17). The kernel's documented recovery from
   * a lost reference is "Re-pick the face", surfaced as a one-click repair on the
   * failing row (`repick-face.spec.ts` proves the affordance ARMS the pick, and
   * stops there). This finishes the loop: pick a real face, save, and the feature
   * must rebuild. It could not before — the re-pick stamped the tip, which here is
   * a feature LATER than the hole under repair, so the save came back 422 and the
   * only documented escape hatch from topological-naming failure was a dead end.
   */
  test("re-pick after a rebuild orphans a reference → the feature rebuilds", async ({
    page,
  }) => {
    const fx = await seedMidTreeSubject(page, "Anchor repick", (extrudeId) => ({
      name: "Hole1",
      feature: {
        type: "hole",
        version: 1,
        params: {
          face: {
            kind: "subshape",
            feature_id: extrudeId,
            subshape_type: "face",
            selector: {
              selector_version: 1,
              // Off the body entirely: the resilient resolver cannot re-match
              // it, so the hole is ORPHANED exactly as an upstream edit leaves
              // it — `subshape_unresolved`.
              signature: {
                subshape_type: "face",
                surface: "plane",
                area_mm2: 987654,
                centroid: { x: 500, y: 500, z: 500 },
                normal: { x: 0, y: 0, z: 1 },
              },
            },
          },
          position: { x: 500, y: 500, z: 500 },
          diameter_mm: 5,
          depth: { kind: "through_all" },
        },
      },
    }));

    await page.goto(`/parts/${fx.partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 60_000,
    });
    const errorRow = page.getByTestId("feature-error-2");
    await expect(errorRow).toContainText("subshape_unresolved");

    // The one-click repair opens the hole editor with its face pick re-armed.
    await page.getByTestId("feature-repick-face-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Re-pick the cube's top face — a real face of the body the hole sits on.
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    const patch = await capturePatch(page, fx.partId, async () => {
      await page.getByTestId("hole-submit").click();
    });
    expect(stampedAnchors(patch.request).map((id) => roleOf(fx, id))).toEqual([
      "Extrude1 (owns the sub-shape)",
    ]);

    // THE BAR: the save is accepted and the orphaned feature rebuilds.
    expect(patch.status, patch.body).toBe(200);
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  });
});
