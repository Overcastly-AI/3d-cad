import { expect, test, type Page } from "./fixtures";

import { enterSketch } from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

/**
 * TYPED SKETCH INPUT, POINT AFTER POINT (REFERENCE-RUN 2026-09-30, found
 * modelling the helical gear).
 *
 * TYPED-COORD-HIJACK: with the Line tool live, `10 Tab 0 Enter`,
 * `10 Tab 20 Enter` draws the line (10,0)-(10,20) exactly (G2 typed
 * placement). The line tool does not chain, so the engineer types the next
 * line's first point, `-10 Tab 20 Enter`. The finished line had armed its
 * draw-time length cell (FB-16), and a digit focused that cell: the keystrokes
 * meant for the next point became the previous line's LENGTH. Measured on
 * 9767a90: the stored line was (10,0)-(10,1020) and the next line was never
 * drawn.
 *
 * TYPED-POINT-RACE: spline fit points typed at about 300 ms per point were
 * merged or dropped. Eight typed involute points stored a 2-point straight
 * spline plus a separate 8-point one.
 *
 * One rule covers both, and it is the one Fusion's and SolidWorks' typed
 * sketch input keep: after a commit, the next keystrokes go to the NEXT
 * entity's input. A size strip on a shape whose points were typed does not
 * take typing (the size is already exact), and a typed point is placed in the
 * keydown that presses its Enter, not when React gets round to drawing cells.
 *
 * The burst tests queue every keystroke on one CDP session with NO await
 * between them (see draw-dimension-arming.spec.ts for why that, and not
 * `page.keyboard`, is the fastest a user can possibly be).
 */

interface PersistedEntity {
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
  center?: { x: number; y: number };
  points?: Array<{ x: number; y: number }>;
}

/** One key at a time, as a hand types a number it already knows. */
async function typePoint(page: Page, x: string, y: string): Promise<void> {
  for (const key of x) await page.keyboard.press(key);
  await page.keyboard.press("Tab");
  for (const key of y) await page.keyboard.press(key);
  await page.keyboard.press("Enter");
}

interface Cdp {
  send: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  detach: () => Promise<void>;
}

const CODES: Readonly<Record<string, { code: string; vk: number }>> = {
  "-": { code: "Minus", vk: 189 },
  ".": { code: "Period", vk: 190 },
  Tab: { code: "Tab", vk: 9 },
  Enter: { code: "Enter", vk: 13 },
};

/** Queue one key's keydown/keyup on an open CDP session, unawaited. */
function queueKey(cdp: Cdp, key: string): void {
  const known = CODES[key];
  const code = known?.code ?? `Digit${key}`;
  const vk = known?.vk ?? key.charCodeAt(0);
  const text = key.length === 1 ? key : key === "Enter" ? "\r" : undefined;
  for (const type of ["keyDown", "keyUp"] as const) {
    void cdp.send("Input.dispatchKeyEvent", {
      type,
      ...(type === "keyDown" && text !== undefined ? { text } : {}),
      key,
      code,
      windowsVirtualKeyCode: vk,
      nativeVirtualKeyCode: vk,
    });
  }
}

/** The keys that type `points`, each as `x Tab y Enter`. */
function pointKeys(points: ReadonlyArray<readonly [string, string]>): string[] {
  return points.flatMap(([x, y]) => [...x, "Tab", ...y, "Enter"]);
}

/**
 * Every key in one burst: nothing awaited between two keystrokes. With
 * `gapMs`, a steady hand instead: that long between keys (the reference run
 * typed about 300 ms per point, 4 keys, so about 75 ms a key).
 */
async function burst(
  page: Page,
  keys: readonly string[],
  gapMs = 0,
): Promise<void> {
  const cdp = (await page.context().newCDPSession(page)) as unknown as Cdp;
  for (const key of keys) {
    queueKey(cdp, key);
    if (gapMs > 0) await page.waitForTimeout(gapMs);
  }
  await cdp.send("Runtime.evaluate", { expression: "1" }); // flush the queue
  await cdp.detach();
}

async function openSketch(page: Page, name: string) {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  return { token, partId: part.id };
}

async function saveAndRead(
  page: Page,
  token: string,
  partId: string,
): Promise<PersistedEntity[]> {
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{ feature: { params: { entities: PersistedEntity[] } } }>;
  };
  return body.features[0]?.feature.params.entities ?? [];
}

const asPoint = ([x, y]: readonly [string, string]) => ({
  x: Number(x),
  y: Number(y),
});

test.use({ viewport: { width: 1280, height: 800 } });

test("typed coordinates for the next line never resize the line before", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token, partId } = await openSketch(page, "Typed line sequence");
  await page.keyboard.press("l");
  await page.mouse.move(1000, 250);

  // Two lines of a keyway-style profile, every point typed.
  await typePoint(page, "10", "0");
  await expect(page.getByTestId("point-entry")).toHaveCount(0);
  await typePoint(page, "10", "20");
  await expect(page.getByTestId("point-entry")).toHaveCount(0);
  // What the engineer sees before typing on: the line is drawn and its length
  // cell has armed. Waiting for it makes the hijack deterministic.
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  await typePoint(page, "-10", "20");
  await typePoint(page, "-10", "0");

  const entities = await saveAndRead(page, token, partId);
  const lines = entities.filter((e) => e.kind === "line");

  // The first line is exactly what was typed, and the second line exists.
  expect(lines[0]?.start, JSON.stringify(lines)).toEqual({ x: 10, y: 0 });
  expect(lines[0]?.end, JSON.stringify(lines)).toEqual({ x: 10, y: 20 });
  expect(lines, JSON.stringify(lines)).toHaveLength(2);
  expect(lines[1]?.start).toEqual({ x: -10, y: 20 });
  expect(lines[1]?.end).toEqual({ x: -10, y: 0 });
});

for (const gapMs of [0, 20, 75]) {
  test(`eight spline fit points typed ${gapMs} ms apart all land, in order`, async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { token, partId } = await openSketch(page, "Typed spline burst");
    await page.keyboard.press("s");
    await page.mouse.move(1000, 250);

    // An involute-like flank: decimals, a negative, eight points.
    const fit = [
      ["20", "-1.5"],
      ["20.25", "0.5"],
      ["20.75", "2.25"],
      ["21.5", "3.75"],
      ["22.5", "5"],
      ["23.75", "6"],
      ["25.25", "6.75"],
      ["27", "7.25"],
    ] as const;
    // The last Enter, with no cells open, finishes the spline.
    await burst(page, [...pointKeys(fit), "Enter"], gapMs);
    await expect(page.getByTestId("point-entry")).toHaveCount(0);

    const entities = await saveAndRead(page, token, partId);
    const splines = entities.filter((e) => e.kind === "spline");
    expect(splines, JSON.stringify(entities)).toHaveLength(1);
    expect(splines[0]?.points).toEqual(fit.map(asPoint));
  });
}

test("lines and an arc typed with no waits land exactly as typed", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token, partId } = await openSketch(page, "Typed burst");
  await page.keyboard.press("l");
  await page.mouse.move(1000, 250);
  await burst(
    page,
    pointKeys([
      ["10", "0"],
      ["10", "20"],
      ["-10", "20"],
      ["-10", "0"],
    ]),
  );
  await expect(page.getByTestId("point-entry")).toHaveCount(0);

  // Arc: centre, start, end (the end lies on the start's radius).
  await page.keyboard.press("a");
  await burst(
    page,
    pointKeys([
      ["30", "5"],
      ["40", "5"],
      ["30", "15"],
    ]),
  );
  await expect(page.getByTestId("point-entry")).toHaveCount(0);

  const entities = await saveAndRead(page, token, partId);
  const lines = entities.filter((e) => e.kind === "line");
  expect(lines, JSON.stringify(entities)).toHaveLength(2);
  expect(lines[0]).toMatchObject({
    start: { x: 10, y: 0 },
    end: { x: 10, y: 20 },
  });
  expect(lines[1]).toMatchObject({
    start: { x: -10, y: 20 },
    end: { x: -10, y: 0 },
  });
  const arcs = entities.filter((e) => e.kind === "arc");
  expect(arcs, JSON.stringify(entities)).toHaveLength(1);
  expect(arcs[0]?.center).toEqual({ x: 30, y: 5 });
  expect(arcs[0]?.start).toEqual({ x: 40, y: 5 });
  expect(arcs[0]?.end?.x).toBeCloseTo(30, 9);
  expect(arcs[0]?.end?.y).toBeCloseTo(15, 9);
});
