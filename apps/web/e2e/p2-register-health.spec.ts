import { expect, test, type Page } from "./fixtures";

import { evaluateViaApi, seedAllEdgeFillet, seedCube } from "./partSeed";
import {
  createPartViaApi,
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
