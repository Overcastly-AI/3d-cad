import { expect, test, type Page } from "./fixtures";

import { seedSession } from "./support";

/**
 * QA verification of SHEET-RESCALE-2 (`a3316f8`) — written independently of the
 * builder's own `drawing-rescale.spec.ts`, on purpose: this file re-derives the
 * measurement rather than importing the builder's helpers, so a shared helper
 * that measures the wrong thing cannot make both suites agree.
 *
 * The claim under test is a GESTURE, so every capability case here drives the
 * real control (`selectOption` on the real `<select>`, `page.mouse`, `Tab`,
 * touch taps) and asserts on what the user can see. The API is used only to
 * ESTABLISH state that no gesture can produce — an off-ladder scale — and to
 * read back what was persisted.
 *
 * Measurement: projected edge length in SHEET MILLIMETRES, taken from the pick
 * band `<rect>`'s own `width` attribute. Not the `drawing-view` group (it
 * carries the view label and placement frame, which are chrome and do not
 * scale) and not a screen `boundingBox` (the band is a constant 2.6 mm wide in
 * sheet space, so `hypot(w,h)` carries a constant term that turned an exact
 * 0.50 into 0.5056 on a previous pass).
 */

const LADDER = ["5:1", "2:1", "1:1", "1:2", "1:5", "1:10"] as const;
const PROJECTIONS = ["front", "top", "right", "iso"] as const;

/** The ratio a "n:d" label names. */
function ratioOf(label: string): number {
  const [n, d] = label.split(":").map(Number);
  if (!Number.isFinite(n) || !Number.isFinite(d) || !n || !d) {
    throw new Error(`unreadable scale label ${label}`);
  }
  return n / d;
}

/** The next scale DOWN the ladder — a reduction, so the re-scaled sheet cannot
 * overflow its paper and turn a redraw assertion into a layout-issue test. */
function nextSmaller(drafted: string): string {
  const i = LADDER.indexOf(drafted as (typeof LADDER)[number]);
  if (i < 0) throw new Error(`fit chose ${drafted}, off the picker's ladder`);
  const next = LADDER[i + 1];
  if (next === undefined) throw new Error(`${drafted} is the ladder's bottom`);
  return next;
}

/** A 60 x 40 x 30 mm block through the real gateway. */
async function createBlock(
  page: Page,
  token: string,
  name: string,
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers,
  });
  expect(part.ok(), `create part: ${part.status()}`).toBeTruthy();
  const partId = ((await part.json()) as { id: string }).id;

  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            {
              id: "e1",
              kind: "line",
              start: { x: 0, y: 0 },
              end: { x: 60, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 60, y: 0 },
              end: { x: 60, y: 40 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 60, y: 40 },
              end: { x: 0, y: 40 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 40 },
              end: { x: 0, y: 0 },
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers,
  });
  expect(sketch.ok(), `sketch: ${sketch.status()}`).toBeTruthy();
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };

  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: 30,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers,
  });
  expect(extrude.ok(), `extrude: ${extrude.status()}`).toBeTruthy();
  return partId;
}

/** Open a fresh drawing and lay out the four standard views. */
async function seedLaidOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<string> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill(name);
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 60_000,
  });
  return new URL(page.url()).pathname.split("/").pop() ?? "";
}

interface Tree {
  docVersion: number;
  sheetId: string;
  scales: string[];
}

async function readTree(
  page: Page,
  token: string,
  drawingId: string,
): Promise<Tree> {
  const response = await page.request.get(`/api/v1/drawings/${drawingId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), `read tree: ${response.status()}`).toBeTruthy();
  const body = (await response.json()) as {
    doc_version: number;
    sheets: {
      sheet: { id: string };
      views: { scale: { numerator: number; denominator: number } }[];
    }[];
  };
  const content = body.sheets[0];
  if (content === undefined) throw new Error("no sheet on this drawing");
  return {
    docVersion: body.doc_version,
    sheetId: content.sheet.id,
    scales: content.views.map(
      (v) => `${v.scale.numerator}:${v.scale.denominator}`,
    ),
  };
}

function soleScale(scales: string[]): string {
  const unique = new Set(scales);
  expect(unique.size, `sheet must carry ONE scale, saw ${[...unique]}`).toBe(1);
  const first = scales[0];
  if (first === undefined) throw new Error("sheet has no views");
  return first;
}

/**
 * Longest projected edge per view, in SHEET MILLIMETRES — the pick band rect's
 * own `width` in the SVG user space, which for this sheet is millimetres.
 */
async function edgeLengthsMm(page: Page): Promise<Record<string, number>> {
  for (const p of PROJECTIONS) {
    await expect(
      page
        .locator(`[data-testid="drawing-pick-edge"][data-view="${p}"]`)
        .first(),
    ).toBeAttached({ timeout: 60_000 });
  }
  const out = await page.evaluate(() => {
    const sizes: Record<string, number> = {};
    for (const group of document.querySelectorAll<SVGGElement>(
      '[data-testid="drawing-pick-edge"]',
    )) {
      const view = group.getAttribute("data-view") ?? "?";
      let longest = sizes[view] ?? 0;
      for (const rect of group.querySelectorAll<SVGRectElement>("rect")) {
        longest = Math.max(longest, rect.width.baseVal.value);
      }
      sizes[view] = longest;
    }
    return sizes;
  });
  for (const p of PROJECTIONS) {
    if (!out[p]) throw new Error(`no measurable edge in the ${p} view`);
  }
  return out;
}

/** What the Scale cell ACTUALLY says to a person looking at it: the text of the
 * option the browser has selected, plus the control's value and the option's
 * own disabled flag. Read from the DOM, not from the React props. */
async function scaleCellReading(page: Page): Promise<{
  value: string;
  shownText: string;
  selectedIndex: number;
  selectedDisabled: boolean;
  optionTexts: string[];
  disabledTexts: string[];
}> {
  return page.evaluate(() => {
    const select = document.querySelector<HTMLSelectElement>(
      '[data-testid="drawing-scale-select"]',
    );
    if (select === null) throw new Error("no drawing-scale-select in the DOM");
    const chosen = select.selectedOptions[0] ?? null;
    return {
      value: select.value,
      shownText:
        chosen === null ? "<none selected>" : chosen.textContent!.trim(),
      selectedIndex: select.selectedIndex,
      selectedDisabled: chosen === null ? false : chosen.disabled,
      optionTexts: [...select.options].map((o) => o.textContent!.trim()),
      disabledTexts: [...select.options]
        .filter((o) => o.disabled)
        .map((o) => o.textContent!.trim()),
    };
  });
}

/** Write a scale no gesture can produce, straight at the API. */
async function writeScaleViaApi(
  page: Page,
  token: string,
  drawingId: string,
  numerator: number,
  denominator: number,
): Promise<void> {
  const tree = await readTree(page, token, drawingId);
  const response = await page.request.patch(
    `/api/v1/drawings/${drawingId}/sheets/${tree.sheetId}`,
    {
      data: {
        expected_version: tree.docVersion,
        scale: { numerator, denominator },
      },
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  expect(
    response.ok(),
    `off-ladder write ${numerator}:${denominator}: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
}

test.describe("QA SHEET-RESCALE-2 — the Scale cell is a real gesture", () => {
  test("the picker is genuinely hittable and re-picking redraws every view by the exact ratio", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlock(page, account.token, "QA rescale block");
    const drawingId = await seedLaidOutDrawing(
      page,
      partId,
      "QA rescale drawing",
    );

    const before = await readTree(page, account.token, drawingId);
    const drafted = soleScale(before.scales);
    const target = nextSmaller(drafted);

    // 1. The control exists post-layout, is unique, and is not disabled.
    const picker = page.getByTestId("drawing-scale-select");
    await expect(picker).toHaveCount(1);
    await expect(picker).toBeVisible();
    await expect(picker).toBeEnabled();
    await expect(picker).toHaveValue(drafted);
    // The dead readout it replaced must be gone — one cell, not two.
    await expect(page.getByTestId("drawing-scale-readout")).toHaveCount(0);

    // 2. HITTABLE by a real pointer: the point a user aims at resolves to the
    // control itself, not to a chrome element sitting over it. This is the
    // check `force: true` skips.
    const hit = await page.evaluate(() => {
      const select = document.querySelector<HTMLSelectElement>(
        '[data-testid="drawing-scale-select"]',
      )!;
      const box = select.getBoundingClientRect();
      const at = document.elementFromPoint(
        box.left + box.width / 2,
        box.top + box.height / 2,
      );
      return {
        width: Math.round(box.width * 10) / 10,
        height: Math.round(box.height * 10) / 10,
        resolvesToSelf: at === select,
        resolved: at === null ? "null" : at.tagName.toLowerCase(),
      };
    });
    expect(hit.resolvesToSelf, `centre resolved to <${hit.resolved}>`).toBe(
      true,
    );
    // The product's own dense touch floor is 24 px.
    expect(hit.height, "control height (dense floor)").toBeGreaterThanOrEqual(
      24,
    );

    console.log(`[QA] picker box ${hit.width}x${hit.height} px, hits itself`);

    // 2b. CROSS-SURFACE COHERENCE. The change swapped an engraved `Readout`
    // for an operable cell and claims the caption still reads like its
    // neighbours. Measured against the Size readout's caption in the same
    // band, because a caption that quietly became a different size is the
    // change announcing itself — and an unknown Tailwind utility here would be
    // silent, not an error.
    const captions = await page.evaluate(() => {
      const read = (el: Element | null | undefined) => {
        if (!el) return null;
        const s = getComputedStyle(el);
        return {
          text: el.textContent?.trim() ?? "",
          fontSize: s.fontSize,
          letterSpacing: s.letterSpacing,
          textTransform: s.textTransform,
          color: s.color,
          fontFamily: s.fontFamily.split(",")[0],
        };
      };
      const sizeCell = document
        .querySelector('[data-testid="drawing-size-readout"]')
        ?.closest("div");
      // `justify-center` is what distinguishes the band CELL from the
      // SelectField's own `flex flex-col gap-0.5` wrapper inside it.
      const scaleCell = document
        .querySelector('[data-testid="drawing-scale-select"]')
        ?.closest("div.justify-center");
      return {
        size: read(sizeCell?.querySelector("span")),
        scale: read(scaleCell?.querySelector("span[aria-hidden='true']")),
      };
    });

    console.log(`[QA] captions: ${JSON.stringify(captions)}`);
    expect(captions.scale, "the post-layout Scale caption must exist").not.toBe(
      null,
    );
    expect(captions.scale!.text).toBe("Scale");
    expect(
      captions.scale!.fontSize,
      "Scale's caption must match its neighbours' engraving",
    ).toBe(captions.size!.fontSize);
    expect(captions.scale!.letterSpacing).toBe(captions.size!.letterSpacing);
    expect(captions.scale!.textTransform).toBe(captions.size!.textTransform);
    expect(captions.scale!.color).toBe(captions.size!.color);
    expect(captions.scale!.fontFamily).toBe(captions.size!.fontFamily);
    // 10px is the `2xs` rung; an unknown utility would silently inherit ~16px.
    expect(parseFloat(captions.scale!.fontSize)).toBeLessThan(12);

    const edgesBefore = await edgeLengthsMm(page);
    await expect(page.getByTestId("title-block-scale")).toHaveText(drafted);

    // 3. The GESTURE: a real selectOption on the real control.
    await picker.selectOption(target);

    // The title block is composed SERVER-side from views[0].scale, so it only
    // changes once the write landed and the sheet re-composed.
    await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
      timeout: 60_000,
    });
    await expect(picker).toHaveValue(target);
    await expect(picker).toBeEnabled();

    // 4. Persisted, on every view.
    const after = await readTree(page, account.token, drawingId);
    expect(new Set(after.scales)).toEqual(new Set([target]));

    // 5. Every view actually redrew, by EXACTLY the ratio asked for.
    const edgesAfter = await edgeLengthsMm(page);
    const expected = ratioOf(target) / ratioOf(drafted);
    for (const p of PROJECTIONS) {
      const b = edgesBefore[p]!;
      const a = edgesAfter[p]!;

      console.log(
        `[QA] ${p}: ${b.toFixed(5)} mm -> ${a.toFixed(5)} mm  ratio ${(a / b).toFixed(6)} (expect ${expected.toFixed(6)})`,
      );
      expect(a / b, `${p} view must redraw by exactly ${expected}`).toBeCloseTo(
        expected,
        5,
      );
    }
  });

  test("an OFF-LADDER stored scale is stated truthfully, not misreported as the first option", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlock(page, account.token, "QA offladder block");
    const drawingId = await seedLaidOutDrawing(
      page,
      partId,
      "QA offladder drawing",
    );
    const drafted = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );

    // Two off-ladder shapes an API client can legitimately write: a plausible
    // drafting scale that simply is not on our six-rung ladder, and an
    // unreduced pair whose RATIO is on the ladder but whose LABEL is not.
    for (const [n, d] of [
      [1, 4],
      [3, 7],
      [2, 4],
    ] as const) {
      const stored = `${n}:${d}`;
      await writeScaleViaApi(page, account.token, drawingId, n, d);
      await page.goto(`/drawings/${drawingId}`);
      await expect(page.getByTestId("drawing-sheet")).toBeVisible({
        timeout: 60_000,
      });
      await expect(page.getByTestId("title-block-scale")).toHaveText(stored, {
        timeout: 60_000,
      });

      const reading = await scaleCellReading(page);

      console.log(
        `[QA] stored ${stored} -> cell says "${reading.shownText}" (value=${reading.value}, idx=${reading.selectedIndex}, disabled=${reading.selectedDisabled}, options=${JSON.stringify(reading.optionTexts)})`,
      );

      // THE claim: the cell states the true stored scale. Anything else is a
      // regression this change introduced, since the Readout it replaced could
      // not lie.
      expect(
        reading.shownText,
        `cell must state the stored scale ${stored}, not ${reading.shownText}`,
      ).toBe(stored);
      expect(reading.value).toBe(stored);
      // Shown but not choosable — the guard entry must not offer a re-pick of
      // something the ladder cannot express.
      expect(reading.selectedDisabled, "guard entry must be disabled").toBe(
        true,
      );
      expect(reading.disabledTexts).toEqual([stored]);
      // The whole ladder is still choosable beside it.
      for (const rung of LADDER) {
        expect(reading.optionTexts).toContain(rung);
      }
      // And the cell agrees with the sheet the user is looking at.
      await expect(page.getByTestId("title-block-scale")).toHaveText(stored);
    }

    // Recovering from an off-ladder scale by gesture must work: pick a real
    // rung and the guard entry disappears.
    await page.getByTestId("drawing-scale-select").selectOption(drafted);
    await expect(page.getByTestId("title-block-scale")).toHaveText(drafted, {
      timeout: 60_000,
    });
    const recovered = await scaleCellReading(page);
    expect(recovered.shownText).toBe(drafted);
    expect(recovered.disabledTexts).toEqual([]);
  });

  test("the pending-write window discards nothing and never strands the control disabled", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlock(page, account.token, "QA pending block");
    const drawingId = await seedLaidOutDrawing(
      page,
      partId,
      "QA pending drawing",
    );
    const drafted = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );
    const first = nextSmaller(drafted);
    const second = nextSmaller(first);
    const picker = page.getByTestId("drawing-scale-select");

    // Count the PATCHes the two gestures actually produce, so a swallowed
    // gesture is visible as a request that was never made rather than inferred.
    const patched: string[] = [];
    page.on("request", (request) => {
      if (
        request.method() === "PATCH" &&
        /\/sheets\/[^/]+$/.test(new URL(request.url()).pathname)
      ) {
        patched.push(request.postData() ?? "");
      }
    });

    // Sample what the CELL SHOWS, frame by frame, from the moment of the pick.
    // The control is deliberately non-optimistic, so between the gesture and
    // the server's answer it displays the OLD scale and goes inert — that is a
    // window a user sees, and its LENGTH is the difference between "honest"
    // and "my pick was ignored". Measure it rather than reasoning about it.
    await page.evaluate(() => {
      const select = document.querySelector<HTMLSelectElement>(
        '[data-testid="drawing-scale-select"]',
      )!;
      const samples: { t: number; value: string; disabled: boolean }[] = [];
      const t0 = performance.now();
      const tick = () => {
        samples.push({
          t: performance.now() - t0,
          value: select.value,
          disabled: select.disabled,
        });
        if (performance.now() - t0 < 10_000) requestAnimationFrame(tick);
      };
      select.addEventListener("change", () => requestAnimationFrame(tick), {
        once: true,
      });
      (window as unknown as { __qaSamples: typeof samples }).__qaSamples =
        samples;
    });

    // Two picks as fast as the harness can make them. `selectOption` waits for
    // the control to be enabled, so if the writer disables it mid-flight the
    // second gesture lands after the first settles rather than being lost.
    await picker.selectOption(first);
    await picker.selectOption(second);

    await expect(page.getByTestId("title-block-scale")).toHaveText(second, {
      timeout: 60_000,
    });
    await expect(picker).toHaveValue(second);
    // Not stranded.
    await expect(picker).toBeEnabled();
    // No error banner left behind.
    await expect(page.getByTestId("drawing-action-error")).toHaveCount(0);

    const stored = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );
    expect(stored, "the LAST gesture is what the sheet is drawn at").toBe(
      second,
    );

    console.log(
      `[QA] two rapid picks -> ${patched.length} sheet PATCH(es); stored ${stored}`,
    );
    expect(patched.length, "both gestures must reach the server").toBe(2);

    // How long the first pick spent showing the value the user did NOT pick,
    // and how long the control was inert. Reported, not gated — the number is
    // the finding, and a machine-speed threshold would be a flake.
    const window_ = await page.evaluate(() => {
      const samples = (
        window as unknown as {
          __qaSamples: { t: number; value: string; disabled: boolean }[];
        }
      ).__qaSamples;
      const disabled = samples.filter((s) => s.disabled);
      const start = samples[0]?.value ?? "";
      const moved = samples.find((s) => s.value !== start);
      return {
        frames: samples.length,
        disabledMs:
          disabled.length === 0
            ? 0
            : disabled[disabled.length - 1]!.t - disabled[0]!.t,
        staleMs: moved === undefined ? -1 : moved.t,
        firstValue: start,
        lastValue: samples[samples.length - 1]?.value ?? "<none>",
      };
    });

    console.log(
      `[QA] pending window: inert ${window_.disabledMs.toFixed(0)} ms across ${window_.frames} frames; cell showed "${window_.firstValue}" from the pick until ${window_.staleMs.toFixed(0)} ms, ending at "${window_.lastValue}"`,
    );
  });

  test("a FAILED write leaves the honest reading and re-enables the control", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlock(page, account.token, "QA failwrite block");
    const drawingId = await seedLaidOutDrawing(
      page,
      partId,
      "QA failwrite drawing",
    );
    const drafted = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );
    const target = nextSmaller(drafted);
    const picker = page.getByTestId("drawing-scale-select");

    await page.route(/\/api\/v1\/drawings\/[^/]+\/sheets\/[^/]+$/, (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "boom", message: "The sheet could not be updated." },
        }),
      });
    });

    await picker.selectOption(target);

    // The cell must fall back to what the sheet is ACTUALLY drawn at.
    await expect(picker).toHaveValue(drafted, { timeout: 30_000 });
    await expect(picker).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByTestId("title-block-scale")).toHaveText(drafted);
    const stored = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );
    expect(stored).toBe(drafted);

    // And the failure is SAID, not swallowed — a silent no-op is the dead end.
    const errorText = await page
      .locator("[role='alert'], [data-testid*='error']")
      .allInnerTexts();

    console.log(`[QA] failed-write surfaces: ${JSON.stringify(errorText)}`);
    expect(
      errorText.join(" ").length,
      "a failed re-scale must say so somewhere on screen",
    ).toBeGreaterThan(0);

    // The control still works once the failure clears.
    await page.unroute(/\/api\/v1\/drawings\/[^/]+\/sheets\/[^/]+$/);
    await picker.selectOption(target);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
      timeout: 60_000,
    });
  });

  test("round-trip: after a reload the sheet, the title block and the cell all agree with what was persisted", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlock(page, account.token, "QA roundtrip block");
    const drawingId = await seedLaidOutDrawing(
      page,
      partId,
      "QA roundtrip drawing",
    );
    const drafted = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );
    const target = nextSmaller(drafted);

    await page.getByTestId("drawing-scale-select").selectOption(target);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
      timeout: 60_000,
    });
    const edgesLive = await edgeLengthsMm(page);

    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByTestId("drawing-scale-select")).toHaveValue(target);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target);
    const edgesReloaded = await edgeLengthsMm(page);
    for (const p of PROJECTIONS) {
      expect(
        edgesReloaded[p]!,
        `${p} must redraw identically after a reload`,
      ).toBeCloseTo(edgesLive[p]!, 5);
    }
    expect(
      new Set((await readTree(page, account.token, drawingId)).scales),
    ).toEqual(new Set([target]));
  });

  test("keyboard: the cell is a tab stop with a visible focus state, an accessible name, and is operable without a mouse", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlock(page, account.token, "QA keyboard block");
    const drawingId = await seedLaidOutDrawing(
      page,
      partId,
      "QA keyboard drawing",
    );
    const drafted = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );
    const picker = page.getByTestId("drawing-scale-select");

    // Accessible name, whatever the visible caption is doing.
    const name = await picker.evaluate((el) => {
      const select = el as HTMLSelectElement;
      const labelled = select.labels?.[0]?.textContent?.trim();
      return (
        select.getAttribute("aria-label") ?? labelled ?? "<no accessible name>"
      );
    });

    console.log(`[QA] accessible name: "${name}"`);
    expect(name.toLowerCase()).toContain("scale");

    // Reachable by TAB from the page, not just focusable programmatically.
    await page.locator("body").click({ position: { x: 4, y: 4 } });
    let reached = false;
    for (let i = 0; i < 80; i += 1) {
      await page.keyboard.press("Tab");
      if (
        await page.evaluate(
          () =>
            document.activeElement?.getAttribute("data-testid") ===
            "drawing-scale-select",
        )
      ) {
        reached = true;

        console.log(`[QA] Scale reached at tab stop ${i + 1}`);
        break;
      }
    }
    expect(reached, "the Scale cell must be reachable by Tab").toBe(true);

    // A VISIBLE focus state — measured on the cell that owns the ring, not
    // asserted from the class name.
    const focusRing = await picker.evaluate((el) => {
      const cell = el.parentElement!;
      const s = getComputedStyle(cell);
      return {
        outlineStyle: s.outlineStyle,
        outlineWidth: s.outlineWidth,
        outlineColor: s.outlineColor,
      };
    });

    console.log(`[QA] focus ring: ${JSON.stringify(focusRing)}`);
    expect(focusRing.outlineStyle).not.toBe("none");
    expect(parseFloat(focusRing.outlineWidth)).toBeGreaterThanOrEqual(1);

    // Operable from the keyboard alone.
    //
    // NEGATIVE CONTROL FIRST. Headless Chromium's `<select>` popup is a native
    // widget the browser does not build, so an ArrowDown that moves nothing
    // may be the HARNESS and not the control — and reporting that as an a11y
    // defect would be exactly the "assertion that cannot observe its subject"
    // trap in reverse. A vanilla `<select>` injected into the same page,
    // driven by the same keystroke, says which it is.
    const baseline = await page.evaluate(async () => {
      const probe = document.createElement("select");
      for (const v of ["a", "b", "c"]) {
        const option = document.createElement("option");
        option.value = v;
        option.textContent = v;
        probe.append(option);
      }
      probe.id = "qa-keyboard-baseline";
      document.body.append(probe);
      probe.focus();
      return probe.value;
    });
    await page.keyboard.press("ArrowDown");
    const baselineAfter = await page.evaluate(() => {
      const probe = document.querySelector<HTMLSelectElement>(
        "#qa-keyboard-baseline",
      )!;
      const value = probe.value;
      probe.remove();
      return value;
    });
    const arrowWorksHere = baselineAfter !== baseline;

    console.log(
      `[QA] vanilla <select> ArrowDown: ${baseline} -> ${baselineAfter} (harness can drive a native select: ${arrowWorksHere})`,
    );

    // Watch what the keystroke actually CAUSES, not what the cell reads one
    // tick later: the cell is a controlled React value that deliberately does
    // not hold the pick optimistically, so an immediate re-read shows the OLD
    // value whether the gesture landed or was ignored. The request is the
    // discriminator.
    const patched: string[] = [];
    page.on("request", (request) => {
      if (
        request.method() === "PATCH" &&
        /\/sheets\/[^/]+$/.test(new URL(request.url()).pathname)
      ) {
        patched.push(request.postData() ?? "");
      }
    });

    await picker.focus();
    const before = await picker.inputValue();
    await page.keyboard.press("ArrowDown");
    const immediately = await picker.inputValue();
    // Give the write the same window the mouse path gets before judging it.
    await page
      .getByTestId("title-block-scale")
      .filter({ hasNotText: before })
      .waitFor({ timeout: 15_000 })
      .catch(() => undefined);
    const after = await picker.inputValue();
    const stored = soleScale(
      (await readTree(page, account.token, drawingId)).scales,
    );

    console.log(
      `[QA] Scale ArrowDown: ${before} -> (immediately) ${immediately} -> (settled) ${after}; stored ${stored}; sheet PATCHes fired: ${patched.length}`,
    );

    if (arrowWorksHere) {
      // The harness CAN move a native select, so a Scale cell that does not
      // move is this control's defect.
      expect(after, "ArrowDown must move the selection").not.toBe(before);
      await expect(page.getByTestId("title-block-scale")).toHaveText(after, {
        timeout: 60_000,
      });
      expect(
        soleScale((await readTree(page, account.token, drawingId)).scales),
      ).toBe(after);
      expect(after).not.toBe(drafted);
    } else {
      // The harness cannot. Fall back to the property that IS observable here
      // and is what keyboard operability rests on: the control is a real
      // `<select>` with a live `change` handler, so the browser's own keyboard
      // selection reaches the same code path a mouse pick does. Driven through
      // the platform's own selection API + a trusted-shaped `change`, not by
      // calling the React prop.
      const target = nextSmaller(drafted);
      await picker.selectOption(target);
      await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
        timeout: 60_000,
      });
      expect(
        soleScale((await readTree(page, account.token, drawingId)).scales),
      ).toBe(target);
      // And the control keeps focus through the write, so a keyboard user is
      // not dumped back to the top of the tab order by their own edit.
      const keptFocus = await page.evaluate(
        () =>
          document.activeElement?.getAttribute("data-testid") ===
          "drawing-scale-select",
      );

      console.log(`[QA] focus retained across the write: ${keptFocus}`);
      expect(keptFocus, "focus must survive the re-scale write").toBe(true);
    }
  });
});

test.describe("QA SHEET-RESCALE-2 — touch", () => {
  test("the Scale cell is reachable and operable on a touch device", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      hasTouch: true,
      isMobile: false,
      viewport: { width: 1280, height: 800 },
    });
    const page = await context.newPage();
    try {
      const account = await seedSession(page);
      const partId = await createBlock(page, account.token, "QA touch block");
      const drawingId = await seedLaidOutDrawing(
        page,
        partId,
        "QA touch drawing",
      );
      const drafted = soleScale(
        (await readTree(page, account.token, drawingId)).scales,
      );
      const target = nextSmaller(drafted);
      const picker = page.getByTestId("drawing-scale-select");

      // The touch target the finger has to find. 24 px is this product's own
      // dense floor (`min-h-target-dense`).
      const box = await picker.boundingBox();
      if (box === null) throw new Error("the Scale cell has no box on touch");

      console.log(
        `[QA touch] cell ${box.width.toFixed(1)}x${box.height.toFixed(1)} px at 1280x800`,
      );
      expect(box.height).toBeGreaterThanOrEqual(24);

      // A real tap must land on the control, not on chrome above it.
      await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
      const tapped = await page.evaluate(
        () =>
          document.activeElement?.getAttribute("data-testid") ===
          "drawing-scale-select",
      );

      console.log(`[QA touch] tap focused the select: ${tapped}`);
      expect(tapped, "a tap at the cell's centre must reach the select").toBe(
        true,
      );

      await picker.selectOption(target);
      await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
        timeout: 60_000,
      });
      expect(
        soleScale((await readTree(page, account.token, drawingId)).scales),
      ).toBe(target);
    } finally {
      await context.close();
    }
  });
});
