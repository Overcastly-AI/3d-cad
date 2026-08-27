import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * REACH-2 — a pattern says WHAT it repeats, and the tree selection is the answer
 * (`docs/design/pattern-scope.md`). Driven entirely through the real browser
 * against the real stack; nothing is seeded over the API but the empty part.
 *
 * The capability existed in the gateway contract and the kernel for a full
 * release and NO USER COULD REACH IT: `PatternParamsV1.scope` had no control in
 * any dialog, so every pattern the product could author was the legacy
 * whole-body reading — the one §1 measures as a coin flip that reports `ok`
 * either way. This spec is the reachability oracle for that
 * (`scripts/check-ui-parity.py` reads the e2e suite), so every step below is a
 * click a user makes.
 *
 * THE PROOF IS GEOMETRIC, NOT A 2xx. Params models are pydantic-default
 * `extra="ignore"`, so a payload that spells the selection at the wrong key
 * validates, evaluates and silently gives the OLD reading — seven kernel tests
 * once passed against the wrong scope that way. So the assertion is on the
 * evaluated VOLUME: six bores' worth of material gone, and a bounding box that
 * did not grow. A whole-body reading of the same dialog would leave the volume
 * up and the part six times longer.
 */

/** Ø8 through the plate: the exact material one bore removes. */
function boreVolumeMm3(thicknessMm: number): number {
  return Math.PI * 4 * 4 * thicknessMm;
}

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The three numbers of the "Extents X x Y x Z mm" readout, in mm. */
async function extents(page: Page): Promise<[number, number, number]> {
  const text = await page.getByTestId("prop-extents").innerText();
  const nums = (text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? []).map(
    Number.parseFloat,
  );
  expect(nums.length, `extents readout: ${text}`).toBeGreaterThanOrEqual(3);
  return [nums[0] as number, nums[1] as number, nums[2] as number];
}

/** The evaluated body volume in mm³ (the inspector's mass-properties cell). */
async function volume(page: Page): Promise<number> {
  // The cell renders "Volume / 35,770 / mm³" — the label and the unit carry no
  // digits, so the first number in it is the value.
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
  const value = Number.parseFloat(match?.[0] ?? "");
  expect(Number.isFinite(value), `volume readout: ${text}`).toBe(true);
  return value;
}

/** Draw a rectangle (two clicks) and persist it; wait for the solve. */
async function sketchRectangleAndSave(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(560, 360);
  await page.mouse.move(1060, 700);
  await page.mouse.click(1060, 700);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Sketch on XY and extrude 10 mm — the plate every case here starts from. */
async function buildPlate(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expectRenderedBody(page);
}

/** Click the body's TOP face node (greatest z in the pick-node accessible name). */
async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Where a drilled hole sits, and where the ring it will be patterned about is. */
interface Drilled {
  /** Plate centre, in world X/Y (the top face's own frame is world-aligned). */
  centre: { x: number; y: number };
  /** Bolt-circle radius the hole was placed at. */
  radius: number;
  /** Plate thickness — the depth every through bore removes. */
  thickness: number;
}

/**
 * Drill ONE Ø8 through-hole off-centre, through the UI: open Hole, click the
 * top face, dial the DRO to a point on the bolt circle, submit.
 *
 * Nothing here is hard-coded to a plate size — the sketch is drawn with the
 * mouse, so the plate's size is whatever those two clicks made. Every number is
 * read back off the running app and the ring is sized from it, which is what
 * makes the closed-form volume assertion below exact rather than approximate.
 */
async function drillOffCentreHole(page: Page): Promise<Drilled> {
  const [ex, ey, ez] = await extents(page);
  // The premise the ring depends on: six Ø8 bores on a radius of min/4 are
  // pairwise disjoint (their centres are `radius` apart at 60°) and clear of
  // the edge. Stated as an assertion so a resized sketch fails loudly here
  // rather than as a mystifying volume miss 40 lines later.
  expect(
    Math.min(ex, ey),
    "plate too small for a 6-up Ø8 bolt circle",
  ).toBeGreaterThan(40);
  const radius = Math.min(ex, ey) / 4;

  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await clickTopFace(page);

  // The face's own frame: origin at the part origin projected onto the face,
  // axes along world X/Y for a top face. Asserted rather than assumed, because
  // the pattern's axis point below is a WORLD point.
  await expect(page.getByTestId("hole-frame")).toContainText("X→+X");
  await expect(page.getByTestId("hole-frame")).toContainText("Y→+Y");

  // Picking the face seeds the DRO to the face CENTRE, so these two fields are
  // the plate centre in world X/Y — the axis the bolt circle turns about.
  const centre = {
    x: Number.parseFloat(
      await page.getByTestId("hole-position-x").inputValue(),
    ),
    y: Number.parseFloat(
      await page.getByTestId("hole-position-y").inputValue(),
    ),
  };
  expect(Number.isFinite(centre.x) && Number.isFinite(centre.y)).toBe(true);

  await page.getByTestId("hole-position-x").fill(String(centre.x + radius));
  await page.getByTestId("hole-position-y").fill(String(centre.y));
  await page.getByTestId("hole-diameter").fill("8");
  await expect(page.getByTestId("hole-submit")).toBeEnabled();
  await page.getByTestId("hole-submit").click();

  await expect(
    page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
  ).toBeVisible();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  return { centre, radius, thickness: ez };
}

/** The body's world-space bounding box, as "x, y, z" mm pairs. */
async function bbox(
  page: Page,
): Promise<{ min: [number, number, number]; max: [number, number, number] }> {
  const read = async (testId: string): Promise<[number, number, number]> => {
    const text = await page.getByTestId(testId).innerText();
    const nums = (text.replace(/,/g, " ").match(/-?\d+(?:\.\d+)?/g) ?? []).map(
      Number.parseFloat,
    );
    return [nums[0] as number, nums[1] as number, nums[2] as number];
  };
  return { min: await read("prop-bbox-min"), max: await read("prop-bbox-max") };
}

/**
 * Drill ONE Ø8 through-hole at (x0, cy) where BOTH x0 and -x0 sit well inside
 * the plate — so its reflection about the YZ origin plane lands on material.
 *
 * The mirror's only planes here are the three origin datums, and where the world
 * origin falls inside a mouse-drawn plate is not knowable in advance. So the
 * offset is derived from the measured box rather than assumed: a reflected cut
 * that missed the body would come back as `mirror_feature_unreachable`, which
 * would be a fixture bug wearing the costume of a product bug.
 */
async function drillMirrorableHole(
  page: Page,
): Promise<{ y: number; thickness: number }> {
  const box = await bbox(page);
  const half = Math.min(box.max[0], -box.min[0]) - 8;
  expect(
    half,
    "the world origin is not comfortably inside the plate",
  ).toBeGreaterThan(8);
  const x0 = half / 2;

  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await clickTopFace(page);
  await expect(page.getByTestId("hole-frame")).toContainText("X→+X");
  const y = Number.parseFloat(
    await page.getByTestId("hole-position-y").inputValue(),
  );
  await page.getByTestId("hole-position-x").fill(String(x0));
  await page.getByTestId("hole-diameter").fill("8");
  await page.getByTestId("hole-submit").click();
  await expect(
    page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
  ).toBeVisible();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  return { y, thickness: box.max[2] - box.min[2] };
}

test.describe("pattern scope — the tree selection is what gets repeated", () => {
  test("select Hole1, press Pattern, get six holes (not a six-times plate)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bolt circle");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    const plateVolume = await volume(page);
    const drilled = await drillOffCentreHole(page);

    // One bore's worth of material is gone. This pins the drill (Ø8, through
    // 10 mm) in closed form, so the six-hole assertion below has a known unit.
    const oneHole = await volume(page);
    expect(plateVolume - oneHole).toBeCloseTo(
      boreVolumeMm3(drilled.thickness),
      1,
    );

    // §1.1's UNRELATED FEATURE, and the reason it is here rather than left out
    // as noise: WITHOUT it, `plate → hole → pattern` gives the SAME six-hole
    // body under either reading, because the legacy `body` scope happens to
    // array the immediately-preceding cut's tool. Measured — an earlier draft of
    // this spec forced `{kind: "body"}` onto the wire and every volume and
    // bounding-box assertion still passed. A 3 mm corner fillet is all it takes
    // to break that coincidence: from here the two readings are a six-hole plate
    // and a plate repeated six times, and the numbers below can tell them apart.
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await page.getByTestId("fillet-radius").fill("3");
    await page.getByTestId("fillet-radius").press("Enter");
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Fillet1" }),
    ).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const filleted = await volume(page);
    const [filletedX] = await extents(page);

    // ---- THE FLOW UNDER TEST -------------------------------------------
    // Click the Hole1 row. Selecting a feature row opens that feature's editor
    // (and locks the band while it is open), so Escape closes it — the SELECTION
    // survives, which is the whole point: the tree still says what the subject
    // is after the dialog is gone.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);

    // The verb now PROPOSES the subject: the Modify strip reads "Repeat Hole1"
    // instead of a generic "Pattern".
    const patternVerb = page.getByTestId("new-pattern");
    await expect(patternVerb).toBeVisible();
    // The button also carries its tooltip stamp (label + the `P` chip), so the
    // exact gate is the accessible name; the visible words are asserted by
    // containment.
    await expect(patternVerb).toContainText("Repeat Hole1");
    await expect(patternVerb).toHaveAttribute(
      "aria-label",
      "Repeat Hole1 — place it in a linear or circular array (P)",
    );

    await patternVerb.click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();

    // The editor opens ALREADY SCOPED to Hole1 — no pick is armed, nothing to
    // hunt for. (A pick would have put face nodes in the canvas; there are none.)
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("pattern-scope-body")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      0,
    );
    await expect(page.getByTestId("pattern-scope-note")).toContainText(
      "Repeats Hole1's cut at every placement",
    );

    // Circular, about +Z through the plate centre, 6 up over 360°.
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-axis-direction").selectOption("+z");
    await page.getByTestId("pattern-axis-x").fill(String(drilled.centre.x));
    await page.getByTestId("pattern-axis-y").fill(String(drilled.centre.y));
    await page.getByTestId("pattern-axis-z").fill("0");
    await page.getByTestId("pattern-angle").fill("360");
    await page.getByTestId("pattern-count").fill("6");
    // THE WIRE ASSERTION, and it is not belt-and-braces. Params models are
    // pydantic-default `extra="ignore"`, so spelling the selection at the wrong
    // level — `params.features` instead of `params.scope` — validates, evaluates
    // and silently gives the legacy whole-body reading (design §7.1; it cost the
    // kernel side seven green tests against the wrong scope). No server-side
    // guard exists or can easily exist, so the dialog's own payload is where
    // that typo has to be caught.
    const write = page.waitForRequest(
      (request) =>
        request.url().includes(`/parts/${part.id}/features`) &&
        request.method() === "POST",
    );
    await expect(page.getByTestId("pattern-submit")).toBeEnabled();
    await page.getByTestId("pattern-submit").click();
    const params = (
      (await write).postDataJSON() as {
        feature: { params: Record<string, unknown> };
      }
    ).feature.params;
    expect(Object.keys(params)).not.toContain("features");
    expect(params.scope).toEqual({
      kind: "features",
      features: [{ kind: "feature", feature_id: expect.any(String) }],
    });

    // The tree row says what it repeats — derived from the params and the tree,
    // so renaming Hole1 can never leave this badge lying.
    const patternRow = page.getByTestId("feature-row").nth(4);
    await expect(patternRow).toContainText("pattern · Hole1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-4")).toHaveCount(0);
    await expectRenderedBody(page);

    // ---- THE GEOMETRIC PROOF -------------------------------------------
    // Five MORE bores through the filleted plate, in closed form: the bolt
    // circle sits a quarter-extent in, so every placed cut passes through full
    // material and removes exactly π·4²·t. The `body` reading of these same
    // numbers fuses six copies of the whole plate instead — volume UP, not down.
    await expect
      .poll(() => volume(page), { timeout: 30_000 })
      .toBeLessThan(filleted - 4 * boreVolumeMm3(drilled.thickness));
    const sixHoles = await volume(page);
    expect(filleted - sixHoles).toBeCloseTo(
      5 * boreVolumeMm3(drilled.thickness),
      1,
    );

    // …and the part did not get bigger. Volume alone is not a sufficient
    // witness (design §8: the wrong body even has identical topology counts),
    // so the bounding box is asserted independently.
    const [patternedX] = await extents(page);
    expect(patternedX).toBeCloseTo(filletedX, 3);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/pattern-scope-after-desktop.png`,
    });
  });

  test("flipping to This body states the reading instead of silently changing it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Scope reading");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    await drillOffCentreHole(page);

    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();

    // Even with NOTHING selected in the tree, the tip cut is proposed — a
    // whole-body pattern of a just-drilled hole is §1's coin flip, so the tool
    // opens on the reading that can only mean one thing.
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Flip to the legacy reading. The editor SAYS what that reading is: today
    // it happens to repeat the hole, and it stops doing so the moment another
    // feature lands between them. Both results report `ok`, which is exactly
    // why silence here was the defect.
    await page.getByTestId("pattern-scope-body").click();
    await expect(page.getByTestId("pattern-scope-body")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const note = page.getByTestId("pattern-scope-note");
    await expect(note).toContainText("whatever the tree hands it");
    await expect(note).toContainText("Hole1's cut today");
    await expect(note).toContainText(
      "the whole body once another feature lands between them",
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/pattern-scope-body-reading.png`,
    });

    // Flipping back restores the subject — the selection is a suggestion the
    // user can toggle, never something they have to re-state.
    await page.getByTestId("pattern-scope-features").click();
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );
    await expect(page.getByTestId("pattern-scope-note")).toContainText(
      "Repeats Hole1's cut",
    );
  });

  test("a scoped pattern round-trips: re-opening it shows Hole1, not a guess", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Round trip");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    const drilled = await drillOffCentreHole(page);

    await page.getByTestId("new-pattern").click();
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-axis-x").fill(String(drilled.centre.x));
    await page.getByTestId("pattern-axis-y").fill(String(drilled.centre.y));
    await page.getByTestId("pattern-count").fill("4");
    await page.getByTestId("pattern-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Reload: the scope is persisted, so it survives the round trip through the
    // real API rather than living in the editor's memory.
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(4, {
      timeout: 30_000,
    });
    await page.getByTestId("feature-select-3").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("pattern-count")).toHaveValue("4");
  });
});

test.describe("mirror scope — the same question, the same words", () => {
  test("select Hole1, press Mirror, reflect the CUT and not the plate", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirrored bore");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    const drilled = await drillMirrorableHole(page);
    const oneHole = await volume(page);

    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    const mirrorVerb = page.getByTestId("new-mirror");
    await expect(mirrorVerb).toContainText("Mirror Hole1");
    await mirrorVerb.click();

    await expect(page.getByTestId("mirror-scope-features")).toHaveText("Hole1");
    await expect(page.getByTestId("mirror-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("mirror-scope-note")).toContainText(
      "Reflects Hole1's cut about the plane",
    );

    // YZ (x = 0) — the plane the hole was placed symmetrically about.
    await page.getByTestId("mirror-plane-YZ").click();
    await expect(page.getByTestId("mirror-readout")).toHaveText("YZ");

    const write = page.waitForRequest(
      (request) =>
        request.url().includes(`/parts/${part.id}/features`) &&
        request.method() === "POST",
    );
    await page.getByTestId("mirror-submit").click();
    const params = (
      (await write).postDataJSON() as {
        feature: { params: Record<string, unknown> };
      }
    ).feature.params;
    expect(Object.keys(params)).not.toContain("features");
    expect(params.scope).toEqual({
      kind: "features",
      features: [{ kind: "feature", feature_id: expect.any(String) }],
    });

    await expect(page.getByTestId("feature-row").nth(3)).toContainText(
      "mirror · Hole1",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // A SECOND BORE, not a doubled plate: reflecting the hole's cut removes one
    // more bore's worth of material. The v1 whole-body reading would have
    // reflected and fused the plate itself — volume up, box wider.
    await expect
      .poll(() => volume(page), { timeout: 30_000 })
      .toBeLessThan(oneHole);
    expect(oneHole - (await volume(page))).toBeCloseTo(
      boreVolumeMm3(drilled.thickness),
      1,
    );
  });
});

test.describe("pattern scope founder screenshots", () => {
  test("the scope row at the 1280x800 floor", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Scope laptop");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    await drillOffCentreHole(page);

    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("new-pattern")).toContainText("Repeat Hole1");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/pattern-scope-verb-laptop.png`,
    });

    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-scope")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/pattern-scope-editor-laptop.png`,
    });
  });
});
