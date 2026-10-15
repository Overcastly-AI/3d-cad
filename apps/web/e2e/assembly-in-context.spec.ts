import { expect, test, type Page } from "./fixtures";

import { pickDispatch, waitForSolved } from "./assemblyFlow";
import { installSceneProbe, waitForCameraStill } from "./invariants";
import { distinctCanvasColors, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ASM-A3-IN-CONTEXT — Edit in Place, end to end on the real stack.
 *
 * A3's carriage plate (120 x 140 x 8) sits over a rail (350 x 12 x 8, fourteen
 * Ø3.5 holes at 25 pitch from 12.5) placed at Y +40. In the assembly, the
 * plate is opened IN PLACE from its component menu; its sketch projects the
 * rail's 8th hole (the rail drawn ghosted around the plate, its edges offered
 * by Project) and the circle is cut through the plate. Then:
 *
 *  1. the link resolves in the assembly at the rail's hole (Y 40);
 *  2. the rail moves to Y +45 (A3's spacing edit): the plate's hole follows,
 *     the value is stored, and the plate opened alone cuts it there too
 *     (out of context it keeps its last resolved value);
 *  3. it all survives a reload;
 *  4. the rail is removed: the plate's reference is a typed, visible error,
 *     in the assembly and in the plate's in-place workspace, and the plate
 *     keeps its hole where it last was.
 */

type Entity =
  | { id: string; kind: "line"; start: XY; end: XY }
  | { id: string; kind: "circle"; center: XY; radius: number };
interface XY {
  x: number;
  y: number;
}

const R = 1.75;
const HOLE = Math.PI * R * R;
const PLATE_AREA = 120 * 140;

function rectangle(x0: number, y0: number, x1: number, y1: number): Entity[] {
  const p = [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
  return p.map((start, i) => ({
    id: `e${i + 1}`,
    kind: "line" as const,
    start,
    end: p[(i + 1) % 4] as XY,
  }));
}

async function api<T>(
  page: Page,
  token: string,
  method: "get" | "post" | "patch" | "delete",
  path: string,
  data?: unknown,
): Promise<T> {
  const response = await page.request[method](`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    ...(data === undefined ? {} : { data }),
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()) as T;
}

/** A part from one XY sketch extruded 8, through the real gateway. */
async function prism(
  page: Page,
  token: string,
  name: string,
  entities: Entity[],
): Promise<string> {
  const { id } = await api<{ id: string }>(page, token, "post", "/parts", {
    name,
  });
  const sketch = await api<{ feature: { id: string }; tree_version: number }>(
    page,
    token,
    "post",
    `/parts/${id}/features`,
    {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: entities.map((e) => ({ ...e, construction: false })),
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
  );
  await api(page, token, "post", `/parts/${id}/features`, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 8,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return id;
}

async function stage(page: Page, token: string) {
  const holes: Entity[] = Array.from({ length: 14 }, (_, k) => ({
    id: `h${k + 1}`,
    kind: "circle" as const,
    center: { x: 12.5 + 25 * k, y: 0 },
    radius: R,
  }));
  const rail = await prism(page, token, "Rail", [
    ...rectangle(0, -6, 350, 6),
    ...holes,
  ]);
  const plate = await prism(
    page,
    token,
    "Carriage plate",
    rectangle(-60, -70, 60, 70),
  );
  const { id } = await api<{ id: string }>(page, token, "post", "/assemblies", {
    name: "Linear stage",
  });
  let version = 0;
  const ids: string[] = [];
  for (const [ref, name, at] of [
    [rail, "Rail <1>", [25, 40, 10]],
    [plate, "Carriage plate <1>", [200, 0, 26]],
  ] as const) {
    const body = await api<{ instance: { id: string }; doc_version: number }>(
      page,
      token,
      "post",
      `/assemblies/${id}/instances`,
      {
        expected_version: version,
        ref_document_id: ref,
        ref_document_kind: "part",
        name,
        grounded: true,
        placement: {
          position: { x: at[0], y: at[1], z: at[2] },
          orientation: { x: 0, y: 0, z: 0, w: 1 },
        },
      },
    );
    version = body.doc_version;
    ids.push(body.instance.id);
  }
  return {
    rail,
    plate,
    assembly: id,
    railOcc: ids[0] ?? "",
    plateOcc: ids[1] ?? "",
  };
}

interface Evaluated {
  properties: { volume: number; centroid: { x: number; y: number } } | null;
}

/** The plate evaluated alone: its volume and centroid. */
async function plateAlone(page: Page, token: string, plate: string) {
  const body = await api<Evaluated>(
    page,
    token,
    "post",
    `/parts/${plate}/evaluate`,
  );
  return body.properties;
}

/** The plate's centroid y with its hole centred at plate-y `y`. */
const centroidY = (y: number) => (-HOLE * y) / (PLATE_AREA - HOLE);

interface Tree {
  features: {
    name: string;
    feature: {
      params: {
        entities?: {
          id: string;
          projection?: {
            in_context?: { resolved?: { center: { y: number } } };
          };
        }[];
      };
    };
  }[];
}

async function storedHoleY(
  page: Page,
  token: string,
  plate: string,
): Promise<number | null> {
  const tree = await api<Tree>(page, token, "get", `/parts/${plate}/features`);
  for (const f of tree.features) {
    for (const e of f.feature.params.entities ?? []) {
      const y = e.projection?.in_context?.resolved?.center.y;
      if (y !== undefined) return y;
    }
  }
  return null;
}

async function waitPartSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
}

test.describe("ASM-A3-IN-CONTEXT — Edit in Place", () => {
  test("project a rail's hole into the plate, cut, move the rail, remove it", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: 1600, height: 1000 });
    const { token } = await seedSession(page);
    const s = await stage(page, token);
    await installSceneProbe(page);

    // ---- Enter Edit in Place from the plate's component menu --------------
    await page.goto(`/assemblies/${s.assembly}`);
    await waitForSolved(page);
    await page
      .locator(`[data-testid="instance-row"][data-instance-id="${s.plateOcc}"]`)
      .click({ button: "right" });
    await page.getByTestId("instance-ctx-edit-in-place").click();
    await expect(page).toHaveURL(
      new RegExp(
        `/parts/${s.plate}\\?context=${s.assembly}&occurrence=${s.plateOcc}`,
      ),
    );
    const banner = page.getByTestId("in-context-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("Linear stage");
    await waitPartSolved(page);
    await expect(banner).toHaveAttribute("data-loading", "false", {
      timeout: 60_000,
    });

    // ---- Sketch on the plate's XY plane, P, click the rail's 8th hole ------
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await page.keyboard.press("p");
    await expect(page.getByTestId("tool-project")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // The rail's own edges, offered in its frame: hole 8's top rim is the
    // circle through (185.75, 0, 8) (its signature midpoint).
    const rims = page.locator(
      `[data-testid^="mate-axis-${s.railOcc}-"][data-edge-curve="circle"]`,
    );
    await expect(rims.first()).toBeAttached({ timeout: 60_000 });
    const target = await rims.evaluateAll((nodes) =>
      nodes
        .map((node) => ({
          id: node.getAttribute("data-testid") ?? "",
          mid: (node.getAttribute("data-edge-mid") ?? "")
            .split(",")
            .map(Number),
        }))
        .find(
          ({ mid }) =>
            Math.abs((mid[0] ?? NaN) - 185.75) < 1e-6 &&
            Math.abs((mid[2] ?? NaN) - 8) < 1e-6,
        ),
    );
    expect(target, "rail hole 8's top rim is offered").toBeDefined();
    await pickDispatch(page, `[data-testid="${target?.id ?? ""}"]`);
    await expect(page.getByTestId("project-count")).toHaveText("1 projected");
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(8);
    // The founder's picture: zoom in on the projected hole, the rail ghosted
    // under the plate with its other holes offered.
    const mark = await page
      .locator(`[data-testid="${target?.id ?? ""}"]`)
      .boundingBox();
    if (mark !== null) {
      await page.mouse.move(mark.x + mark.width / 2, mark.y + mark.height / 2);
      for (let i = 0; i < 10; i += 1) await page.mouse.wheel(0, -300);
    }
    await waitForCameraStill(page);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/asm-in-context.png` });

    await page.keyboard.press("Escape");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await waitPartSolved(page);

    // ---- Cut it through the plate ------------------------------------------
    await expect(page.getByTestId("new-extrude")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-op-cut").click();
    await page.getByTestId("extrude-distance").fill("8");
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("feature-row")).toHaveCount(4, {
      timeout: 30_000,
    });
    await waitPartSolved(page);
    await expect(page.getByTestId("in-context-link-e1")).toHaveAttribute(
      "data-state",
      "ok",
      { timeout: 60_000 },
    );
    await expect(page.getByTestId("in-context-link-e1")).toHaveAttribute(
      "data-centre",
      "12.5,40,-8",
    );
    await expect.poll(() => storedHoleY(page, token, s.plate)).toBe(40);
    const at40 = await plateAlone(page, token, s.plate);
    expect(at40?.volume ?? NaN).toBeCloseTo(8 * (PLATE_AREA - HOLE), 6);
    expect(at40?.centroid.y ?? NaN).toBeCloseTo(centroidY(40), 9);

    // ---- Back in the assembly: the link resolves at the rail's hole --------
    await page.getByTestId("in-context-return").click();
    await expect(page).toHaveURL(new RegExp(`/assemblies/${s.assembly}$`));
    await waitForSolved(page);
    const stamp = page.getByTestId("assembly-in-context-link-e1");
    await expect(stamp).toHaveAttribute("data-centre", "12.5,40,-8");

    // ---- Move the rail +40 -> +45 (A3's spacing edit) ----------------------
    const graph = await api<{ doc_version: number }>(
      page,
      token,
      "get",
      `/assemblies/${s.assembly}`,
    );
    await api(
      page,
      token,
      "patch",
      `/assemblies/${s.assembly}/instances/${s.railOcc}`,
      {
        expected_version: graph.doc_version,
        placement: {
          position: { x: 25, y: 45, z: 10 },
          orientation: { x: 0, y: 0, z: 0, w: 1 },
        },
      },
    );
    await page.reload();
    await waitForSolved(page);
    await expect(stamp).toHaveAttribute("data-centre", "12.5,45,-8", {
      timeout: 60_000,
    });
    await expect(stamp).toHaveAttribute("data-state", "ok");
    // Stored as the plate's last value: the plate alone cuts it at 45 too.
    await expect
      .poll(() => storedHoleY(page, token, s.plate), { timeout: 30_000 })
      .toBe(45);
    const at45 = await plateAlone(page, token, s.plate);
    expect(at45?.centroid.y ?? NaN).toBeCloseTo(centroidY(45), 9);

    // ---- It survives a reload ---------------------------------------------
    await page.reload();
    await waitForSolved(page);
    await expect(stamp).toHaveAttribute("data-centre", "12.5,45,-8");
    await expect(page.getByTestId("assembly-in-context-error-e1")).toHaveCount(
      0,
    );

    // ---- Remove the rail: a typed, visible error; the hole stays ----------
    await page
      .locator(`[data-testid="instance-row"][data-instance-id="${s.railOcc}"]`)
      .click({ button: "right" });
    await page.getByTestId("instance-ctx-remove").click();
    await waitForSolved(page);
    const error = page.getByTestId("assembly-in-context-error-e1");
    await expect(error).toBeVisible({ timeout: 60_000 });
    await expect(error).toHaveAttribute("data-reason", "component_missing");
    await expect(error).toContainText("Carriage plate <1>");
    await expect(error).toContainText("removed from the assembly");
    const kept = await plateAlone(page, token, s.plate);
    expect(kept?.centroid.y ?? NaN).toBeCloseTo(centroidY(45), 9);
    expect(await storedHoleY(page, token, s.plate)).toBe(45);

    // The plate's in-place workspace says so on its sketch.
    await page
      .locator(`[data-testid="instance-row"][data-instance-id="${s.plateOcc}"]`)
      .click({ button: "right" });
    await page.getByTestId("instance-ctx-edit-in-place").click();
    const own = page.getByTestId("in-context-error-e1");
    await expect(own).toBeVisible({ timeout: 60_000 });
    await expect(own).toHaveAttribute("data-reason", "component_missing");
    await expect(own).toContainText("Sketch");
  });

  test("a loop of in-context references is refused with the chain named", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const s = await stage(page, token);
    const link = (host: string, occurrence: string, part: string) => ({
      assembly_id: s.assembly,
      host_occurrence_id: host,
      occurrence_id: occurrence,
      part_id: part,
      edge: {
        curve: "circle",
        end_a: { x: 1.75, y: 0, z: 8 },
        end_b: { x: 1.75, y: 0, z: 8 },
        midpoint: { x: -1.75, y: 0, z: 8 },
        length_mm: 2 * Math.PI * R,
      },
    });
    const sketch = (l: unknown) => ({
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "c1",
            kind: "circle",
            center: { x: 0, y: 0 },
            radius: R,
            projection: { in_context: l },
          },
        ],
        constraints: [],
      },
    });
    // Plate -> rail is fine.
    await api(page, token, "post", `/parts/${s.plate}/features`, {
      name: "Sketch2",
      feature: sketch(link(s.plateOcc, s.railOcc, s.rail)),
      expected_tree_version: 2,
    });
    // Rail -> plate closes the loop.
    const refused = await page.request.post(
      `/api/v1/parts/${s.rail}/features`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          name: "Sketch2",
          feature: sketch(link(s.railOcc, s.plateOcc, s.plate)),
          expected_tree_version: 2,
        },
      },
    );
    expect(refused.status()).toBe(422);
    const body = (await refused.json()) as {
      error: { code: string; message: string };
    };
    expect(body.error.code).toBe("in_context_cycle");
    expect(body.error.message).toContain("Rail -> Carriage plate -> Rail");
  });
});
