import { expect, test, type Page } from "./fixtures";

import {
  createFeature,
  evaluateViaApi,
  seedAllEdgeFillet,
  seedCube,
  setRollbackViaApi,
  SQUARE_20,
} from "./partSeed";
import {
  createPartViaApi,
  openRowActions,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * THE REGISTER'S REBUILD COLUMN — the drawer finally says "this one is broken"
 * (backend `c98c454`, UI-REVIEW 2026-07-30 verdict 1: "'is broken' is the one I
 * would add").
 *
 * Every state is produced by the REAL stack, never mocked, because the whole
 * value of the column is that it reports a persisted verdict rather than a
 * guess: a clean part is really evaluated clean; a broken one really fails in
 * OCCT (all-edge fillet r50 on a 20 mm cube); a stale one really has a tree
 * write after its evaluate. If the derivation ever moves, this spec fails.
 *
 * Assertions are SOFT where they are measurements, so one regression cannot
 * hide the rest of the picture. `SHOT_TAG=before` captures the pre-change pass.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

function report(label: string, value: unknown): void {
  console.log(`[measure] ${label} = ${JSON.stringify(value)}`);
}

/**
 * A drawer holding every rebuild state the API can report, in register order:
 *
 *   1 clean          evaluated, no feature errors, tree unchanged since
 *   2 broken         evaluated, a feature errored, tree unchanged since
 *   3 was clean      evaluated clean, then the tree moved  → stale
 *   4 was broken     evaluated with errors, then the tree moved → stale
 *   5 never          named and never evaluated
 */
async function seedRegisterOfEveryState(page: Page): Promise<void> {
  const { token } = await seedSession(page);

  const clean = await createPartViaApi(page, token, "Bracket plate");
  await seedCube(page, token, clean.id);
  expect(await evaluateViaApi(page, token, clean.id)).toEqual(["ok", "ok"]);

  const broken = await createPartViaApi(page, token, "Motor mount");
  const brokenTree = await seedCube(page, token, broken.id);
  await seedAllEdgeFillet(page, token, broken.id, 50, brokenTree);
  expect(await evaluateViaApi(page, token, broken.id)).toContain("error");

  const staleOk = await createPartViaApi(page, token, "Spindle housing");
  const staleOkTree = await seedCube(page, token, staleOk.id);
  await evaluateViaApi(page, token, staleOk.id);
  await seedAllEdgeFillet(page, token, staleOk.id, 2, staleOkTree);

  const staleFailed = await createPartViaApi(page, token, "Idler arm");
  const staleFailedTree = await seedCube(page, token, staleFailed.id);
  const filletTree = await seedAllEdgeFillet(
    page,
    token,
    staleFailed.id,
    50,
    staleFailedTree,
  );
  await evaluateViaApi(page, token, staleFailed.id);
  await seedAllEdgeFillet(page, token, staleFailed.id, 2, filletTree);

  await createPartViaApi(page, token, "Cover blank");
}

/** The register, freshly loaded (the health record is written asynchronously). */
async function openRegister(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByTestId("parts-table")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("part-row")).toHaveCount(5);
}

test.describe("register rebuild health — 1440x900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("reports the persisted verdict for every state, and never guesses", async ({
    page,
  }) => {
    await seedRegisterOfEveryState(page);
    await openRegister(page);

    const rows = page.getByTestId("part-row");
    const health = (n: number) =>
      rows.nth(n).locator('[data-testid="part-health"]');

    // The four verdicts, in the drawer's own words.
    await expect(health(0)).toHaveAttribute("data-health", "ok");
    await expect(health(0)).toContainText("Clean");

    await expect(health(1)).toHaveAttribute("data-health", "failed");
    await expect(health(1)).toContainText("Broken");

    // STALE renders INDETERMINATE — the same posture (and the same dashed
    // drafting rule) as the clash schedule's UNVERIFIED: the tree moved, so
    // health is genuinely unknown. Never a tick, never a flag.
    await expect(health(2)).toHaveAttribute("data-health", "stale");
    await expect(health(2)).toContainText("Was clean");
    await expect(health(3)).toHaveAttribute("data-health", "stale");
    await expect(health(3)).toContainText("Was broken");
    // The record's raw status is reported, but never as a current verdict.
    await expect(health(3)).not.toContainText("Broken ");

    await expect(health(4)).toHaveAttribute("data-health", "never");

    // "ok" means NO FEATURE ERRORED — it is not a claim that the part has a
    // body, and the cell's own title has to say so.
    const okTitle = await health(0).getAttribute("title");
    report("ok title", okTitle);
    expect.soft(okTitle ?? "").toMatch(/body/i);

    // The stale cell spends the raw record: it says WHICH way it went and that
    // the tree moved since — better than "unknown", still not a verdict.
    const staleTitle = await health(3).getAttribute("title");
    report("stale title", staleTitle);
    expect.soft(staleTitle ?? "").toMatch(/tree changed/i);

    // LAST WORKED keeps meaning "someone worked on it": recording a rebuild
    // does not bump `updated_at`, so an evaluated-but-unedited part is still
    // NOT STARTED. (Rows 1-4 were authored through the API, so they read as
    // worked; row 5 was only named.)
    await expect(rows.nth(4).getByTestId("part-unstarted")).toBeVisible();

    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/register-health-${SHOT_TAG}-1440.png`,
      }),
    );
  });

  test("the gutter number is the row ordinal it actually is", async ({
    page,
  }) => {
    await seedRegisterOfEveryState(page);
    await openRegister(page);

    const rows = page.getByTestId("part-row");
    const ordinal = (n: number) =>
      rows.nth(n).locator('[data-testid="part-ordinal"]');

    // Not a zero-padded filing identity: those renumber on delete, and a user
    // who cites "sheet 002" is then holding a reference to a different part.
    await expect(ordinal(0)).toHaveText("1");
    await expect(ordinal(1)).toHaveText("2");
    const header = page.getByTestId("parts-ordinal-header");
    await expect(header).toContainText("#");
    await expect(header).toContainText("Row");

    // Prove the renumbering against the REAL delete, so the claim the column
    // makes is checked against the behaviour it has.
    await openRowActions(rows.nth(0));
    await rows.nth(0).getByTestId("part-delete").click();
    await page.getByTestId("part-delete-confirm").click();
    await expect(page.getByTestId("part-row")).toHaveCount(4, {
      timeout: 30_000,
    });
    await expect(ordinal(0)).toHaveText("1");
    await expect(rows.nth(0).getByTestId("part-open")).toContainText(
      "Motor mount",
    );
  });
});

/**
 * The SECOND axis (audit J3b): `eval_state` says whether what ran built,
 * `eval_scope` says how much ran. Both parts below evaluate CLEAN and only one
 * of them is a clean part — the difference is where the travel stop is, and the
 * whole drawer is authored through the real API so the scope is the one
 * documents actually recorded.
 */
test.describe("register rebuild health — the rolled-back prefix", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a clean PREFIX is not reported as a clean part", async ({ page }) => {
    const { token } = await seedSession(page);

    // 1. The stop parked BEFORE the extrude: the evaluate covers the sketch
    //    only, succeeds, and records `ok` over a prefix.
    const parked = await createPartViaApi(page, token, "Bracket plate");
    const sketch = await createFeature(page, token, parked.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    const extrude = await createFeature(page, token, parked.id, {
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
    await setRollbackViaApi(
      page,
      token,
      parked.id,
      sketch.feature.id,
      extrude.tree_version,
    );
    await evaluateViaApi(page, token, parked.id);

    // 2. The stop parked on the LAST feature excludes nothing, so the same
    //    control must NOT hedge a part that genuinely did build.
    const tip = await createPartViaApi(page, token, "Motor mount");
    const tipTree = await seedCube(page, token, tip.id);
    const tipFeatures = await page.request.get(
      `/api/v1/parts/${tip.id}/features`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const lastFeature = (
      (await tipFeatures.json()) as { features: { id: string }[] }
    ).features.at(-1);
    await setRollbackViaApi(
      page,
      token,
      tip.id,
      lastFeature?.id ?? null,
      tipTree,
    );
    expect(await evaluateViaApi(page, token, tip.id)).toEqual(["ok", "ok"]);

    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    const health = (n: number) =>
      page
        .getByTestId("part-row")
        .nth(n)
        .locator('[data-testid="part-health"]');

    // Shot first, assertions after: the same spec run against HEAD~ captures
    // the BEFORE state (both rows reading a bare "Clean") for the founder pair.
    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/register-scope-${SHOT_TAG}-1440.png`,
      }),
    );

    // The state is still `ok` — it is the SCOPE that withdraws the word.
    await expect(health(0)).toHaveAttribute("data-health", "ok");
    await expect(health(0)).toHaveAttribute("data-health-scope", "rolled_back");
    await expect(health(0)).toContainText("Clean to stop");
    const parkedTitle = await health(0).getAttribute("title");
    report("rolled-back title", parkedTitle);
    expect.soft(parkedTitle ?? "").toMatch(/travel stop/i);

    // ...and a stop that excludes nothing reads exactly as it always did.
    await expect(health(1)).toHaveAttribute("data-health", "ok");
    await expect(health(1)).toHaveText(/^Clean$/);
  });
});

test.describe("register rebuild health — 1280x800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the column holds at laptop width without a root scroll", async ({
    page,
  }) => {
    await seedRegisterOfEveryState(page);
    await openRegister(page);

    const overflow = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
    }));
    report("root overflow @1280", overflow);
    expect
      .soft(overflow.scrollHeight)
      .toBeLessThanOrEqual(overflow.clientHeight);

    // The table never scrolls sideways at laptop width either.
    const table = await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>(
        '[data-testid="parts-table"]',
      );
      return el === null
        ? null
        : { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
    });
    report("table width fit @1280", table);
    expect
      .soft(table?.scrollWidth ?? 0)
      .toBeLessThanOrEqual(table?.clientWidth ?? 0);

    await expect(
      page
        .getByTestId("part-row")
        .nth(1)
        .locator('[data-testid="part-health"]'),
    ).toContainText("Broken");

    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/register-health-${SHOT_TAG}-1280.png`,
      }),
    );
  });
});
