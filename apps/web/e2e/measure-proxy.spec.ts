/**
 * MEASURE-PROXY-1 — A CLICK AT THE CENTRE OF A MEASURE MARK IS NOT SWALLOWED BY
 * A NEIGHBOUR'S EMPTY BOX.
 *
 * ## What T-14 reported, and what it actually was
 *
 * `docs/AUDIT-PRODUCT.md` T-14: "Measure sprays 65 markers over a 15-face part
 * and one of my clicks hit nothing… a click at the exact centre of
 * `measure-edge-4`'s bounding box registered NO SELECTION AT ALL because a
 * neighbouring marker sat on top of it — Playwright's own actionability check
 * refused the same element as 'not stable'."
 *
 * The ticket inferred coincident FACES and prescribed MATE-1's face depth-stack.
 * Measured on the audit's own part, that is not the mechanism — Measure offers
 * no faces at all, only edges and vertices. What sits on top is drei's own
 * wrapper: `Html` gives every mark an absolutely-positioned div that inherits
 * `pointer-events: auto`, carries no handler, and takes the mark's 24x24 BOX —
 * while `PickNode` is `rounded-full`, so its hit region is the inscribed
 * Ø24 circle. The ~21% of the box outside that circle was a pointer target
 * that did nothing, and a NEIGHBOUR's corner lands on other marks' centres.
 *
 * Reproduced here on a rebuild of T-14's plate, which yields its counts
 * verbatim (26 vertex + 39 edge = 65 proxies over 15 faces). Measured through
 * this spec, before and after, same camera: **5 marks land on a bare
 * positioning box -> 0**, and a real `page.mouse.click` at those points went
 * from doing nothing to reaching the geometry underneath. The residue is
 * legitimate and named in the log line: four marks whose EDGE is buried
 * (PICKMARK-OCCLUDE-1 — they are deliberately not targets) and two genuine
 * overlaps, `measure-edge-0` under `measure-vertex-4` (12.1 px apart, resolved
 * by the documented vertex-over-edge precedence) and `measure-edge-13` under
 * `measure-edge-31`, where the BAND agrees with the DOM about which is in
 * front. Neither is a proxy contradicting the hit-test.
 *
 * ## Why the assertion is about WRAPPERS and not about a count
 *
 * Which marks overlap is a function of the camera; that a wrapper with no
 * behaviour can be the topmost thing under a control is a function of the code.
 * Asserting the second is what makes this a regression test rather than a
 * screenshot of one pose.
 */
import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/** T-14's own part: 150 x 80 x 8 plate, R10 corners, 4 x Ø6.6, central Ø25. */
async function seedMotorMountPlate(
  page: Page,
  token: string,
  partId: string,
): Promise<void> {
  const outline = await createFeature(page, token, partId, {
    name: "Outline",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "b",
            kind: "line",
            start: { x: -65, y: -40 },
            end: { x: 65, y: -40 },
          },
          {
            id: "abr",
            kind: "arc",
            center: { x: 65, y: -30 },
            start: { x: 65, y: -40 },
            end: { x: 75, y: -30 },
          },
          {
            id: "r",
            kind: "line",
            start: { x: 75, y: -30 },
            end: { x: 75, y: 30 },
          },
          {
            id: "atr",
            kind: "arc",
            center: { x: 65, y: 30 },
            start: { x: 75, y: 30 },
            end: { x: 65, y: 40 },
          },
          {
            id: "t",
            kind: "line",
            start: { x: 65, y: 40 },
            end: { x: -65, y: 40 },
          },
          {
            id: "atl",
            kind: "arc",
            center: { x: -65, y: 30 },
            start: { x: -65, y: 40 },
            end: { x: -75, y: 30 },
          },
          {
            id: "l",
            kind: "line",
            start: { x: -75, y: 30 },
            end: { x: -75, y: -30 },
          },
          {
            id: "abl",
            kind: "arc",
            center: { x: -65, y: -30 },
            start: { x: -75, y: -30 },
            end: { x: -65, y: -40 },
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: 0,
  });
  const solid = await createFeature(page, token, partId, {
    name: "Plate",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: outline.feature.id },
        distance_mm: 8,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: outline.tree_version,
  });
  const holes = await createFeature(page, token, partId, {
    name: "Holes",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "h1",
            kind: "circle",
            center: { x: -23.5, y: -23.5 },
            radius: 3.3,
          },
          {
            id: "h2",
            kind: "circle",
            center: { x: 23.5, y: -23.5 },
            radius: 3.3,
          },
          {
            id: "h3",
            kind: "circle",
            center: { x: 23.5, y: 23.5 },
            radius: 3.3,
          },
          {
            id: "h4",
            kind: "circle",
            center: { x: -23.5, y: 23.5 },
            radius: 3.3,
          },
          { id: "bore", kind: "circle", center: { x: 0, y: 0 }, radius: 12.5 },
        ],
        constraints: [],
      },
    },
    expected_tree_version: solid.tree_version,
  });
  await createFeature(page, token, partId, {
    name: "Bores",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: holes.feature.id },
        distance_mm: 8,
        operation: "cut",
        direction: "normal",
      },
    },
    expected_tree_version: holes.tree_version,
  });
}

interface MarkProbe {
  id: string;
  buried: boolean;
  cx: number;
  cy: number;
  /** `self` | `mark:<id>` | `canvas` | `wrapper:<owner>` | `other` */
  topmost: string;
}

/**
 * For every measure proxy: what does a pointer at its OWN CENTRE actually
 * reach? `elementFromPoint` and not a `toBeVisible()` — a box property cannot
 * observe "something is on top of it", which is the whole failure mode here.
 */
async function probeMarks(page: Page): Promise<MarkProbe[]> {
  return page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="viewport"] canvas');
    const marks = [
      ...document.querySelectorAll(
        '[data-testid^="measure-edge-"],[data-testid^="measure-vertex-"]',
      ),
    ];
    return marks.map((el) => {
      const id = el.getAttribute("data-testid") ?? "?";
      const r = el.getBoundingClientRect();
      const cx = Math.round((r.left + r.right) / 2);
      const cy = Math.round((r.top + r.bottom) / 2);
      const hit = document.elementFromPoint(cx, cy);
      let topmost = "other";
      if (hit === null) topmost = "none";
      else if (hit === el || el.contains(hit)) topmost = "self";
      else if (hit === canvas || hit.contains(canvas as Node))
        topmost = "canvas";
      else {
        const owner = hit.closest("[data-testid]");
        const ownerId = owner?.getAttribute("data-testid") ?? "";
        const isMarkId = /^measure-(edge|vertex)-\d+$/.test(ownerId);
        if (isMarkId && (hit === owner || owner?.contains(hit) === true)) {
          topmost = `mark:${ownerId}`;
        } else {
          // A div that OWNS a mark but is not part of the control — drei's
          // positioning wrapper. This is the defect: an empty box on top of a
          // neighbour's target.
          const inner = hit.querySelector("[data-testid]");
          const innerId = inner?.getAttribute("data-testid") ?? "?";
          topmost =
            hit.tagName === "DIV" && inner !== null
              ? `wrapper:${innerId}`
              : "other";
        }
      }
      return {
        id,
        buried: el.getAttribute("data-buried") === "true",
        cx,
        cy,
        topmost,
      };
    });
  });
}

async function openPlateWithMeasureArmed(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Motor mount plate");
  await seedMotorMountPlate(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(16);
  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
  await page.getByTestId("measure-tool").click();
  await expect(
    page.locator('[data-testid^="measure-edge-"]').first(),
  ).toBeAttached({ timeout: 20_000 });
  await expect(viewport).toHaveAttribute("data-edge-mark-seats", "settled", {
    timeout: 30_000,
  });
  await waitForFrames(page, 4);
}

test.describe("MEASURE-PROXY-1 — a mark's own centre reaches the mark", () => {
  test("no proxy's centre lands on a neighbour's empty positioning box", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await openPlateWithMeasureArmed(page);

    // THE FIXTURE, ASSERTED — T-14's own counts. If these move the part
    // changed and none of the numbers below are comparable with the report's.
    await expect(page.locator('[data-testid^="measure-vertex-"]')).toHaveCount(
      26,
    );
    await expect(page.locator('[data-testid^="measure-edge-"]')).toHaveCount(
      39,
    );

    const probes = await probeMarks(page);
    expect(probes.length).toBe(65);
    const wrappers = probes.filter((p) => p.topmost.startsWith("wrapper:"));
    const self = probes.filter((p) => p.topmost === "self");
    console.log(
      `    [MEASURE-PROXY] ${self.length}/65 marks answer at their own centre; ` +
        `${wrappers.length} land on a bare positioning box; ` +
        `others: ${probes
          .filter(
            (p) => p.topmost !== "self" && !p.topmost.startsWith("wrapper:"),
          )
          .map((p) => `${p.id}->${p.topmost}${p.buried ? "(buried)" : ""}`)
          .join(",")}`,
    );

    // THE CLAIM. A div with no behaviour must never be the topmost thing under
    // a control — that is what made T-14's click register nothing at all.
    expect(
      wrappers.map((w) => `${w.id}->${w.topmost}`),
      "a mark's centre must never resolve to a neighbour's bare positioning box",
    ).toEqual([]);

    // NON-VACUITY: the probe must actually be finding the marks. Without this,
    // "zero wrappers" is satisfied by a page with no marks on it.
    expect(
      self.length,
      "most marks must still answer at their own centre",
    ).toBeGreaterThan(55);
  });

  test("a real mouse click at a mark's centre selects that mark's entity", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await openPlateWithMeasureArmed(page);
    const prompt = page.getByTestId("measure-prompt");
    await expect(prompt).toContainText("Pick a point or edge");

    // Drive the marks the way a hand does — a real `page.mouse.click` at the
    // control's centre, never `click({ force: true })`, which would skip the
    // actionability check that IS the subject here (T-14's own tell was
    // Playwright refusing the element as "not stable").
    const probes = await probeMarks(page);
    const reachable = probes.filter((p) => p.topmost === "self" && !p.buried);
    expect(reachable.length).toBeGreaterThan(20);

    const vertex = reachable.find((p) => p.id.startsWith("measure-vertex-"));
    const edge = reachable.find((p) => p.id.startsWith("measure-edge-"));
    expect(vertex, "the plate offers a reachable vertex mark").toBeDefined();
    expect(edge, "the plate offers a reachable edge mark").toBeDefined();

    await page.mouse.click((vertex as MarkProbe).cx, (vertex as MarkProbe).cy);
    await expect(prompt).toContainText("Pick the second point or edge");
    await expect(prompt).toContainText("Vertex");

    await page.getByTestId("measure-clear").click();
    await expect(prompt).toContainText("Pick a point or edge");

    await page.mouse.click((edge as MarkProbe).cx, (edge as MarkProbe).cy);
    await expect(prompt).toContainText("Pick the second point or edge");
    await expect(prompt).toContainText("Edge");
  });
});
