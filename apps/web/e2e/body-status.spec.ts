import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * WHAT THE WORKSPACE CLAIMS ABOUT THE BODY ON SCREEN — driven against the real
 * stack, on a part that is really broken (OCCT genuinely cannot build an r50
 * fillet on a 20 mm cube; the same failure `p2-register-health.spec.ts` uses).
 *
 * Why this spec exists: every `body-status` assertion in the suite was
 * HAPPY-PATH (`toHaveText("Up to date")` in `hole.spec.ts` and
 * `feature-selection.spec.ts`), and that is precisely how AUDIT-ENGINEERING J2
 * shipped — on a part with one broken feature the same screen read "Failed"
 * (Solve), "Up to date" (Status) and "Ready" (Export), and the last one would
 * hand over a STEP of the last-good PREFIX with nothing marking it. The
 * non-happy paths are covered here: a broken feature, a rolled-back prefix, and
 * the export gate in both cases.
 *
 * The founder shots are their own tests, waiting only on hooks that exist on
 * BOTH sides of the change (`feature-row`, `body-inspector`, `eval-status`), so
 * the same frame can be captured against old sources with `SHOT_TAG=before`.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/**
 * Sketch → extrude → an r50 all-edge fillet OCCT refuses → an r1 fillet that is
 * never attempted. The result is the audit's exact situation: a real prefix body
 * (the 20 mm cube), one errored feature, and one innocent feature stranded
 * behind it.
 */
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

/** The same three ops, all buildable — the part the travel stop is set on. */
async function seedSoundPart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Bracket plate");
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
  await createFeature(page, account.token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 2 },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

/** Open the workspace and wait for the evaluate to land (30s under load). */
async function openPart(
  page: Page,
  partId: string,
  features: number,
): Promise<void> {
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(features, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
}

/**
 * Did clicking this cell actually produce a file?
 *
 * `force` on purpose: a gated `PanelActionCell` uses `aria-disabled` rather than
 * the native attribute (so the reason it is grey has somewhere to live), and it
 * SWALLOWS the activation itself. Forcing past Playwright's actionability check
 * is therefore the only way to prove the swallow — a user cannot get a file out
 * of this cell even by trying.
 */
async function clickProducesDownload(
  page: Page,
  testId: string,
): Promise<boolean> {
  const settled = page
    .waitForEvent("download", { timeout: 3_000 })
    .then(() => true)
    .catch(() => false);
  await page.getByTestId(testId).click({ force: true });
  return settled;
}

test.describe("body status honesty — 1440x900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("founder shot: the workspace of a part with a broken feature", async ({
    page,
  }) => {
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await page.mouse.move(1400, 880); // park the cursor off the model
    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/body-status-${SHOT_TAG}-1440.png`,
      }),
    );
  });

  test("Solve, Status and Export tell the SAME story about a broken tree", async ({
    page,
  }) => {
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);

    // 1) SOLVE — the cell that was already right.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });

    // 2) STATUS — was "Up to date" over this exact tree.
    const status = page.getByTestId("body-status");
    await expect(status).toHaveAttribute("data-body-status", "partial");
    await expect(status).toHaveText("Partial");
    await expect(page.getByTestId("body-status-detail")).toContainText(
      "built to Extrude1",
    );
    await expect(page.getByTestId("body-status-detail")).toContainText(
      "Fillet1 failed",
    );

    // 3) EXPORT — was "Ready", and would have written a partial STEP.
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "feature-error",
    );
    await expect(page.getByTestId("part-export-status")).toHaveText(
      "Fillet1 failed",
    );
    await expect(page.getByTestId("part-export-step")).toBeDisabled();
    expect(await clickProducesDownload(page, "part-export-step")).toBe(false);
    expect(await clickProducesDownload(page, "part-export-stl")).toBe(false);

    // The viewport says the solid is not the part (N3), and offers the fix.
    const notice = page.getByTestId("partial-body-notice");
    await expect(notice).toContainText("Showing the last good state");
    await expect(notice).toContainText("built to Extrude1");
    await page.getByTestId("partial-body-show-failure").click();
    await expect(page.getByTestId("feature-select-2")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("a stranded feature names the failure that stopped the build", async ({
    page,
  }) => {
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });

    // Row 4 (`Corner fillets R1`) was never attempted. A bare "SKIP" badge made
    // that read as a fillet bug (AUDIT-PRODUCT N3).
    const stranded = page.getByTestId("feature-row").nth(3);
    await expect(stranded).toHaveAttribute("data-blocked-by", /.+/);
    await expect(
      stranded.getByLabel(
        "evaluation skipped: not attempted — Fillet1 failed first",
      ),
    ).toBeVisible();
    await expect(page.getByTestId("feature-excluded-note")).toContainText(
      "does not depend on Fillet1",
    );
  });

  test("a rolled-back export is allowed, and says partial on screen AND in the filename", async ({
    page,
  }) => {
    const partId = await seedSoundPart(page);
    await openPart(page, partId, 3);

    // The whole tree builds: this is the state that may claim currency.
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("part-export-status")).toHaveText("Ready");

    // Travel stop after Extrude1 — the fillet is held out of the build.
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("timeline-strip")).not.toHaveAttribute(
      "data-busy",
      "true",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("body-status")).toHaveText("Rolled back", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "partial",
    );
    await expect(page.getByTestId("part-export-status")).toHaveText("Partial");
    await expect(page.getByTestId("part-export-notice")).toContainText(
      "travel stop",
    );

    // The file itself carries the claim — a download outlives the screen.
    const download = page.waitForEvent("download");
    await page.getByTestId("part-export-step").click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/-partial\.step$/);
  });
});

test.describe("body status honesty — 1366x768", () => {
  test.use({ viewport: { width: 1366, height: 768 } });

  test("founder shot: the same broken part at laptop width", async ({
    page,
  }) => {
    const partId = await seedBrokenPart(page);
    await openPart(page, partId, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await page.mouse.move(1330, 750);
    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/body-status-${SHOT_TAG}-1366.png`,
      }),
    );

    // The added sentence must not push the frame into a root scroll.
    const overflow = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
    }));
    expect
      .soft(overflow.scrollHeight)
      .toBeLessThanOrEqual(overflow.clientHeight);
  });

  test("the EXPORT strip is fully on-frame in every state — it is pinned, not last", async ({
    page,
  }) => {
    /**
     * The fold this keeps shut (UI-REVIEW 2026-07-30 P1, its SECOND regression):
     * the inspector's height is clamped so it clears the reference cube, and
     * whatever sat last in its scrolling column was whatever fell off the
     * bottom. At 1366x768 with the travel stop moved, 19.5 of the strip's 98.5
     * px were visible and the sentence warning that the file will be marked
     * PARTIAL was 100% hidden — the user was told something by a line they
     * could not see. Copy was trimmed twice to buy the space back; the strip is
     * now PINNED by `FloatingPanel.footer` instead, so the readouts scroll and
     * the actions cannot move.
     *
     * Measured on the real stack, in the two states QA found clipped.
     */
    /**
     * VISIBLE, not merely laid out. The strip was clipped by the PANEL's own
     * scroll box, not by the window, so a viewport-bounds check passes on the
     * broken layout — the probe has to be "is this pixel reachable", i.e. the
     * element's centre hit-tests to itself (the `p1-token-scale` reachability
     * idiom) AND its box lies inside its scroll container's client box.
     */
    const onFrame = async (testId: string) =>
      page.evaluate((id) => {
        const el = document.querySelector(`[data-testid="${id}"]`);
        if (el === null) return "missing";
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return "collapsed";
        if (r.bottom > window.innerHeight || r.top < 0) return "off-window";
        let node = el.parentElement;
        while (node !== null) {
          const style = getComputedStyle(node);
          if (/(auto|scroll)/.test(style.overflowY)) {
            const box = node.getBoundingClientRect();
            if (r.bottom > box.bottom + 0.5 || r.top < box.top - 0.5) {
              return `clipped by ${node.className.slice(0, 24)}`;
            }
            break;
          }
          node = node.parentElement;
        }
        const hit = document.elementFromPoint(
          r.left + r.width / 2,
          r.top + r.height / 2,
        );
        return hit !== null && (el.contains(hit) || hit.contains(el))
          ? "visible"
          : "covered";
      }, testId);

    const partId = await seedSoundPart(page);
    await openPart(page, partId, 3);
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    expect(await onFrame("part-export-controls")).toBe("visible");

    // Travel-stop state: the strip grows a notice AND the status cell's
    // qualifier wraps — the exact combination that clipped it.
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("timeline-strip")).not.toHaveAttribute(
      "data-busy",
      "true",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("part-export-status")).toHaveText("Partial");
    expect(await onFrame("part-export-controls")).toBe("visible");
    expect(await onFrame("part-export-notice")).toBe("visible");

    // Feature-error state: the third clipped case (21.5 px, measured).
    const broken = await seedBrokenPart(page);
    await openPart(page, broken, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    expect(await onFrame("part-export-controls")).toBe("visible");
  });
});
