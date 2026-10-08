import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, waitForCameraStill } from "./invariants";
import { createFeature } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * SKETCH-PROJECT-EDGES, the web half: Fusion's Project / SolidWorks' Convert
 * Entities, end to end on the real stack.
 *
 * The QA case it was built for: a 120 x 80 x 35 housing (R5 vertical rounds,
 * shelled to a 2 mm wall, open at the top) gets a 3 mm lip sketched on its
 * rim. Without Project the lip is typed geometry and keeps 120 when the base
 * is widened; with it, the lip's sketch is the rim's own 16 edges and follows
 * them. So: sketch on the rim face, press P, click the outer and inner rim
 * edges, extrude 3 mm; retype the base width 120 -> 130 and the body must be
 * the analytic 130 mm part (the golden's closed form, no bridge across the
 * cavity); then take the inner rim away and the sketch row must say so.
 *
 * The base, rounds and shell are seeded from the golden model's own features
 * (`revise-width-lip-projected-rim-130x80x35`, refs captured at width 120), so
 * this spec and the kernel golden describe one part. Everything the feature is
 * about — the face pick, P, the sixteen edge clicks, the save and the extrude —
 * goes through the UI.
 */

const GOLDEN = fileURLToPath(
  new URL(
    "../../../services/geometry/goldens/revise-width-lip-projected-rim-130x80x35/model.json",
    import.meta.url,
  ),
);

interface GoldenFeature {
  id: string;
  feature: { type: string; params: Record<string, unknown> };
}

/** The golden's closed form at width 130 (expected.json `derivation`). */
const K = 4 - Math.PI;
const volumeAt = (width: number): number => {
  const outer = width * 80 - 25 * K;
  const inner = (width - 4) * 76 - 9 * K;
  return 38 * outer - 36 * inner;
};

/** Seed Sketch1 (width 120), Extrude1, Fillet1 and Shell1 from the golden. */
async function seedHousing(page: Page, token: string, partId: string) {
  const golden = JSON.parse(readFileSync(GOLDEN, "utf8")) as {
    features: GoldenFeature[];
  };
  const names = ["Sketch1", "Extrude1", "Fillet1", "Shell1"];
  const ids = new Map<string, string>();
  let treeVersion = 0;
  for (const [index, name] of names.entries()) {
    const source = golden.features[index] as GoldenFeature;
    let text = JSON.stringify(source.feature);
    for (const [from, to] of ids) text = text.split(from).join(to);
    const feature = JSON.parse(text) as GoldenFeature["feature"];
    if (index === 0) setWidth(feature, 120);
    const created = await createFeature(page, token, partId, {
      name,
      feature,
      expected_tree_version: treeVersion,
    });
    ids.set(source.id, created.feature.id);
    treeVersion = created.tree_version;
  }
  return { sketchId: ids.get(golden.features[0]?.id ?? "") ?? "" };
}

/** Retype the centred base rectangle's width (its x extents). */
function setWidth(feature: GoldenFeature["feature"], width: number): void {
  const entities = feature.params["entities"] as {
    start: { x: number };
    end: { x: number };
  }[];
  for (const entity of entities) {
    for (const point of [entity.start, entity.end]) {
      point.x = Math.sign(point.x) * (width / 2);
    }
  }
}

async function api<T>(
  page: Page,
  token: string,
  method: "get" | "post" | "patch" | "delete",
  path: string,
  data?: unknown,
): Promise<{ status: number; body: T }> {
  const response = await page.request[method](`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    ...(data === undefined ? {} : { data }),
  });
  return { status: response.status(), body: (await response.json()) as T };
}

interface Tree {
  tree_version: number;
  features: { id: string; name: string; feature: GoldenFeature["feature"] }[];
}

interface Evaluated {
  properties: { volume: number; bounding_box: { max: { x: number } } } | null;
  features: {
    feature_id: string;
    status: string;
    data?: { projections?: { entity: string; state: string }[] } | null;
  }[];
}

async function evaluate(page: Page, token: string, partId: string) {
  return (
    await api<Evaluated>(page, token, "post", `/parts/${partId}/evaluate`)
  ).body;
}

/** PATCH one feature's params through the API (the upstream edit). */
async function patchFeature(
  page: Page,
  token: string,
  partId: string,
  name: string,
  edit: (feature: GoldenFeature["feature"]) => void,
): Promise<void> {
  const { body: tree } = await api<Tree>(
    page,
    token,
    "get",
    `/parts/${partId}/features`,
  );
  const row = tree.features.find((f) => f.name === name);
  expect(row, `${name} in the tree`).toBeDefined();
  const feature = structuredClone(row?.feature) as GoldenFeature["feature"];
  edit(feature);
  const { status } = await api(
    page,
    token,
    "patch",
    `/parts/${partId}/features/${row?.id ?? ""}`,
    { feature, expected_tree_version: tree.tree_version },
  );
  expect(status).toBe(200);
}

async function waitSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
}

/** Click the rim face: the topmost pickable face (z = 35, the ring). */
async function sketchOnRim(page: Page, partId: string): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-pick-face").click();
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  let best = -1;
  let bestZ = -Infinity;
  for (let i = 0; i < (await nodes.count()); i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] ?? "NaN");
    if (z > bestZ) {
      bestZ = z;
      best = i;
    }
  }
  expect(bestZ).toBeCloseTo(35, 3);
  const datum = page.waitForResponse(
    (r) =>
      r.url().includes(`/parts/${partId}/features`) &&
      r.request().method() === "POST",
  );
  // The ring's centroid is over the cavity, so its node sits where the canvas
  // takes the pointer; the node's own click (its keyboard path) is the pick.
  await nodes.nth(best).dispatchEvent("click");
  expect((await datum).status()).toBe(201);
  await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
    timeout: 15_000,
  });
}

/** The 16 rim edge marks: every offered edge whose mid-span sits at z = 35. */
async function rimEdgeMarks(page: Page): Promise<string[]> {
  const marks = page.locator('[data-testid^="edge-pick-"]');
  await expect(marks.first()).toBeAttached({ timeout: 30_000 });
  return page.evaluate(() =>
    [...document.querySelectorAll('[data-testid^="edge-pick-"]')].flatMap(
      (el) => {
        const at = /centred at (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)/.exec(
          el.getAttribute("aria-label") ?? "",
        );
        return at !== null && Math.abs(Number(at[3]) - 35) < 0.05
          ? [el.getAttribute("data-testid") ?? ""]
          : [];
      },
    ),
  );
}

test.describe("SKETCH-PROJECT-EDGES — a lip that follows its rim", () => {
  test("project the rim, extrude a lip, widen the base, lose the inner rim", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Lip housing");
    await seedHousing(page, token, part.id);
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await waitSolved(page);
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(16);

    // ---- Sketch on the rim, press P, click the sixteen rim edges ----------
    await sketchOnRim(page, part.id);
    await page.keyboard.press("p");
    await expect(page.getByTestId("tool-project")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("project-prompt")).toBeVisible();
    const rim = await rimEdgeMarks(page);
    // Outer loop: 4 lines + 4 R5 rounds; inner loop: 4 lines + 4 R3 rounds.
    expect(rim).toHaveLength(16);
    // The first pick is a real pointer click on an edge's mark. The rest use
    // the mark's own click (its keyboard path): at this camera several marks
    // sit under the tree panel or off the sheet, and which ones is a camera
    // fact, not a Project fact.
    for (const [i, id] of rim.entries()) {
      const mark = page.getByTestId(id);
      if (i === 0) await mark.click();
      else await mark.dispatchEvent("click");
      await expect(page.getByTestId("project-count")).toHaveText(
        `${i + 1} projected`,
      );
    }
    // A projected edge is taken: clicking it again projects nothing.
    await page.getByTestId(rim[0] ?? "").dispatchEvent("click");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "already projected",
    );
    await expect(page.getByTestId("project-count")).toHaveText("16 projected");

    // Escape drops the tool (Fusion's Esc ends a command), then the strip
    // saves the sketch.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("tool-project")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await waitSolved(page);

    // ---- Extrude the ring 3 mm --------------------------------------------
    await expect(page.getByTestId("new-extrude")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").fill("3");
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("feature-row")).toHaveCount(7, {
      timeout: 30_000,
    });
    await waitSolved(page);
    const at120 = await evaluate(page, token, part.id);
    expect(at120.properties?.volume ?? NaN).toBeCloseTo(volumeAt(120), 3);

    // ---- Widen the base 120 -> 130 ----------------------------------------
    await patchFeature(page, token, part.id, "Sketch1", (f) =>
      setWidth(f, 130),
    );
    const at130 = await evaluate(page, token, part.id);
    // The golden's closed form: the lip is the 130 mm rim, flush with the
    // walls. A lip left at 120 is 120 mm³ short; a bridge over the 126 x 76
    // cavity would add ~28 000 mm³. Both fail this.
    expect(at130.properties?.volume ?? NaN).toBeCloseTo(volumeAt(130), 3);
    expect(at130.properties?.volume ?? NaN).toBeCloseTo(49926.637001147, 3);
    expect(at130.properties?.bounding_box.max.x ?? NaN).toBeCloseTo(65, 6);
    const sketch2 = at130.features[5];
    expect(sketch2?.data?.projections).toHaveLength(16);
    expect(sketch2?.data?.projections?.every((p) => p.state === "ok")).toBe(
      true,
    );

    // The founder's picture: the widened lip, and its sketch's purple rim.
    await page.reload();
    await waitSolved(page);
    await page.getByTestId("feature-row").nth(5).click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(16);
    // Fit (0) frames the whole rim: the 130 mm lip under its purple loops.
    await page.keyboard.press("0");
    await waitForCameraStill(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-project-lip-130.png`,
    });
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });

    // ---- Take the inner rim away -------------------------------------------
    // The shell itself cannot be deleted: the rim datum and the projections
    // name it, so documents refuses with its dependents (409), as Fusion's
    // own references would. Closing the shell's opening takes the inner rim
    // away instead: those 8 projections go sick, keep their last position,
    // and the sketch still builds.
    const shellId = (
      await api<Tree>(page, token, "get", `/parts/${part.id}/features`)
    ).body.features[3]?.id;
    const { body: treeNow } = await api<Tree>(
      page,
      token,
      "get",
      `/parts/${part.id}/features`,
    );
    const refused = await api(
      page,
      token,
      "delete",
      `/parts/${part.id}/features/${shellId ?? ""}?expected_tree_version=${treeNow.tree_version}`,
    );
    expect(refused.status).toBe(409);
    await patchFeature(page, token, part.id, "Shell1", (f) => {
      (f.params["faces"] as { refs: unknown[] }).refs = [];
    });
    await page.reload();
    await waitSolved(page);
    const notice = page.getByTestId("feature-projection-5");
    await expect(notice).toBeVisible({ timeout: 30_000 });
    await expect(notice).toContainText(
      "8 projected edges no longer exist; the sketch keeps their last position.",
    );
    await expect(page.getByTestId("timeline-projection-5")).toBeAttached();
  });
});
