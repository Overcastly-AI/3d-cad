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
 * Drill ONE through-hole off-centre, through the UI: open Hole, click the top
 * face, dial the DRO to a point on the bolt circle, submit. Ø8 by default — the
 * diameter every volume assertion here is written against ({@link
 * boreVolumeMm3}); the founder screenshots pass a bigger one, which they can
 * because they assert nothing about volume.
 *
 * Nothing here is hard-coded to a plate size — the sketch is drawn with the
 * mouse, so the plate's size is whatever those two clicks made. Every number is
 * read back off the running app and the ring is sized from it, which is what
 * makes the closed-form volume assertion below exact rather than approximate.
 */
async function drillOffCentreHole(
  page: Page,
  diameterMm = 8,
): Promise<Drilled> {
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
  await page.getByTestId("hole-diameter").fill(String(diameterMm));
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

/**
 * What a USER can actually read on screen for `testId` — measured with the
 * user's own mechanisms, never with a proxy that skips the step being claimed.
 *
 * Three of this repo's green-suite/broken-product defects came from assertions
 * that could not observe their own failure mode, and every one of them would
 * sail through a naive check here. `toBeVisible()` returns TRUE for a node
 * clipped to `1x1 @ (-1,43)`. `toContainText` reads `textContent`, so a label
 * hidden by `display:none` still matches — which is precisely what the band's
 * shed labels are, and why the existing `toContainText("Repeat Hole1")`
 * assertion above passes at a width where those words are not on screen. And a
 * tooltip's copy is in the DOM at all times, so containment cannot tell a
 * proposal from a hover hint.
 *
 * So this returns the painted box AND what `elementFromPoint` finds at its
 * centre: is this node what a mouse would land on, or is something over it?
 */
async function paintedNode(
  page: Page,
  testId: string,
): Promise<{
  text: string;
  width: number;
  height: number;
  hit: boolean;
} | null> {
  return page.evaluate((id) => {
    const node = document.querySelector(`[data-testid="${id}"]`);
    if (node === null) return null;
    const box = node.getBoundingClientRect();
    const at = document.elementFromPoint(
      box.left + box.width / 2,
      box.top + box.height / 2,
    );
    return {
      text: (node.textContent ?? "").trim(),
      width: box.width,
      height: box.height,
      hit:
        at !== null && (at === node || node.contains(at) || at.contains(node)),
    };
  }, testId);
}

/**
 * The painted width of a band tool's own LABEL — the channel P1-1 says is shed.
 * Zero means the band measured itself into the icon tier and the renamed verb
 * is NOT on screen, which is the state the scope cell exists to answer. The
 * tooltip stamp is excluded by name: it carries the same words and is exactly
 * the hover-only channel under complaint.
 */
async function verbLabelWidth(
  page: Page,
  testId: string,
  word: string,
): Promise<number> {
  return page.evaluate(
    ([id, needle]) => {
      const button = document.querySelector(`[data-testid="${id}"]`);
      if (button === null) return -1;
      let widest = 0;
      for (const child of Array.from(button.children)) {
        if (child.hasAttribute("data-tooltip")) continue;
        if (!(child.textContent ?? "").includes(needle as string)) continue;
        widest = Math.max(widest, child.getBoundingClientRect().width);
      }
      return widest;
    },
    [testId, word],
  );
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

/**
 * REACH-2-FLOW — the proposal PATTERN-1 shipped was reachable and not yet
 * DISCOVERABLE. Four separately-measured flow defects, one case each, so a
 * regression in one cannot hide behind the other three.
 */
test.describe("REACH-2-FLOW — the proposal survives the 1280 floor and Cancel", () => {
  test("P1-1/P1-2/P1-3: the subject is painted, marked, and kept through Cancel", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Scope reach");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    await drillOffCentreHole(page);

    // Name the subject the way the ticket advertises it.
    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);

    // ---- P1-1: THE PROPOSAL IS ON SCREEN, NOT UNDER THE POINTER ---------
    // First the premise, so this case cannot pass for the wrong reason: the
    // band really has shed the renamed verb at this width. If the label were
    // painted, the scope cell would be belt-and-braces rather than the only
    // channel, and a later band change could silently make this case vacuous.
    expect(
      await verbLabelWidth(page, "new-pattern", "Repeat"),
      "the Modify verb's own label must be shed at 1280x800 — if it is not, this case is not testing what it claims",
    ).toBe(0);

    const cell = await paintedNode(page, "band-scope-subject");
    expect(cell, "the band's scope cell must exist at 1280x800").not.toBeNull();
    expect(cell?.text).toBe("Hole1");
    // A real box, not a `1x1` clip and not a zero-height stroke — the three
    // shapes this repo has measured an "invisible visible" element taking.
    expect(cell?.width ?? 0).toBeGreaterThan(24);
    expect(cell?.height ?? 0).toBeGreaterThan(8);
    // …and nothing is on top of it, so the words reach a real pair of eyes.
    expect(cell?.hit).toBe(true);

    // The cell is a control, not a tile: it retires the state it announces.
    // (Mandate 3a(c) — chrome that only decorates is a defect.)
    await expect(page.getByTestId("band-scope-clear")).toHaveAttribute(
      "aria-label",
      "Clear Hole1 — pattern and mirror go back to the whole body",
    );

    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();

    // The in-command band keeps saying what the command holds — under its OWN
    // hooks. While a command is open the tool groups stay in the DOM as
    // `sr-only`, so a shared id would put two nodes behind one testid and let a
    // spec be answered by the hidden one (`sr-only` is VISIBLE to every
    // visibility API — this repo has measured that).
    await expect(page.getByTestId("in-command-scope-subject")).toHaveText(
      "Hole1",
    );
    expect(await page.getByTestId("band-scope").count()).toBe(1);

    // ---- P1-2: SOMETHING IN THE FRAME ECHOES THE SUBJECT ----------------
    // The editor names HOLE1 in a side panel; on a plate with two identical
    // bores that settles nothing. The tree row and the timeline chip now carry
    // the same brass SCOPE stamp — one word, one meaning, three surfaces.
    await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
      "data-scoped",
      "true",
    );
    const treeStamp = await paintedNode(page, "feature-scoped-2");
    expect(treeStamp?.text).toBe("Scope");
    expect(treeStamp?.width ?? 0).toBeGreaterThan(8);
    expect(treeStamp?.height ?? 0).toBeGreaterThan(8);
    await expect(page.getByTestId("timeline-chip-2")).toHaveAttribute(
      "data-scoped",
      "true",
    );
    const chipStamp = await paintedNode(page, "timeline-scoped-2");
    expect(chipStamp?.width ?? 0).toBeGreaterThan(8);

    // The mark tracks the COMMAND, not the selection, so it must go away the
    // instant the user chooses the other reading — a mark that outlives the
    // fact it states is worse than no mark at all.
    await page.getByTestId("pattern-scope-body").click();
    await expect(page.getByTestId("feature-row").nth(2)).not.toHaveAttribute(
      "data-scoped",
      "true",
    );
    await expect(page.getByTestId("timeline-chip-2")).not.toHaveAttribute(
      "data-scoped",
      "true",
    );
    await page.getByTestId("pattern-scope-features").click();
    await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
      "data-scoped",
      "true",
    );

    // ---- P1-3: BACKING OUT IS FREE --------------------------------------
    // Cancel used to destroy the very selection that made the proposal
    // possible, so trying again cost the whole click/Escape/press sequence.
    // The band says as much before you press it.
    await expect(page.getByTestId("in-command-cancel")).toContainText(
      "Esc — keeps Hole1",
    );
    await page.getByTestId("in-command-cancel").click();
    await expect(page.getByTestId("pattern-editor")).toHaveCount(0);

    // The selection is intact on every surface it was ever shown on…
    await expect(page.getByTestId("feature-select-2")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const kept = await paintedNode(page, "band-scope-subject");
    expect(kept?.text).toBe("Hole1");
    // …and the very next press is scoped, with no re-selection in between.
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );

    // Escape is the keyboard twin of Cancel and must not disagree with it.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("pattern-editor")).toHaveCount(0);
    await expect(page.getByTestId("feature-select-2")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // The retraction works, and it is the only thing that clears the subject.
    await page.getByTestId("band-scope-clear").click();
    await expect(page.getByTestId("band-scope")).toHaveCount(0);
    await expect(page.getByTestId("feature-select-2")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("P1-4: a seed is taken from the row without opening that feature's editor", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Seed from row");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    await drillOffCentreHole(page);

    // Point the tree selection somewhere ELSE first, using only the gestures
    // that predate this change. Two things then follow from one setup: the seed
    // below cannot be coming from the selection (it is Extrude1), and this case
    // owes nothing to the band's scope cell, so reverting either fix reddens
    // exactly one of the two cases rather than both.
    await page.getByTestId("feature-select-1").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("feature-select-1")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // The advertised gesture used to charge a toll: clicking the row opens that
    // feature's own editor, which locks the band AND the accelerators, so the
    // real sequence was "open a dialog nobody asked for, abandon it, press P".
    // The row's own menu asks the question directly.
    const row = page.getByTestId("feature-row").nth(2);
    const box = await row.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(
      (box?.x ?? 0) + (box?.width ?? 0) / 2,
      (box?.y ?? 0) + (box?.height ?? 0) / 2,
      { button: "right" },
    );

    const repeat = page.getByTestId("tree-ctx-pattern");
    await expect(repeat).toHaveText(/Repeat Hole1/);
    // A real mouse click at the item's centre — not a `force`, not a keyboard
    // shortcut standing in for one.
    const itemBox = await repeat.boundingBox();
    expect(itemBox).not.toBeNull();
    await page.mouse.click(
      (itemBox?.x ?? 0) + (itemBox?.width ?? 0) / 2,
      (itemBox?.y ?? 0) + (itemBox?.height ?? 0) / 2,
    );

    // The pattern opens scoped to Hole1 — and the HOLE editor never appeared,
    // which is the acceptance criterion stated as a negative.
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
      "data-scoped",
      "true",
    );

    // Mirror asks the same question on the same menu — two verbs, one grammar.
    await page.keyboard.press("Escape");
    await page.mouse.click(
      (box?.x ?? 0) + (box?.width ?? 0) / 2,
      (box?.y ?? 0) + (box?.height ?? 0) / 2,
      { button: "right" },
    );
    await expect(page.getByTestId("tree-ctx-mirror")).toHaveText(
      /Mirror Hole1/,
    );

    // …and it is not offered where the kernel cannot honour it: a fillet has a
    // result and no rigid tool, so the row does not pretend it can be repeated
    // (pattern-scope §7 rule 4 — refused kinds are never offered).
    await page.keyboard.press("Escape");
    await page.getByTestId("new-fillet").click();
    await page.getByTestId("fillet-radius").fill("3");
    await page.getByTestId("fillet-radius").press("Enter");
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Fillet1" }),
    ).toBeVisible();
    const filletRow = page.getByTestId("feature-row").nth(3);
    const filletBox = await filletRow.boundingBox();
    await page.mouse.click(
      (filletBox?.x ?? 0) + (filletBox?.width ?? 0) / 2,
      (filletBox?.y ?? 0) + (filletBox?.height ?? 0) / 2,
      { button: "right" },
    );
    await expect(page.getByTestId("tree-ctx-edit")).toBeVisible();
    await expect(page.getByTestId("tree-ctx-pattern")).toHaveCount(0);
  });
});

/**
 * The FEATURE TINT actually painted on the body, in canvas pixels.
 *
 * `data-selected-faces` is the raster-independent companion and it is asserted
 * beside every reading here — but it is a count the app publishes about itself,
 * and this repo has measured three separate defects where the app's own account
 * of a control was true while the pixels were not. So the load-bearing witness
 * is the ink.
 *
 * WHY WARMTH RATHER THAN A LITERAL TOKEN MATCH. `countTokenPixels` works where
 * a token lands on the canvas at its own hex — line materials do. This tint does
 * not: `featureSelect.faceTint` MULTIPLIES the studio matcap (matcaps carry no
 * emissive channel, which is what keeps the machined read), so the painted
 * colour is the token times whatever the matcap was, and no single hex describes
 * it. What survives the multiply is the DIRECTION of the shift: every tinted
 * pixel is pushed toward brass, i.e. red-over-blue. Measured on the fixture
 * below: 384 warm px with the hole scoped, **0** with the scope on `This body` —
 * so the threshold has the whole range to itself and is not a knife-edge.
 *
 * Alpha-gated because the canvas is transparent (the atmosphere is painted by
 * the DOM wrapper beneath it), so an untouched pixel reads as 0,0,0,0 and would
 * otherwise be counted by any bare channel comparison.
 */
async function tintedPixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return -1;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return -1;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const b = data[i + 2] ?? 0;
      const alpha = data[i + 3] ?? 0;
      if (alpha > 200 && r > 70 && r - b >= 25) count += 1;
    }
    return count;
  });
}

/**
 * REACH-2-FLOW-B — the viewport tint answers the COMMAND's question.
 *
 * Deferred from REACH-2-FLOW because `apps/web/src/viewport/**` was another
 * agent's territory at the time. What that left: keeping the selection alive
 * through the editor (P1-3) restored the seed's face tint for free, but the tint
 * read `selectedFeatureId`, so it went on saying `Hole1` after the user chose
 * `This body`, and said nothing at all when the editor seeded from the TIP with
 * nothing selected. The tree stamp and the timeline chip read `scopedFeatureIds`
 * and get both cases right; the viewport now reads the same source.
 */
test.describe("REACH-2-FLOW-B — the tint follows the command, not the selection", () => {
  test("flipping to This body clears the tint; a tip-seeded command paints one", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Scope tint");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    await drillOffCentreHole(page);
    // The drill leaves its own editor open; the body is at rest after Escape.
    await page.keyboard.press("Escape");

    const viewport = page.getByTestId("viewport");
    const treeRow = page.getByTestId("feature-row").nth(2);

    // ---- THE SUBJECT IS NAMED, AND PAINTED --------------------------------
    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(viewport).toHaveAttribute("data-body-highlight", "feature", {
      timeout: 15_000,
    });

    const total = Number(await viewport.getAttribute("data-total-faces"));
    const litScoped = Number(
      await viewport.getAttribute("data-selected-faces"),
    );
    expect(total).toBeGreaterThan(6); // a box (6) reshaped by a through-bore
    expect(litScoped).toBeGreaterThan(0);
    // A PROPER subset — the matcap survives on every face the pattern will not
    // touch, so the tint reads as "this feature", not as a clay swap.
    expect(litScoped).toBeLessThan(total);
    const inkScoped = await tintedPixels(page);
    expect(inkScoped, "the scoped feature must be painted").toBeGreaterThan(50);

    // ---- FLIP TO `This body`: THE INK GOES WITH IT ------------------------
    // Same camera, same body, same editor — only the answer changed. So the
    // difference below is the tint and nothing else.
    await page.getByTestId("pattern-scope-body").click();
    await expect(page.getByTestId("pattern-scope-body")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // …in the same frame the tree stamp clears, which is the acceptance
    // criterion: three surfaces, one question, one answer.
    await expect(treeRow).not.toHaveAttribute("data-scoped", "true");
    await expect(viewport).toHaveAttribute("data-body-highlight", "none");
    await expect(viewport).toHaveAttribute("data-selected-faces", "0");
    expect(
      await tintedPixels(page),
      "no face may stay lit once the command acts on the whole body",
    ).toBe(0);

    // Nothing is painted, deliberately: a whole-body scope has nothing to
    // stand out AGAINST, so a full-body brass would hide the machined read and
    // carry exactly as much information as this does. The reading is stated in
    // words on the row that asked, where it is legible.
    await expect(page.getByTestId("pattern-scope-note")).toContainText(
      "whatever the tree hands it",
    );

    // ---- AND BACK ---------------------------------------------------------
    await page.getByTestId("pattern-scope-features").click();
    await expect(treeRow).toHaveAttribute("data-scoped", "true");
    await expect(viewport).toHaveAttribute("data-body-highlight", "feature");
    await expect(viewport).toHaveAttribute(
      "data-selected-faces",
      String(litScoped),
    );
    expect(await tintedPixels(page)).toBeGreaterThan(50);

    // ---- THE CASE SELECTION CANNOT EXPRESS --------------------------------
    // A reload clears the tree selection AND the pre-selection store, so the
    // frame starts with no highlight from any other source — asserted, so the
    // tint below cannot be inherited from one of them.
    await page.keyboard.press("Escape");
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(3, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(viewport).toHaveAttribute("data-body-highlight", "none", {
      timeout: 15_000,
    });
    expect(await tintedPixels(page)).toBe(0);

    // The editor seeds itself from the TIP cut with nothing selected — and the
    // viewport now says so. Before this fix the frame stayed grey while the
    // panel named `Hole1`.
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );
    await expect(page.getByTestId("feature-select-2")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(viewport).toHaveAttribute("data-body-highlight", "feature", {
      timeout: 15_000,
    });
    const litTip = Number(await viewport.getAttribute("data-selected-faces"));
    expect(litTip).toBeGreaterThan(0);
    expect(litTip).toBeLessThan(total);
    expect(
      await tintedPixels(page),
      "a tip-seeded command must paint its subject with nothing selected",
    ).toBeGreaterThan(50);
  });
});

/**
 * Founder before/after for REACH-2-FLOW-B (gated behind UPDATE_SCREENSHOTS —
 * see e2e/fixtures.ts). This test regenerates the AFTER pair.
 *
 * The BEFORE pair cannot be regenerated by any committed spec, because it is
 * the behaviour this change deleted: it was captured once by reverting
 * `highlightedFeatureIds` to the selection-only reading, running this same
 * test, and renaming the two files `-after-` -> `-before-`. That is the honest
 * shape of a before/after for a fix — the before is an artefact, not a mode.
 *
 * A Ø24 bore rather than the Ø8 the assertions use: the assertions only need
 * the tint to EXIST (they count it), a founder needs to SEE it, and at Ø8 the
 * lit face is a 3 px sliver of cylinder wall.
 */
test.describe("REACH-2-FLOW-B founder screenshots", () => {
  test("the scope's tint at the 1280x800 floor", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Scope tint shot");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    await drillOffCentreHole(page, 24);
    await page.keyboard.press("Escape");

    // 1) The command acts on the WHOLE BODY. Before: the bore stayed brass, so
    //    the frame named a subject the pattern would not touch.
    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await page.getByTestId("pattern-scope-body").click();
    await expect(page.getByTestId("pattern-scope-body")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/reach2b-scope-body-after-laptop.png`,
    });

    // 2) A TIP-SEEDED command with nothing selected. Before: the panel named
    //    Hole1 and the frame said nothing at all.
    await page.keyboard.press("Escape");
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(3, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-scope-features")).toHaveText(
      "Hole1",
    );
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/reach2b-scope-tip-after-laptop.png`,
    });
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
