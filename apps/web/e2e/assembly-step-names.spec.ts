import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * STEPNAME-1B — DOES THE ASSEMBLY STEP A USER DOWNLOADS NAME ITS COMPONENTS?
 *
 * `AUDIT-PRODUCT` S-22 opened an exported assembly and found its components
 * named by raw UUID. The geometry writer was never the cause — it has threaded
 * the instance name into the NAUO and the shared PRODUCT since `0d3ea59`, and
 * the UUID is its documented fallback for a request that carries no name. The
 * caller that omitted it was the browser's own `buildEvaluateAssemblyRequest`,
 * whose output IS the export request. So the whole defect lived in one field,
 * and no backend test could see it: `services/documents` sends the name.
 *
 * WHY THIS SPEC EXISTS RATHER THAN A UNIT ASSERTION ON THE REQUEST OBJECT. A
 * field in a request proves that we sent it, not that it meant anything —
 * params models are pydantic-default `extra="ignore"`, so a misspelt field name
 * validates, evaluates and returns the legacy behaviour with every gate
 * agreeing (measured on this repo, PATTERN-1). The only oracle that cannot be
 * fooled that way is the artefact the user actually receives, so this clicks
 * the real STEP cell in the real band, takes the bytes off the wire, and parses
 * the part-21 text.
 *
 * WHY A NON-ASCII NAME. It is the case that was broken end to end until
 * `6c52d5f`: `TCollection_ExtendedString(str)` binds `isMultiByte=False` and
 * walked UTF-8 bytes one at a time, so `"Flänsch"` reached the file as the
 * UTF-8 encoding of its own latin-1 misreading. A present-and-corrupted name is
 * worse than an absent one — a STEP file is what the user hands to a machinist
 * — so sending the name at all was only safe once that was fixed, and this
 * keeps both halves pinned together. Note the assertion has to DECODE the
 * literal as UTF-8 and demand equality: the name was "in the file" before that
 * fix too, which is exactly why a substring check would have passed on
 * mojibake.
 */

const PART_NAME = "Flänsch";

/**
 * A part-21 string literal, with the standard's quote escape written out.
 *
 * `[^']*` is the naive form and it is wrong here: it stops at the first quote
 * of an escaped pair (`'Jim''s bracket'`), silently truncating the name, which
 * reads exactly like "the name is missing from the file". Mirrors the kernel
 * suite's `_LITERAL` (`services/geometry/tests/test_step_names.py`) so the two
 * sides of the wire are read by the same rule.
 */
const LITERAL = "'((?:[^']|'')*)'";
const PRODUCT_RE = new RegExp(
  `PRODUCT\\s*\\(\\s*${LITERAL}\\s*,\\s*${LITERAL}`,
  "g",
);
const NAUO_RE = new RegExp(
  `NEXT_ASSEMBLY_USAGE_OCCURRENCE\\s*\\(\\s*${LITERAL}\\s*,\\s*${LITERAL}`,
  "g",
);

/** OCCT stamps its own translator PRODUCTs in; asserting over them is vacuous. */
const OCCT_PRODUCT_PREFIX = "Open CASCADE STEP translator";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * A part-21 literal as the string the writer meant.
 *
 * Both of the standard's escapes have to be undone or a name containing either
 * reads as absent: a quote is doubled, and a backslash is doubled because
 * backslash introduces the control directives.
 */
function unescapeLiteral(literal: string): string {
  return literal.replace(/''/g, "'").replace(/\\\\/g, "\\");
}

/** Matches of `re` group 2 (the NAME field of PRODUCT / NAUO), in file order. */
function names(text: string, re: RegExp): string[] {
  return [...text.matchAll(re)].map((match) => unescapeLiteral(match[2] ?? ""));
}

/** OUR PRODUCT names — OCCT's own translator entries dropped. */
function productNames(text: string): string[] {
  return names(text, PRODUCT_RE).filter(
    (name) => !name.startsWith(OCCT_PRODUCT_PREFIX),
  );
}

/**
 * Every NON-EMPTY occurrence name. OCCT writes a second, unnamed NAUO level per
 * component (the part body is a compound, so it becomes a sub-assembly); those
 * carry `''`.
 */
function occurrenceNames(text: string): string[] {
  return names(text, NAUO_RE).filter((name) => name !== "");
}

/** Click a band cell and return the downloaded bytes. */
async function download(page: Page, testId: string): Promise<Buffer> {
  const pending = page.waitForEvent("download");
  await page.getByTestId(testId).click();
  const file = await pending;
  return readFile(await file.path());
}

test.describe("Assemblies — the exported STEP names its components", () => {
  test("two instances of an accented part export as named occurrences and one shared PRODUCT", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, PART_NAME);
    await seedCube(page, account.token, part.id);

    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Flange stack");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page
      .getByTestId("assembly-row")
      .filter({ hasText: "Flange stack" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);

    // Two instances of ONE part: the case where the instance/part naming split
    // is observable at all (they must share a single PRODUCT and differ at the
    // occurrence).
    await page.getByTestId("add-instance").click();
    const cell = page.getByTestId(`add-instance-part-${part.id}`);
    for (let n = 1; n <= 2; n++) {
      await cell.click();
      await expect(page.getByTestId("instance-row")).toHaveCount(n, {
        timeout: 30_000,
      });
    }
    await page.getByTestId("add-instance-done").click();

    const step = page.getByTestId("assembly-export-band-step");
    await expect(step).toBeEnabled({ timeout: 30_000 });
    const text = (await download(page, "assembly-export-band-step")).toString(
      "utf-8",
    );

    // The occurrences carry the instance names the workspace minted, whole.
    expect(occurrenceNames(text)).toEqual([
      `${PART_NAME} <1>`,
      `${PART_NAME} <2>`,
    ]);

    // ONE shared PRODUCT for the part, suffix stripped — the writer's rule, and
    // the reason the client must send the name verbatim rather than pre-strip.
    const products = productNames(text);
    expect(products.filter((name) => name === PART_NAME)).toHaveLength(1);
    expect(products).toContain("Flange stack");

    // The regression itself: nothing in the file is named by a UUID. Asserted
    // over every name rather than against the two known ids, so it also catches
    // a future caller that drops the field again.
    expect(
      [...products, ...occurrenceNames(text)].filter((name) =>
        UUID_RE.test(name),
      ),
    ).toEqual([]);
  });
});
