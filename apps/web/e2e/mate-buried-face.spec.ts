import { expect, test, type Page } from "./fixtures";
import { seedSession, SCREENSHOT_DIR } from "./support";
import { waitForSolved } from "./assemblyFlow";

/**
 * MATE-1 — reaching a BURIED mate face, driven through the real UI with a real
 * mouse.
 *
 * ## The fixture, and why it is the honest one
 *
 * The audit's own (S-15), one step earlier in the flow: a bracket dropped
 * roughly into place, half-sunk through a plate. A coincident mate joins faces
 * that will END UP touching, so at the moment you go to author one they are
 * already in contact or already interpenetrating — which means the two faces
 * you must point at are inside each other's material. Look from above and the
 * bracket is in the way; from below, the plate. There is no camera to orbit to,
 * so this is not a case of aiming better.
 *
 * Measured on the seated variant of this fixture BEFORE the fix, through this
 * same UI — a 528-point pointer census over a 1280x800 frame in four cameras
 * (iso, two under-views, one round) — the bracket's underside was the addressed
 * face at ZERO of them. Worse, the two ends of the pick disagreed: at
 * (668, 372) in the under-view the viewport HIGHLIGHTED the bracket's underside
 * while the click COMMITTED the plate's underside — a different face on a
 * different part, silently, because hover took the farthest hit (no
 * `stopPropagation` on move) and the click took the nearest (which did stop).
 *
 * ## What this spec pins
 *
 *  1. the buried face is still not reachable by AIMING — nothing here pretends
 *     the camera problem went away; the column is the way in, not better aim;
 *  2. the column names it, in true depth order, with the part it belongs to,
 *     and aiming at a row traces that face in the viewport;
 *  3. picking it commits THAT face — asserted on the PERSISTED MATE's own face
 *     signatures, never on a click landing, because "the pick worked and mated
 *     the wrong face" is this defect's whole failure mode and the two parts
 *     have identical face counts.
 */

/** A rectangular block part: `w` x `d` extruded `h` from the XY plane. */
async function createBlockViaApi(
  page: Page,
  token: string,
  name: string,
  w: number,
  d: number,
  h: number,
): Promise<string> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  if (!part.ok()) throw new Error(`create part failed: ${part.status()}`);
  const partId = ((await part.json()) as { id: string }).id;
  const corners = [
    [0, 0],
    [w, 0],
    [w, d],
    [0, d],
  ] as const;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: corners.map((corner, i) => ({
            id: `e${i + 1}`,
            kind: "line",
            start: { x: corner[0], y: corner[1] },
            end: {
              x: (corners[(i + 1) % corners.length] as readonly number[])[0],
              y: (corners[(i + 1) % corners.length] as readonly number[])[1],
            },
          })),
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  if (!sketch.ok()) throw new Error(`sketch failed: ${sketch.status()}`);
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };
  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: h,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!extrude.ok()) throw new Error(`extrude failed: ${extrude.status()}`);
  return partId;
}

/** A point in a part's own local frame, as the API returns it. */
interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** A grounded 60 x 40 x 6 plate with a 24 x 16 x 4 bracket dropped through it. */
async function seatedBracketAssembly(page: Page): Promise<{
  assemblyId: string;
  token: string;
  plateInstance: string;
  bracketInstance: string;
}> {
  const account = await seedSession(page);
  const auth = { Authorization: `Bearer ${account.token}` };
  const plate = await createBlockViaApi(
    page,
    account.token,
    "Plate",
    60,
    40,
    6,
  );
  const bracket = await createBlockViaApi(
    page,
    account.token,
    "Bracket",
    24,
    16,
    // A seated PAD, not a tower. Height is load-bearing for the fixture: under
    // the workspace's oblique default camera a ray entering a tall block's top
    // leaves through a SIDE wall, so the underside is never in the column and
    // the test would be exercising a different geometry than the one it
    // describes. 4 mm keeps the ray passing straight through the seam.
    4,
  );

  const asm = await page.request.post("/api/v1/assemblies", {
    data: { name: "Seated bracket" },
    headers: auth,
  });
  if (!asm.ok()) throw new Error(`create assembly failed: ${asm.status()}`);
  const asmBody = (await asm.json()) as { id: string; doc_version: number };

  const add = async (
    name: string,
    refId: string,
    grounded: boolean,
    position: { x: number; y: number; z: number },
    version: number,
  ): Promise<number> => {
    const response = await page.request.post(
      `/api/v1/assemblies/${asmBody.id}/instances`,
      {
        data: {
          name,
          ref_document_id: refId,
          ref_document_kind: "part",
          grounded,
          placement: { position },
          expected_version: version,
        },
        headers: auth,
      },
    );
    if (!response.ok()) {
      throw new Error(`add ${name} failed: ${response.status()}`);
    }
    return ((await response.json()) as { doc_version: number }).doc_version;
  };

  let version = asmBody.doc_version;
  version = await add("Plate 1", plate, true, { x: 0, y: 0, z: 0 }, version);
  // The bracket is dropped in ROUGHLY, half-sunk into the plate (z = 3 puts its
  // 4 mm body across the plate's 6 mm top), and centred in plan so it is
  // entirely within the plate's footprint. That is the state a modeller is
  // actually in when they reach for a mate — you place a part near where it
  // goes and then constrain it — and it makes BOTH faces of the mate genuinely
  // buried: the bracket's underside sits inside the plate's material, and the
  // plate's top face sits inside the bracket's. Neither is visible from any
  // camera, so neither can be aimed at.
  await add("Bracket 1", bracket, false, { x: 18, y: 12, z: 3 }, version);

  await page.goto(`/assemblies/${asmBody.id}`);
  await waitForSolved(page);
  const ids = await page
    .getByTestId("instance-row")
    .evaluateAll((rows) =>
      rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
    );
  const [plateInstance, bracketInstance] = ids;
  if (!plateInstance || !bracketInstance) {
    throw new Error(`expected two instances, got ${ids.length}`);
  }
  return {
    assemblyId: asmBody.id,
    token: account.token,
    plateInstance,
    bracketInstance,
  };
}

/** The canvas rect, for pointer work in viewport coordinates. */
async function canvasRect(
  page: Page,
): Promise<{ x: number; y: number; width: number; height: number }> {
  const box = await page
    .getByTestId("viewport")
    .locator("canvas")
    .first()
    .boundingBox();
  if (box === null) throw new Error("no viewport canvas");
  return box;
}

/** The column the strip is showing, as `instanceId:faceIndex`, near first. */
async function columnRows(page: Page): Promise<string[]> {
  return page
    .getByTestId("mate-column")
    .locator("[data-testid^='mate-column-row-']")
    .evaluateAll((nodes) =>
      nodes.map((n) => {
        const el = n as HTMLElement;
        return `${el.dataset.instance}:${el.dataset.face}`;
      }),
    );
}

/**
 * Aim at a face, and report the column the cursor then addresses.
 *
 * The aim point is derived from the face's own `PickNode`, which sits at its
 * area centroid — so it is the middle of the face by construction rather than a
 * pixel someone measured once and nobody re-measures. It cannot be the centroid
 * EXACTLY, for a reason worth stating: that node is a 24 px DOM button over the
 * canvas, so directly on it the canvas receives no pointer event at all (the
 * fourth product pass reported the same thing as T-14, on Measure). So this
 * steps outward in rings until the canvas answers with a column that satisfies
 * `ok` — near the centroid, off the button.
 *
 * Keyed on the COLUMN rather than on the hover stamp, because near a body's
 * silhouette the ray leaves through a SIDE wall instead of the face under test:
 * a perfectly valid column that says nothing about burial.
 */
async function aimAtFace(
  page: Page,
  testId: string,
  what: string,
  ok: (rows: string[]) => boolean,
): Promise<string[]> {
  const box = await page.locator(`[data-testid="${testId}"]`).boundingBox();
  if (box === null) throw new Error(`no pick node ${testId}`);
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const seen = new Set<string>();
  for (const radius of [16, 22, 28, 34, 40, 46]) {
    for (let step = 0; step < 12; step += 1) {
      const angle = (step * Math.PI) / 6;
      await page.mouse.move(
        cx + radius * Math.cos(angle),
        cy + radius * Math.sin(angle),
      );
      const rows = await columnRows(page);
      seen.add(rows.join(" -> "));
      if (ok(rows)) return rows;
    }
  }
  throw new Error(
    `no point near ${testId} gives a column ${what}; saw ${[...seen].join(" | ")}`,
  );
}

test.describe("MATE-1 — a mate face buried between two parts", () => {
  test.setTimeout(300_000);

  test("the column reaches it, and the mate it authors is the right one", async ({
    page,
  }) => {
    const { assemblyId, token, plateInstance, bracketInstance } =
      await seatedBracketAssembly(page);
    const viewport = page.getByTestId("viewport");

    await page.getByTestId("mate-coincident").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await expect(
      page.locator(`[data-testid^="mate-face-${bracketInstance}-"]`).first(),
    ).toBeAttached({ timeout: 30_000 });

    // The bracket's bottom face. Its accessible name carries the centroid in
    // the PART's own frame, which is how the fixture names it: 12, 8, 0 is the
    // middle of a 24 x 16 block's underside.
    const buriedNode = page.locator(
      `[data-testid="mate-face-${bracketInstance}-4"]`,
    );
    await expect(buriedNode).toHaveAttribute(
      "aria-label",
      /centred at 12, 8, 0 /,
    );

    // ——— 1. STILL ESSENTIALLY UNREACHABLE BY AIMING ——————————————————————
    //
    // The column is the way IN; it is not better aim, and this spec must not
    // quietly become a claim that the camera problem went away.
    //
    // The bound is a fraction rather than zero, and the reason is honest
    // geometry rather than flake tolerance. On the audit's 12 mm-tall bracket
    // this measured 0 of 528 samples in each of four cameras. On the 4 mm pad
    // this fixture uses — chosen so an oblique ray passes through the seam at
    // all — a hairline of pixels along the pad's silhouette DOES strike the
    // underside first, because at 4 mm the top and bottom silhouettes are a
    // couple of pixels apart. Measured here: 1 of 234. That sliver is not a
    // pick affordance; nobody hits a one-pixel band on purpose, and it is not
    // where a modeller aims. Anything above a couple of percent would mean the
    // face had become genuinely aimable and this test had stopped describing
    // the defect.
    const box = await canvasRect(page);
    let aimedAtBuried = 0;
    let sampled = 0;
    for (let y = box.y + 20; y < box.y + box.height - 20; y += 48) {
      for (let x = box.x + 20; x < box.x + box.width - 20; x += 48) {
        await page.mouse.move(x, y);
        sampled += 1;
        const stamp = await viewport.getAttribute("data-mate-pick-hover");
        if (stamp === `${bracketInstance}:4`) aimedAtBuried += 1;
      }
    }
    expect(sampled, "the frame was actually sampled").toBeGreaterThan(200);
    expect(
      aimedAtBuried / sampled,
      `buried face reached by aiming at ${aimedAtBuried}/${sampled} samples`,
    ).toBeLessThan(0.02);

    // ——— 2. THE COLUMN NAMES IT ——————————————————————————————————————————
    //
    // Aim squarely at the bracket's TOP face — the only thing aiming could ever
    // give you here — and read what else is under the cursor. Squarely matters:
    // near the bracket's silhouette the ray leaves through a side wall instead
    // of the seated underside, which is a perfectly valid column that says
    // nothing about burial.
    const rows = await aimAtFace(
      page,
      `mate-face-${bracketInstance}-5`,
      "entering through the bracket's top and leaving through its underside",
      (found) =>
        found[0] === `${bracketInstance}:5` &&
        found.includes(`${bracketInstance}:4`),
    );
    const column = page.getByTestId("mate-column");
    await expect(column).toBeVisible();

    // Every row, in the order the ray meets them. Looking down at a bracket
    // half-sunk into a plate the ray crosses, in true depth order: the
    // bracket's top (z = 7), the plate's top INSIDE it (z = 6), the bracket's
    // underside inside the plate (z = 3), and the plate's underside (z = 0).
    // Four faces, where the pick before MATE-1 could only ever report the
    // first, and where the middle two are the mate — both invisible.
    const trace = `column: ${rows.join(" -> ")}`;
    expect(rows.length, trace).toBeGreaterThanOrEqual(4);
    expect(rows.slice(0, 4), trace).toEqual([
      `${bracketInstance}:5`,
      `${plateInstance}:5`,
      `${bracketInstance}:4`,
      `${plateInstance}:4`,
    ]);

    const buriedRow = column.locator(
      `[data-instance="${bracketInstance}"][data-face="4"]`,
    );
    // The row says WHOSE face it is and WHERE — the two things that tell
    // coincident candidates apart.
    await expect(buriedRow).toHaveAttribute(
      "aria-label",
      /^Bracket 1, Planar face 5, centred at 12, 8, 0 /,
    );

    // Aiming at the row traces THAT face in the viewport, before committing to
    // it — which is what makes this a pick rather than a guess.
    await buriedRow.hover();
    await expect(viewport).toHaveAttribute(
      "data-mate-pick-hover",
      `${bracketInstance}:4`,
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/mate-buried-face-after.png`,
    });

    // ——— 3. PICKING IT COMMITS THAT FACE ————————————————————————————————
    await buriedRow.click();
    await expect(buriedNode).toHaveAttribute("aria-pressed", "true");

    // The mating face on the OTHER part, through the same column — and it is
    // buried too: the plate's TOP face is inside the bracket that is sitting
    // through it. Two invisible faces, one mate.
    await aimAtFace(
      page,
      `mate-face-${bracketInstance}-5`,
      "reaching the plate's top face through the bracket",
      (found) => found.includes(`${plateInstance}:5`),
    );
    await expect(column).toBeVisible();
    await column
      .locator(`[data-instance="${plateInstance}"][data-face="5"]`)
      .click();

    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 60_000,
    });
    await waitForSolved(page);

    // ——— THE ASSERTION THAT MATTERS ——————————————————————————————————————
    //
    // Not "a mate appeared" — WHICH FACES IT JOINED, read back off the
    // PERSISTED mate. This is the check the ticket asks for by name: a pick
    // that lands but mates the wrong face is this defect's whole failure mode,
    // and the two parts here have identical face COUNTS, so nothing short of
    // reading the stored geometry can tell one answer from the other.
    //
    // The signature is what the solver actually resolves against, so asserting
    // on it asserts on the mate itself rather than on a UI echo of it. Both
    // centroids are in their own part's LOCAL frame: 12, 8, 0 is the middle of
    // the 24 x 16 bracket's underside; 30, 20, 6 is the middle of the
    // 60 x 40 x 6 plate's top. Both are buried; neither could be reached
    // before.
    const stored = await page.request.get(`/api/v1/assemblies/${assemblyId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(stored.ok(), `read assembly: ${stored.status()}`).toBe(true);
    const doc = (await stored.json()) as {
      mates: {
        mate: {
          type: string;
          a?: { instance_id: string; signature: { centroid: Vec3 } };
          b?: { instance_id: string; signature: { centroid: Vec3 } };
        };
      }[];
    };
    expect(doc.mates).toHaveLength(1);
    const joined = doc.mates[0]?.mate;
    expect(joined?.type).toBe("coincident");
    const ends = [joined?.a, joined?.b].map((end) =>
      end === undefined
        ? "missing"
        : `${end.instance_id}@${end.signature.centroid.x},${end.signature.centroid.y},${end.signature.centroid.z}`,
    );
    expect(new Set(ends), `mate joins: ${ends.join(" <-> ")}`).toEqual(
      new Set([`${bracketInstance}@12,8,0`, `${plateInstance}@30,20,6`]),
    );
  });
});
