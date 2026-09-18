/**
 * A COMMAND EDITOR SEEDS FROM THE FEATURE, NEVER FROM THE LAST SESSION (F-9).
 *
 * The product audit of 2026-09-16 found `Fillet1`, stored at `radius_mm: 8`,
 * re-opening pre-filled at **20** — the number the gauge had been dragged to
 * before 8 was typed. One Enter away from a silent 2.5x change, with nothing on
 * screen saying the field disagreed with the feature.
 *
 * The mechanism is the gauge OVERRIDE channel outliving its command. A gauge
 * drag writes `{ mm }` into `PartPage`, the open editor echoes it into its
 * field, and `useGaugeOverride`'s own doc calls the reset "ANCHOR B — the line
 * everyone forgets". It was called from `closeEditor` only, and a SAVE does not
 * go through `closeEditor` — so the box survived the save, and the next editor
 * to mount applied it over its own seed on its first effect pass.
 *
 * The assertion is on the FIELD, not on the override: what a user can read is
 * the whole subject here, and a stand-in for it (the box being null) would stay
 * green the day somebody re-introduces the clobber through a different channel.
 */
import { expect, test } from "./fixtures";
import { MOUNTS } from "./gaugeMounts";
import { installSceneProbe } from "./invariants";

const filletMount = MOUNTS.find((m) => m.id === "fillet-radius");
if (filletMount === undefined) throw new Error("fillet-radius mount is gone");

test("a saved fillet re-opens at its stored radius, not at the last drag", async ({
  page,
}) => {
  // The shared mount leaves a 20 mm cube with NEW FILLET open, radius 8, one
  // edge picked and the camera in iso. The probe goes in BEFORE it, because the
  // mount does its own `goto` and an init script only applies to loads that
  // come after it.
  await installSceneProbe(page);
  await filletMount.open(page);
  const radius = page.getByTestId("fillet-radius");
  await expect(radius).toHaveValue("8");

  // Move the gauge. The route is the grip's own keyboard nudge rather than a
  // pixel drag: it writes the value through exactly the same `onChange` the
  // pointer does, and it does not depend on which cube edge the mount happened
  // to pick — a foreshortened track has no screen direction to drag along, and
  // that is a camera artefact, not the subject here. The value it lands on does
  // not matter; what matters is that it is NOT the number we then commit, so a
  // field reading it afterwards can only have come from the stale channel.
  const grip = page.getByTestId("fillet-radius-handle");
  await expect(grip).toBeVisible();
  await grip.focus();
  for (let i = 0; i < 4; i += 1) await page.keyboard.press("ArrowUp");
  const nudged = await radius.inputValue();
  expect(nudged).not.toBe("8");

  // Type the radius the feature is actually created with, and commit.
  await radius.fill("8");
  await page.getByTestId("fillet-submit").click();
  await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });

  // Re-open the SAVED feature from the tree. This is the first re-entry — the
  // audit's second open was already correct, because cancelling had cleared the
  // box on the way out.
  await page.getByTestId("feature-row").filter({ hasText: "Fillet1" }).click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await expect(radius).toHaveValue("8");
});
