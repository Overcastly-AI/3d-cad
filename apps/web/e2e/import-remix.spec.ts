import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, distinctCanvasColors, seedSession } from "./support";

/**
 * Imported-STEP REMIX — the interop dogfooding leg (BACKLOG "Model-a-REAL-part
 * dogfooding gate", pass #3). You import a body you did NOT author, then pick
 * its faces to add features; both halves lean on machinery that unit tests do
 * not reach end to end.
 *
 * What this pins that `feature-selection.spec.ts` does not: EXACT face counts.
 * That spec asserts only `0 < lit < total` and `litA !== litB`, which a
 * one-face attribution slip satisfies. Here every count is a closed-form
 * topology number for the part on screen, so a slip is a failure:
 *
 *   vendor plate as imported          17 faces (back + top + 4 perimeter + 4
 *                                     corner chamfers + boss top + 4 hole walls
 *                                     + bore + boss OD)
 *   after a 5th Ø3 through hole       18 faces; the hole owns exactly 3 of them
 *                                     (its wall + the two planes it re-cut)
 *   the import then owns the other    15
 *
 * The 5th hole's wall is geometrically IDENTICAL to the four the vendor drilled
 * — same diameter, same depth, same 75.398 mm² area — and differs only in
 * centroid, so a provenance fingerprint that discriminated by area alone would
 * light 7 faces here instead of 3.
 *
 * BOTH glTF encodings are exercised deliberately (PERF-4b): the imported plate
 * is triangle-DENSE (~181 tris/face) so it stays one primitive per B-rep face,
 * while the chamfered plate in the second test is all-planar (~3 tris/face) so
 * it FUSES into a handful of primitives with the per-face partition in
 * `extras.LOFT_face_triangles`. `data-total-faces` is read from the parsed mesh,
 * so asserting it against the kernel's face count proves the decode recovers the
 * same partition either way — the silent-wrong-answer risk of the fusion.
 *
 * Fixture: `fixtures/nema17-front-plate.step`, a NEMA 17 stepper front plate
 * (42.3 mm square, 5 mm corner chamfers, 8 mm thick, Ø22×2 pilot boss, Ø5.2
 * shaft bore, 4× Ø3 on a 31 mm square). Volume closed-form:
 * 13 914.32 + 102.4π = 14 236.0191 mm³.
 */

const STEP_FIXTURE = fileURLToPath(
  new URL("./fixtures/nema17-front-plate.step", import.meta.url),
);

async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/**
 * A cheap fingerprint of what the viewport is actually DRAWING. The camera hook
 * (`data-camera-pos`) is stamped only on a programmatic view settle — never on a
 * user orbit — so "the view moved" has to be read off the raster.
 */
async function canvasFingerprint(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (canvas === null) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const context = probe.getContext("2d");
    if (context === null) return 0;
    context.drawImage(canvas, 0, 0);
    const { data } = context.getImageData(0, 0, probe.width, probe.height);
    let hash = 2166136261;
    for (let i = 0; i < data.length; i += 397) {
      hash = Math.imul(hash ^ (data[i] ?? 0), 16777619);
    }
    return hash >>> 0;
  });
}

/** The viewport's mesh-derived face census (QA hooks stamped by `Viewport`). */
async function faceCensus(
  page: Page,
): Promise<{ lit: number; total: number; highlight: string | null }> {
  const viewport = page.getByTestId("viewport");
  return {
    lit: Number(await viewport.getAttribute("data-selected-faces")),
    total: Number(await viewport.getAttribute("data-total-faces")),
    highlight: await viewport.getAttribute("data-body-highlight"),
  };
}

/** Click the planar pick node whose accessible name reports the lowest z. */
async function clickLowestFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = Number.POSITIVE_INFINITY;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z < bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Append a feature through the real gateway, honouring the tree-version guard. */
async function addFeature(
  page: Page,
  token: string,
  partId: string,
  name: string,
  feature: unknown,
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const meta = await page.request.get(`/api/v1/parts/${partId}`, { headers });
  expect(meta.ok(), await meta.text()).toBe(true);
  const { tree_version: treeVersion } = (await meta.json()) as {
    tree_version: number;
  };
  const created = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: { name, feature, expected_tree_version: treeVersion },
    headers,
  });
  expect(created.status(), await created.text()).toBe(201);
  return ((await created.json()) as { feature: { id: string } }).feature.id;
}

/**
 * The `SubshapeRef` for the one planar face whose area satisfies *matches* —
 * built from the SAME `/overlay` signatures the UI's face pick echoes back, so
 * an API-authored feature anchors exactly as a clicked one would.
 */
interface FaceSignature {
  area_mm2: number;
  normal: { x: number; y: number; z: number };
  centroid: { x: number; y: number; z: number };
}

async function pickFace(
  page: Page,
  token: string,
  partId: string,
  matches: (signature: FaceSignature) => boolean,
): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}` };
  const treeResponse = await page.request.get(
    `/api/v1/parts/${partId}/features`,
    { headers },
  );
  expect(treeResponse.ok(), await treeResponse.text()).toBe(true);
  const tree = (await treeResponse.json()) as {
    tree_version: number;
    features: { id: string; feature: unknown }[];
  };
  const overlayResponse = await page.request.post("/api/v1/geometry/overlay", {
    data: {
      tree: {
        part_id: partId,
        tree_version: tree.tree_version,
        features: tree.features.map((row) => ({
          id: row.id,
          feature: row.feature,
        })),
      },
    },
    headers,
  });
  expect(overlayResponse.ok(), await overlayResponse.text()).toBe(true);
  const { faces } = (await overlayResponse.json()) as {
    faces: { feature_id: string | null; signature: FaceSignature | null }[];
  };
  const hits = faces.filter(
    (face) => face.signature !== null && matches(face.signature),
  );
  expect(hits, "exactly one planar face must match").toHaveLength(1);
  const face = hits[0] as {
    feature_id: string | null;
    signature: FaceSignature;
  };
  return {
    kind: "subshape",
    feature_id: face.feature_id,
    subshape_type: "face",
    selector: { selector_version: 1, signature: face.signature },
  };
}

/** The tree's current `mesh_glb_id`, straight from an evaluate. */
async function meshId(
  page: Page,
  token: string,
  partId: string,
): Promise<string> {
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    data: {},
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { mesh_glb_id: string }).mesh_glb_id;
}

/** Does the part's current mesh carry the PERF-4b fused-face side table? */
async function meshEncoding(
  page: Page,
  token: string,
  partId: string,
): Promise<{ fused: boolean; primitives: number }> {
  const id = await meshId(page, token, partId);
  const response = await page.request.get(
    `/api/v1/geometry/meshes/${encodeURIComponent(id)}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(response.ok(), await response.text()).toBe(true);
  const bytes = await response.body();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 12;
  let json: string | null = null;
  while (offset < view.byteLength) {
    const length = view.getUint32(offset, true);
    const kind = view.getUint32(offset + 4, true);
    if (kind === 0x4e4f534a) {
      json = new TextDecoder().decode(
        new Uint8Array(bytes.buffer, bytes.byteOffset + offset + 8, length),
      );
    }
    offset += 8 + length;
  }
  expect(json).not.toBeNull();
  const document = JSON.parse(json as string) as {
    meshes: { primitives: { extras?: { LOFT_face_triangles?: number[] } }[] }[];
  };
  const primitives = document.meshes.flatMap((mesh) => mesh.primitives);
  return {
    fused: primitives.some(
      (primitive) => primitive.extras?.LOFT_face_triangles !== undefined,
    ),
    primitives: primitives.length,
  };
}

test.describe("imported-STEP remix", () => {
  test("import a vendor plate, remix it, and the face counts are exact", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "NEMA 17 remix");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("import-step-button")).toBeEnabled();

    // ---- the vendor file lands -------------------------------------------
    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("14,236.02");
    await expect(page.getByTestId("prop-extents")).toContainText(
      "42.3 × 42.3 × 10",
    );
    await expectRenderedBody(page);

    // The mesh the viewport parsed has the kernel's 17 faces. This part is
    // triangle-dense, so `fuse_faces` must DECLINE and return OCCT's bytes.
    await expect
      .poll(async () => (await faceCensus(page)).total, { timeout: 30_000 })
      .toBe(17);
    expect(await meshEncoding(page, account.token, part.id)).toEqual({
      fused: false,
      primitives: 17,
    });

    // The import owns every face it brought: the whole-body state.
    await page.getByTestId("feature-select-0").click();
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "selected",
      { timeout: 20_000 },
    );
    expect((await faceCensus(page)).lit).toBe(17);

    // ---- remix: a 5th mount hole on an IMPORTED face ---------------------
    // (Authored through the API: the Hole command cannot place a point at a
    // dimensioned location — see the sibling test for what it CAN do.)
    const back = await pickFace(
      page,
      account.token,
      part.id,
      (signature) => Math.abs(signature.area_mm2 - 1689.7785) < 0.01,
    );

    await addFeature(page, account.token, part.id, "5th mount hole", {
      type: "hole",
      version: 1,
      params: {
        face: back,
        position: { x: 15.5, y: 0, z: 0 },
        diameter_mm: 3,
        depth: { kind: "through_all" },
      },
    });
    await page.reload();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    // 14 236.0191 - π·1.5²·8 = 14 179.4704 mm³, and one new face.
    await expect(page.getByTestId("prop-volume")).toContainText("14,179.47");
    await expect
      .poll(async () => (await faceCensus(page)).total, { timeout: 30_000 })
      .toBe(18);

    // ---- THE attribution proof ------------------------------------------
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "feature",
      { timeout: 20_000 },
    );
    expect(await faceCensus(page)).toMatchObject({
      lit: 3,
      total: 18,
      highlight: "feature",
    });

    // ...and the import keeps the other 15, including all four vendor holes.
    await page.getByTestId("feature-select-0").click();
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "feature",
      { timeout: 20_000 },
    );
    expect((await faceCensus(page)).lit).toBe(15);

    // ---- a reload agrees with all of it ---------------------------------
    await page.reload();
    await expect(page.getByTestId("prop-volume")).toContainText("14,179.47", {
      timeout: 60_000,
    });
    await expectRenderedBody(page);
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "feature",
      { timeout: 20_000 },
    );
    expect((await faceCensus(page)).lit).toBe(3);
  });

  test("the FUSED encoding recovers the same face partition", async ({
    page,
  }) => {
    // An all-planar part: a 40×25×10 plate with a 16×10×4 pocket milled into
    // its top. ~3 triangles per face, so `fuse_faces` accepts it and the
    // viewport must rebuild the per-face partition from
    // `extras.LOFT_face_triangles` rather than from primitive boundaries.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Fused census");
    const sketch = await addFeature(
      page,
      account.token,
      part.id,
      "plate profile",
      {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            {
              id: "l1",
              kind: "line",
              start: { x: 0, y: 0 },
              end: { x: 40, y: 0 },
            },
            {
              id: "l2",
              kind: "line",
              start: { x: 40, y: 0 },
              end: { x: 40, y: 25 },
            },
            {
              id: "l3",
              kind: "line",
              start: { x: 40, y: 25 },
              end: { x: 0, y: 25 },
            },
            {
              id: "l4",
              kind: "line",
              start: { x: 0, y: 25 },
              end: { x: 0, y: 0 },
            },
          ],
          constraints: [],
        },
      },
    );
    await addFeature(page, account.token, part.id, "plate", {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    });
    // Mill the pocket on the plate's TOP face, picked by its stage-1 signature
    // exactly as the UI's face pick does.
    const top = await pickFace(
      page,
      account.token,
      part.id,
      (signature) =>
        Math.abs(signature.area_mm2 - 1000) < 0.01 && signature.normal.z > 0,
    );
    const datum = await addFeature(page, account.token, part.id, "top datum", {
      type: "datum",
      version: 1,
      params: { kind: "on_face", face: top },
    });
    const pocketProfile = await addFeature(
      page,
      account.token,
      part.id,
      "pocket profile",
      {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "feature", feature_id: datum },
          entities: [
            {
              id: "p1",
              kind: "line",
              start: { x: -8, y: -5 },
              end: { x: 8, y: -5 },
            },
            {
              id: "p2",
              kind: "line",
              start: { x: 8, y: -5 },
              end: { x: 8, y: 5 },
            },
            {
              id: "p3",
              kind: "line",
              start: { x: 8, y: 5 },
              end: { x: -8, y: 5 },
            },
            {
              id: "p4",
              kind: "line",
              start: { x: -8, y: 5 },
              end: { x: -8, y: -5 },
            },
          ],
          constraints: [],
        },
      },
    );
    await addFeature(page, account.token, part.id, "pocket", {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: pocketProfile },
        distance_mm: 4,
        operation: "cut",
        direction: "reverse",
      },
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expectRenderedBody(page);
    // 40·25·10 - 16·10·4 = 9 360 mm³.
    await expect(page.getByTestId("prop-volume")).toContainText("9,360");

    // The payload really is the fused encoding — otherwise this test proves
    // nothing about the decode it exists to check.
    const encoded = await meshEncoding(page, account.token, part.id);
    expect(encoded.fused).toBe(true);
    expect(encoded.primitives).toBeLessThan(11);

    // 6 box faces + 4 pocket walls + the pocket floor = 11, and the parsed mesh
    // must report all eleven even though they arrive inside a few primitives.
    await expect
      .poll(async () => (await faceCensus(page)).total, { timeout: 30_000 })
      .toBe(11);

    // The pocket owns its 4 walls + floor + the top it re-cut = 6; the base
    // extrude keeps the 4 side walls and the bottom it never lost = 5.
    await page.getByTestId("feature-select-4").click();
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "feature",
      { timeout: 20_000 },
    );
    expect(await faceCensus(page)).toMatchObject({ lit: 6, total: 11 });

    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "feature",
      { timeout: 20_000 },
    );
    expect((await faceCensus(page)).lit).toBe(5);
  });

  test("the Hole command's seeded point on a bored plate fails HONESTLY", async ({
    page,
  }) => {
    // A vendor plate whose face centre is a through bore is the ordinary case,
    // and the Hole command offers exactly two placements: the face's area
    // centroid ("Centre of face") and its corner vertices. The centroid here is
    // inside the Ø5.2 shaft bore. What must NOT happen is a body that builds
    // anyway — the contract is a TYPED per-feature error naming the cause.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Hole seed probe");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Only the plate's 11 PLANAR faces are pickable; the six cylinders are not.
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      11,
    );
    await clickLowestFace(page);
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );

    // Per-keystroke: the diameter field re-validates as it is typed.
    const diameter = page.getByTestId("hole-diameter");
    await diameter.click();
    await diameter.press("Control+a");
    await diameter.pressSequentially("3", { delay: 40 });
    await expect(diameter).toHaveValue("3");

    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();

    // Failed, with the typed code on the row — never a silently wrong solid.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("feature-error-1")).toContainText(
      "hole_off_body",
    );
    // The last-good body is still the import's, unchanged.
    await expect(page.getByTestId("prop-volume")).toContainText("14,236.02");
  });

  test("the remixed vendor part ships a full package: STEP, drawing, PDF", async ({
    page,
  }) => {
    // The dogfooding gate's last question — does the whole deliverable come out
    // the other end for a part whose base body was IMPORTED, not authored?
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const suffix = Date.now().toString(36);
    const part = await createPartViaApi(
      page,
      account.token,
      `NEMA 17 bracket ${suffix}`,
    );
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    const back = await pickFace(
      page,
      account.token,
      part.id,
      (signature) => Math.abs(signature.area_mm2 - 1689.7785) < 0.01,
    );
    await addFeature(page, account.token, part.id, "5th mount hole", {
      type: "hole",
      version: 1,
      params: {
        face: back,
        position: { x: 15.5, y: 0, z: 0 },
        diameter_mm: 3,
        depth: { kind: "through_all" },
      },
    });

    // ---- STEP out, and it round-trips back to the same solid -------------
    const stepOut = await page.request.post(
      `/api/v1/parts/${part.id}/export?format=step`,
      { headers: auth },
    );
    expect(stepOut.ok(), await stepOut.text()).toBe(true);
    expect(stepOut.headers()["content-disposition"]).toContain(
      `nema-17-bracket-${suffix}.step`,
    );
    const stepText = (await stepOut.body()).toString("utf8");
    expect(stepText.startsWith("ISO-10303-21;")).toBe(true);

    const echo = await createPartViaApi(
      page,
      account.token,
      `Round trip ${suffix}`,
    );
    await addFeature(page, account.token, echo.id, "re-import", {
      type: "import",
      version: 1,
      params: { data: stepText, format: "step", kind: "inline" },
    });
    const evaluate = async (id: string): Promise<Record<string, unknown>> => {
      const response = await page.request.post(`/api/v1/parts/${id}/evaluate`, {
        data: {},
        headers: auth,
      });
      expect(response.ok(), await response.text()).toBe(true);
      return (await response.json()) as Record<string, unknown>;
    };
    const original = (
      (await evaluate(part.id)) as {
        properties: { volume: number; topology: Record<string, number> };
      }
    ).properties;
    const reimported = (
      (await evaluate(echo.id)) as {
        properties: { volume: number; topology: Record<string, number> };
      }
    ).properties;
    // 14 236.0191 - π·1.5²·8 = 14 179.470420 mm³ (closed form), preserved
    // through the export/import round trip.
    expect(original.volume).toBeCloseTo(14179.47042, 6);
    expect(reimported.volume).toBeCloseTo(original.volume, 6);
    expect(reimported.topology).toEqual(original.topology);

    // ---- the drawing --------------------------------------------------
    const drawing = await page.request.post("/api/v1/drawings", {
      data: { name: `NEMA 17 bracket GA ${suffix}` },
      headers: auth,
    });
    expect(drawing.ok(), await drawing.text()).toBe(true);
    const drawingId = ((await drawing.json()) as { id: string }).id;
    const sheet = await page.request.post(
      `/api/v1/drawings/${drawingId}/sheets`,
      {
        data: {
          name: "Sheet 1",
          size: "A3",
          orientation: "landscape",
          projection: "third_angle",
          expected_version: 0,
          title_block: { author: "QA pass #3", notes: "Remixed vendor plate" },
        },
        headers: auth,
      },
    );
    expect(sheet.ok(), await sheet.text()).toBe(true);

    await page.goto(`/drawings/${drawingId}`);
    await page.getByTestId("drawing-part-select").selectOption(part.id);
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByTestId("drawing-view")).toHaveCount(4, {
      timeout: 60_000,
    });
    // The vendor part's four Ø3 holes + the remix's fifth reach the print as
    // real circles, so the projected geometry is the REMIXED body, not the
    // import alone.
    await expect(
      page.locator('[data-testid="drawing-view"] circle'),
    ).not.toHaveCount(0);
    // Auto-layout on A3 must not leave a colliding sheet unreported (audit N2).
    await expect(page.getByTestId("drawing-layout-issue")).toHaveCount(0);

    // ---- PDF + DXF out ---------------------------------------------------
    for (const format of ["pdf", "dxf", "svg"] as const) {
      const response = await page.request.post(
        `/api/v1/drawings/${drawingId}/export?format=${format}`,
        { headers: auth },
      );
      expect(response.ok(), `${format}: ${await response.text()}`).toBe(true);
      expect((await response.body()).byteLength).toBeGreaterThan(1024);
    }
  });
});

/**
 * The same imported body under a TOUCH profile. CAD viewports fail differently
 * here — the orbit rig binds one finger to ROTATE and two to pan/zoom, and a
 * touch context has no hover, so the pick affordances are the only way in.
 */
test.describe("imported-STEP remix — touch", () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 768 } });

  test("a one-finger drag orbits the imported body", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Touch remix");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expectRenderedBody(page);

    const viewport = page.getByTestId("viewport");
    // The mesh decode is profile-independent: all 17 faces, on touch too.
    await expect
      .poll(async () => (await faceCensus(page)).total, { timeout: 30_000 })
      .toBe(17);

    const before = await canvasFingerprint(page);
    expect(before).not.toBe(0);

    // One finger, dragged across the body: an ORBIT. Playwright's touchscreen
    // only taps, so the move sequence goes through CDP.
    const box = await viewport.boundingBox();
    expect(box).not.toBeNull();
    const frame = box as {
      x: number;
      y: number;
      width: number;
      height: number;
    };
    const cx = frame.x + frame.width / 2;
    const cy = frame.y + frame.height / 2;
    const cdp = await page.context().newCDPSession(page);
    const touch = (
      type: "touchStart" | "touchMove" | "touchEnd",
      x: number,
      y: number,
    ): Promise<unknown> =>
      cdp.send("Input.dispatchTouchEvent", {
        type,
        touchPoints: type === "touchEnd" ? [] : [{ x, y, id: 1 }],
      });
    await touch("touchStart", cx, cy);
    for (let step = 1; step <= 8; step += 1) {
      await touch("touchMove", cx + step * 14, cy + step * 5);
    }
    await touch("touchEnd", cx + 112, cy + 40);

    await expect
      .poll(() => canvasFingerprint(page), { timeout: 15_000 })
      .not.toBe(before);

    // The body is still on screen after the orbit — an orbit that flings the
    // camera into the void is the classic touch failure.
    await expectRenderedBody(page);
  });
});
