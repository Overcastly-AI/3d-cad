/**
 * THE NINE GAUGE MOUNTS, AND HOW TO GET EACH ONE ON SCREEN.
 *
 * `ParametricGauge` is mounted nine times across the app — eight components,
 * one of which (`PatternGaugeLayer`) mounts two instruments on one feature:
 *
 *   extrude-depth · fillet-radius · chamfer-distance · shell-thickness
 *   revolve-angle · draft-angle · datum-offset
 *   pattern-count-gauge · pattern-spacing-gauge
 *
 * Every one of those recipes already existed, once each, inside the spec file
 * for its own verb (`extrude-grip-reach`, `fillet-chamfer-gauge`,
 * `craft9b-gauges`, `revolve-gauge`, `draft-gauge`, `pattern-gauges`). A pass
 * that must visit ALL nine cannot copy six of them; this is the DRY extraction
 * on the sixth real use, and it is deliberately the ONLY new thing this module
 * does — the openers are the same flows those specs drive, seeded through the
 * API wherever the original drove the sketcher by hand, because what is under
 * test here is the instrument, not the route to it.
 *
 * WHY EVERY OPENER ENDS IN ISO. A track pointed straight at the eye has no
 * readable direction on screen, so there is no axis to walk and no midpoint to
 * press — that is a camera artefact, not a defect, and framing it away is what
 * lets a reachability number mean something. Five of the six original specs
 * carry the same line and the same comment.
 */
import { expect, type Page } from "./fixtures";
import { waitForCameraRest } from "./invariants";
import {
  createFeature,
  rectangleSketch,
  seedCube,
  SQUARE_20,
} from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/** Every gauge id in the app, in the order this pass reports them. */
export const GAUGE_IDS = [
  "extrude-depth",
  "fillet-radius",
  "chamfer-distance",
  "shell-thickness",
  "revolve-angle",
  "draft-angle",
  "datum-offset",
  "pattern-count-gauge",
  "pattern-spacing-gauge",
] as const;

export type GaugeId = (typeof GAUGE_IDS)[number];

/** A 40 mm block section for the shell/datum mounts (craft9b's fixture). */
const SQUARE_40 = rectangleSketch(0, 0, 40, 40);

/** A washer section on XZ: 10..30 in x, 0..10 in z, clear of the revolve axis. */
export const SECTION_XZ = {
  ...rectangleSketch(10, 0, 20, 10),
  plane: { kind: "datum_plane", plane: "XZ" },
};

/**
 * A registered session and an empty part, returned TOGETHER.
 *
 * Returning only the id was the first draft and it was wrong in a way worth
 * recording: the caller then needs a token to seed features and the obvious
 * move is a second `seedSession`, which registers a DIFFERENT account. The part
 * is not that account's, so every follow-up `createFeature` comes back 404
 * `part_not_found` — a clean, loud failure that reads like a broken fixture
 * rather than like the ownership bug it is.
 */
async function openPart(
  page: Page,
  name: string,
): Promise<{ partId: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  return { partId: part.id, token: account.token };
}

/** Dismiss the first-run navigation cue, which hangs over the lower viewport. */
async function dismissNavCue(page: Page): Promise<void> {
  const cue = page.getByTestId("nav-cue-dismiss");
  if (await cue.isVisible().catch(() => false)) {
    await cue.click();
    await expect(page.getByTestId("nav-cue")).toHaveCount(0);
  }
}

async function iso(page: Page): Promise<void> {
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
}

/**
 * Pick one face-pick node by its centroid's last coordinate, read off the
 * accessible NAME rather than from a screen projection.
 *
 * `dispatchEvent("click")` rather than a real press, and stated rather than
 * hidden: several faces of a seeded cube project UNDER the top-left editor
 * panel, so a real mouse press would be measuring the panel's occlusion of the
 * pick overlay — a different (real, already-filed) question from the one this
 * module exists to ask. The gauge's own controls are all pressed for real.
 */
async function pickFaceAt(
  page: Page,
  prefix: string,
  coordinate: number,
): Promise<void> {
  const nodes = page.locator(`[data-testid^="${prefix}"]`);
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  const count = await nodes.count();
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const got = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(got) && Math.abs(got - coordinate) < 0.5) {
      await nodes.nth(i).dispatchEvent("click");
      return;
    }
  }
  throw new Error(`no ${prefix} node with last coordinate ~${coordinate}`);
}

/** Pick the first edge whose gauge ends up with a walkable projected track. */
async function pickFirstEdge(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  await nodes.first().dispatchEvent("click");
  await expect(page.getByTestId("selected-count")).not.toHaveText("0 selected");
}

export interface Mount {
  id: GaugeId;
  /** The panel field this gauge drives, for a value cross-check. */
  field: string;
  /**
   * Whether this instrument publishes a TAG (its number, drawn on the work).
   *
   * `pattern-count-gauge` passes `tag="none"` deliberately — the pattern mounts
   * two instruments on one feature and only one may speak for the pair — so its
   * `-readout` is correctly absent and a census that graded every mount the
   * same way would file a design decision as a zero-area defect. It is declared
   * here rather than probed, so the probe can assert the absence rather than
   * tolerate it.
   */
  tag: "leader" | "none";
  /** Put the gauge on screen, framed so its track has a screen direction. */
  open: (page: Page) => Promise<void>;
}

export const MOUNTS: readonly Mount[] = [
  {
    id: "extrude-depth",
    tag: "leader",
    field: "extrude-distance",
    open: async (page) => {
      const { partId, token } = await openPart(page, "Touch extrude");
      await createFeature(page, token, partId, {
        name: "Sketch1",
        feature: { type: "sketch", version: 1, params: SQUARE_20 },
        expected_tree_version: 0,
      });
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 60_000,
      });
      await page.getByTestId("new-extrude").click();
      await expect(page.getByTestId("extrude-editor")).toBeVisible();
      await page.getByTestId("extrude-distance").fill("30");
      await iso(page);
    },
  },
  {
    id: "fillet-radius",
    tag: "leader",
    field: "fillet-radius",
    open: async (page) => {
      const partId = await seedCubePart(page, "Touch fillet");
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await waitForCube(page);
      await page.getByTestId("new-fillet").click();
      await expect(page.getByTestId("fillet-editor")).toBeVisible();
      await page.getByTestId("fillet-radius").fill("8");
      await page.getByTestId("fillet-mode-pick").click();
      await iso(page);
      await pickFirstEdge(page);
    },
  },
  {
    id: "chamfer-distance",
    tag: "leader",
    field: "chamfer-distance",
    open: async (page) => {
      const partId = await seedCubePart(page, "Touch chamfer");
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await waitForCube(page);
      await page.getByTestId("new-chamfer").click();
      await expect(page.getByTestId("chamfer-editor")).toBeVisible();
      await page.getByTestId("chamfer-distance").fill("8");
      await page.getByTestId("chamfer-mode-pick").click();
      await iso(page);
      await pickFirstEdge(page);
    },
  },
  {
    id: "shell-thickness",
    tag: "leader",
    field: "shell-thickness",
    open: async (page) => {
      const partId = await seedBlockPart(page, "Touch shell");
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await expect(page.getByTestId("prop-volume")).toContainText("64,000", {
        timeout: 60_000,
      });
      await page.getByTestId("new-shell").click();
      await expect(page.getByTestId("shell-editor")).toBeVisible();
      await pickFaceAt(page, "shell-face-", 40);
      await expect(page.getByTestId("shell-open-count")).toHaveText(
        "1 face open",
      );
      await page.getByTestId("shell-thickness").fill("6");
      await iso(page);
    },
  },
  {
    id: "revolve-angle",
    tag: "leader",
    field: "revolve-angle",
    open: async (page) => {
      const { partId, token } = await openPart(page, "Touch revolve");
      await createFeature(page, token, partId, {
        name: "Section",
        feature: { type: "sketch", version: 1, params: SECTION_XZ },
        expected_tree_version: 0,
      });
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 60_000,
      });
      const action = page.getByTestId("new-revolve");
      await expect(action).toBeEnabled({ timeout: 30_000 });
      await action.click();
      await expect(page.getByTestId("revolve-editor")).toBeVisible();
      // MID-RANGE, and it is load-bearing. The seed angle is 360, which is
      // `MAX_REVOLVE_DEG`, so a drag that increases the value is CLAMPED and
      // the honest reading "grabbed=true, 360 -> 360" reads exactly like a dead
      // handle. Opening at 120 lets the instrument move in both directions, so
      // a value that does not move is a defect rather than a bound.
      await page.getByTestId("revolve-angle").fill("120");
      await iso(page);
    },
  },
  {
    id: "draft-angle",
    tag: "leader",
    field: "draft-angle",
    open: async (page) => {
      const partId = await seedCubePart(page, "Touch draft");
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await waitForCube(page);
      await page.getByTestId("new-draft").click();
      await expect(page.getByTestId("draft-editor")).toBeVisible();
      await iso(page);
      // A SIDE face (centroid at mid-height) meets the neutral plane along its
      // own bottom edge, which is the line the taper pivots on. The TOP face is
      // parallel to it and correctly grows no instrument at all.
      await pickFaceAt(page, "draft-face-", 10);
      await expect(page.getByTestId("draft-taper-count")).toHaveText(
        "1 face tapered",
      );
    },
  },
  {
    id: "datum-offset",
    tag: "leader",
    field: "datum-offset",
    open: async (page) => {
      const partId = await seedBlockPart(page, "Touch datum");
      await page.goto(`/parts/${partId}`);
      await dismissNavCue(page);
      await expect(page.getByTestId("prop-volume")).toContainText("64,000", {
        timeout: 60_000,
      });
      await page.getByTestId("tool-datum").click();
      await expect(page.getByTestId("datum-editor")).toBeVisible();
      // The KIND is named rather than inherited: datum seeds itself from
      // whatever face was selected when invoked, so leaving it implicit makes
      // the seat depend on test ORDER.
      await page.getByTestId("datum-kind").selectOption("offset");
      await page.getByTestId("datum-offset").fill("25");
      await iso(page);
    },
  },
  {
    id: "pattern-count-gauge",
    tag: "none",
    field: "pattern-count",
    open: openPattern,
  },
  {
    id: "pattern-spacing-gauge",
    tag: "leader",
    field: "pattern-spacing",
    open: openPattern,
  },
];

/** A part whose body is a 20 mm cube at the origin. */
async function seedCubePart(page: Page, name: string): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await seedCube(page, account.token, part.id);
  return part.id;
}

/** A part whose body is a 40 mm block at the origin. */
async function seedBlockPart(page: Page, name: string): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_40 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 40,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 60_000,
  });
}

/** Both pattern instruments on one seeded cube. */
async function openPattern(page: Page): Promise<void> {
  const partId = await seedCubePart(page, "Touch pattern");
  await page.goto(`/parts/${partId}`);
  await dismissNavCue(page);
  await waitForCube(page);
  await page.getByTestId("new-pattern").click();
  await expect(page.getByTestId("pattern-editor")).toBeVisible();
  await iso(page);
  await expect(page.getByTestId("pattern-count-gauge-handle")).toBeVisible();
  await expect(page.getByTestId("pattern-spacing-gauge-handle")).toBeVisible();
}
