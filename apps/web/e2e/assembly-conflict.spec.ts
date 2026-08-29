import { expect, test, type Page } from "./fixtures";

import { pickDispatch, setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR } from "./support";

/**
 * MATEUI-1 — the mate-conflict diagnosis, read the way a user reads it.
 *
 * The reported defect, verbatim from the SOLVE tab with two conflicting mates:
 *
 *     mates [UUID('4ae95465-…'), UUID('b78a814e-…')] are mutually
 *     unsatisfiable Remove or relax mate 4ae95465-…
 *
 * Three faults, one cause: the geometry service's own prose was printed to the
 * user, so (a) a Python `list[uuid.UUID]` repr leaked into the UI, (b) the mate
 * it names appears nowhere in the mates panel — two Coincident mates on the
 * same pair rendered as two identical rows — and (c) two unterminated sentences
 * fused into a run-on.
 *
 * (b) is the real defect, so (b) is what these cases prove MECHANICALLY: every
 * identifier the message prints is parsed back out of the rendered text and
 * must resolve to exactly one row in the panel, and the row must answer to a
 * real click. A case that only checks the string looks tidier and covers less.
 *
 * The no-identifier assertion runs over the WHOLE rendered message rather than
 * the two ids this fixture happens to hold, so a future field stringified into
 * the prose fails here too.
 */

/** The UUID shape, anywhere in a string. */
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/**
 * Author two mates that cannot both hold: B's bottom face pinned flush to A's
 * top face (B lands at z = 10) and the SAME face held 20 mm off it. One face,
 * two parallel target planes at different heights — the solver's own
 * `test_contradictory_mates_are_conflicting_with_offenders` shape, so the
 * conflict is a translation along one axis with no rotation to iterate on.
 */
async function authorConflictingMates(
  page: Page,
  idA: string,
  idB: string,
): Promise<void> {
  await page.getByTestId("mate-coincident").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
  );
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
  );
  await expect(page.getByTestId("mate-row")).toHaveCount(1, {
    timeout: 30_000,
  });
  await waitForSolved(page);

  await page.getByTestId("mate-distance").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
  );
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
  );
  await page.getByTestId("mate-value").fill("20");
  await page.getByTestId("mate-commit").click();
  await expect(page.getByTestId("mate-row")).toHaveCount(2, {
    timeout: 30_000,
  });
  await waitForSolved(page);
}

/**
 * What the user actually READS in the diagnosis: `innerText`, not
 * `textContent`. The latter includes `display:none` nodes, which is how a
 * hidden label passed a visibility proxy for weeks (CLAUDE.md, the
 * assertion-cannot-observe-the-failure family).
 */
async function diagnosisText(page: Page): Promise<string> {
  return (await page.getByTestId("assembly-diagnosis").innerText()).trim();
}

test.describe("MATEUI-1 — a conflict names mates the panel can show you", () => {
  test("prints no identifier, and every mate it names is findable", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);
    await authorConflictingMates(page, idA, idB);

    await expect(page.getByTestId("assembly-solve-status")).toHaveText(
      "Conflicting",
      { timeout: 30_000 },
    );

    const message = await diagnosisText(page);

    // (a) No raw identifier, over the WHOLE message — not the two ids this
    // fixture knows about. `UUID(` is Python's constructor repr; the bracketed
    // list is how it arrived on screen.
    expect(message).not.toMatch(UUID_RE);
    expect(message).not.toContain("UUID(");
    expect(message).not.toContain("[");
    expect(message).not.toContain("mutually unsatisfiable");

    // (c) Two sentences, separated. The reported run-on was two clauses with
    // no terminator between them, so assert the terminator is there.
    expect(message).toMatch(/\.\s/);
    expect(message.endsWith(".")).toBe(true);

    // (b) THE REAL DEFECT. Parse the handles back out of what was rendered and
    // demand each one resolve to exactly one row in the mates panel.
    const tags = [...message.matchAll(/\bM\d+\b/g)].map((m) => m[0]);
    expect(tags.length).toBeGreaterThanOrEqual(2);
    for (const tag of tags) {
      const row = page.locator(
        `[data-testid="mate-row"][data-mate-tag="${tag}"]`,
      );
      await expect(row).toHaveCount(1);
      // The tag is INK on that row, at a size a person can read and a pointer
      // can reach — never a data attribute standing in for a visible handle.
      const seat = row.locator("[data-testid^='mate-tag-']");
      await expect(seat).toHaveText(tag);
      const box = await seat.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThan(8);
      expect(box!.height).toBeGreaterThan(8);
      const owner = await page.evaluate(
        ([x, y]) => {
          const el = document.elementFromPoint(x, y);
          return el?.closest("[data-mate-tag]")?.getAttribute("data-mate-tag");
        },
        [box!.x + box!.width / 2, box!.y + box!.height / 2] as const,
      );
      expect(owner).toBe(tag);
    }

    // The message names the mates the SOLVER named — as many rows as the
    // diagnosis has offenders, so a message that quietly named the wrong two
    // would fail rather than read tidily.
    const conflictRows = page.locator(
      '[data-testid="mate-row"] >> text=conflict',
    );
    expect(await conflictRows.count()).toBe(tags.length);
  });

  test("removes a named mate from where the message is read", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);
    await authorConflictingMates(page, idA, idB);
    await expect(page.getByTestId("assembly-solve-status")).toHaveText(
      "Conflicting",
      { timeout: 30_000 },
    );

    const message = await diagnosisText(page);
    const firstTag = message.match(/\bM\d+\b/)?.[0];
    expect(firstTag).toBeTruthy();
    const mateId = await page
      .locator(`[data-testid="mate-row"][data-mate-tag="${firstTag}"]`)
      .getAttribute("data-mate-id");
    expect(mateId).toBeTruthy();

    const action = page.getByTestId(`diagnosis-remove-${mateId}`);
    await expect(action).toBeVisible();
    // The action names the mate the same way the message does — one vocabulary
    // across the message, the button and the tree row.
    await expect(action).toHaveText(new RegExp(`Remove\\s+${firstTag}\\b`));

    // A REAL pointer click at the control's centre, not `force` and not a
    // synthetic dispatch: the claim is that a user can press it.
    const box = await action.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);

    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    // The conflict is gone, and so is the diagnosis that named it.
    await expect(page.getByTestId("assembly-solve-status")).not.toHaveText(
      "Conflicting",
    );
    await expect(
      page.locator(`[data-testid="mate-row"][data-mate-id="${mateId}"]`),
    ).toHaveCount(0);
  });

  test("founder frames — the reported message beside the one that shipped", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });

    // Capture the geometry service's OWN prose off the wire, so the "before"
    // frame is the real reported defect rather than a re-typed impression of
    // it. The fields are still sent; this fix stopped RENDERING them.
    let served: { message?: string; suggested_fix?: string | null } | null =
      null;
    await page.route("**/api/v1/geometry/assembly/evaluate", async (route) => {
      const response = await route.fetch();
      const body = await response.text();
      try {
        const parsed = JSON.parse(body) as {
          diagnosis?: { message?: string; suggested_fix?: string | null };
        };
        if (parsed.diagnosis) served = parsed.diagnosis;
      } catch {
        // A non-JSON body is not this spec's business; pass it through.
      }
      await route.fulfill({ response, body });
    });

    const { idA, idB } = await setupTwoInstances(page);
    await authorConflictingMates(page, idA, idB);
    // Disarm the mate tool so the frames show the workspace at rest, not a
    // half-open command HUD that has nothing to do with the diagnosis.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("mate-hud")).toHaveCount(0);
    await expect(page.getByTestId("assembly-solve-status")).toHaveText(
      "Conflicting",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("assembly-diagnosis")).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mateui1-after-1280.png`,
    });

    // The BEFORE frame: put the served strings back on screen exactly as the
    // old JSX joined them (`{message}{" " + suggested_fix}`), drop the actions
    // and the row tags this fix added. Everything else is the same frame, so
    // the pair differs only where the defect was.
    const before = served as {
      message?: string;
      suggested_fix?: string | null;
    } | null;
    expect(before?.message).toBeTruthy();
    await page.evaluate(
      (diag) => {
        const paragraph = document.querySelector(
          '[data-testid="assembly-diagnosis"]',
        );
        if (paragraph)
          paragraph.textContent =
            diag.message + (diag.suggested_fix ? ` ${diag.suggested_fix}` : "");
        document
          .querySelector('[data-testid="assembly-diagnosis-actions"]')
          ?.remove();
        document
          .querySelectorAll("[data-testid^='mate-tag-']")
          .forEach((tag) => tag.remove());
      },
      before as { message: string; suggested_fix: string | null },
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mateui1-before-1280.png`,
    });

    // The frames must actually differ where the defect was — a pair of
    // identical screenshots is worse than none.
    const reported = await diagnosisText(page);
    expect(reported).toMatch(UUID_RE);
  });
});
