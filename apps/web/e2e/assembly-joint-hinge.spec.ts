/**
 * S5b — THE JOINT DIALOG, on a hinge: two 40×25×10 plates, each with a Ø10
 * hole at (20, 12.5), joined Fusion-style through the hole centres.
 *
 *  1. Joint (J): origin A is A's top hole rim, origin B is B's bottom rim; the
 *     dialog opens, Revolute is chosen and the server-solved preview snaps B
 *     onto A before anything is stored. OK stores "Revolute 1"; the solve
 *     reports 1 free DOF (the hinge).
 *  2. Dragging B turns it about the hinge and nowhere else: B's own origin (a
 *     point ON the axis) holds still to < 1e-6 mm while the joint turns. The
 *     release is ONE PATCH of the value.
 *  3. Typing 200° against a max of 180° is refused, in the server's words,
 *     naming the limit.
 *  4. The limits and the value survive a reload, and Ctrl+Z undoes a value
 *     change (one step), leaving the limits alone.
 *
 * WebGL is invisible to the DOM, so the spec reads the joint's axis and the
 * camera from the `data-joint-drag` QA stamp and projects points of B's top
 * face to the screen itself — then makes the real pointer gesture. The solved
 * joint is read off its tree row's `data-joint-*` attributes (full precision).
 */
import { expect, test, type Page } from "./fixtures";

import { pickDispatch, setupTwoInstances, waitForSolved } from "./assemblyFlow";

type V3 = [number, number, number];

interface DriveStamp {
  canvas: [number, number, number, number];
  viewProj: number[];
  mateId: string;
  point: V3;
  dir: V3;
  value: number;
}

/** World (scene) point → page pixels through the stamp's view-projection. */
function toScreen(t: DriveStamp, p: V3): { x: number; y: number } {
  const [left, top, width, height] = t.canvas;
  const e = t.viewProj;
  const at = (i: number) => e[i] as number;
  const [x, y, z] = p;
  const cx = at(0) * x + at(4) * y + at(8) * z + at(12);
  const cy = at(1) * x + at(5) * y + at(9) * z + at(13);
  const cw = at(3) * x + at(7) * y + at(11) * z + at(15);
  return {
    x: left + ((cx / cw + 1) / 2) * width,
    y: top + ((1 - cy / cw) / 2) * height,
  };
}

/** Kernel (Z-up) → scene (Y-up): (x, y, z) → (x, z, −y). */
const scene = (x: number, y: number, z: number): V3 => [x, z, -y];

/** The drive stamp once it has held still (camera at rest). */
async function settledStamp(page: Page): Promise<DriveStamp> {
  let last = "";
  await expect
    .poll(
      async () => {
        const raw =
          (await page
            .getByTestId("viewport")
            .getAttribute("data-joint-drag")) ?? "";
        const still = raw !== "" && raw === last;
        last = raw;
        return still;
      },
      {
        timeout: 20_000,
        intervals: [300],
        message: "the joint drive stamp never appeared / settled",
      },
    )
    .toBe(true);
  return JSON.parse(last) as DriveStamp;
}

interface JointReadout {
  rot: number;
  originA: V3;
  originB: V3;
  axis: V3;
}

/** The settled solve's joint readout off its tree row. */
async function readJoint(page: Page): Promise<JointReadout> {
  await waitForSolved(page);
  const row = page.getByTestId("mate-row").first();
  await expect(row).toHaveAttribute("data-joint-rot", /.+/);
  const attr = async (name: string) => (await row.getAttribute(name)) ?? "";
  return {
    rot: Number(await attr("data-joint-rot")),
    originA: JSON.parse(await attr("data-joint-origin-a")) as V3,
    originB: JSON.parse(await attr("data-joint-origin-b")) as V3,
    axis: JSON.parse(await attr("data-joint-axis")) as V3,
  };
}

const gap = (a: V3, b: V3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

async function openEditor(page: Page) {
  await page.getByTestId("mate-row").first().dblclick();
  await expect(page.getByTestId("joint-dialog")).toHaveAttribute(
    "data-joint-mode",
    "edit",
  );
}

test.describe("assembly joint — hinge", () => {
  test("revolute through the hole centres: DOF 1, drag about a fixed axis, limits, reload, undo", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { idA, idB } = await setupTwoInstances(page);

    // ——— 1. Joint: pick the two hole centres, choose Revolute, OK ————————
    await page.keyboard.press("j");
    await expect(page.getByTestId("mate-joint")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await pickDispatch(
      page,
      `[data-testid^="joint-origin-${idA}-circle-"][aria-label$="at 20, 12.5, 10 millimetres"]`,
    );
    await pickDispatch(
      page,
      `[data-testid^="joint-origin-${idB}-circle-"][aria-label$="at 20, 12.5, 0 millimetres"]`,
    );
    const dialog = page.getByTestId("joint-dialog");
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId("joint-motion-ball")).toBeDisabled();
    await page.getByTestId("joint-motion-revolute").click();
    await expect(page.getByTestId("joint-rotMax")).toBeVisible();

    // B snaps onto A in the PREVIEW, before anything is stored: its seed was
    // x = 80, the hole centres coincide at x = 20 with B's origin at x = 20.
    await expect
      .poll(
        async () =>
          Number(
            await page
              .getByTestId(`assembly-balloon-${idB}`)
              .getAttribute("data-solved-x"),
          ),
        { timeout: 30_000, message: "the preview never snapped B onto A" },
      )
      .toBeLessThan(1);
    await expect(page.getByTestId("mate-row")).toHaveCount(0);
    const shot = process.env["JOINT_DIALOG_SHOT"];
    if (shot) {
      await expect(dialog).toHaveAttribute("data-previewing", "false");
      await page.screenshot({ path: shot });
    }

    await page.getByTestId("joint-ok").click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });
    const row = page.getByTestId("mate-row");
    await expect(row).toHaveCount(1, { timeout: 30_000 });
    await expect(row).toHaveAttribute("data-mate-label", "Revolute 1");
    await expect(row).toContainText("Revolute 1");
    await waitForSolved(page);
    await expect(page.getByTestId("assembly-dof")).toHaveText(/1$/);

    const before = await readJoint(page);
    // Both origins on the hinge axis, which is world +Z through (20, 12.5).
    expect(gap(before.originA, [20, 12.5, 10])).toBeLessThan(1e-6);
    expect(gap(before.originB, before.originA)).toBeLessThan(1e-6);
    expect(gap(before.axis, [0, 0, 1])).toBeLessThan(1e-9);

    // ——— 2. Drag B about the hinge: its origin on the axis holds still ————
    await page.getByTestId(`assembly-balloon-${idB}`).click();
    const stamp = await settledStamp(page);
    expect(stamp.mateId).toBe(await row.getAttribute("data-mate-id"));
    // Points of B's top face (kernel z = 20) at 15 mm from the axis.
    const onTop = (deg: number) => {
      const r = ((deg + before.rot) * Math.PI) / 180;
      return toScreen(
        stamp,
        scene(20 + 15 * Math.cos(r), 12.5 + 15 * Math.sin(r), 20),
      );
    };
    const patches: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "PATCH" && /\/mates\//.test(request.url())) {
        patches.push(request.url());
      }
    });
    const start = onTop(0);
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    for (const deg of [15, 30, 45, 60]) {
      const p = onTop(deg);
      await page.mouse.move(p.x, p.y);
    }
    await page.mouse.up();

    await expect
      .poll(async () => (await readJoint(page)).rot, {
        timeout: 30_000,
        message: "the drag never landed a new joint value",
      })
      .toBeGreaterThan(before.rot + 50);
    const after = await readJoint(page);
    expect(after.rot - before.rot).toBeCloseTo(60, 0);
    // THE HINGE HOLDS: B's origin is a point on the axis and does not move.
    expect(gap(after.originB, before.originB)).toBeLessThan(1e-6);
    expect(gap(after.originA, before.originA)).toBeLessThan(1e-6);
    expect(gap(after.axis, before.axis)).toBeLessThan(1e-9);
    expect(patches, "one release, one PATCH").toHaveLength(1);
    await expect(page.getByTestId("assembly-dof")).toHaveText(/1$/);
    // Driven to a value, the hinge PLACES B: not a warning.
    await expect(page.getByTestId("assembly-solve-status")).toHaveText(
      /Positioned by Revolute 1/i,
    );

    // ——— 3. 200° against a max of 180° is refused, naming the limit ———————
    await openEditor(page);
    await page.getByTestId("joint-rotMax").fill("180");
    await page.getByTestId("joint-rotValue").fill("200");
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-error")).toContainText(
      "Revolute 1: 200° exceeds max 180°",
    );
    await expect(page.getByTestId("joint-dialog")).toBeVisible();

    await page.getByTestId("joint-rotValue").fill("45");
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-dialog")).toBeHidden({
      timeout: 30_000,
    });
    await expect(page.getByTestId("mate-value-echo")).toHaveText("45°");
    await expect
      .poll(async () => (await readJoint(page)).rot, { timeout: 30_000 })
      .toBeCloseTo(45, 6);

    // ——— 4. Reload: limits and value are the server's ————————————————————
    await page.reload();
    await waitForSolved(page);
    await expect(page.getByTestId("mate-value-echo")).toHaveText("45°");
    expect((await readJoint(page)).rot).toBeCloseTo(45, 6);
    await openEditor(page);
    await expect(page.getByTestId("joint-rotMax")).toHaveValue("180");
    await expect(page.getByTestId("joint-rotValue")).toHaveValue("45");

    // A value change, then Ctrl+Z: one step back, limits untouched.
    await page.getByTestId("joint-rotValue").fill("90");
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-dialog")).toBeHidden({
      timeout: 30_000,
    });
    await expect(page.getByTestId("mate-value-echo")).toHaveText("90°");
    await waitForSolved(page);
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("mate-value-echo")).toHaveText("45°", {
      timeout: 30_000,
    });
    await expect
      .poll(async () => (await readJoint(page)).rot, { timeout: 30_000 })
      .toBeCloseTo(45, 6);
    await openEditor(page);
    await expect(page.getByTestId("joint-rotMax")).toHaveValue("180");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("joint-dialog")).toBeHidden();
  });
});
