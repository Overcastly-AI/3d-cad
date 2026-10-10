/**
 * S4b in the Joint dialog: the CYLINDRICAL and PLANAR joints, on the same two
 * 40×25×10 hole plates as the hinge spec, joined through the hole centres.
 *
 * Cylindrical: DOF 2. A plain drag turns B about the axis and Shift+drag
 * slides it along it; each release is ONE value PATCH carrying BOTH axes (the
 * axis not dragged keeps its stored value), and both values survive a reload.
 *
 * Planar: driven onto its 90° max, the joint reads "at limit" on its tree row
 * and on Move's drive card. Shift+drag slides B across the plane: ONE
 * placement PATCH (the in-plane slide has no value), B stays on the plane and
 * the joint stays at its limit.
 */
import { expect, type Page, test } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import {
  type DriveStamp,
  gap,
  type JointReadout,
  openEditor,
  pickHoleCentres,
  readJoint,
  scene,
  settledStamp,
  toScreen,
  type V3,
} from "./jointFlow";

interface Patch {
  url: string;
  body: Record<string, unknown>;
}

/** Every PATCH the page sends, with its JSON body. */
function recordPatches(page: Page): Patch[] {
  const patches: Patch[] = [];
  page.on("request", (request) => {
    if (request.method() !== "PATCH") return;
    patches.push({
      url: request.url(),
      body: (request.postDataJSON() ?? {}) as Record<string, unknown>,
    });
  });
  return patches;
}

/**
 * A point of B's top face (10 mm above its bottom-rim origin), `radius` mm
 * from the joint axis at world angle `deg` (B's local X sits at the joint's
 * rot), offset by `shift` mm (kernel frame).
 */
function onTop(
  stamp: DriveStamp,
  joint: JointReadout,
  deg: number,
  shift: V3 = [0, 0, 0],
) {
  const r = ((deg + joint.rot) * Math.PI) / 180;
  const [x, y, z] = joint.originB;
  return toScreen(
    stamp,
    scene(
      x + 15 * Math.cos(r) + shift[0],
      y + 15 * Math.sin(r) + shift[1],
      z + 10 + shift[2],
    ),
  );
}

/** Press, move through `points`, release; Shift held throughout when asked. */
async function drag(
  page: Page,
  points: { x: number; y: number }[],
  shift = false,
) {
  const [first, ...rest] = points;
  if (first === undefined) throw new Error("a drag needs a press point");
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.move(first.x, first.y);
  await page.mouse.down();
  for (const p of rest) await page.mouse.move(p.x, p.y);
  await page.mouse.up();
  if (shift) await page.keyboard.up("Shift");
}

/** Review screenshots, only when JOINT_MOTIONS_SHOTS names a directory. */
async function shot(page: Page, name: string) {
  const dir = process.env["JOINT_MOTIONS_SHOTS"];
  if (dir) await page.screenshot({ path: `${dir}/${name}.png` });
}

const mateValue = (p: Patch | undefined) =>
  (p?.body["value"] ?? null) as { rot_deg: number; lin_mm: number } | null;

test.describe("assembly joint — cylindrical and planar", () => {
  test("cylindrical: DOF 2, drag turns and Shift+drag slides, both axes sent and kept across a reload", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { idA, idB } = await setupTwoInstances(page);

    await pickHoleCentres(page, idA, idB);
    await page.getByTestId("joint-motion-cylindrical").click();
    // Both axes take limits and a value (the wire's rule).
    await expect(page.getByTestId("joint-rotMax")).toBeVisible();
    await expect(page.getByTestId("joint-linMax")).toBeVisible();
    // Seat B on A (slide 0); leave the turn free to drag.
    await page.getByTestId("joint-linValue").fill("0");
    await shot(page, "cylindrical-dialog");
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-dialog")).toBeHidden({
      timeout: 30_000,
    });
    const row = page.getByTestId("mate-row");
    await expect(row).toHaveAttribute("data-mate-label", "Cylindrical 1");
    await waitForSolved(page);
    await expect(page.getByTestId("assembly-dof")).toHaveText(/2$/);

    const before = await readJoint(page);
    expect(before.lin).toBeCloseTo(0, 6);
    expect(gap(before.originB, before.originA)).toBeLessThan(1e-6);
    expect(gap(before.axis, [0, 0, 1])).toBeLessThan(1e-9);

    // ——— a plain drag turns about the axis ————————————————————————————
    await page.getByTestId(`assembly-balloon-${idB}`).click();
    let stamp = await settledStamp(page);
    expect(stamp.motion).toBe("cylindrical");
    const patches = recordPatches(page);
    await drag(
      page,
      [0, 15, 30, 45, 60].map((d) => onTop(stamp, before, d)),
    );
    await expect
      .poll(async () => (await readJoint(page)).rot, {
        timeout: 30_000,
        message: "the drag never turned the joint",
      })
      .toBeGreaterThan(before.rot + 50);
    const turned = await readJoint(page);
    expect(turned.rot - before.rot).toBeCloseTo(60, 0);
    expect(turned.lin).toBeCloseTo(0, 6);
    expect(gap(turned.originB, before.originB)).toBeLessThan(1e-6);
    expect(patches, "one release, one PATCH").toHaveLength(1);
    const first = mateValue(patches[0]);
    // BOTH axes: the slide not dragged keeps its stored 0.
    expect(first?.lin_mm).toBe(0);
    expect(first?.rot_deg).toBeCloseTo(turned.rot, 6);

    // ——— Shift+drag slides along it ————————————————————————————————
    stamp = await settledStamp(page);
    await drag(
      page,
      [0, 3, 6, 9, 12].map((k) => onTop(stamp, turned, 0, [0, 0, k])),
      true,
    );
    await expect
      .poll(async () => (await readJoint(page)).lin, {
        timeout: 30_000,
        message: "Shift+drag never slid the joint",
      })
      .toBeGreaterThan(4);
    const slid = await readJoint(page);
    expect(patches, "one more release, one more PATCH").toHaveLength(2);
    expect(patches[1]?.url).toMatch(/\/mates\//);
    const second = mateValue(patches[1]);
    // BOTH axes again: the turn keeps the value the first drag stored.
    expect(second?.rot_deg).toBe(first?.rot_deg);
    expect(slid.lin).toBeCloseTo(second?.lin_mm ?? Number.NaN, 6);
    expect(slid.rot).toBeCloseTo(turned.rot, 6);
    // The slide runs along the axis: B's origin moves only in z.
    expect(slid.originB[0]).toBeCloseTo(before.originB[0], 6);
    expect(slid.originB[1]).toBeCloseTo(before.originB[1], 6);
    await expect(page.getByTestId("mate-value-echo")).toContainText(" · ");

    // ——— both values survive a reload ————————————————————————————————
    await page.reload();
    await waitForSolved(page);
    const reloaded = await readJoint(page);
    expect(reloaded.rot).toBeCloseTo(slid.rot, 6);
    expect(reloaded.lin).toBeCloseTo(slid.lin, 6);
    await expect(page.getByTestId("assembly-dof")).toHaveText(/2$/);
    await openEditor(page);
    await expect(page.getByTestId("joint-rotValue")).not.toHaveValue("");
    await expect(page.getByTestId("joint-linValue")).not.toHaveValue("");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("joint-dialog")).toBeHidden();
  });

  test("planar: driven onto its limit it reads at limit; Shift+drag slides it across the plane", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { idA, idB } = await setupTwoInstances(page);

    await pickHoleCentres(page, idA, idB);
    await page.getByTestId("joint-motion-planar").click();
    // A turn limit and value only: the in-plane slide has no single value.
    await expect(page.getByTestId("joint-rotMax")).toBeVisible();
    await expect(page.getByTestId("joint-linMax")).toBeHidden();
    await expect(page.getByTestId("joint-linValue")).toBeHidden();
    await page.getByTestId("joint-rotMax").fill("90");
    await page.getByTestId("joint-rotValue").fill("90");
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-dialog")).toBeHidden({
      timeout: 30_000,
    });
    const row = page.getByTestId("mate-row");
    await expect(row).toHaveAttribute("data-mate-label", "Planar 1");
    await waitForSolved(page);
    await expect(page.getByTestId("assembly-dof")).toHaveText(/3$/);

    const before = await readJoint(page);
    expect(before.rot).toBeCloseTo(90, 6);
    expect(before.atLimit).toBe(true);
    await expect(row.getByTestId("mate-at-limit")).toHaveText(/at limit/i);
    // B sits on A's top plane.
    expect(before.originB[2]).toBeCloseTo(10, 6);

    // Move on the jointed part: the drive card says so too.
    await page.getByTestId(`assembly-balloon-${idB}`).click();
    await page.keyboard.press("m");
    await expect(page.getByTestId("joint-drive")).toBeVisible();
    await expect(page.getByTestId("joint-drive-at-limit")).toBeVisible();
    const stamp = await settledStamp(page);
    expect(stamp.motion).toBe("planar");
    expect(stamp.atLimit).toBe(true);
    await shot(page, "planar-at-limit");

    // ——— Shift+drag: across the plane, one placement PATCH ——————————————
    const patches = recordPatches(page);
    await drag(
      page,
      [0, 2, 4, 6, 8].map((k) => onTop(stamp, before, 0, [k, k / 2, 0])),
      true,
    );
    await expect
      .poll(async () => (await readJoint(page)).originB[0], {
        timeout: 30_000,
        message: "Shift+drag never slid the planar joint",
      })
      .toBeGreaterThan(before.originB[0] + 4);
    const after = await readJoint(page);
    expect(patches, "one release, one PATCH").toHaveLength(1);
    expect(patches[0]?.url).toMatch(/\/instances\//);
    expect(after.originB[0] - before.originB[0]).toBeCloseTo(8, 0);
    expect(after.originB[1] - before.originB[1]).toBeCloseTo(4, 0);
    expect(after.originB[2]).toBeCloseTo(10, 6);
    expect(after.rot).toBeCloseTo(90, 6);
    expect(after.atLimit).toBe(true);
    await expect(row.getByTestId("mate-at-limit")).toBeVisible();

    // ——— a plain drag turns it about its own origin, off the limit ————————
    const turnStamp = await settledStamp(page);
    const turnPatches = recordPatches(page);
    const path = [0, -10, -20, -30].map((d) => onTop(turnStamp, after, d));
    const [press, ...rest] = path;
    if (press === undefined) throw new Error("no press point");
    await page.mouse.move(press.x, press.y);
    await page.mouse.down();
    for (const p of rest) await page.mouse.move(p.x, p.y);
    await shot(page, "planar-turn-mid-drag");
    await page.mouse.up();
    await expect
      .poll(async () => (await readJoint(page)).rot, {
        timeout: 30_000,
        message: "the drag never turned the planar joint",
      })
      .toBeLessThan(70);
    const turned = await readJoint(page);
    expect(turned.rot).toBeCloseTo(60, 0);
    expect(turned.atLimit).toBe(false);
    // The turn is about B's own origin: its in-plane seat holds.
    expect(gap(turned.originB, after.originB)).toBeLessThan(1e-6);
    expect(turnPatches).toHaveLength(1);
    expect(mateValue(turnPatches[0])?.lin_mm).toBeNull();
    await expect(row.getByTestId("mate-at-limit")).toBeHidden();
    await expect(page.getByTestId("joint-drive-at-limit")).toBeHidden();
  });
});
