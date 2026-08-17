import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Sketch mirror (BACKLOG #4, closes #4): the symmetric-profile tool. Mirror
 * ADDS a reflected copy of each selected entity about an axis line, wired to
 * the real stateless geometry endpoint (`/geometry/sketch/mirror`) through the
 * gateway. Real stack: gateway + documents + geometry, no mocks.
 *
 * The common case this pairs with is a construction centerline: draw the half,
 * mark the axis as construction, mirror the half about it. Like offset, mirror
 * never rewrites the sources — the result carries ONLY the new copies, which
 * the client APPENDS. v1 mirrors geometry only (no auto symmetric constraints).
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
  radius?: number;
}

/** Reflect a point across the infinite line through a→b (x=0 axis → −x). */
function reflect(p: Pt, a: Pt, b: Pt): Pt {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  const projX = a.x + t * dx;
  const projY = a.y + t * dy;
  return { x: 2 * projX - p.x, y: 2 * projY - p.y };
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ" = "XY") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm → screen-px mapper (same technique as constraints/construction
 * specs): read the DRO at two points with snap off so later clicks land on
 * exact millimetre coordinates.
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

test.describe("sketch mirror", () => {
  test("mirror a half about a construction centerline; reflected copies append and the sketch solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror bracket");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );

    // 1) The vertical centerline (0,−20)→(0,20): e1. Mark it construction (N)
    //    so it reads as a reference axis, the symmetric-profile idiom.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -20 });
    await clickPlane(page, at, { x: 0, y: 20 });
    await page.keyboard.press("Escape"); // back to select
    await clickPlane(page, at, { x: 0, y: 0 }); // select the axis at its midpoint
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("n"); // → construction
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );

    // 2) The half to reflect: a line e2 and a circle e3, both to the +x side.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 10 });
    await clickPlane(page, at, { x: 30, y: 10 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 20, y: -10 }); // center
    await clickPlane(page, at, { x: 28, y: -10 }); // rim → r = 8
    await expect(page.getByTestId("sketch-save")).toContainText("3 entities");

    // 3) Mirror tool (I) — a two-phase pick. Phase one: select the two entities.
    await page.keyboard.press("i");
    await expect(page.getByTestId("tool-mirror")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("mirror-prompt")).toHaveAttribute(
      "data-phase",
      "targets",
    );
    await clickPlane(page, at, { x: 20, y: 10 }); // the line e2
    await expect(page.getByTestId("mirror-count")).toContainText("1 entity");
    await clickPlane(page, at, { x: 28, y: -10 }); // the circle e3 (on its rim)
    await expect(page.getByTestId("mirror-count")).toContainText("2 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-mirror-before.png`,
    });

    // Phase two: choose the axis (Choose axis ↵), then hover the centerline —
    // the live reflection ghost shows where the copies will land.
    await page.getByTestId("mirror-advance").click();
    await expect(page.getByTestId("mirror-prompt")).toHaveAttribute(
      "data-phase",
      "axis",
    );
    await page.mouse.move(at({ x: 0, y: 5 }).x, at({ x: 0, y: 5 }).y);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-mirror-ghost.png`,
    });

    // Click the centerline → one POST to the geometry service.
    const mirrorResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/mirror") &&
        r.request().method() === "POST",
    );
    await clickPlane(page, at, { x: 0, y: 5 });
    const mirror = await mirrorResponse;
    expect(mirror.status()).toBe(200);

    const req = mirror.request().postDataJSON() as {
      targets: string[];
      axis: { kind: string; entity: string };
      entities: SketchEntity[];
    };
    const body = (await mirror.json()) as { entities: SketchEntity[] };
    // One reflected copy per target, in order; sources NOT echoed.
    expect(body.entities).toHaveLength(2);
    expect(req.axis.kind).toBe("entity");
    const axis = req.entities.find(
      (e) => e.id === req.axis.entity,
    ) as SketchEntity;
    const a = axis.start as Pt;
    const b = axis.end as Pt;

    req.targets.forEach((targetId, i) => {
      const source = req.entities.find(
        (e) => e.id === targetId,
      ) as SketchEntity;
      const copy = body.entities[i] as SketchEntity;
      expect(copy.id).not.toBe(source.id); // fresh id, no collision
      expect(copy.kind).toBe(source.kind);
      if (source.kind === "line") {
        const rs = reflect(source.start as Pt, a, b);
        const re = reflect(source.end as Pt, a, b);
        expect(copy.start?.x).toBeCloseTo(rs.x, 2);
        expect(copy.start?.y).toBeCloseTo(rs.y, 2);
        expect(copy.end?.x).toBeCloseTo(re.x, 2);
        expect(copy.end?.y).toBeCloseTo(re.y, 2);
      } else if (source.kind === "circle") {
        const rc = reflect(source.center as Pt, a, b);
        expect(copy.center?.x).toBeCloseTo(rc.x, 2);
        expect(copy.center?.y).toBeCloseTo(rc.y, 2);
        expect(copy.radius).toBeCloseTo(source.radius as number, 2);
      }
    });

    // Appended, not swapped: 3 → 5, honest note.
    await expect(page.getByTestId("sketch-edit-note")).toContainText(
      "Mirrored",
    );
    await expect(page.getByTestId("sketch-save")).toContainText("5 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-mirror-after.png`,
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

  test("mirror about the sketch's OWN centerline — the Y datum axis (MIRROR-1)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror datum");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );

    // A half-profile on the +x side and NO drawn centerline — the whole point.
    // Before this shipped, the only mirror axis was a line you had drawn, so
    // the symmetric-bracket idiom cost a construction line the part does not
    // need; the sketch's own Y axis was invisible to the picker.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 10 });
    await clickPlane(page, at, { x: 30, y: 10 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 20, y: -10 }); // center
    await clickPlane(page, at, { x: 28, y: -10 }); // rim → r = 8
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");

    await page.keyboard.press("i");
    await clickPlane(page, at, { x: 20, y: 10 }); // the line
    await clickPlane(page, at, { x: 28, y: -10 }); // the circle
    await expect(page.getByTestId("mirror-count")).toContainText("2 entities");
    await page.getByTestId("mirror-advance").click();
    await expect(page.getByTestId("mirror-prompt")).toHaveAttribute(
      "data-phase",
      "axis",
    );
    // The prompt says the axis can be the frame — the capability is readable
    // without having to hover the invisible cross to discover it.
    await expect(page.getByTestId("mirror-count")).toContainText(
      "Click a line or an origin axis",
    );

    // Hover the Y axis: it answers in the pick language the drawn geometry
    // already speaks (brass), and the ghost previews the reflected copies.
    const onAxis = { x: 0, y: 8 };
    await page.mouse.move(at(onAxis).x, at(onAxis).y);
    await expect(page.getByTestId("sketch-axis-label-y")).toHaveAttribute(
      "data-pick-state",
      "hover",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mirror-datum-axis-after-1600.png`,
    });

    const mirrorResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/mirror") &&
        r.request().method() === "POST",
    );
    await clickPlane(page, at, onAxis);
    const mirror = await mirrorResponse;
    expect(mirror.status()).toBe(200);

    const req = mirror.request().postDataJSON() as {
      targets: string[];
      axis: { kind: string; a?: Pt; b?: Pt };
      entities: SketchEntity[];
    };
    // A POINTS axis, not an entity ref: the frame is materialised into the
    // sketch only when a constraint names it, so an entity ref would name a
    // line the payload does not carry. Nothing was added to the sketch to make
    // the mirror possible — mirror adds copies, not relationships.
    expect(req.axis.kind).toBe("points");
    expect(req.entities.map((e) => e.id)).toEqual(["e1", "e2"]);
    const a = req.axis.a as Pt;
    const b = req.axis.b as Pt;
    expect(a.x).toBeCloseTo(0, 9);
    expect(b.x).toBeCloseTo(0, 9);
    expect(Math.abs(b.y - a.y)).toBeGreaterThan(0);

    // The backend's copies are the exact reflection about x = 0.
    const body = (await mirror.json()) as { entities: SketchEntity[] };
    expect(body.entities).toHaveLength(2);
    req.targets.forEach((targetId, i) => {
      const source = req.entities.find(
        (e) => e.id === targetId,
      ) as SketchEntity;
      const copy = body.entities[i] as SketchEntity;
      if (source.kind === "line") {
        const rs = reflect(source.start as Pt, a, b);
        const re = reflect(source.end as Pt, a, b);
        expect(copy.start?.x).toBeCloseTo(rs.x, 2);
        expect(copy.start?.y).toBeCloseTo(rs.y, 2);
        expect(copy.end?.x).toBeCloseTo(re.x, 2);
        expect(copy.end?.y).toBeCloseTo(re.y, 2);
      } else {
        const rc = reflect(source.center as Pt, a, b);
        expect(copy.center?.x).toBeCloseTo(rc.x, 2);
        expect(copy.center?.y).toBeCloseTo(rc.y, 2);
        expect(copy.radius).toBeCloseTo(source.radius as number, 2);
      }
    });

    await expect(page.getByTestId("sketch-edit-note")).toContainText(
      "Mirrored",
    );
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mirror-datum-axis-done-after-1600.png`,
    });

    // Save → the mirrored sketch persists and STILL SOLVES.
    const evalPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/evaluate`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    const evalResponse = await evalPromise;
    expect(evalResponse.status()).toBe(200);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
  });

  test("a drawn line still wins the axis pick where it lies over an axis", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror over Y");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );

    // The idiomatic centerline is a construction line drawn ON the Y axis. The
    // frame lies invisibly beneath it, and must not steal the click.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -20 });
    await clickPlane(page, at, { x: 0, y: 20 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 10 });
    await clickPlane(page, at, { x: 30, y: 10 });
    await page.keyboard.press("Escape");

    await page.keyboard.press("i");
    await clickPlane(page, at, { x: 20, y: 10 });
    await expect(page.getByTestId("mirror-count")).toContainText("1 entity");
    await page.getByTestId("mirror-advance").click();

    const mirrorResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/mirror") &&
        r.request().method() === "POST",
    );
    await clickPlane(page, at, { x: 0, y: 5 });
    const mirror = await mirrorResponse;
    const req = mirror.request().postDataJSON() as {
      axis: { kind: string; entity?: string };
    };
    expect(req.axis).toEqual({ kind: "entity", entity: "e1" });
  });

  test("Escape cascades axis → targets → drop tool without leaving the sketch", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror escape");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -20 });
    await clickPlane(page, at, { x: 0, y: 20 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 10 });
    await clickPlane(page, at, { x: 30, y: 10 });

    await page.keyboard.press("i");
    await clickPlane(page, at, { x: 20, y: 10 }); // one target
    await expect(page.getByTestId("mirror-count")).toContainText("1 entity");
    await page.keyboard.press("Enter"); // → axis phase
    await expect(page.getByTestId("mirror-prompt")).toHaveAttribute(
      "data-phase",
      "axis",
    );

    await page.keyboard.press("Escape"); // axis → targets (picks kept)
    await expect(page.getByTestId("mirror-prompt")).toHaveAttribute(
      "data-phase",
      "targets",
    );
    await expect(page.getByTestId("mirror-count")).toContainText("1 entity");
    await page.keyboard.press("Escape"); // targets with picks → clear
    await expect(page.getByTestId("mirror-prompt")).toBeVisible();
    await page.keyboard.press("Escape"); // empty → drop the tool
    await expect(page.getByTestId("mirror-prompt")).toBeHidden();
    // Still in the sketch — the escape cascade never exited it.
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
  });
});

test.describe("sketch mirror — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("mirror tool stays reachable; founder screenshot", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror laptop");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 520, y: 320 },
      { x: 760, y: 540 },
    );
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -20 });
    await clickPlane(page, at, { x: 0, y: 20 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 8 });
    await clickPlane(page, at, { x: 26, y: 8 });

    await expect(page.getByTestId("tool-mirror")).toBeVisible();
    await page.keyboard.press("i");
    await clickPlane(page, at, { x: 18, y: 8 });
    await expect(page.getByTestId("mirror-count")).toContainText("1 entity");
    await page.getByTestId("mirror-advance").click();
    await page.mouse.move(at({ x: 0, y: 5 }).x, at({ x: 0, y: 5 }).y);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-mirror-laptop.png`,
    });
  });

  test("the centerline is reachable with no drawn axis; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror datum LT");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 520, y: 320 },
      { x: 760, y: 540 },
    );
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 8 });
    await clickPlane(page, at, { x: 26, y: 8 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 18, y: -8 });
    await clickPlane(page, at, { x: 24, y: -8 });

    await page.keyboard.press("i");
    await clickPlane(page, at, { x: 18, y: 8 });
    await clickPlane(page, at, { x: 24, y: -8 });
    await expect(page.getByTestId("mirror-count")).toContainText("2 entities");
    await page.getByTestId("mirror-advance").click();
    await page.mouse.move(at({ x: 0, y: 6 }).x, at({ x: 0, y: 6 }).y);
    await expect(page.getByTestId("sketch-axis-label-y")).toHaveAttribute(
      "data-pick-state",
      "hover",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mirror-datum-axis-after-1280.png`,
    });
  });
});
