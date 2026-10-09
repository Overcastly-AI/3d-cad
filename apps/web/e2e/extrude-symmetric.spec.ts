import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * EXTRUDE-SYMMETRIC — the editor's Extent option, end to end.
 *
 * SolidWorks (Mid Plane), Onshape and Fusion (Symmetric) extrude both ways
 * from the sketch plane, the typed depth being the whole length. The part is
 * the golden `extrude-cut-symmetric-pocket-offset-xz-40x40x20`: a 40 x 40 x 20
 * block (32 000 mm³) and a 10 x 10 profile on the plane y = +4 (XZ offset -4)
 * overhanging the top by 5. Cut Symmetric 30 removes y in [-11, 19]:
 * 10 x 30 x 5 = 1 500 mm³, leaving 30 500. One-sided it could not: along XZ's
 * normal (-y) it removes 24 long (30 800 left), reversed 16 (31 200).
 */

const BLOCK_VOLUME_MM3 = 40 * 40 * 20;
const SYMMETRIC_CUT_VOLUME_MM3 = BLOCK_VOLUME_MM3 - 10 * 30 * 5;

function rectangle(
  x0: number,
  y0: number,
  w: number,
  h: number,
  plane: unknown,
) {
  const corners = [
    [x0, y0],
    [x0 + w, y0],
    [x0 + w, y0 + h],
    [x0, y0 + h],
  ] as const;
  return {
    plane,
    entities: corners.map(([x, y], i) => {
      const [nx, ny] = corners[(i + 1) % 4] as readonly [number, number];
      return {
        id: `e${i + 1}`,
        kind: "line",
        start: { x, y },
        end: { x: nx, y: ny },
      };
    }),
    constraints: [],
  };
}

async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

interface Seeded {
  partId: string;
  token: string;
}

/** The block and the pocket profile, seeded through the real gateway. */
async function seedBlockAndProfile(page: Page): Promise<Seeded> {
  const account = await seedSession(page);
  const headers = { Authorization: `Bearer ${account.token}` };
  const partResponse = await page.request.post("/api/v1/parts", {
    data: { name: "Symmetric pocket" },
    headers,
  });
  if (!partResponse.ok()) {
    throw new Error(`e2e create part failed: ${partResponse.status()}`);
  }
  const partId = ((await partResponse.json()) as { id: string }).id;
  let version = 0;
  const post = async (name: string, feature: unknown): Promise<string> => {
    const response = await page.request.post(
      `/api/v1/parts/${partId}/features`,
      { data: { name, feature, expected_tree_version: version }, headers },
    );
    if (!response.ok()) {
      throw new Error(
        `e2e feature failed: ${response.status()} ${await response.text()}`,
      );
    }
    const json = (await response.json()) as {
      feature: { id: string };
      tree_version: number;
    };
    version = json.tree_version;
    return json.feature.id;
  };

  const blockProfile = await post("Block profile", {
    type: "sketch",
    version: 1,
    params: rectangle(-20, -20, 40, 40, { kind: "datum_plane", plane: "XY" }),
  });
  await post("Block", {
    type: "extrude",
    version: 1,
    params: {
      profile: { kind: "feature", feature_id: blockProfile },
      distance_mm: 20,
      operation: "add",
      direction: "normal",
      merge: true,
    },
  });
  const datum = await post("Plane y+4", {
    type: "datum",
    version: 1,
    params: { base: "XZ", offset_mm: -4, flip: false },
  });
  await post("Pocket profile", {
    type: "sketch",
    version: 1,
    params: rectangle(-5, 15, 10, 10, { kind: "feature", feature_id: datum }),
  });
  return { partId, token: account.token };
}

test.describe("Extrude Extent: Symmetric (EXTRUDE-SYMMETRIC)", () => {
  test("a symmetric cut splits the depth about the sketch plane", async ({
    page,
  }) => {
    const seeded = await seedBlockAndProfile(page);
    await page.goto(`/parts/${seeded.partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBe(BLOCK_VOLUME_MM3);

    await expect(page.getByTestId("new-extrude")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page
      .getByTestId("extrude-profile")
      .selectOption({ label: "Pocket profile" });

    // One side is the default; the direction toggle is there.
    await expect(page.getByTestId("extrude-extent-one-side")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("extrude-dir-normal")).toBeVisible();

    await page.getByTestId("extrude-op-cut").click();
    await page.getByTestId("extrude-extent-symmetric").click();
    await expect(page.getByTestId("extrude-extent-symmetric")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Nothing to flip while symmetric, so the toggle leaves; the note says why.
    await expect(page.getByTestId("extrude-dir-normal")).toHaveCount(0);
    await expect(page.getByTestId("extrude-direction-hint")).toContainText(
      "Half the distance each side of the plane.",
    );
    await page.getByTestId("extrude-distance").fill("30");
    // The ghost is told, so it straddles the plane before Save.
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-extent",
      "symmetric",
    );
    await page.waitForTimeout(400); // let the throttled ghost settle
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-symmetric-editor-desktop.png`,
    });

    await page.getByTestId("extrude-distance").press("Enter");
    // THE PROOF, the golden's number: 32 000 - 10 x 30 x 5 = 30 500 mm³.
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBe(SYMMETRIC_CUT_VOLUME_MM3);
    await expect(page.getByTestId("extrude-error")).toHaveCount(0);

    // And it is STORED symmetric (the wire field), not just drawn that way.
    const tree = await page.request.get(
      `/api/v1/parts/${seeded.partId}/features`,
      { headers: { Authorization: `Bearer ${seeded.token}` } },
    );
    expect(tree.ok()).toBe(true);
    const features = (
      (await tree.json()) as {
        features: {
          feature: { type: string; params: Record<string, unknown> };
        }[];
      }
    ).features.filter((f) => f.feature.type === "extrude");
    expect(features.map((f) => f.feature.params.extent)).toEqual([
      undefined,
      "symmetric",
    ]);
  });
});
