import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { cpus, loadavg } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "../fixtures";
import { createPartViaApi, seedSession } from "../support";

/**
 * THE GAUNTLET'S BROWSER LEG — pick one face on a REAL imported part.
 *
 * `scripts/gauntlet.py` grades the kernel on parts somebody else made; this is
 * the same idea for the viewport. `docs/GEOMETRY-QA.md` (2026-09-15) measured
 * "55-73 s to select one face" on `gearbox-11752` (1 018 B-rep faces, 399 478
 * triangles, 452 of them offered as pickable face marks) and nothing in the
 * sharded suite could ever see it: every fixture there is small enough that a
 * brute-force raycast is free. PERF-REAL-1 re-measured it at the tip before
 * fixing it, and the face-mark seat pass had NOT SETTLED after 158 frames and
 * eleven minutes: every one of its thousands of raycasts read all 399 478
 * triangles, 24 of them a frame.
 *
 * ## What is asserted, and why it is a FRAME COUNT
 *
 * Wall time here is a property of the machine as much as of the code — under
 * this container's software GL one frame of this part costs ~2.5 s, and a
 * shared runner moves every clock. The property the fix changed is how many
 * FRAMES the seat pass needs once the marks exist: it used to need ~190 for one
 * camera pose (thousands of raycasts at 24 a frame) and now needs a handful. So
 * the gate is `MAX_SEAT_RENDERS` r3f renders (`window.__loftRenderTick`, the
 * app's own render probe) from the first mark attaching to
 * `data-face-mark-seats=settled`.
 *
 * The window starts at the first MARK, not at the arm click, on purpose. Before
 * the marks exist the camera is easing into the plane-pick vantage, and that
 * ease is time-based: it takes ~60 frames at 60 fps and ~3 at 0.4 fps. Counted
 * from the click, the same build would pass here and fail on a real GPU. From
 * the first mark, the count is the seat pass's alone, and the ceiling separates
 * the two builds on either kind of machine. Wall times and the load average are
 * PRINTED, as every gauntlet number is, never asserted.
 *
 * ## Not a CI gate
 *
 * Same standing rule as `just gauntlet`: the fixture is third-party CAD this
 * MIT repo may not redistribute, so it is fetched (digest-pinned, from
 * `services/geometry/goldens-gauntlet/fixtures.json`) into the gitignored
 * `.gauntlet-cache/` that `scripts/gauntlet.py` also uses. It has its own
 * config so the sharded suite never collects it. Against a running stack:
 *
 *     GAUNTLET_WEB_ORIGIN=http://127.0.0.1:5173 \
 *       pnpm --filter @loft/web exec playwright test -c e2e/gauntlet/playwright.config.ts
 */

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const MANIFEST = resolve(
  REPO,
  "services/geometry/goldens-gauntlet/fixtures.json",
);
const CACHE = resolve(REPO, ".gauntlet-cache");
const FIXTURE = "gearbox-11752";

/**
 * Renders the seat pass may take, first mark to settled. Measured after
 * PERF-REAL-1: 4-5 here (the pass, then `SEAT_CONFIRM_FRAMES`), and at 60 fps the
 * 6 ms slice floor would make it ~15. Before it: ~190 for one camera pose, and
 * the pass had not settled after 158. The ceiling sits well clear of both.
 */
const MAX_SEAT_RENDERS = 40;

/** How long to wait for the settle before calling it a failure, ms. */
const SETTLE_TIMEOUT_MS = Number(
  process.env["GAUNTLET_SETTLE_TIMEOUT_MS"] ?? 300_000,
);

interface ManifestEntry {
  name: string;
  url: string;
  sha256: string;
}

/** The fixture's bytes, fetched once into the shared cache, digest-verified. */
async function fixtureStep(): Promise<string> {
  const manifest = JSON.parse(readFileSync(MANIFEST, "utf8")) as {
    fixtures: ManifestEntry[];
  };
  const entry = manifest.fixtures.find((f) => f.name === FIXTURE);
  if (entry === undefined) throw new Error(`${FIXTURE} is not in ${MANIFEST}`);
  const target = resolve(CACHE, `${entry.name}.stp`);
  const digest = (bytes: Buffer) =>
    createHash("sha256").update(bytes).digest("hex");
  if (existsSync(target)) {
    const held = readFileSync(target);
    if (digest(held) === entry.sha256) return held.toString("utf8");
  }
  const response = await fetch(entry.url);
  if (!response.ok) {
    throw new Error(`fetching ${entry.url}: HTTP ${response.status}`);
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  // A changed upstream file is a DIFFERENT part — refuse, never measure it.
  expect(digest(bytes), `${entry.name} digest`).toBe(entry.sha256);
  mkdirSync(CACHE, { recursive: true });
  writeFileSync(target, bytes);
  return bytes.toString("utf8");
}

/** The app's own render counter (`RenderProbe` in `Viewport.tsx`). */
async function renders(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      (window as { __loftRenderTick?: number }).__loftRenderTick ?? Number.NaN,
  );
}

test.describe("gauntlet — face pick on a real imported part", () => {
  test(`${FIXTURE}: arm, settle and pick one face`, async ({ page }) => {
    test.setTimeout(SETTLE_TIMEOUT_MS + 600_000);
    const step = await fixtureStep();
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, FIXTURE);
    const headers = { Authorization: `Bearer ${account.token}` };
    const meta = await page.request.get(`/api/v1/parts/${part.id}`, {
      headers,
    });
    const { tree_version: treeVersion } = (await meta.json()) as {
      tree_version: number;
    };
    const created = await page.request.post(
      `/api/v1/parts/${part.id}/features`,
      {
        data: {
          name: FIXTURE,
          feature: {
            type: "import",
            version: 1,
            params: { data: step, format: "step", kind: "inline" },
          },
          expected_tree_version: treeVersion,
        },
        headers,
        timeout: 300_000,
      },
    );
    expect(created.status(), await created.text()).toBe(201);

    const load = loadavg()
      .map((l) => l.toFixed(2))
      .join(" ");
    const ms: Record<string, number> = {};
    let started = Date.now();
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 300_000,
    });
    ms["open -> solved"] = Date.now() - started;
    const cue = page.getByTestId("nav-cue-dismiss");
    if (await cue.isVisible().catch(() => false)) await cue.click();

    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("plane-pick-face")).toBeVisible({
      timeout: 120_000,
    });

    // ARM, and count renders until every offered mark has a seat.
    const viewport = page.getByTestId("viewport");
    const armedAt = await renders(page);
    started = Date.now();
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible({
      timeout: 120_000,
    });
    ms["arm -> prompt"] = Date.now() - started;
    const marks = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(marks.first()).toBeAttached({ timeout: 120_000 });
    ms["arm -> first mark"] = Date.now() - started;
    const markedAt = await renders(page);
    const settled = await expect(viewport)
      .toHaveAttribute("data-face-mark-seats", "settled", {
        timeout: SETTLE_TIMEOUT_MS,
      })
      .then(() => true)
      .catch(() => false);
    ms["arm -> seats settled"] = Date.now() - started;
    const settledAt = await renders(page);
    const frames = settledAt - armedAt;
    const seatRenders = settledAt - markedAt;

    const census = await page.evaluate(() => {
      const all = [
        ...document.querySelectorAll<HTMLElement>(
          '[data-testid^="plane-pick-face-"]',
        ),
      ];
      let buried = 0;
      let hittable = 0;
      let target: { id: string; x: number; y: number } | null = null;
      for (const mark of all) {
        if (mark.dataset["buried"] === "true") buried += 1;
        const box = mark.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        const x = box.left + box.width / 2;
        const y = box.top + box.height / 2;
        const hit = document.elementFromPoint(x, y);
        if (hit === mark || mark.contains(hit)) {
          hittable += 1;
          target ??= { id: mark.dataset["testid"] ?? "?", x, y };
        }
      }
      return { total: all.length, buried, hittable, target };
    });

    // PICK one face with a real pointer, and time it to the seated sketch.
    let picked = false;
    if (census.target !== null) {
      started = Date.now();
      await page.mouse.click(census.target.x, census.target.y);
      await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
        timeout: 300_000,
      });
      ms["click -> sketch on face"] = Date.now() - started;
      picked = true;
    }

    // The gauntlet's honesty rule: every number travels with its load.
    const report =
      `[gauntlet face-pick] ${FIXTURE} | ${cpus().length} cores, loadavg ` +
      `${load} | renders first mark->settled ${seatRenders} (ceiling ` +
      `${MAX_SEAT_RENDERS}), arm->settled ${frames} | marks ` +
      `${census.total}, buried ` +
      `${census.buried}, hittable ${census.hittable} | ` +
      Object.entries(ms)
        .map(([k, v]) => `${k} ${(v / 1000).toFixed(1)} s`)
        .join(" | ");
    console.log(report);

    expect(
      settled,
      `the armed pick never settled (${frames} renders in ${ms["arm -> seats settled"]} ms)`,
    ).toBe(true);
    expect(
      seatRenders,
      `renders from the first face mark to data-face-mark-seats=settled`,
    ).toBeLessThanOrEqual(MAX_SEAT_RENDERS);
    // NON-VACUITY: the gearbox offers hundreds of planar faces, and a pick that
    // settled by offering nothing, or nothing a pointer can reach, proves
    // nothing about picking.
    expect(census.total).toBeGreaterThan(100);
    expect(census.hittable).toBeGreaterThan(0);
    expect(picked).toBe(true);
  });
});
