import { expect, type Page } from "./fixtures";

import { distinctCanvasColors, seedSession } from "./support";

/**
 * Shared assembly-workspace e2e plumbing (extracted from `assembly.spec.ts`
 * when the undo/redo spec became its second consumer — the DRY rule): build
 * the hole-plate part via the real gateway, stand up a two-instance assembly
 * through the UI, and author the coincident + concentric "bolt" pair by
 * picking geometry in the viewport.
 */

/** Build a 40×25×10 plate with a Ø10 through hole via the real gateway. */
export async function createPlateWithHoleViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  if (!part.ok()) {
    throw new Error(
      `create part failed: ${part.status()} ${await part.text()}`,
    );
  }
  const partId = ((await part.json()) as { id: string }).id;

  // A closed rectangle (outer loop) + a circle (inner loop) → a plate with a
  // hole when extruded (multi-loop closed profile, Phase 2).
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            {
              id: "e1",
              kind: "line",
              start: { x: 0, y: 0 },
              end: { x: 40, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 40, y: 0 },
              end: { x: 40, y: 25 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 40, y: 25 },
              end: { x: 0, y: 25 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 25 },
              end: { x: 0, y: 0 },
            },
            {
              id: "e5",
              kind: "circle",
              center: { x: 20, y: 12.5 },
              radius: 5,
              construction: false,
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  if (!sketch.ok()) {
    throw new Error(`sketch failed: ${sketch.status()} ${await sketch.text()}`);
  }
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
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!extrude.ok()) {
    throw new Error(
      `extrude failed: ${extrude.status()} ${await extrude.text()}`,
    );
  }
  return { id: partId };
}

/**
 * A balloon's solved pose, read TOGETHER WITH ITS PROVENANCE.
 *
 * Scene space is Y-up (`assembly/placement`: OCCT `(x, y, z)` → `(x, z, -y)`),
 * so `y` here is the solved OCCT **z** — the seating axis a coincident mate
 * moves, and the number the kernel investigation compared.
 *
 * `stale` comes from `closest("[data-eval-stale]")` in the SAME DOM read as the
 * pose, which is the point: the workspace retains the previous evaluation
 * across a refetch on purpose (`placeholderData: keepPreviousData`, so the
 * camera does not teleport), and for ~600 ms after a mate write these
 * attributes therefore carry the PRE-mate pose. Nothing about the numbers
 * themselves says so. A missing stamp counts as stale, so removing the
 * attribute fails every pose read loudly instead of quietly restoring the
 * defect.
 */
export interface SolvedPose {
  x: number;
  y: number;
  z: number;
  stale: boolean;
}

export async function balloonPose(
  page: Page,
  instanceId: string,
): Promise<SolvedPose | null> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="assembly-balloon-${id}"]`);
    if (el === null) return null;
    const host = el.closest("[data-eval-stale]");
    const num = (name: string) =>
      Number.parseFloat(el.getAttribute(name) ?? "NaN");
    return {
      x: num("data-solved-x"),
      y: num("data-solved-y"),
      z: num("data-solved-z"),
      stale: host === null || host.getAttribute("data-eval-stale") !== "false",
    };
  }, instanceId);
}

/**
 * The solved scene-space x of an instance's balloon (== solved OCCT world x),
 * or `NaN` while the solve on screen is superseded.
 *
 * NaN RATHER THAN THE NUMBER, deliberately: every caller polls this
 * (`expect.poll(() => balloonX(...)).toBeCloseTo(...)`), so a superseded pose
 * makes the poll keep waiting instead of reading through the window and
 * asserting against a previous solve. Throwing would abort the poll on its
 * first tick; returning the stale number is the defect this change exists to
 * close. There is no way to get a number out of here that is not current.
 */
export async function balloonX(
  page: Page,
  instanceId: string,
): Promise<number> {
  const pose = await balloonPose(page, instanceId);
  if (pose === null || pose.stale) return Number.NaN;
  return pose.x;
}

/**
 * Wait until the solve ON SCREEN is the answer for the graph as it stands.
 *
 * THE OLD BARRIER WAS SATISFIED BY AN ALREADY-TRUE CONDITION — it polled
 * `assembly-solve-status` for anything that was not `Solving…` or `—`, and the
 * retained previous solve reads `Under constrained` like any other. So it
 * returned on its first tick, mid-refetch, and every pose read after it got the
 * pre-mate answer. That is how a correctly-solved mate came to be reported as a
 * mate that did nothing.
 *
 * AND IT WAS BROKEN A SECOND, INDEPENDENT WAY that the measurement turned up:
 * the status cell is `uppercase` in CSS and `innerText` returns RENDERED text,
 * so the string it was matching is `SOLVING…` — which `/Solving|^—$/` does not
 * match. The barrier therefore released even on a page that was honestly
 * reporting itself mid-solve; the only thing it ever actually waited out was
 * the em dash. Measured in the before/after trace for MATE-OBS: at t+1223 ms
 * the cell read `SOLVING…` and the old predicate counted it as settled.
 *
 * A STATUS STRING CANNOT BE THE BARRIER, whatever it says: geometry's
 * `test_status_alone_cannot_distinguish_the_two` proves a seating solve and a
 * constraint-free solve BOTH report `under_constrained`, so a barrier keyed on
 * the status word releases identically in a world where mates do nothing. The
 * wait is therefore on PROVENANCE — `data-eval-stale="false"`, which
 * `deriveAssemblySolve` can only produce for a settled evaluation of the
 * current `[assembly, doc_version, partStamp]` key.
 *
 * Note the attribute must be PRESENT and `"false"`: a missing stamp times out
 * rather than passing, so this cannot decay into a no-op.
 */
export async function waitForSolved(page: Page): Promise<string> {
  const workspace = page.getByTestId("assembly-workspace");
  await expect
    .poll(() => workspace.getAttribute("data-eval-stale"), {
      timeout: 30_000,
      message:
        "the assembly workspace never reported a settled solve for the current " +
        'doc_version (data-eval-stale never reached "false") — a null here ' +
        "means the provenance stamp is missing from AssemblyPage's <main>, not " +
        "that the solve is slow",
    })
    .toBe("false");
  return (await page.getByTestId("assembly-solve-status").innerText()).trim();
}

/** Dispatch a click straight to a pick node (bypasses in-canvas occlusion). */
export async function pickDispatch(
  page: Page,
  selector: string,
): Promise<void> {
  const node = page.locator(selector).first();
  await expect(node).toHaveCount(1, { timeout: 20_000 });
  await node.dispatchEvent("click");
}

/**
 * Seed a session, build the hole-plate part, open a fresh assembly, and add two
 * instances (A auto-grounded, B seeded apart at x ≈ 80). Shared by every mate
 * flow so each test only authors its own mate.
 */
export async function setupTwoInstances(page: Page): Promise<{
  idA: string;
  idB: string;
  seedX: number;
  token: string;
  assemblyId: string;
}> {
  const account = await seedSession(page);
  const part = await createPlateWithHoleViaApi(
    page,
    account.token,
    "Hole plate",
  );

  // 1) Create the assembly from the register UI.
  await page.goto("/assemblies");
  await expect(page.getByTestId("create-assembly-name")).toBeVisible();
  await page.getByTestId("create-assembly-name").fill("Bolted plates");
  await page.getByTestId("create-assembly-name").press("Enter");
  const row = page
    .getByTestId("assembly-row")
    .filter({ hasText: "Bolted plates" });
  await expect(row).toBeVisible();
  await row.getByTestId("assembly-open").click();
  await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
  await expect(page.getByTestId("assembly-name")).toHaveText("Bolted plates");

  // 2) Add two instances of the part through the add-part panel (first is
  //    auto-grounded; the second seeds apart at x = 80).
  await page.getByTestId("add-instance").click();
  await expect(page.getByTestId("add-instance-panel")).toBeVisible();
  const partCell = page.getByTestId(`add-instance-part-${part.id}`);
  await partCell.click();
  await expect(page.getByTestId("instance-row")).toHaveCount(1, {
    timeout: 15_000,
  });
  await partCell.click();
  await expect(page.getByTestId("instance-row")).toHaveCount(2, {
    timeout: 15_000,
  });
  await page.getByTestId("add-instance-done").click();

  // The two instance ids in tree order (A grounded, B free).
  const ids = await page
    .getByTestId("instance-row")
    .evaluateAll((rows) =>
      rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
    );
  const [idA, idB] = ids;
  if (!idA || !idB) throw new Error("expected two instance ids");

  // Both instances render (two lit plates paint many shades).
  await waitForSolved(page);
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // The free instance sits at its authored seed (x ≈ 80) before any mate.
  const seedX = await balloonX(page, idB);
  expect(seedX).toBeGreaterThan(60);

  const assemblyId = page.url().split("/").pop() ?? "";

  return { idA, idB, seedX, token: account.token, assemblyId };
}

/**
 * Author the "bolt" mate pair in the viewport: Coincident (A's top face z=10 ↔
 * B's bottom face z=0, flush) then Concentric (a hole edge on each — the axes
 * align and the plates bolt up). Asserts each mate lands in the tree.
 */
export async function authorBoltMates(
  page: Page,
  idA: string,
  idB: string,
): Promise<void> {
  await page.getByTestId("mate-coincident").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
  );
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
  );
  await expect(page.getByTestId("mate-row")).toHaveCount(1, {
    timeout: 30_000,
  });
  await waitForSolved(page);

  await page.getByTestId("mate-concentric").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(page, `[data-testid^="mate-axis-${idA}-"]`);
  await pickDispatch(page, `[data-testid^="mate-axis-${idB}-"]`);
  await expect(page.getByTestId("mate-row")).toHaveCount(2, {
    timeout: 30_000,
  });
}
