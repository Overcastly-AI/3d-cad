/**
 * S5a — ASSEMBLY MOVE, driven the way a modeller drives Fusion's Move.
 *
 * The free plate (B, seeded unmated at kernel (80, 0, 0)) is moved +30 mm in Y
 * and turned 90° about Z twice over: once by the TRIAD (press on the green
 * arrow, drag, release; then Shift-drag the Z ring a quarter turn) and once by
 * TYPED cells (Y = 30, Rz = 90, Enter). Each path is then reloaded — the pose is
 * the server's, not the session's — and undone with Ctrl+Z.
 *
 * Persistence is counted at the wire: a triad release is ONE `PATCH`, typed
 * values are ONE `PATCH`, and neither a drag in progress nor an Esc-cancelled
 * edit writes anything.
 *
 * Copy (ASM-COPY) is Fusion's Copy/Paste in one chord: Ctrl+D on the grounded
 * anchor makes ONE `POST .../copy`, a free "<3>" 20 mm along X, with Move open
 * on it; Ctrl+Z then removes it as one step.
 *
 * The triad lives in WebGL, so the spec reads its handles from the
 * `data-move-triad` QA stamp (world points + the camera's view-projection) and
 * projects them to the screen itself — then does the real pointer gesture.
 */
import { expect, test, type Page } from "./fixtures";

import { balloonPose, setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { cameraPose, installSceneProbe } from "./invariants";
import { SCREENSHOT_DIR } from "./support";

type V3 = [number, number, number];

interface TriadStamp {
  canvas: [number, number, number, number];
  viewProj: number[];
  origin: V3;
  dirs: [V3, V3, V3];
  arrows: [V3, V3, V3];
  rings: { grab: V3; quarter: V3 }[];
}

const HALF = Math.SQRT1_2;

async function readTriad(page: Page): Promise<TriadStamp | null> {
  const raw = await page
    .getByTestId("viewport")
    .getAttribute("data-move-triad");
  return raw === null ? null : (JSON.parse(raw) as TriadStamp);
}

/** Wait for the triad to sit at a scene-space origin, and return its stamp. */
async function triadAt(page: Page, origin: V3): Promise<TriadStamp> {
  await expect
    .poll(
      async () => {
        const t = await readTriad(page);
        if (t === null) return Number.POSITIVE_INFINITY;
        return Math.hypot(...t.origin.map((n, i) => n - (origin[i] as number)));
      },
      { timeout: 20_000, message: "the triad never reached the part's pose" },
    )
    .toBeLessThan(1e-3);
  // Then until the stamp holds still: the camera has come to rest and the
  // fixed-size handle scale has settled behind it.
  let last = "";
  await expect
    .poll(
      async () => {
        const raw =
          (await page
            .getByTestId("viewport")
            .getAttribute("data-move-triad")) ?? "";
        const still = raw !== "" && raw === last;
        last = raw;
        return still;
      },
      { timeout: 20_000, intervals: [250] },
    )
    .toBe(true);
  return JSON.parse(last) as TriadStamp;
}

/** World point → page pixels, through the stamp's view-projection. */
function toScreen(t: TriadStamp, p: V3): { x: number; y: number } {
  const [left, top, width, height] = t.canvas;
  const e = t.viewProj; // column-major
  const [x, y, z] = p;
  const cx =
    (e[0] as number) * x +
    (e[4] as number) * y +
    (e[8] as number) * z +
    (e[12] as number);
  const cy =
    (e[1] as number) * x +
    (e[5] as number) * y +
    (e[9] as number) * z +
    (e[13] as number);
  const cw =
    (e[3] as number) * x +
    (e[7] as number) * y +
    (e[11] as number) * z +
    (e[15] as number);
  return {
    x: left + ((cx / cw + 1) / 2) * width,
    y: top + ((1 - cy / cw) / 2) * height,
  };
}

/** Press at `from`, sweep to `to` in steps, release. */
async function drag(
  page: Page,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.move(from.x, from.y + 0.5);
  await page.mouse.down();
  // The handles read the pointer's ABSOLUTE position against the press, so a
  // few steps land exactly where many would; each one costs a re-render.
  const steps = 4;
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(
      from.x + ((to.x - from.x) * i) / steps,
      from.y + ((to.y - from.y) * i) / steps,
    );
  }
  await page.mouse.up();
}

/** B's settled pose: scene position + scene quaternion (x, y, z, w). */
async function settledPose(page: Page, id: string) {
  await waitForSolved(page);
  const pose = await balloonPose(page, id);
  const quat = await page
    .getByTestId(`assembly-balloon-${id}`)
    .getAttribute("data-solved-quat");
  return {
    pose,
    quat: (quat ?? "").split(",").map(Number) as [
      number,
      number,
      number,
      number,
    ],
  };
}

/**
 * The moved pose, asserted in scene terms: kernel (80, 30, 0) is scene
 * (80, 0, -30), and a quarter turn about kernel +Z is a quarter turn about
 * scene +Y, quaternion (0, √½, 0, √½).
 */
async function expectMoved(page: Page, id: string, tolerance: number) {
  await expect
    .poll(
      async () => {
        const { pose, quat } = await settledPose(page, id);
        if (pose === null || pose.stale) return "stale";
        const ok =
          Math.abs(pose.x - 80) < tolerance &&
          Math.abs(pose.y) < tolerance &&
          Math.abs(pose.z + 30) < tolerance &&
          Math.abs(quat[0]) < 1e-3 &&
          Math.abs(Math.abs(quat[1]) - HALF) < 1e-3 &&
          Math.abs(quat[2]) < 1e-3 &&
          Math.abs(Math.abs(quat[3]) - HALF) < 1e-3;
        return ok ? "moved" : JSON.stringify({ pose, quat });
      },
      { timeout: 30_000 },
    )
    .toBe("moved");
}

/** B back at its seed: kernel (80, 0, 0), identity orientation. */
async function expectAtSeed(page: Page, id: string) {
  await expect
    .poll(
      async () => {
        const { pose, quat } = await settledPose(page, id);
        if (pose === null || pose.stale) return "stale";
        const ok =
          Math.abs(pose.x - 80) < 1e-3 &&
          Math.abs(pose.y) < 1e-3 &&
          Math.abs(pose.z) < 1e-3 &&
          Math.abs(Math.abs(quat[3]) - 1) < 1e-4;
        return ok ? "seed" : JSON.stringify({ pose, quat });
      },
      { timeout: 30_000 },
    )
    .toBe("seed");
}

/** Count the placement PATCHes the page sends. */
function countPatches(page: Page): { count: () => number } {
  let n = 0;
  page.on("request", (request) => {
    if (
      request.method() === "PATCH" &&
      /\/instances\/[0-9a-f-]+/.test(request.url()) &&
      (request.postData() ?? "").includes("placement")
    ) {
      n += 1;
    }
  });
  return { count: () => n };
}

test.describe("Assembly Move (S5a)", () => {
  // Two-instance setup, two gestures, a reload and the undos: past the 60 s
  // default on a loaded software-GL box (measured 66 s), well inside on CI.
  test.describe.configure({ timeout: 150_000 });

  test("the triad moves 30 in Y and turns 90° about Z; one PATCH per release; reload keeps it; Ctrl+Z restores", async ({
    page,
  }) => {
    // The LIVE camera (not the settle stamp, which a user orbit never writes).
    await installSceneProbe(page);
    const { idA, idB } = await setupTwoInstances(page);
    const patches = countPatches(page);

    // The grounded anchor wears the pin, and Move says why it is not offered.
    await expect(
      page.getByTestId(`assembly-balloon-${idA}`).locator("svg"),
    ).toHaveCount(1);
    await page.getByTestId(`instance-select-${idA}`).click();
    await expect(page.getByTestId("move-instance")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(page.getByTestId("move-instance")).toHaveAccessibleDescription(
      /Grounded/,
    );

    // Select the free plate and open Move from the command band.
    await page.getByTestId(`instance-select-${idB}`).click();
    await page.getByTestId("move-instance").click();
    await expect(page.getByTestId("move-panel")).toBeVisible();
    await expect(page.getByTestId("move-y")).toHaveValue("0");

    // The workspace opens on the FRONT view, which looks straight down the
    // kernel Y axis. From the TOP view the Y arrow lies flat on the screen
    // and the Z ring is a true circle, so both gestures read at full length.
    await page.getByTestId("view-top").click();

    // 1) Drag the green (kernel Y) arrow 30 mm along its own axis.
    let triad = await triadAt(page, [80, 0, 0]);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-move-triad.png`,
    });
    const grab = triad.arrows[1];
    const dirY = triad.dirs[1];
    const target: V3 = [
      grab[0] + 30 * dirY[0],
      grab[1] + 30 * dirY[1],
      grab[2] + 30 * dirY[2],
    ];
    await drag(page, toScreen(triad, grab), toScreen(triad, target));
    // The cells followed the drag; the release wrote ONE PATCH.
    await expect
      .poll(async () => Number(await page.getByTestId("move-y").inputValue()))
      .toBeCloseTo(30, 0);
    await expect.poll(() => patches.count()).toBe(1);

    // 2) Shift-drag the Z ring a quarter turn (Shift snaps to 10°).
    triad = await triadAt(page, [
      80,
      0,
      -Number(await page.getByTestId("move-y").inputValue()),
    ]);
    await page.keyboard.down("Shift");
    await drag(
      page,
      toScreen(triad, triad.rings[2]!.grab),
      toScreen(triad, triad.rings[2]!.quarter),
    );
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("move-rz")).toHaveValue("90");
    await expect.poll(() => patches.count()).toBe(2);

    // OK with nothing pending closes the command and writes nothing more.
    await page.getByTestId("move-ok").click();
    await expect(page.getByTestId("move-panel")).toHaveCount(0);
    await expectMoved(page, idB, 0.5);
    expect(patches.count()).toBe(2);

    // The pose is the server's: a reload draws it again.
    await page.reload();
    await expectMoved(page, idB, 0.5);

    // Two releases, two undo steps: Ctrl+Z twice is back at the seed.
    await page.keyboard.press("Control+z");
    await waitForSolved(page);
    await page.keyboard.press("Control+z");
    await expectAtSeed(page, idB);

    // Esc MID-DRAG: the drag is dropped, nothing is written, and the camera
    // still orbits. drei's handles switch the orbit off on press and on again
    // only in their own pointer-up, which an unmounted triad never receives.
    await page.getByTestId(`instance-select-${idB}`).click();
    await page.getByTestId("move-instance").click();
    await page.getByTestId("view-top").click();
    const seedTriad = await triadAt(page, [80, 0, 0]);
    const press = toScreen(seedTriad, seedTriad.arrows[0]);
    await page.mouse.move(press.x, press.y);
    await page.mouse.down();
    await page.mouse.move(press.x + 40, press.y);
    await page.keyboard.press("Escape");
    await page.mouse.up();
    await expect(page.getByTestId("move-panel")).toHaveCount(0);
    await expectAtSeed(page, idB);
    expect(patches.count()).toBe(2);

    const before = (await cameraPose(page)).position;
    await page.mouse.move(300, 700);
    await page.mouse.down();
    await page.mouse.move(380, 650, { steps: 4 });
    await page.mouse.move(460, 600, { steps: 4 });
    await page.mouse.up();
    await expect
      .poll(
        async () => {
          const after = (await cameraPose(page)).position;
          return Math.hypot(...after.map((v, i) => v - (before[i] as number)));
        },
        {
          timeout: 10_000,
          message: "the camera did not orbit after Esc mid-drag",
        },
      )
      .toBeGreaterThan(1);
  });

  test("typed X/Y/Z/Rx/Ry/Rz commit on Enter as ONE PATCH; Esc cancels and restores", async ({
    page,
  }) => {
    const { idB } = await setupTwoInstances(page);
    const patches = countPatches(page);

    // M on the selected part opens Move; the first cell has focus.
    await page.getByTestId(`instance-select-${idB}`).click();
    await page.keyboard.press("m");
    await expect(page.getByTestId("move-panel")).toBeVisible();
    await expect(page.getByTestId("move-x")).toBeFocused();

    // Esc drops a typed edit: the preview returns and nothing is written.
    await page.getByTestId("move-y").fill("55");
    await expect
      .poll(async () => (await balloonPose(page, idB))?.z)
      .toBeCloseTo(-55, 3);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("move-panel")).toHaveCount(0);
    await expectAtSeed(page, idB);
    expect(patches.count()).toBe(0);

    // Type the move and commit with Enter: one PATCH, one undo step.
    await page.keyboard.press("m");
    await page.getByTestId("move-y").fill("30");
    await page.getByTestId("move-rz").fill("90");
    await page.getByTestId("move-rz").press("Enter");
    await expect(page.getByTestId("move-panel")).toHaveCount(0);
    await expectMoved(page, idB, 1e-3);
    expect(patches.count()).toBe(1);

    await page.reload();
    await expectMoved(page, idB, 1e-3);

    await page.keyboard.press("Control+z");
    await expectAtSeed(page, idB);
  });

  test("Ctrl+D copies even a grounded part: free, '<3>', +20 mm X, Move open on it; Ctrl+Z removes it", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);
    const patches = countPatches(page);
    let copies = 0;
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        /\/instances\/[0-9a-f-]+\/copy$/.test(new URL(request.url()).pathname)
      ) {
        copies += 1;
      }
    });

    // The grounded anchor refuses Move but offers Copy: in the Component
    // group and in its row's menu, both with the chord.
    await page.getByTestId(`instance-select-${idA}`).click();
    const copyButton = page.getByTestId("copy-instance");
    await expect(copyButton).not.toHaveAttribute("aria-disabled", "true");
    await expect(copyButton).toHaveAccessibleName(/^Copy — (Ctrl\+D|⌘D)$/);
    await page.getByTestId(`instance-select-${idA}`).click({ button: "right" });
    await expect(page.getByTestId("instance-ctx-copy")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("instance-context-menu")).toHaveCount(0);

    await page.keyboard.press("Control+d");

    // ONE write, and the copy lands as the third row, numbered after the two.
    await expect(page.getByTestId("instance-row")).toHaveCount(3, {
      timeout: 15_000,
    });
    const ids = await page
      .getByTestId("instance-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
      );
    const idC = ids.find((id) => id !== idA && id !== idB);
    if (idC === undefined) throw new Error("no copy row");
    await expect(page.getByTestId(`instance-select-${idC}`)).toHaveText(
      /Hole plate <3>$/,
    );

    // Fusion's paste: the copy is selected and Move is open ON IT.
    await expect(page.getByTestId("move-panel")).toBeVisible();
    await expect(page.getByTestId("move-panel")).toContainText(
      "Hole plate <3>",
    );
    await expect(page.getByTestId("move-instance")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("move-x")).toHaveValue("20");
    await expect(page.getByTestId("move-y")).toHaveValue("0");
    await expect(page.getByTestId("move-z")).toHaveValue("0");

    // The copy is free (no pin) and sits 20 mm along X from its source, which
    // is still grounded at the origin.
    await expect(
      page.getByTestId(`assembly-balloon-${idC}`).locator("svg"),
    ).toHaveCount(0);
    await expect(
      page.getByTestId(`assembly-balloon-${idA}`).locator("svg"),
    ).toHaveCount(1);
    await expect
      .poll(
        async () => {
          await waitForSolved(page);
          const pose = await balloonPose(page, idC);
          if (pose === null || pose.stale) return "stale";
          return [pose.x, pose.y, pose.z].map((n) => n.toFixed(3)).join(",");
        },
        { timeout: 30_000 },
      )
      .toBe("20.000,0.000,0.000");

    // OK with nothing typed closes Move without a write.
    await page.getByTestId("move-ok").click();
    await expect(page.getByTestId("move-panel")).toHaveCount(0);
    expect(copies).toBe(1);
    expect(patches.count()).toBe(0);

    // The copy was ONE undo step: Ctrl+Z takes it away, and nothing else.
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("instance-row")).toHaveCount(2, {
      timeout: 15_000,
    });
    await expect(page.getByTestId(`instance-select-${idC}`)).toHaveCount(0);
    await expect(page.getByTestId(`assembly-balloon-${idC}`)).toHaveCount(0);
    await expectAtSeed(page, idB);
  });
});
