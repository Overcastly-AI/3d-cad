import { expect, test, type Page } from "@playwright/test";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Sketch fillet/chamfer (BACKLOG #5, closes #5): the corner clean-up tools.
 * Fillet rounds and Chamfer bevels the corner two lines share, wired to the
 * real stateless geometry endpoints (`/geometry/sketch/{fillet,chamfer}`)
 * through the gateway. Real stack: gateway + documents + geometry, no mocks.
 *
 * Unlike the additive offset/mirror, a corner REWRITES the set (like
 * trim/extend): the two source lines are trimmed in place, ids preserved, plus
 * an appended bridge (a tangent arc for fillet, a straight line for chamfer)
 * with a fresh id. The client SWAPS the whole rewritten set in. v1 is line-line
 * corners only.
 */

interface Pt {
  x: number;
  y: number;
}
interface SketchEntity {
  id: string;
  kind: string;
  start?: Pt;
  end?: Pt;
  center?: Pt;
}

const dist = (a: Pt, b: Pt): number => Math.hypot(a.x - b.x, a.y - b.y);

/** The endpoint of `line` nearest to `corner` — the one a corner op trims. */
function nearEndpoint(line: SketchEntity, corner: Pt): Pt {
  const s = line.start as Pt;
  const e = line.end as Pt;
  return dist(s, corner) <= dist(e, corner) ? s : e;
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ" = "XY") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm → screen-px mapper (same technique as the constraints / mirror /
 * offset specs): read the DRO at two points with snap off so later clicks land
 * on exact millimetre coordinates.
 */
async function calibratePlane(
  page: Page,
  s1: Pt,
  s2: Pt,
): Promise<(pt: Pt) => Pt> {
  await page.keyboard.press("g"); // snap off for raw readings
  {
    let last: number | null = null;
    await expect
      .poll(
        async () => {
          await page.mouse.move(s1.x + 2, s1.y);
          await page.mouse.move(s1.x, s1.y);
          const value = Number.parseFloat(
            await page.getByTestId("dro-x").innerText(),
          );
          const stable =
            last !== null && Number.isFinite(value) && value === last;
          last = value;
          return stable;
        },
        { timeout: 15_000 },
      )
      .toBe(true);
  }
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<Pt> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (distinctFromX === undefined ||
            Math.abs(value - distinctFromX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  await page.keyboard.press("g"); // snap back on for drawing
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(page: Page, at: (pt: Pt) => Pt, pt: Pt) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/** The perpendicular L both corner tests share: e1 along +x, e2 along +y. */
async function drawCornerL(page: Page, at: (pt: Pt) => Pt) {
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 0 }); // e1: (0,0)→(40,0)
  await page.keyboard.press("Escape");
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: 0, y: 0 }); // snaps to the shared vertex
  await clickPlane(page, at, { x: 0, y: 30 }); // e2: (0,0)→(0,30)
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
}

test.describe("sketch fillet / chamfer", () => {
  test("fillet r2 rounds the corner: a tangent arc appears, both lines trim, sketch solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Fillet bracket");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );
    await drawCornerL(page, at);

    // Fillet tool (U) — a two-line pick, then an inline radius editor.
    await page.keyboard.press("u");
    await expect(page.getByTestId("tool-fillet")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("corner-prompt")).toHaveAttribute(
      "data-phase",
      "legs",
    );
    await clickPlane(page, at, { x: 20, y: 0 }); // pick e1
    await expect(page.getByTestId("corner-count")).toContainText("1 of 2");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-fillet-before.png`,
    });
    await clickPlane(page, at, { x: 0, y: 15 }); // pick e2 → editor opens
    await expect(page.getByTestId("corner-prompt")).toHaveAttribute(
      "data-phase",
      "value",
    );
    await expect(page.getByTestId("corner-editor")).toBeVisible();

    // Enter the radius and apply → one POST to the geometry service.
    await page.getByTestId("corner-input").fill("2");
    const filletResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/fillet") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("corner-apply").click();
    const fillet = await filletResponse;
    expect(fillet.status()).toBe(200);

    const req = fillet.request().postDataJSON() as {
      a: string;
      b: string;
      radius: number;
    };
    const body = (await fillet.json()) as { entities: SketchEntity[] };
    // REWRITE, not append: 2 source lines (ids preserved, trimmed) + 1 arc.
    expect(body.entities).toHaveLength(3);
    const arcs = body.entities.filter((e) => e.kind === "arc");
    expect(arcs).toHaveLength(1);
    const arc = arcs[0] as SketchEntity;
    // The tangent arc carries the radius we asked for.
    expect(dist(arc.center as Pt, arc.start as Pt)).toBeCloseTo(2, 1);

    // Both legs survive by id and are trimmed back to their tangent points —
    // the near-corner endpoint moved from the shared vertex (0,0) to r=2 away.
    const corner: Pt = { x: 0, y: 0 };
    for (const id of [req.a, req.b]) {
      const leg = body.entities.find((e) => e.id === id) as SketchEntity;
      expect(leg.kind).toBe("line");
      expect(dist(nearEndpoint(leg, corner), corner)).toBeCloseTo(2, 1);
    }

    // Swapped in place: still 3 entities, honest note.
    await expect(page.getByTestId("sketch-edit-note")).toContainText(
      "Filleted",
    );
    await expect(page.getByTestId("sketch-save")).toContainText("3 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-fillet-after.png`,
    });

    // Save → the sketch persists and STILL SOLVES.
    const evalPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/evaluate`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    const evalResponse = await evalPromise;
    expect(evalResponse.status()).toBe(200);
    const evalBody = (await evalResponse.json()) as {
      features: Array<{ status: string; data: { kind: string } | null }>;
    };
    expect(evalBody.features[0]?.status).toBe("ok");
    expect(evalBody.features[0]?.data?.kind).toBe("solved_sketch");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
  });

  test("chamfer d3 bevels the corner: a straight bridge appears, both lines trim, sketch solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Chamfer bracket");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );
    await drawCornerL(page, at);

    // Chamfer tool (B — Bevel).
    await page.keyboard.press("b");
    await expect(page.getByTestId("tool-chamfer")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickPlane(page, at, { x: 20, y: 0 }); // pick e1
    await clickPlane(page, at, { x: 0, y: 15 }); // pick e2 → editor opens
    await expect(page.getByTestId("corner-editor")).toBeVisible();

    await page.getByTestId("corner-input").fill("3");
    const chamferResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/chamfer") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("corner-apply").click();
    const chamfer = await chamferResponse;
    expect(chamfer.status()).toBe(200);

    const req = chamfer.request().postDataJSON() as { a: string; b: string };
    const body = (await chamfer.json()) as { entities: SketchEntity[] };
    // REWRITE: 2 trimmed source lines + 1 straight bridge — all lines, no arc.
    expect(body.entities).toHaveLength(3);
    expect(body.entities.every((e) => e.kind === "line")).toBe(true);
    // Exactly one line is the fresh bridge (id neither source leg).
    const bridges = body.entities.filter(
      (e) => e.id !== req.a && e.id !== req.b,
    );
    expect(bridges).toHaveLength(1);

    // Both legs survive by id, trimmed back the setback distance (3 mm).
    const corner: Pt = { x: 0, y: 0 };
    for (const id of [req.a, req.b]) {
      const leg = body.entities.find((e) => e.id === id) as SketchEntity;
      expect(dist(nearEndpoint(leg, corner), corner)).toBeCloseTo(3, 1);
    }

    await expect(page.getByTestId("sketch-edit-note")).toContainText(
      "Chamfered",
    );
    await expect(page.getByTestId("sketch-save")).toContainText("3 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-chamfer-after.png`,
    });

    const evalPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/evaluate`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    const evalResponse = await evalPromise;
    expect(evalResponse.status()).toBe(200);
    const evalBody = (await evalResponse.json()) as {
      features: Array<{ status: string; data: { kind: string } | null }>;
    };
    expect(evalBody.features[0]?.status).toBe("ok");
    expect(evalBody.features[0]?.data?.kind).toBe("solved_sketch");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
  });

  test("a radius larger than the legs reads as a clean message, not a crash", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Fillet oversize");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );
    await drawCornerL(page, at);

    await page.keyboard.press("u");
    await clickPlane(page, at, { x: 20, y: 0 });
    await clickPlane(page, at, { x: 0, y: 15 });
    await expect(page.getByTestId("corner-editor")).toBeVisible();

    // 500 mm dwarfs the 30 mm leg → the corner cannot be rounded.
    await page.getByTestId("corner-input").fill("500");
    const filletResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/fillet") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("corner-apply").click();
    const fillet = await filletResponse;
    expect(fillet.status()).toBe(422);

    // The rejection surfaces as a legible hint — no rewrite, no crash. The
    // picks survive (the editor stays open) so a smaller radius can be retyped.
    const hint = page.getByTestId("constraint-hint");
    await expect(hint).toBeVisible();
    await expect(hint).not.toBeEmpty();
    await expect(page.getByTestId("corner-editor")).toBeVisible();
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-fillet-too-large.png`,
    });
  });
});

test.describe("sketch fillet — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("fillet tool stays reachable; founder screenshot", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Fillet laptop");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 520, y: 320 },
      { x: 760, y: 540 },
    );
    await drawCornerL(page, at);

    await expect(page.getByTestId("tool-fillet")).toBeVisible();
    await page.keyboard.press("u");
    await clickPlane(page, at, { x: 20, y: 0 });
    await clickPlane(page, at, { x: 0, y: 15 });
    await expect(page.getByTestId("corner-editor")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-fillet-laptop.png`,
    });
  });
});
