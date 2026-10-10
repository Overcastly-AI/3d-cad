import { expect, type Page } from "./fixtures";

import { pickDispatch, waitForSolved } from "./assemblyFlow";

/**
 * Shared joint e2e plumbing (extracted from `assembly-joint-hinge.spec.ts`
 * when `assembly-joint-motions.spec.ts` became its second consumer): the
 * drive stamp a spec projects through, the joint readout off a tree row, and
 * the two hole-centre picks that open the Joint dialog.
 *
 * WebGL is invisible to the DOM, so a spec reads the joint's axis and the
 * camera from the `data-joint-drag` QA stamp and projects points of B to the
 * screen itself, then makes the real pointer gesture.
 */

export type V3 = [number, number, number];

export interface DriveStamp {
  canvas: [number, number, number, number];
  viewProj: number[];
  mateId: string;
  motion: string;
  point: V3;
  dir: V3;
  value: number;
  atLimit: boolean;
}

/** World (scene) point → page pixels through the stamp's view-projection. */
export function toScreen(t: DriveStamp, p: V3): { x: number; y: number } {
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
export const scene = (x: number, y: number, z: number): V3 => [x, z, -y];

/** The drive stamp once it has held still (camera at rest). */
export async function settledStamp(page: Page): Promise<DriveStamp> {
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

export interface JointReadout {
  rot: number;
  /** NaN when the motion has no slide. */
  lin: number;
  atLimit: boolean;
  originA: V3;
  originB: V3;
  axis: V3;
}

/** The settled solve's joint readout off its tree row. */
export async function readJoint(page: Page): Promise<JointReadout> {
  await waitForSolved(page);
  const row = page.getByTestId("mate-row").first();
  await expect(row).toHaveAttribute("data-joint-rot", /.+/);
  const attr = async (name: string) => (await row.getAttribute(name)) ?? "";
  const lin = await attr("data-joint-lin");
  return {
    rot: Number(await attr("data-joint-rot")),
    lin: lin === "" ? Number.NaN : Number(lin),
    atLimit: (await attr("data-joint-at-limit")) === "true",
    originA: JSON.parse(await attr("data-joint-origin-a")) as V3,
    originB: JSON.parse(await attr("data-joint-origin-b")) as V3,
    axis: JSON.parse(await attr("data-joint-axis")) as V3,
  };
}

export const gap = (a: V3, b: V3) =>
  Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

export async function openEditor(page: Page) {
  await page.getByTestId("mate-row").first().dblclick();
  await expect(page.getByTestId("joint-dialog")).toHaveAttribute(
    "data-joint-mode",
    "edit",
  );
}

/**
 * Arm Joint (J) and pick A's top hole rim then B's bottom one: the dialog
 * opens on the two hole centres (both on world +Z through (20, 12.5)).
 */
export async function pickHoleCentres(page: Page, idA: string, idB: string) {
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
  await expect(page.getByTestId("joint-dialog")).toBeVisible();
}
