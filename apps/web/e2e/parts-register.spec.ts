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

/**
 * Long enough to overrun even the widened NAME column — the ellipsis case.
 *
 * LENGTHENED 2026-08-26, and the reason is the interesting part: this spec went
 * red at `scrollWidth (449) > clientWidth (449)` when the register moved to
 * `max-w-sheet` and the REBUILD column learned to collapse. Nothing about
 * ellipsising broke — NAME simply got wide enough to fit the old fixture
 * exactly, which is the outcome REGISTER-1 was chasing. A fixture sized to a
 * layout is a gate that quietly stops testing its subject the moment the layout
 * improves, so this one now clears the widest column the drawer can offer with
 * room to spare rather than by a handful of pixels. (200 chars is the ceiling —
 * `MAX_PART_NAME_LENGTH`.)
 */
const OVERLONG =
  "Left-hand outboard motor mount adapter plate, revision C, as machined — " +
  "do not scale from this drawing, dimensions in millimetres unless stated";

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
    /**
     * …and by a MARGIN, which is an assertion about the fixture rather than the
     * product, deliberately. Twice now this spec has gone red at
     * `scrollWidth === clientWidth` because the NAME column got wider — the
     * outcome the surrounding test is celebrating — and each time the failure
     * looked like an ellipsis regression. The symmetric and much worse outcome
     * is the one nobody would have noticed: a fixture that overruns by a single
     * pixel passes while testing almost nothing. This fails loudly when the name
     * stops being comfortably too long, so the next widening is a fixture edit
     * with an obvious cause instead of a hunt.
     */
    expect(report.scrollWidth).toBeGreaterThan(report.clientWidth * 1.25);

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

/**
 * THE RETURN TRIP (REGISTER-2 / UI-REVIEW P1-3). Measured before this change on
 * a 120-part drawer at 1280x800: the register loaded FILED ascending so the part
 * you touched last was row 120; `main.scrollHeight` was 5145 px against a 756 px
 * frame with the only create control at the bottom of it; and `thead tr`
 * computed `position: static`, so scrolling lost the column headers, the sort
 * controls, the FILTER and the count together.
 */
test.describe("parts register — the return trip", () => {
  /** 120 parts, filed oldest-first; the LAST one filed is the last one worked. */
  async function seedDeepDrawer(page: import("@playwright/test").Page) {
    const { token } = await seedSession(page);
    for (let i = 1; i <= 120; i += 1) {
      await createPartViaApi(page, token, `Part ${String(i).padStart(3, "0")}`);
    }
  }

  test("opens on what you worked last, and says so on the header", async ({
    page,
  }) => {
    await seedDeepDrawer(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(120, {
      timeout: 60_000,
    });

    await expect(page.getByTestId("part-open").first()).toHaveText("Part 120");
    await expect(
      page.getByTestId("parts-sort-activity-header"),
    ).toHaveAttribute("aria-sort", "descending");
    // The order it replaced is one click away, and it still means what it said.
    await page.getByTestId("parts-sort-filed").click();
    await expect(page.getByTestId("part-open").first()).toHaveText("Part 001");
  });

  test("the drawer scrolls, the page does not, and the controls stay put", async ({
    page,
  }) => {
    await seedDeepDrawer(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(120, {
      timeout: 60_000,
    });

    const frame = await page.evaluate(() => {
      const main = document.querySelector("main")!;
      const scroller = document.querySelector<HTMLElement>(
        '[data-testid="parts-scroll"]',
      )!;
      return {
        pageOverflow: main.scrollHeight - main.clientHeight,
        drawerOverflow: scroller.scrollHeight - scroller.clientHeight,
        headerPosition: getComputedStyle(
          document.querySelector('[data-testid="parts-sort-name-header"]')!,
        ).position,
      };
    });
    // Was 5145 - 756 = 4389 px of PAGE scroll. Now the page does not scroll at
    // all and the rows do — which is what makes everything else here hold.
    expect(frame.pageOverflow).toBeLessThanOrEqual(1);
    expect(frame.drawerOverflow).toBeGreaterThan(1000);
    expect(frame.headerPosition).toBe("sticky");

    // The create control is ON SCREEN at 120 parts. It used to be at y = 5150.
    const create = page.getByTestId("create-part-name");
    await expect(create).toBeInViewport();

    // …and it is still there at the bottom of the drawer, together with the
    // sort controls, the FILTER and the count.
    await page.evaluate(() => {
      const scroller = document.querySelector<HTMLElement>(
        '[data-testid="parts-scroll"]',
      )!;
      scroller.scrollTop = scroller.scrollHeight;
    });
    await expect(page.getByTestId("part-open").last()).toBeInViewport();
    await expect(page.getByTestId("parts-sort-name-header")).toBeInViewport();
    await expect(page.getByTestId("parts-filter")).toBeInViewport();
    await expect(page.getByTestId("parts-count")).toBeInViewport();
    await expect(create).toBeInViewport();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/parts-register-120-1280.png`,
    });
  });

  test("filing from the pinned line still files into the register", async ({
    page,
  }) => {
    await seedDeepDrawer(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(120, {
      timeout: 60_000,
    });
    // The line carries the next ordinal for the WHOLE drawer, not the view.
    await expect(page.getByTestId("create-part-name")).toBeInViewport();
    await page
      .getByTestId("create-part-name")
      .fill("Filed from the pinned line");
    await page.getByTestId("create-part-submit").click();
    // Creating a part opens it (FINDINGS #22), which is the proof it was real.
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/, { timeout: 30_000 });
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(121, {
      timeout: 60_000,
    });
    // …and the newest work is the first row, which is the whole point.
    await expect(page.getByTestId("part-open").first()).toHaveText(
      "Filed from the pinned line",
    );
  });
});
