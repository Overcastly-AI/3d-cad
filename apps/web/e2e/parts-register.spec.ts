import { expect, test } from "./fixtures";

import {
  createPartViaApi,
  openRowActions,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * THE PARTS REGISTER AS A FILE BROWSER (REGISTER-1 / UI-REVIEW 2026-08-17 P1-2).
 *
 * The founder's report was "the main file page looks like an after thought". The
 * audit confirmed the read and refuted the diagnosis: the surface is considered,
 * it is just considered as a LOG BOOK, and a working engineer needs a place to
 * find one model out of two hundred. Every assertion below is one of the audit's
 * own measurements, taken in a real browser at the frame it was taken in
 * (1280x800, 18 parts + 2 folders — an empty drawer flatters any layout):
 *
 *  - NAME was 173 px of 957 (18 %) while the four row verbs held 256 px (27 %),
 *    so the widest column in a file browser was RENAME / DUPLICATE / MOVE /
 *    DELETE at 1.5x the only column that tells two rows apart;
 *  - a name that overran its cell was CLIPPED MID-GLYPH — computed
 *    `text-overflow: clip`, `title: null` — so two parts whose names diverge
 *    past the cut were indistinguishable and the rest was unrecoverable;
 *  - UNITS spent 72 px per row on `mm, mm, mm, mm`.
 *
 * The numbers are asserted as numbers on purpose. "The name column is wider now"
 * is the kind of claim that survives a regression; `>= 400 px and >= 4x the verb
 * column` does not.
 */

/** Long enough to overrun even the widened NAME column — the ellipsis case. */
const OVERLONG =
  "Left-hand outboard motor mount adapter plate, revision C, as machined";

const NAMES = [
  OVERLONG,
  "Bracket plate",
  "Rib 2",
  "Rib 10",
  "Spacer — 4 mm",
  "Housing, lower",
  "Housing, upper",
  "Gearbox cover",
  "Idler pulley",
  "Tensioner arm",
  "Shaft collar 12 mm",
  "Bearing block",
  "Mounting rail",
  "End cap",
  "Cable clamp",
  "Sensor bracket rev B",
  "Baseplate",
  "Stiffener gusset",
];

async function seedDrawer(page: import("@playwright/test").Page) {
  const { token } = await seedSession(page);
  const auth = { Authorization: `Bearer ${token}` };
  for (const name of ["Gearbox", "Fixtures"]) {
    const created = await page.request.post("/api/v1/folders", {
      data: { name, kind: "part" },
      headers: auth,
    });
    expect(created.ok()).toBeTruthy();
  }
  for (const name of NAMES) await createPartViaApi(page, token, name);
  // A real account holds more than parts; the assembly is here so the drawer is
  // not an artificially clean sample.
  await page.request.post("/api/v1/assemblies", {
    data: { name: "Drive train" },
    headers: auth,
  });
  return token;
}

/** Every column header's rendered width, keyed by the word it prints. */
async function columnWidths(
  page: import("@playwright/test").Page,
): Promise<Record<string, number>> {
  return page.evaluate(() => {
    const table = document.querySelector('[data-testid="parts-table"]')!;
    const out: Record<string, number> = {};
    table.querySelectorAll("thead th").forEach((th, index) => {
      const label = (th.textContent ?? "").trim().split("Activate")[0]!.trim();
      out[label === "" ? `col${index}` : label] = Math.round(
        th.getBoundingClientRect().width,
      );
    });
    out.total = Math.round(table.getBoundingClientRect().width);
    return out;
  });
}

test.describe("parts register — the identifying column", () => {
  test("NAME takes the width the row verbs used to, and says so in pixels", async ({
    page,
  }) => {
    await seedDrawer(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(18);

    const widths = await columnWidths(page);
    // Measured BEFORE this change, same seed, same frame: Name 173, Actions 256.
    expect(widths.Name).toBeGreaterThanOrEqual(400);
    expect(widths.Actions).toBeLessThanOrEqual(80);
    expect(widths.Name).toBeGreaterThan(4 * widths.Actions!);
    // …and NAME is now the widest column in the table, which is the whole claim.
    const widest = Math.max(
      ...Object.entries(widths)
        .filter(([key]) => key !== "total")
        .map(([, px]) => px),
    );
    expect(widths.Name).toBe(widest);

    // UNITS is not a per-row column when the whole drawer speaks one unit; the
    // fact is stated once, on the header rule.
    expect(widths.Units).toBeUndefined();
    await expect(page.getByTestId("parts-drawer-units")).toHaveText("mm");
  });

  test("a name too long for its cell ellipsises and keeps its full text", async ({
    page,
  }) => {
    await seedDrawer(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const link = page
      .getByTestId("part-row")
      .filter({ hasText: "Left-hand outboard" })
      .getByTestId("part-open");

    // Recoverable: the full name is one hover away, at BOTH widths the audit
    // measured. This is the half that was `title: null`.
    await expect(link).toHaveAttribute("title", OVERLONG);
    const report = await link.evaluate((el) => ({
      textOverflow: getComputedStyle(el).textOverflow,
      display: getComputedStyle(el).display,
      clientWidth: el.clientWidth,
      scrollWidth: el.scrollWidth,
    }));
    // Visible: an ellipsis, not a mid-glyph cut. `clip` was the computed value
    // before, because the anchor was an atomic `inline-flex` box.
    expect(report.textOverflow).toBe("ellipsis");
    expect(report.display).toBe("block");
    expect(report.scrollWidth).toBeGreaterThan(report.clientWidth);

    await page.setViewportSize({ width: 1600, height: 1000 });
    await expect(link).toHaveAttribute("title", OVERLONG);
    expect(await link.evaluate((el) => getComputedStyle(el).textOverflow)).toBe(
      "ellipsis",
    );
  });
});

test.describe("parts register — one mark holds the row's verbs", () => {
  test("the verbs are behind the mark, and DELETE still costs a confirmation", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    await createPartViaApi(page, token, "Bracket plate");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const row = page.getByTestId("part-row");
    await expect(row).toHaveCount(1);

    // Closed: one control in the action cell, not four.
    await expect(row.getByTestId("part-rename")).toHaveCount(0);
    await expect(row.getByTestId("part-actions")).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    await openRowActions(row);
    for (const verb of ["part-rename", "part-duplicate", "part-delete"]) {
      await expect(page.getByTestId(verb)).toBeVisible();
    }
    // The parts drawer supports filing, so MOVE is here too — four verbs, one
    // mark. (A drawer WITHOUT filing omits it rather than offering it inert;
    // that branch is covered in DocumentRegister.test.tsx, where the register
    // can be rendered without a `filing` prop.)
    await expect(page.getByTestId("part-move")).toBeVisible();

    await page.getByTestId("part-delete").click();
    // The menu closed behind the verb and the ROW is the confirmation.
    await expect(page.getByRole("menu")).toHaveCount(0);
    await expect(page.getByTestId("part-delete-confirm")).toBeVisible();
    await page.getByTestId("part-delete-cancel").click();
    await expect(page.getByTestId("part-row")).toHaveCount(1);
  });

  test("the mark is keyboard-reachable and Escape gives focus back", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    await createPartViaApi(page, token, "Bracket plate");
    await page.goto("/");
    const trigger = page.getByTestId("part-actions");
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menu")).toBeVisible();
    // The verbs name the row they act on — a table of "More" buttons is a
    // screen-reader list of nothing.
    await expect(page.getByRole("menu")).toHaveAttribute(
      "aria-label",
      "Actions for Bracket plate",
    );
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu")).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("founder shot — a realistic drawer at both widths", async ({ page }) => {
    await seedDrawer(page);
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(18);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/parts-register-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(page.getByTestId("parts-table")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/parts-register-1280.png`,
    });
  });
});
