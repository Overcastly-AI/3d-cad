import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import type { FileChooser } from "@playwright/test";

import { expect, type Page, test } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * REACH-2 FLOW FOLLOW-UPS — the two findings UI-REVIEW 2026-08-27 held on
 * `f4c590b`, proved against the real stack.
 *
 * P1-A: the empty register's copy proposed a STEP import and the layout put it
 * **422 px below at 1280x800 and 622 px below at 1600x1000**. The measurement
 * that mattered was the second one: a gap that GROWS with the screen is a
 * layout defect, not a copy defect, which is why the fix is a fork and not a
 * reworded sentence. Both widths are measured here for exactly that reason —
 * one width could be tuned by hand and would prove nothing.
 *
 * P1-B: a long import had no `role="progressbar"` anywhere, `animationName:
 * none` on every descendant of the busy line, and no way to stop it. A 52 KB
 * fixture took 3.35 s against a 16 MiB client ceiling.
 *
 * NOTE ON METHOD, and it is the point of this file: every "the user can do
 * this" claim is asserted with the USER'S OWN MECHANISM — `elementFromPoint` at
 * the control's centre, a real `page.mouse.click`, a real `filechooser` event.
 * `toBeVisible()` is a box property and passed a control shoved outside the
 * frame last week; `click({ force: true })` skips actionability and passed a
 * target no mouse could hit. There is no `force: true` in this file and there
 * must never be one.
 */

/** The `kind: "part"` branch — small, real, and it round-trips fast. */
const FLAT_STEP = fileURLToPath(
  new URL("./fixtures/box-10x20x30.step", import.meta.url),
);

/** What the DOM measures for the empty state, in one round trip. */
interface EmptyMetrics {
  bodyBottom: number;
  bodyText: string;
  createTop: number;
  importTop: number;
  forkTop: number;
  /** `elementFromPoint` at each control's own centre, resolved to a testid. */
  hitCreate: string;
  hitImport: string;
  copyPointsDown: boolean;
  labelContrast: number;
  overflows: boolean;
}

async function measureEmpty(page: Page): Promise<EmptyMetrics> {
  return page.evaluate(() => {
    const el = (sel: string): HTMLElement => {
      const found = document.querySelector<HTMLElement>(sel);
      if (found === null) throw new Error(`no ${sel}`);
      return found;
    };
    /**
     * Which control a real pointer would actually reach at that point. This is
     * the check `toBeVisible()` cannot make: a box can have a position and a
     * size and still be under something else.
     */
    const hit = (sel: string): string => {
      const box = el(sel).getBoundingClientRect();
      const at = document.elementFromPoint(
        box.left + box.width / 2,
        box.top + box.height / 2,
      );
      return at !== null && el(sel).contains(at) ? "self" : "blocked";
    };
    const luminance = (rgb: string): number => {
      const parts = rgb.match(/\d+(\.\d+)?/g) ?? [];
      const channel = (raw: string): number => {
        const c = Number(raw) / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      return (
        0.2126 * channel(parts[0] ?? "0") +
        0.7152 * channel(parts[1] ?? "0") +
        0.0722 * channel(parts[2] ?? "0")
      );
    };

    const body = el('[data-testid="assemblies-empty"] p:nth-of-type(2)');
    const label = [...document.querySelectorAll("p")].find(
      (p) => p.textContent === "Start from a STEP file",
    );
    if (label === undefined) throw new Error("no fork label");
    const style = getComputedStyle(label);
    // The fork label paints on the register's own ground, which is the panel
    // behind it — not the page — so the pair that matters is text vs panel.
    const behind = getComputedStyle(
      el('[data-testid="assemblies-register"]'),
    ).backgroundColor;
    const a = luminance(style.color);
    const b = luminance(behind);
    const contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

    return {
      bodyBottom: Math.round(body.getBoundingClientRect().bottom),
      bodyText: body.textContent ?? "",
      createTop: Math.round(
        el('[data-testid="create-assembly-submit"]').getBoundingClientRect()
          .top,
      ),
      importTop: Math.round(
        el('[data-testid="assembly-import-button"]').getBoundingClientRect()
          .top,
      ),
      forkTop: Math.round(
        el('[data-testid="assemblies-empty-fork"]').getBoundingClientRect().top,
      ),
      hitCreate: hit('[data-testid="create-assembly-submit"]'),
      hitImport: hit('[data-testid="assembly-import-button"]'),
      copyPointsDown: /below|above|at the bottom/i.test(body.textContent ?? ""),
      labelContrast: Number(contrast.toFixed(2)),
      overflows:
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    };
  });
}

/**
 * Hold the import route open so the busy state can be observed and stopped.
 *
 * The real 52 KB fixture takes ~3.35 s, which is long enough for a human to
 * worry and too short to assert against without a race. Stalling the ROUTE (not
 * the client) keeps every other part of the path real: the request is made, the
 * bytes are on the wire, and the abort is a genuine `fetch` abort.
 */
async function stallImport(page: Page, ms: number): Promise<void> {
  await page.route("**/assemblies/import**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, ms));
    // A withdrawn request tears the route down under us; that is the case
    // under test, not an error.
    await route.continue().catch(() => undefined);
  });
}

/**
 * Choose a file THE WAY A USER DOES: a real mouse click on the verb, the real
 * file chooser it opens, and the file handed to that chooser.
 *
 * `setInputFiles` on the hidden input is the shortcut, and it lies about focus
 * in a way that matters here. The empty register autofocuses its name field, so
 * a spec that skips the click leaves the caret in a TEXT FIELD — where `Escape`
 * and `?` are correctly ignored, because a user naming an assembly must not
 * have their keystrokes stolen. Driven through the button, focus lands on the
 * button and the page accelerators are live, which is the real situation.
 * Getting this wrong cost two red tests that were reporting on the harness
 * rather than on the product.
 */
async function openChooser(page: Page): Promise<FileChooser> {
  const verb = page.getByTestId("assembly-import-button");
  await expect(verb).toBeEnabled();
  const chooser = page.waitForEvent("filechooser");
  // `locator.click()`, NOT a raw `page.mouse.click` at a pre-measured box. Both
  // are "a real click"; only this one VERIFIES it. Playwright re-resolves the
  // point at click time and runs a hit-target check, so a click that would land
  // on the wrong element fails loudly instead of doing nothing — which is what
  // a hand-rolled `mouse.click` did here, intermittently, because the register
  // settles its query after the coordinate is taken. There is no `force`
  // anywhere in this file; this is the strong end of the same spectrum.
  await verb.click();
  return chooser;
}

async function chooseFile(page: Page, file: string): Promise<void> {
  await (await openChooser(page)).setFiles(file);
}

test.describe("REACH-2 P1-A — the empty register forks", () => {
  for (const [width, height] of [
    [1280, 800],
    [1600, 1000],
  ] as const) {
    test(`both ways in sit together at ${width}x${height}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await seedSession(page);
      await page.goto("/assemblies");
      await expect(page.getByTestId("assemblies-empty-fork")).toBeVisible();

      const m = await measureEmpty(page);

      // THE FINDING, inverted. Before: 422 px at 1280 and 622 px at 1600.
      expect(m.importTop - m.bodyBottom).toBeLessThan(120);
      // The two ways in are one band apart, not a screen apart (was 364 px).
      expect(Math.abs(m.createTop - m.importTop)).toBeLessThan(60);
      // Both descend from the same fork, so neither can drift without the other.
      expect(m.forkTop).toBeLessThan(Math.min(m.createTop, m.importTop));

      // THE COPY CAN STOP GIVING DIRECTIONS. If this ever fails, the layout has
      // regressed and someone has patched it with a sentence again.
      expect(m.copyPointsDown).toBe(false);
      expect(m.bodyText).toContain("bring in a STEP");

      // Reachable by a real pointer, not merely laid out.
      expect(m.hitCreate).toBe("self");
      expect(m.hitImport).toBe("self");
      expect(m.overflows).toBe(false);
      // The fork's eyebrows are new text on an old ground — AA or nothing.
      expect(m.labelContrast).toBeGreaterThanOrEqual(4.5);

      // The end of the claim: the verb a real click reaches actually opens the
      // real file chooser. `hitImport` above proves nothing covers it;
      // `openChooser` proves the click does something. Neither alone is enough
      // — a control can be unoccluded and unwired, or wired and buried.
      const chooser = await openChooser(page);
      expect(chooser.isMultiple()).toBe(false);
      // Close it cleanly: an unanswered chooser leaves the input mid-gesture.
      await chooser.setFiles([]);

      await page.screenshot({
        path: `${SCREENSHOT_DIR}/assembly-import-empty-${width}.png`,
      });
    });
  }

  test("the offer returns to the drawer's last line once something is filed", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await seedSession(page);
    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Bolted plates");
    await page.getByTestId("create-assembly-name").press("Enter");
    await expect(page.getByTestId("assembly-row")).toHaveCount(1);

    const slot = page.getByTestId("assembly-import-slot");
    await expect(slot).toHaveAttribute("data-placement", "line");
    await expect(page.getByTestId("assemblies-empty-fork")).toHaveCount(0);

    // THE PRAISED PROPERTY, re-measured: the slot carries the register's own
    // scribed gutter, so the drawer's left rule runs unbroken from the `#`
    // header to the frame's bottom edge. Asserted as a coordinate rather than a
    // class name, because a transcribed width is exactly what would drift.
    const rules = await page.evaluate(() => {
      const left = (sel: string): number => {
        const el = document.querySelector(sel);
        if (el === null) throw new Error(`no ${sel}`);
        return Math.round(el.getBoundingClientRect().left);
      };
      const slotEl = document.querySelector(
        '[data-testid="assembly-import-slot"]',
      );
      const content = slotEl?.lastElementChild;
      if (content == null) throw new Error("no slot content column");
      return {
        // The ordinal gutter's right edge on a filed row...
        rowContent: left('[data-testid="assembly-row"] td:nth-child(2)'),
        // ...and where the slot's own content starts.
        slotContent: Math.round(content.getBoundingClientRect().left),
      };
    });
    expect(Math.abs(rules.rowContent - rules.slotContent)).toBeLessThanOrEqual(
      2,
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-import-line-1280.png`,
    });
  });
});

test.describe("REACH-2 P1-B — a long import says it is working, and can be stopped", () => {
  test("announces itself as a named progressbar, counts, and withdraws", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await seedSession(page);
    await stallImport(page, 20_000);
    await page.goto("/assemblies");

    await page.getByTestId("assembly-import-input").setInputFiles(FLAT_STEP);

    // (1) ANNOUNCED. Queried BY ROLE AND NAME, which is the whole finding: the
    //     old busy line had neither, so no assistive technology could report
    //     the state at all.
    const bar = page.getByRole("progressbar", {
      name: "Importing box-10x20x30.step",
    });
    await expect(bar).toBeVisible();
    // Indeterminate by omission — a value here would be a prediction the client
    // cannot make.
    await expect(bar).not.toHaveAttribute("aria-valuenow", /.*/);

    // (2) MOVING. `animationName: none` on every descendant was the measured
    //     symptom; this is that measurement, inverted.
    const motion = await page.evaluate(() => {
      const carriage = document.querySelector(
        '[data-testid="assembly-import-progress-carriage"]',
      );
      if (carriage === null) throw new Error("no carriage");
      const style = getComputedStyle(carriage);
      const bed = carriage.parentElement?.getBoundingClientRect();
      return {
        animationName: style.animationName,
        carriageWidth: Math.round(carriage.getBoundingClientRect().width),
        bedWidth: Math.round(bed?.width ?? 0),
      };
    });
    expect(motion.animationName).toBe("travel");
    // The carriage is a carriage, not a fill: under motion it must not span
    // the bed, or it would be claiming a fraction.
    expect(motion.carriageWidth).toBeLessThan(motion.bedWidth);

    // (3) ALIVE. The counter is driven by React, so it advances only while the
    //     app is actually running — which a CSS animation cannot prove.
    const elapsed = page.getByTestId("assembly-import-progress-elapsed");
    await expect(elapsed).toHaveText("0s elapsed");
    await expect(elapsed).toHaveText(/[1-9]\d*s elapsed/, { timeout: 5_000 });

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-import-busy-1280.png`,
    });

    // (4) STOPPABLE, by a real mouse at the control's own centre.
    const cancel = page.getByTestId("assembly-import-cancel");
    const box = await cancel.boundingBox();
    expect(box).not.toBeNull();
    const reached = await page.evaluate(
      (point) => {
        const at = document.elementFromPoint(point.x, point.y);
        return at?.getAttribute("data-testid") ?? at?.tagName ?? "none";
      },
      {
        x: (box?.x ?? 0) + (box?.width ?? 0) / 2,
        y: (box?.y ?? 0) + (box?.height ?? 0) / 2,
      },
    );
    expect(reached).toBe("assembly-import-cancel");
    await page.mouse.click(
      (box?.x ?? 0) + (box?.width ?? 0) / 2,
      (box?.y ?? 0) + (box?.height ?? 0) / 2,
    );

    // Back to the invitation — NOT to an error. The user did this on purpose,
    // and "Import failed" would be blaming them for their own decision.
    await expect(page.getByTestId("assembly-import-hint")).toBeVisible();
    await expect(page.getByTestId("assembly-import-error")).toHaveCount(0);
    await expect(page.getByTestId("assembly-import-progress")).toHaveCount(0);
    // Nothing was filed by the request we withdrew.
    await expect(page.getByTestId("assembly-row")).toHaveCount(0);
  });

  test("Escape withdraws it too, because that is what Escape means here", async ({
    page,
  }) => {
    await seedSession(page);
    await stallImport(page, 20_000);
    await page.goto("/assemblies");
    // Through the verb, so focus is where a real user's would be — see
    // `chooseFile`. Escape is deliberately inert inside the name field.
    await chooseFile(page, FLAT_STEP);
    await expect(page.getByTestId("assembly-import-progress")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("assembly-import-hint")).toBeVisible();
    await expect(page.getByTestId("assembly-import-error")).toHaveCount(0);
  });
});

test.describe("REACH-2 P1-B — the reduced-motion path", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("says 'working' without moving anything", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await seedSession(page);
    await stallImport(page, 20_000);
    await page.goto("/assemblies");
    await page.getByTestId("assembly-import-input").setInputFiles(FLAT_STEP);

    // Still announced — the semantics are not a function of the motion
    // preference, which is the failure mode of "just turn the animation off".
    await expect(
      page.getByRole("progressbar", { name: "Importing box-10x20x30.step" }),
    ).toBeVisible();

    const still = await page.evaluate(() => {
      const carriage = document.querySelector(
        '[data-testid="assembly-import-progress-carriage"]',
      );
      if (carriage === null) throw new Error("no carriage");
      const bed = carriage.parentElement;
      return {
        animationName: getComputedStyle(carriage).animationName,
        carriageWidth: Math.round(carriage.getBoundingClientRect().width),
        bedWidth: Math.round(bed?.getBoundingClientRect().width ?? 0),
      };
    });
    expect(still.animationName).toBe("none");
    // A STATIONARY 28 % segment would read as "28 % done". It fills the bed
    // instead, so it states engagement and claims no progress.
    expect(still.carriageWidth).toBe(still.bedWidth);

    // And the liveness signal survives, which is the whole reason it exists:
    // an animation is not the only way to say "working".
    const elapsed = page.getByTestId("assembly-import-progress-elapsed");
    await expect(elapsed).toHaveText(/[1-9]\d*s elapsed/, { timeout: 5_000 });

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-import-busy-reduced-1280.png`,
    });
    await page.getByTestId("assembly-import-cancel").click();
  });
});

test.describe("REACH-2 P2-A / P3-B — the smaller two", () => {
  test("a result can be dismissed, and the slot's instruction comes back", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/assemblies");
    await page.getByTestId("assembly-import-input").setInputFiles(FLAT_STEP);

    const result = page.getByTestId("assembly-import-result");
    await expect(result).toBeVisible({ timeout: 60_000 });
    // A result evicts the hint, which is correct for one line — but it used to
    // evict it FOREVER, so the slot stopped reading as an affordance after a
    // single import.
    await expect(page.getByTestId("assembly-import-hint")).toHaveCount(0);

    const dismiss = page.getByTestId("assembly-import-dismiss");
    const box = await dismiss.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(
      (box?.x ?? 0) + (box?.width ?? 0) / 2,
      (box?.y ?? 0) + (box?.height ?? 0) / 2,
    );
    await expect(page.getByTestId("assembly-import-hint")).toBeVisible();
    await expect(result).toHaveCount(0);
  });

  test("the I chord is on the sheet, not only on the page that has it", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/assemblies");
    await expect(page.getByTestId("assemblies-register")).toBeVisible();
    // The empty register hands the caret to its name field, and `?` is a
    // character there — correctly so. Step out of the field first; this models
    // "the user is not mid-sentence", which is when any chord is live.
    await page.evaluate(() =>
      (document.activeElement as HTMLElement | null)?.blur(),
    );
    await page.keyboard.press("?");
    const sheet = page.getByTestId("shortcut-sheet");
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText("Import a STEP file");
  });
});

test.describe("REACH-2 — what the review praised, still true", () => {
  test("an oversize file is refused BEFORE the wire, and the refusal is readable", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/assemblies");

    const posts: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/assemblies/import"))
        posts.push(request.url());
    });

    await page.getByTestId("assembly-import-input").setInputFiles({
      name: "supplier.step",
      mimeType: "application/step",
      buffer: Buffer.alloc(17 * 1024 * 1024, 0x20),
    });

    const error = page.getByTestId("assembly-import-error");
    await expect(error).toContainText("16 MB limit");
    await expect(error).toHaveAttribute("role", "alert");
    // The claim is PRE-UPLOAD, so the evidence is the absence of a request —
    // not the presence of a message, which a server could also have produced.
    expect(posts).toEqual([]);

    // Keyboard-readable, with a real focusable exit rather than a hover trap.
    await page.getByTestId("assembly-import-dismiss").focus();
    await expect(page.getByTestId("assembly-import-dismiss")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(error).toHaveCount(0);
    await expect(page.getByTestId("assembly-import-hint")).toBeVisible();
  });

  test("a flat STEP routes to a part with a working link, and a second copy is renamed", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/assemblies");
    const bytes = await readFile(FLAT_STEP, "utf-8");
    expect(bytes.startsWith("ISO-10303-21")).toBe(true);

    await page.getByTestId("assembly-import-input").setInputFiles(FLAT_STEP);
    const result = page.getByTestId("assembly-import-result");
    await expect(result).toBeVisible({ timeout: 60_000 });
    await expect(result).toHaveAttribute("data-import-kind", "part");
    await expect(page.getByTestId("assembly-import-dismiss")).toBeVisible();
    await page.getByTestId("assembly-import-dismiss").click();

    // The collision recovery: same file again yields "(2)", never an error.
    await page.getByTestId("assembly-import-input").setInputFiles(FLAT_STEP);
    await expect(result).toBeVisible({ timeout: 60_000 });
    await expect(result).toContainText("box-10x20x30 (2)");
    await expect(page.getByTestId("assembly-import-error")).toHaveCount(0);

    await page.getByTestId("assembly-import-open").click();
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
  });
});
