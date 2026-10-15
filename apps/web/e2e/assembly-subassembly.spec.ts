import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { pickHoleCentres } from "./jointFlow";
import { SCREENSHOT_DIR, distinctCanvasColors } from "./support";

/**
 * ASM-A3 step 1 — NESTED SUB-ASSEMBLIES, end to end (a bike from wheels).
 *
 *  1. The "wheel": two hole plates on a revolute joint through the holes,
 *     built in its own assembly exactly as the hinge spec builds one.
 *  2. A "bike" inserts the wheel TWICE from the Add panel's sub-assembly list,
 *     plus one more plate. The viewport draws all five plates (two per wheel,
 *     each tagged with its wheel), the tree lists three components.
 *  3. A rigid joint from the loose plate to a plate INSIDE the first wheel:
 *     picked on the nested plate's hole rim like any other part. The plate
 *     lands on top of the wheel, and the joint survives a reload.
 *  4. The BOM reads top level 2 lines / 3, indented with per-wheel and
 *     all-levels counts, parts only 5.
 *  5. The STEP export holds every placed plate.
 *  6. Inserting the bike into the wheel is refused, naming the chain.
 */

/** A balloon's solved scene pose (Y-up: scene y = kernel z). */
async function scenePose(
  page: Page,
  id: string,
): Promise<{ x: number; y: number }> {
  const balloon = page.getByTestId(`assembly-balloon-${id}`);
  return {
    x: Number(await balloon.getAttribute("data-solved-x")),
    y: Number(await balloon.getAttribute("data-solved-y")),
  };
}

/** Every drawn plate's balloon id, with the sub-assembly it belongs to. */
async function balloons(
  page: Page,
): Promise<{ id: string; group: string | null }[]> {
  return page
    .locator('[data-testid^="assembly-balloon-"]')
    .evaluateAll((nodes) =>
      nodes.map((node) => ({
        id: (node.getAttribute("data-testid") ?? "").replace(
          "assembly-balloon-",
          "",
        ),
        group: node.getAttribute("data-group-id"),
      })),
    );
}

const NAUO = /NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(/g;

test.describe("Assemblies — nested sub-assemblies", () => {
  test("two wheels and a plate: draw, joint to a nested part, reload, BOM, STEP, cycle", async ({
    page,
  }) => {
    test.setTimeout(300_000);

    // ——— 1. The wheel: two plates on a revolute joint ————————————————
    const wheel = await setupTwoInstances(page);
    await pickHoleCentres(page, wheel.idA, wheel.idB);
    await page.getByTestId("joint-motion-revolute").click();
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-dialog")).toBeHidden({
      timeout: 30_000,
    });
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    const auth = { Authorization: `Bearer ${wheel.token}` };
    const wheelGraph = (await (
      await page.request.get(`/api/v1/assemblies/${wheel.assemblyId}`, {
        headers: auth,
      })
    ).json()) as { instances: { ref_document_id: string }[] };
    const plateId = wheelGraph.instances[0]?.ref_document_id ?? "";

    // ——— 2. The bike: the wheel twice, plus a plate ——————————————————
    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Bike");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page.getByTestId("assembly-row").filter({ hasText: "Bike" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
    const bikeId = page.url().split("/").pop() ?? "";

    await page.getByTestId("add-instance").click();
    const wheelCell = page.getByTestId(
      `add-instance-assembly-${wheel.assemblyId}`,
    );
    for (const n of [1, 2]) {
      await wheelCell.click();
      await expect(page.getByTestId("instance-row")).toHaveCount(n, {
        timeout: 30_000,
      });
    }
    await page.getByTestId(`add-instance-part-${plateId}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(3, {
      timeout: 30_000,
    });
    await page.getByTestId("add-instance-done").click();
    const [front, rear, plateC] = await page
      .getByTestId("instance-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
      );
    if (!front || !rear || !plateC) throw new Error("expected three rows");

    await waitForSolved(page);
    // Five plates drawn: two in each wheel (tagged with it), and the loose one.
    await expect.poll(async () => (await balloons(page)).length).toBe(5);
    const drawn = await balloons(page);
    expect(drawn.filter((b) => b.group === front)).toHaveLength(2);
    expect(drawn.filter((b) => b.group === rear)).toHaveLength(2);
    expect(
      drawn.filter((b) => b.id === plateC && b.group === null),
    ).toHaveLength(1);
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // The wheel's upper plate sits on its lower one (kernel z 10).
    const frontPlates = drawn.filter((b) => b.group === front);
    const poses = await Promise.all(
      frontPlates.map(async (b) => ({
        id: b.id,
        ...(await scenePose(page, b.id)),
      })),
    );
    const upper = poses.find((p) => Math.abs(p.y - 10) < 1e-3);
    expect(
      upper,
      "the wheel's revolute joint holds its upper plate",
    ).toBeDefined();

    // ——— 3. Joint the loose plate onto the wheel's upper plate ————————
    await pickHoleCentres(page, upper?.id ?? "", plateC);
    await page.getByTestId("joint-motion-rigid").click();
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("joint-dialog")).toBeHidden({
      timeout: 30_000,
    });
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    const seated = await scenePose(page, plateC);
    expect(seated.y).toBeCloseTo(20, 3);
    expect(seated.x).toBeCloseTo(upper?.x ?? NaN, 3);

    // The joint names the NESTED plate, and survives a reload.
    await page.reload();
    await waitForSolved(page);
    await expect(page.getByTestId("mate-row")).toHaveCount(1);
    // Numbered by component: the nested plate is in wheel 1, the plate is 3.
    await expect(page.getByTestId("mate-row")).toContainText("①1 · ②3");
    const reread = (await (
      await page.request.get(`/api/v1/assemblies/${bikeId}`, { headers: auth })
    ).json()) as { mates: { mate: { a: { instance_id: string } } }[] };
    expect(reread.mates[0]?.mate.a.instance_id).toBe(upper?.id);
    const after = await scenePose(page, plateC);
    expect(after.y).toBeCloseTo(20, 3);

    // ——— 4. The bill of materials, three ways ———————————————————————
    await page.getByTestId("inspector-view-bom").click();
    await expect(page.getByTestId("bom-row")).toHaveCount(2);
    await expect(page.getByTestId("bom-total")).toHaveText("3");
    await page.getByTestId("bom-view-indented").click();
    const indented = page.getByTestId("bom-row");
    await expect(indented).toHaveCount(3);
    const read = async () =>
      indented.evaluateAll((rows) =>
        rows.map((r) => [
          (r as HTMLElement).dataset.item,
          r.querySelector('[data-testid="bom-name"]')?.textContent,
          r.querySelector('[data-testid="bom-quantity"]')?.textContent,
          r.querySelector('[data-testid="bom-total-quantity"]')?.textContent,
        ]),
      );
    expect(await read()).toEqual([
      ["1", "Bolted plates", "2", "2"],
      ["1.1", "Hole plate", "2", "4"],
      ["2", "Hole plate", "1", "1"],
    ]);
    await page.mouse.move(1400, 900);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/asm-subassembly.png` });
    await page.getByTestId("bom-view-parts").click();
    await expect(page.getByTestId("bom-row")).toHaveCount(1);
    await expect(page.getByTestId("bom-total")).toHaveText("5");

    // ——— 5. STEP: every placed plate is an occurrence —————————————————
    const step = page.getByTestId("assembly-export-band-step");
    await expect(step).toBeEnabled({ timeout: 30_000 });
    const pending = page.waitForEvent("download");
    await step.click();
    const file = await (await pending).path();
    const text = (await readFile(file)).toString("utf-8");
    expect(text.match(NAUO)).toHaveLength(5);

    // ——— 6. A cycle is refused, naming the chain ——————————————————————
    await page.goto(`/assemblies/${wheel.assemblyId}`);
    await page.getByTestId("add-instance").click();
    await page.getByTestId(`add-instance-assembly-${bikeId}`).click();
    await expect(page.getByTestId("add-instance-submit-error")).toHaveText(
      "Bike already contains Bolted plates, so inserting it here would make the assembly contain itself.",
    );
  });
});
