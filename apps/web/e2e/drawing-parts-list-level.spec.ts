import { expect, test, type Page } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * The drawing's parts list has a STRUCTURE (DRAWING-PARTS-LIST-LEVEL): Top
 * level, Indented or Parts only, SolidWorks' BOM types and the same three the
 * assembly page offers. Bike QA round 3 found the sheet listing "Frame 1 /
 * Crankset 1" with no way to open the sub-assemblies.
 *
 * A bike-shaped assembly (Frame, Fork, a Crankset of two arms, and two of one
 * Wheel of hub, rim and spokes) is drafted, then:
 *  - Top level is the default: four items, Wheel x2;
 *  - Indented numbers each sub-assembly's lines under its top-level item, so
 *    the spokes are 4.3 under the wheel, per wheel and in all;
 *  - the choice is stored with the sheet, so a reload keeps it;
 *  - Parts only lists every spoke the bike holds.
 */

const SPOKES = 8;

async function assemblyViaApi(
  page: Page,
  token: string,
  name: string,
  instances: { ref: string; kind: "part" | "assembly"; name: string }[],
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("/api/v1/assemblies", {
    data: { name },
    headers,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const id = ((await created.json()) as { id: string }).id;
  let version = 0;
  for (const [index, instance] of instances.entries()) {
    const response = await page.request.post(
      `/api/v1/assemblies/${id}/instances`,
      {
        data: {
          expected_version: version,
          ref_document_id: instance.ref,
          ref_document_kind: instance.kind,
          name: instance.name,
          grounded: true,
          placement: {
            position: { x: index * 60, y: 0, z: index * 5 },
            orientation: { x: 0, y: 0, z: 0, w: 1 },
          },
        },
        headers,
      },
    );
    expect(response.ok(), await response.text()).toBe(true);
    version = ((await response.json()) as { doc_version: number }).doc_version;
  }
  return id;
}

async function draftedBike(page: Page): Promise<void> {
  const { token } = await seedSession(page);
  const part = async (name: string) =>
    (await createPlateWithHoleViaApi(page, token, name)).id;
  const [frame, fork, arm, hub, rim, spoke] = [
    await part("Frame"),
    await part("Fork"),
    await part("Crank arm"),
    await part("Hub"),
    await part("Rim"),
    await part("Spoke"),
  ];
  const crankset = await assemblyViaApi(page, token, "Crankset", [
    { ref: arm, kind: "part", name: "Arm <1>" },
    { ref: arm, kind: "part", name: "Arm <2>" },
  ]);
  const wheel = await assemblyViaApi(page, token, "Wheel", [
    { ref: hub, kind: "part", name: "Hub <1>" },
    { ref: rim, kind: "part", name: "Rim <1>" },
    ...Array.from({ length: SPOKES }, (_, i) => ({
      ref: spoke,
      kind: "part" as const,
      name: `Spoke <${i + 1}>`,
    })),
  ]);
  const bike = await assemblyViaApi(page, token, "Bike", [
    { ref: frame, kind: "part", name: "Frame <1>" },
    { ref: fork, kind: "part", name: "Fork <1>" },
    { ref: crankset, kind: "assembly", name: "Crankset <1>" },
    { ref: wheel, kind: "assembly", name: "Front wheel" },
    { ref: wheel, kind: "assembly", name: "Rear wheel" },
  ]);

  const created = await page.request.post("/api/v1/drawings", {
    data: { name: "Bike drawing" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const drawingId = ((await created.json()) as { id: string }).id;
  await page.goto(`/drawings/${drawingId}?source=${bike}`);
  await expect(page.getByTestId("drawing-part-select")).toHaveValue(bike);
  await expect(page.getByTestId("drawing-autolayout")).toHaveAttribute(
    "data-paper",
    /landscape \d+:\d+/,
    { timeout: 60_000 },
  );
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-view")).toHaveCount(4, {
    timeout: 90_000,
  });
}

function row(page: Page, item: string) {
  return page.locator(
    `[data-testid="parts-list-row"][data-item-number="${item}"]`,
  );
}

test("the parts list switches between top level, indented and parts only", async ({
  page,
}) => {
  await draftedBike(page);
  const panel = page.getByTestId("parts-list-panel");
  const rows = page.getByTestId("parts-list-row");

  // Top level is the default, as in SolidWorks and Fusion.
  await expect(panel).toHaveAttribute("data-structure", "top_level");
  await expect(rows).toHaveCount(4, { timeout: 30_000 });
  await expect(row(page, "4").getByTestId("parts-list-name")).toHaveText(
    "Wheel",
  );
  await expect(row(page, "4").getByTestId("parts-list-qty")).toHaveText("2");

  // Indented: the wheel keeps item 4 and its spokes are 4.3.
  await page.getByTestId("parts-list-structure-indented").click();
  await expect(panel).toHaveAttribute("data-structure", "indented");
  await expect(rows).toHaveCount(8, { timeout: 30_000 });
  const spokes = row(page, "4.3");
  await expect(spokes.getByTestId("parts-list-name")).toHaveText("Spoke");
  await expect(spokes).toHaveAttribute("data-level", "1");
  await expect(spokes.getByTestId("parts-list-qty")).toHaveText(`${SPOKES}`);
  await expect(spokes.getByTestId("parts-list-total-qty")).toHaveText(
    `${SPOKES * 2}`,
  );
  await expect(row(page, "3.1").getByTestId("parts-list-name")).toHaveText(
    "Crank arm",
  );

  // Founder shot: the sheet composed, the indented list scrolled to the wheel.
  await expect(page.getByTestId("drawing-composing")).toHaveCount(0, {
    timeout: 90_000,
  });
  await spokes.scrollIntoViewIfNeeded();
  await page.mouse.move(1400, 950);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawing-parts-list-level.png`,
  });

  // Stored with the sheet: a reload reads it back.
  await page.reload();
  await expect(panel).toHaveAttribute("data-structure", "indented", {
    timeout: 60_000,
  });
  await expect(rows).toHaveCount(8, { timeout: 60_000 });
  await expect(row(page, "4.3").getByTestId("parts-list-qty")).toHaveText(
    `${SPOKES}`,
  );

  // Parts only: every spoke on the bike, one line.
  await page.getByTestId("parts-list-structure-parts").click();
  await expect(panel).toHaveAttribute("data-structure", "parts_only");
  await expect(rows).toHaveCount(6, { timeout: 30_000 });
  await expect(row(page, "6").getByTestId("parts-list-name")).toHaveText(
    "Spoke",
  );
  await expect(row(page, "6").getByTestId("parts-list-qty")).toHaveText(
    `${SPOKES * 2}`,
  );
  await expect(page.getByTestId("parts-list-total")).toHaveText(
    `${2 + 2 + 2 * (SPOKES + 2)}`,
  );
});
