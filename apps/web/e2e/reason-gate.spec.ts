import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * REASON-GATE-1 — the PIXEL half. `editorSubmitReason.test.tsx` proves all
 * seventeen editors render a reason and pin it outside the scroll region;
 * jsdom cannot prove it is legible, and legibility is the whole point.
 *
 * SO EVERYTHING HERE IS MEASURED AT 1280x800 — the documented responsive floor,
 * not Playwright's 1600x1000 default. That distinction is not pedantry: HEM-1B's
 * first version of this assertion passed at the default while the product was
 * broken at the floor, because the card's action row rode inside the scrolling
 * body and the sentence fell out of the card entirely (`elementFromPoint` at the
 * reason's own centre returned `feature-tree-section`).
 *
 * AND EVERYTHING IS ASSERTED AS INK, never as markup. `toBeVisible()` is a box
 * property and returns TRUE for a node clipped to 1x1 outside the frame;
 * `toContainText` reads `textContent`, including `display:none` nodes. Neither
 * can observe the failure this ticket is about, so each editor's reason must
 * have a real box AND hit-test to its own Save cell under `elementFromPoint` —
 * the user's own mechanism.
 */

/** A 20 mm cube part with two sketches — enough tree to reach ten editors. */
async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Reason gate");
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
  // A second sketch, so the loft picker has something to leave un-chosen.
  await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

/**
 * One editor reachable from the seeded part, driven into a state its gate
 * refuses. `arrive` does whatever authoring is needed AFTER the card opens;
 * most cases just clear the field the card's own default fills in.
 */
interface Gated {
  /** The toolbar control that opens the card. */
  tool: string;
  /** The card, so the walk fails loudly if the tool opened something else. */
  editor: string;
  /** The commit cell whose reason is under test. */
  submit: string;
  /** What the user did, in the failure message. */
  situation: string;
  arrive: (page: Page) => Promise<void>;
  /** A word the sentence must carry — proof it named THIS field, not any field. */
  names: string;
}

const clear =
  (field: string) =>
  async (page: Page): Promise<void> => {
    await page.getByTestId(field).fill("");
  };

const nothing = async (): Promise<void> => undefined;

const GATED: Gated[] = [
  {
    tool: "new-extrude",
    editor: "extrude-editor",
    submit: "extrude-submit",
    situation: "the distance is cleared",
    arrive: clear("extrude-distance"),
    names: "distance",
  },
  {
    tool: "new-revolve",
    editor: "revolve-editor",
    submit: "revolve-submit",
    situation: "the angle is cleared",
    arrive: clear("revolve-angle"),
    names: "angle",
  },
  {
    tool: "new-loft",
    editor: "loft-editor",
    submit: "loft-submit",
    situation: "a third section slot is added and left empty",
    arrive: async (page) => {
      await page.getByTestId("loft-add-section").click();
    },
    names: "section 03",
  },
  {
    tool: "new-fillet",
    editor: "fillet-editor",
    submit: "fillet-submit",
    situation: "the radius is cleared",
    arrive: clear("fillet-radius"),
    names: "radius",
  },
  {
    tool: "new-chamfer",
    editor: "chamfer-editor",
    submit: "chamfer-submit",
    situation: "the distance is cleared",
    arrive: clear("chamfer-distance"),
    names: "distance",
  },
  {
    tool: "new-shell",
    editor: "shell-editor",
    submit: "shell-submit",
    situation: "the thickness is cleared",
    arrive: clear("shell-thickness"),
    names: "thickness",
  },
  {
    tool: "new-pattern",
    editor: "pattern-editor",
    submit: "pattern-submit",
    situation: "the spacing is cleared",
    arrive: clear("pattern-spacing"),
    names: "spacing",
  },
  {
    // Draft opens ALREADY gated — a taper with no picked faces has nothing to
    // taper — which is the case the fields cannot show inline, and therefore
    // the one the Save cell has to carry.
    tool: "new-draft",
    editor: "draft-editor",
    submit: "draft-submit",
    situation: "no faces are picked yet",
    arrive: nothing,
    names: "faces",
  },
  {
    tool: "new-hole",
    editor: "hole-editor",
    submit: "hole-submit",
    situation: "no face is picked to drill into",
    arrive: nothing,
    names: "face",
  },
  {
    tool: "tool-datum",
    editor: "datum-editor",
    submit: "datum-submit",
    situation: "a midplane with neither reference chosen",
    arrive: async (page) => {
      await page.getByTestId("datum-kind").selectOption("midplane");
    },
    names: "first reference",
  },
];

/**
 * The floor on how many editors this file drives through the real browser. It
 * is not seventeen — six of them (the sheet-metal chain, combine, mirror,
 * sweep) need a different part to exist at all, and the hem already has its own
 * 1280x800 case from HEM-1B. The number is asserted so that trimming the walk
 * to make a failure go away fails here instead.
 */
const EDITORS_MEASURED_IN_PIXELS = 10;

/** The reason's ink: its box, and what a click at its centre would actually hit. */
async function measureReason(
  page: Page,
  submitTestId: string,
): Promise<{
  text: string;
  width: number;
  height: number;
  hit: string | null;
}> {
  const submit = page.getByTestId(submitTestId);
  const reason = submit.locator("[data-disabled-reason]");
  await expect(
    reason,
    `${submitTestId} is gated with nothing to read — the REASON-GATE-1 defect`,
  ).toHaveCount(1);
  const box = await reason.boundingBox();
  expect(box, `${submitTestId}'s reason has no box at all`).not.toBe(null);
  const hit = await page.evaluate(
    ([x, y]) =>
      document
        .elementFromPoint(x as number, y as number)
        ?.closest("[data-testid]")
        ?.getAttribute("data-testid") ?? null,
    [box!.x + box!.width / 2, box!.y + box!.height / 2],
  );
  return {
    text: (await reason.innerText()).trim(),
    width: box!.width,
    height: box!.height,
    hit,
  };
}

test("every reachable editor's gated commit action is legible at 1280x800", async ({
  page,
}) => {
  expect(GATED).toHaveLength(EDITORS_MEASURED_IN_PIXELS);
  // THE FLOOR, set before anything is measured — a sentence that only fits on a
  // big monitor is not an explanation.
  await page.setViewportSize({ width: 1280, height: 800 });

  const partId = await seedCubePart(page);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });

  const measured: string[] = [];
  for (const card of GATED) {
    const tool = page.getByTestId(card.tool);
    await expect(tool, `${card.tool} never became reachable`).toBeEnabled({
      timeout: 30_000,
    });
    await tool.click();
    await expect(page.getByTestId(card.editor)).toBeVisible();
    await card.arrive(page);

    const submit = page.getByTestId(card.submit);
    await expect(
      submit,
      `${card.submit} is NOT gated when ${card.situation} — this case proves nothing`,
    ).toBeDisabled();

    const { text, width, height, hit } = await measureReason(page, card.submit);
    expect(text, `${card.submit} said nothing when ${card.situation}`).not.toBe(
      "",
    );
    // The budget, measured on the rendered string rather than trusted from the
    // module: the footer cell is half a card wide (~19 chars a line).
    expect(
      text.length,
      `"${text}" is too long for the footer cell`,
    ).toBeLessThanOrEqual(48);
    expect(
      text.toLowerCase(),
      `"${text}" does not name what ${card.submit} is waiting for`,
    ).toContain(card.names.toLowerCase());
    // Ink: real area, and the reason's own centre resolves to the cell it
    // explains rather than to whatever is drawn over it.
    expect(width, `"${text}" has no width`).toBeGreaterThan(60);
    expect(height, `"${text}" has no height`).toBeGreaterThan(8);
    expect(hit, `"${text}" is covered by ${hit ?? "nothing testable"}`).toBe(
      card.submit,
    );
    // …and a screen reader is told the same sentence, not a parallel one.
    const describedBy = await submit.getAttribute("aria-describedby");
    expect(
      describedBy,
      `${card.submit} has no accessible description`,
    ).not.toBe(null);
    expect((await page.locator(`#${describedBy}`).innerText()).trim()).toBe(
      text,
    );

    measured.push(`${card.submit}: "${text}" (${Math.round(width)}px)`);
    await page.getByTestId(card.submit.replace("-submit", "-cancel")).click();
    await expect(page.getByTestId(card.editor)).toBeHidden();
  }

  // The evidence tail, so a CI log says WHAT each card told the user.
  console.log(`REASON-GATE 1280x800\n  ${measured.join("\n  ")}`);
  expect(measured).toHaveLength(EDITORS_MEASURED_IN_PIXELS);
});

test("the founder shot: a gated Create explaining itself at 1280x800", async ({
  page,
}) => {
  // The before/after pair the design mandate asks for. The BEFORE half was
  // captured once from a deliberately reverted build (the fix forbids keeping
  // the defect around to regenerate it); this is the after half, refreshed on
  // demand with UPDATE_SCREENSHOTS=1.
  await page.setViewportSize({ width: 1280, height: 800 });
  const partId = await seedCubePart(page);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });

  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-radius").fill("");
  await expect(page.getByTestId("fillet-submit")).toBeDisabled();
  await expect(
    page.getByTestId("fillet-submit").locator("[data-disabled-reason]"),
  ).toHaveText("Enter the radius.");
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/reason-gate-fillet-after-1280.png`,
  });

  await page.getByTestId("fillet-cancel").click();
  await page.getByTestId("new-draft").click();
  await expect(page.getByTestId("draft-editor")).toBeVisible();
  await expect(page.getByTestId("draft-submit")).toBeDisabled();
  await expect(
    page.getByTestId("draft-submit").locator("[data-disabled-reason]"),
  ).toHaveText("Click one or more faces to taper.");
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/reason-gate-draft-after-1280.png`,
  });
});
