import { expect, type Page } from "@playwright/test";

export const SCREENSHOT_DIR = "../../docs/screenshots";

/** Count distinct colors on the WebGL canvas — proves a real render. */
export async function distinctCanvasColors(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    const colors = new Set<number>();
    for (let i = 0; i < data.length; i += 64) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      colors.add((r << 16) | (g << 8) | b);
    }
    return colors.size;
  });
}

/** Wait until the tessellation is applied AND visibly rendered on canvas. */
export async function expectRenderedModel(page: Page): Promise<void> {
  await expect(page.getByTestId("tessellation-status")).toHaveText(
    "Up to date",
    {
      timeout: 30_000,
    },
  );
  // Grid + lit aluminum model produce far more shades than an empty ground.
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 15_000 })
    .toBeGreaterThan(24);
}
