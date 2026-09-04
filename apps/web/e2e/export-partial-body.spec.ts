import { readFile } from "node:fs/promises";

import { expect, test, type Download, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import {
  clickRefusedControl,
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * EXPORT-3 — ONE FAILED FEATURE MUST NOT TAKE THE WHOLE PART'S EXPORT WITH IT.
 *
 * The audit's situation (AUDIT-PRODUCT R-6, live across the 2026-08-16 and
 * 2026-08-21 passes): a part builds cleanly through `Revolve1`, a downstream
 * feature fails, and all four export formats go inert — over a body the auditor
 * described as "what I would send a machinist for a first look". The geometry
 * existed, the gateway would have served it, and the client was the only thing
 * saying no.
 *
 * MEASURED FIRST, because the fix depends on where the gate is (2026-08-28,
 * isolated stack): `POST /parts/{id}/export?format=step` on this exact broken
 * tree returns **200 with 15372 bytes of real STEP**, byte-identical to
 * exporting the healthy prefix on its own. The gate was purely client-side.
 * The server's own refusal is reserved for the case that deserves it — a tree
 * with no body at all is a 422 `tree_export_failed` — which is the third
 * acceptance criterion, asserted below.
 *
 * WHAT THESE TESTS ASSERT ON. Not a 2xx and not "a download started": this repo
 * has a documented case where a misspelled field validated, evaluated and
 * silently returned legacy behaviour with seven green tests. So the STEP bytes
 * are parsed and the SOLID is measured. The discriminator that makes those
 * numbers mean something, measured on the same stack: the same tree with a
 * fillet that SUCCEEDS exports 26 faces / 12 cylindrical surfaces / 63751 B,
 * where the truncated body is 6 faces / 0 cylindrical surfaces / 15372 B. A
 * file that wrongly included the fillet could not pass these assertions.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** Sketch -> Extrude (a clean 20 mm cube) -> an r50 all-edge fillet OCCT
 *  refuses -> an r1 fillet the strict-prefix rule never attempts. */
async function seedBrokenPart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Motor mount");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
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
  const broken = await createFeature(page, account.token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 50 },
    },
    expected_tree_version: extrude.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Corner fillets R1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 1 },
    },
    expected_tree_version: broken.tree_version,
  });
  return part.id;
}

/**
 * THE NEGATIVE CONTROL'S PART: the first body-making operation is the one that
 * fails, so the strict-prefix rule has no prefix to fall back on and there is
 * genuinely nothing to write. A fillet needs an existing body; this tree never
 * makes one.
 */
async function seedNothingBuiltPart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Nothing built");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 5 },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

async function openPart(
  page: Page,
  partId: string,
  features: number,
): Promise<void> {
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(features, {
    timeout: 30_000,
  });
  // Wait on the EXPORT STRIP, not the body inspector: a part with no body
  // renders the `part-export-idle` panel instead of the inspector, and the
  // negative control is exactly that case. The strip is in both branches.
  await expect(page.getByTestId("part-export-controls")).toBeVisible({
    timeout: 30_000,
  });
}

interface SolidShape {
  bytes: number;
  faces: number;
  planes: number;
  cylinders: number;
  solids: number;
  min: [number, number, number];
  max: [number, number, number];
}

/** Measure the SOLID inside a downloaded STEP part-21 file. */
async function measureStep(download: Download): Promise<SolidShape> {
  const path = await download.path();
  const text = await readFile(path, "latin1");
  const count = (entity: string): number =>
    text.split(new RegExp(`=\\s*${entity}\\s*\\(`)).length - 1;
  const points = [
    ...text.matchAll(
      /CARTESIAN_POINT\s*\(\s*''\s*,\s*\(\s*([-0-9.E+]+)\s*,\s*([-0-9.E+]+)\s*,\s*([-0-9.E+]+)\s*\)/g,
    ),
  ].map((m) => [Number(m[1]), Number(m[2]), Number(m[3])] as const);
  expect(points.length, "the STEP file must carry geometry").toBeGreaterThan(0);
  const axis = (i: number): number[] => points.map((p) => p[i] ?? 0);
  return {
    bytes: text.length,
    faces: count("ADVANCED_FACE"),
    planes: count("PLANE"),
    cylinders: count("CYLINDRICAL_SURFACE"),
    solids: count("MANIFOLD_SOLID_BREP"),
    min: [Math.min(...axis(0)), Math.min(...axis(1)), Math.min(...axis(2))] as [
      number,
      number,
      number,
    ],
    max: [Math.max(...axis(0)), Math.max(...axis(1)), Math.max(...axis(2))] as [
      number,
      number,
      number,
    ],
  };
}

test.describe("export of a partially built part — 1280x800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a downstream failure no longer takes the good body's export with it", async ({
    page,
  }) => {
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });

    // The strip is LIVE, and says what the file is before the click.
    const strip = page.getByTestId("part-export-controls");
    await expect(strip).toHaveAttribute("data-export-state", "feature-error");
    await expect(page.getByTestId("part-export-status")).toHaveText("Partial");
    const notice = page.getByTestId("part-export-notice");
    await expect(notice).toContainText("Fillet1 failed");
    await expect(notice).toContainText("the file stops at Extrude1");
    await expect(notice).toContainText("2 features are excluded");

    // THE USER'S OWN MECHANISM. A real pointer at the cell's centre, not
    // `force` and not `locator.click()` on an occluded target — the cell has to
    // be reachable, or "export works" is a claim about the test harness.
    const cell = page.getByTestId("part-export-step");
    await expect(cell).toBeEnabled();
    const box = await cell.boundingBox();
    expect(box, "the STEP cell must have a hit box").not.toBeNull();
    const cx = (box?.x ?? 0) + (box?.width ?? 0) / 2;
    const cy = (box?.y ?? 0) + (box?.height ?? 0) / 2;
    const reached = await page.evaluate(
      ([x, y]) => {
        const hit = document.elementFromPoint(x as number, y as number);
        return hit?.closest('[data-testid="part-export-step"]') !== null;
      },
      [cx, cy],
    );
    expect(reached, "a real pointer must land on the STEP cell").toBe(true);

    const settled = page.waitForEvent("download", { timeout: 30_000 });
    await page.mouse.click(cx, cy);
    const download = await settled;

    // 1) THE FILE SAYS WHAT IT IS, after it leaves the app.
    expect(download.suggestedFilename()).toMatch(/-partial\.step$/);

    // 2) THE ARTIFACT IS THE PRE-FAILURE BODY. A 20 mm cube: six planar faces
    //    and no cylinders. Had the export somehow included the fillet it would
    //    measure 26 faces and 12 cylindrical surfaces (measured), so these
    //    numbers discriminate rather than merely pass.
    const shape = await measureStep(download);
    expect(shape.solids).toBe(1);
    expect(shape.faces).toBe(6);
    expect(shape.planes).toBe(6);
    expect(shape.cylinders).toBe(0);
    shape.min.forEach((v) => expect(v).toBeCloseTo(0, 6));
    shape.max.forEach((v) => expect(v).toBeCloseTo(20, 6));
  });

  test("the command band names the truncation point too — a collapsed panel cannot hide it", async ({
    page,
  }) => {
    // EXPORT-1's lesson applied to EXPORT-3: the band is the export surface
    // that survives collapsing the Inspector, so it is the one that must not go
    // quiet about a truncated file. The strip has a notice line; the band
    // carries the same fact on each cell's accessible DESCRIPTION — which is
    // where an enabled-but-qualified caption lands since A11Y-TOOLBTN-1. It was
    // the accessible NAME until then, because the primitive announced a caption
    // only while DISABLED and this cell is enabled; that workaround renamed the
    // control whenever the gate state moved, so it is retired here.
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });

    const bandCell = page.getByTestId("part-export-band-step");
    await expect(bandCell).toBeEnabled();
    await expect(bandCell).toHaveAccessibleName("Export STEP (exact B-rep)");
    await expect(bandCell).toHaveAccessibleDescription(/stops at Extrude1/);
    await expect(bandCell).toHaveAccessibleDescription(/marked partial/);
  });

  test("a tree with NOTHING built still refuses — the negative control", async ({
    page,
  }) => {
    // Acceptance criterion 3, and the one that keeps criterion 1 honest:
    // without it, "export is enabled" passes trivially by enabling it always.
    // The server agrees here — this tree is a 422 `tree_export_failed`.
    const partId = await seedNothingBuiltPart(page);
    await openPart(page, partId, 2);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });

    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "no-body",
    );
    await expect(page.getByTestId("part-export-status")).toHaveText(
      "Fillet1 failed",
    );
    await expect(page.getByTestId("part-export-notice")).toContainText(
      "Nothing was built before Fillet1",
    );

    // EVERY format is held, and the CLIENT is what holds them.
    //
    // Measured while mutation-testing this spec, and it is the reason the
    // `aria-disabled` assertion below is not redundant with the download check:
    // with the gate deliberately broken to allow export unconditionally, the
    // cells went live, the click reached `exportPartTree` — and STILL no file
    // arrived, because the gateway answers this tree with its own 422
    // `tree_export_failed`. So "no download happened" is satisfied by a server
    // that would have refused anyway, and a negative control resting on it
    // alone would pass over a UI that had stopped refusing entirely. What has
    // to be asserted is the REFUSAL, at the surface the criterion is about.
    for (const format of ["step", "stl", "3mf", "glb"]) {
      const testId = `part-export-${format}`;
      await expect(
        page.getByTestId(testId),
        `${testId} must be held by the client, not only by the server`,
      ).toHaveAttribute("aria-disabled", "true");

      // ...and inert, not merely grey. `clickRefusedControl` proves a real
      // pointer reaches the cell BEFORE forcing the activation past
      // `aria-disabled`, so "no file" means the app refused rather than the
      // synthetic click having landed somewhere else entirely.
      const settled = page
        .waitForEvent("download", { timeout: 2_000 })
        .then(() => true)
        .catch(() => false);
      await clickRefusedControl(page, page.getByTestId(testId), testId);
      expect(await settled, `${testId} must not write a file`).toBe(false);
    }

    // The BAND is held too — the surface a collapsed Inspector leaves behind.
    await expect(page.getByTestId("part-export-band-step")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  test("founder shot: the export strip over a partially built part", async ({
    page,
  }) => {
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await page.mouse.move(1240, 780); // park the cursor off the model
    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/export-partial-${SHOT_TAG}-1280.png`,
      }),
    );
  });
});
