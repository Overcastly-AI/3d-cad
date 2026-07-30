import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR } from "./support";

/**
 * The clash schedule tells the truth about what it measured — the two states
 * side by side, in an INCH assembly, through a real browser against the real
 * stack.
 *
 * 1. A measured overlap (two plates driven onto each other) reads in the
 *    document unit — `in³`, not `mm³`. That was the last mm-only readout on an
 *    inch page after the assembly inspector was converted.
 * 2. A pair the kernel could not measure (`ClashPair.unresolved`, set when the
 *    exact boolean fails while the solved bounding boxes overlap) reads as
 *    UNVERIFIED with a parenthesised upper bound — never as a measured clash
 *    and never as clear.
 *
 * Why the second pair is injected into the response instead of provoked: the
 * unresolved flag is an OCCT robustness fallback. The kernel raises it when
 * `BRepAlgoAPI_Common` fails, which no authorable geometry triggers on demand
 * (the geometry suite forces it by patching the boolean). The response body is
 * the real one from the real interference endpoint with one extra pair appended,
 * so everything below the transport — panel, tree badge, viewport tint — runs on
 * genuine data in the genuine flow. The panel's own rendering of both states is
 * pinned in `AssemblyClashPanel.test.tsx`.
 */

/** Which capture pass this run is (`before` runs against the pre-fix panel). */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** Read the assembly's current concurrency token from the graph GET. */
async function docVersion(
  page: Page,
  token: string,
  assemblyId: string,
): Promise<number> {
  const res = await page.request.get(`/api/v1/assemblies/${assemblyId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) {
    throw new Error(`graph GET failed: ${res.status()} ${await res.text()}`);
  }
  return ((await res.json()) as { doc_version: number }).doc_version;
}

/**
 * Stand up an inch assembly of three plates where A and B genuinely overlap,
 * then append an unresolved A–C pair to the real interference response.
 * Returns the three instance ids in tree (balloon) order.
 */
async function inchAssemblyWithBothClashStates(page: Page): Promise<{
  idA: string;
  idB: string;
  idC: string;
}> {
  const { idA, idB, token, assemblyId } = await setupTwoInstances(page);

  // Drive the free instance onto the grounded one so their bodies overlap.
  const version = await docVersion(page, token, assemblyId);
  const patch = await page.request.patch(
    `/api/v1/assemblies/${assemblyId}/instances/${idB}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        expected_version: version,
        placement: {
          position: { x: 0, y: 0, z: 0 },
          orientation: { w: 1, x: 0, y: 0, z: 0 },
        },
      },
    },
  );
  expect(patch.ok()).toBeTruthy();

  // A third plate, seeded clear of both — the pair the check cannot measure.
  await page.reload();
  await waitForSolved(page);
  await page.getByTestId("add-instance").click();
  await page.locator('[data-testid^="add-instance-part-"]').first().click();
  await expect(page.getByTestId("instance-row")).toHaveCount(3, {
    timeout: 15_000,
  });
  await page.getByTestId("add-instance-done").click();
  await waitForSolved(page);

  const ids = await page
    .getByTestId("instance-row")
    .evaluateAll((rows) =>
      rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
    );
  const idC = ids[2];
  if (idC === undefined || idC === "") throw new Error("expected a third id");

  // Inches: the readout under test.
  const unitSelect = page.getByTestId("document-unit-select");
  await unitSelect.selectOption("in");
  await expect(unitSelect).toHaveValue("in", { timeout: 30_000 });
  await waitForSolved(page);

  await page.route(
    "**/api/v1/geometry/assembly/interference",
    async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as {
        clashes: Record<string, unknown>[];
      };
      body.clashes.push({
        instance_a: idA,
        instance_b: idC,
        // The AABB-overlap magnitude hint the kernel reports for an unresolved
        // pair: 5,210.4 mm³ = 0.318 in³ (an upper bound, not a measurement).
        overlap_volume_mm3: 5210.4,
        unresolved: true,
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    },
  );

  await page.getByTestId("check-interference").click();
  await expect(page.getByTestId("clash-row")).toHaveCount(2, {
    timeout: 30_000,
  });
  return { idA, idB, idC };
}

test.describe("clash schedule — measured vs unverified (1440)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("reads in the document unit and marks the unmeasurable pair", async ({
    page,
  }) => {
    const { idB, idC } = await inchAssemblyWithBothClashStates(page);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/clash-unverified-${SHOT_TAG}-1440.png`,
    });

    const rows = page.getByTestId("clash-row");

    // Measured first, in the document unit — never mm on an inch page.
    const first = rows.nth(0);
    await expect(first).toHaveAttribute("data-unresolved", "false");
    await expect(first).toContainText("in³ overlap");
    await expect(first).not.toContainText("mm");

    // The unverified pair: stamped, bounded, parenthesised, explained.
    const second = rows.nth(1);
    await expect(second).toHaveAttribute("data-unresolved", "true");
    await expect(second.getByTestId("clash-unverified-badge")).toHaveText(
      "Unverified",
    );
    await expect(second.getByTestId("clash-volume")).toHaveText("(0.318)");
    await expect(second).toContainText("in³ at most");
    await expect(page.getByTestId("clash-unverified-note")).toContainText(
      "upper bound, not a measurement",
    );

    // The tree agrees: a measured clash is badged CLASH, an unmeasurable pair
    // UNVERIFIED — the badge never claims a measurement the kernel never took.
    await expect(page.getByTestId(`instance-clash-${idB}`)).toBeVisible();
    await expect(page.getByTestId(`instance-unverified-${idC}`)).toBeVisible();
    await expect(page.getByTestId(`instance-clash-${idC}`)).toHaveCount(0);

    // The VIEWPORT keeps the same three states as the schedule and the tree: it
    // still says "look here" about the unmeasurable pair, but with the
    // unverified language — never the alarm, and never the word "interfering"
    // to a screen reader (UI-REVIEW 2026-07-30 P1).
    const balloonB = page.locator(`[data-testid="assembly-balloon-${idB}"]`);
    await expect(balloonB).toHaveAttribute("data-clash-state", "clash");
    await expect(balloonB).toHaveAttribute("data-clashing", "true");
    await expect(balloonB).toHaveAttribute("aria-label", /interfering/);

    const balloonC = page.locator(`[data-testid="assembly-balloon-${idC}"]`);
    await expect(balloonC).toHaveAttribute("data-clash-state", "unverified");
    await expect(balloonC).toHaveAttribute("data-clashing", "false");
    await expect(balloonC).toHaveAttribute("aria-label", /overlap unverified/);
    await expect(balloonC).not.toHaveAttribute("aria-label", /interfering/);
  });
});

test.describe("clash schedule — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("both clash states read at laptop width (founder shot)", async ({
    page,
  }) => {
    await inchAssemblyWithBothClashStates(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/clash-unverified-${SHOT_TAG}-1280.png`,
    });
    await expect(page.getByTestId("clash-unverified-note")).toBeVisible();
  });
});
