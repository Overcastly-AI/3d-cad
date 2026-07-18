import { expect, test } from "./fixtures";

import { authorBoltMates, balloonX, setupTwoInstances } from "./assemblyFlow";
import { expectHistoryGates, SCREENSHOT_DIR } from "./support";

/**
 * Undo/redo UR3 frontend (docs/design/undo-redo.md) — assembly history driven
 * through the real stack. History is SERVER-side snapshot state, so every UI
 * step below walks the same ring the backend proves byte-identical: author the
 * coincident+concentric "bolt" pair, undo the concentric (the mate leaves the
 * tree AND the solve reverts — the free plate returns to its seed), redo it
 * (the mate returns with its ORIGINAL id and the plates re-bolt), then delete
 * the free instance (its mates cascade away) and undo THAT (instance + both
 * mates return, ids verbatim, and the assembly re-solves bolted). Buttons and
 * chords are mixed for parity; the ring bounds and the armed-mate-tool lock
 * are asserted as honest disabled states, never dead clicks.
 */

test.describe("Assembly undo/redo (UR3)", () => {
  test("mate undo/redo + instance-delete cascade — buttons + chords, honest gates", async ({
    page,
  }) => {
    const { idA, idB, seedX } = await setupTwoInstances(page);

    // At the ring's top after two instance-adds: undo lights up (history
    // exists), redo is honestly disabled — the same shared HistoryGroup the
    // part band renders, in the same leading position.
    await expectHistoryGates(page, { undo: true, redo: false });

    // An ARMED MATE TOOL owns the session: History locks (honest reason, not
    // a dead click) and the chord is inert — a mid-pick Ctrl+Z must never
    // yank the graph out from under the picks.
    await page.getByTestId("mate-coincident").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await expect(page.getByTestId("undo-button")).toBeDisabled();
    await expect(page.getByTestId("redo-button")).toBeDisabled();
    await page.keyboard.press("Control+z");
    // Nothing undid: both instances are still aboard after a settle window.
    await page.waitForTimeout(750);
    await expect(page.getByTestId("instance-row")).toHaveCount(2);
    await page.keyboard.press("Escape");
    await expectHistoryGates(page, { undo: true, redo: false });

    // Author the bolt (coincident + concentric); the free plate snaps in.
    await authorBoltMates(page, idA, idB);
    await expect
      .poll(() => balloonX(page, idB), { timeout: 30_000 })
      .toBeLessThan(seedX - 20);
    const boltedMateIds = await page
      .getByTestId("mate-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.mateId ?? "").sort(),
      );
    expect(boltedMateIds).toHaveLength(2);

    // authorBoltMates leaves the concentric tool ARMED (value-free mates chain
    // — AssemblyPage keeps the tool live to author another), and an armed tool
    // deliberately locks History ("Finish the Concentric mate first"). Disarm
    // it first (Escape), the same hygiene the armed-lock sub-test uses above,
    // so the band's undo lights up.
    await page.keyboard.press("Escape");
    await expectHistoryGates(page, { undo: true, redo: false });

    // Undo #1 (button): the concentric mate leaves the tree AND the solve
    // reverts — the free plate returns to its seed (the remaining coincident
    // only holds the faces flush; x is free again).
    await page.getByTestId("undo-button").click();
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect
      .poll(() => balloonX(page, idB), { timeout: 30_000 })
      .toBeGreaterThan(60);
    await expectHistoryGates(page, { undo: true, redo: true });

    // Redo #1 (Ctrl+Y — the Windows chord): the mate returns with its
    // ORIGINAL id (snapshots restore verbatim, never re-mint) and the plates
    // re-bolt; redo pins disabled at the ring's top again.
    await page.keyboard.press("Control+y");
    await expect(page.getByTestId("mate-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    const redoneMateIds = await page
      .getByTestId("mate-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.mateId ?? "").sort(),
      );
    expect(redoneMateIds).toEqual(boltedMateIds);
    await expect
      .poll(() => balloonX(page, idB), { timeout: 30_000 })
      .toBeLessThan(seedX - 20);
    await expectHistoryGates(page, { undo: true, redo: false });

    // Delete the free instance: its mates cascade away with it.
    await page.getByTestId(`instance-delete-${idB}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("mate-row")).toHaveCount(0);

    // Undo #2 (Ctrl+Z): the instance AND both cascaded mates return, ids
    // verbatim, and the restored graph re-solves bolted.
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("instance-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    const restoredInstanceIds = await page
      .getByTestId("instance-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
      );
    expect(restoredInstanceIds).toContain(idB);
    await expect(page.getByTestId("mate-row")).toHaveCount(2);
    const restoredMateIds = await page
      .getByTestId("mate-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.mateId ?? "").sort(),
      );
    expect(restoredMateIds).toEqual(boltedMateIds);
    await expect
      .poll(() => balloonX(page, idB), { timeout: 30_000 })
      .toBeLessThan(seedX - 20);
    await expectHistoryGates(page, { undo: true, redo: true });

    // Founder shot: the restored bolted assembly with History aboard the band.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-undo-redo-desktop.png`,
    });

    // Redo #2 (button): the delete replays — instance and mates gone again,
    // and the ring's top pins redo disabled once more.
    await page.getByTestId("redo-button").click();
    await expect(page.getByTestId("instance-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("mate-row")).toHaveCount(0);
    await expectHistoryGates(page, { undo: true, redo: false });
  });
});
