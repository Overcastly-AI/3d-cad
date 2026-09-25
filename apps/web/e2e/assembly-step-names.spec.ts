import { readFile } from "node:fs/promises";

import type { StepImportResult } from "../src/api/assemblyImport";

import { expect, test, type Page } from "./fixtures";

import { seedCube, seedDenseHolePlate } from "./partSeed";
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

/**
 * Build an assembly through the real register + workspace — one click per
 * entry of `partIds`, in order — then click the real STEP cell and return the
 * file's text. The names under test are minted by the workspace and carried by
 * the browser's own evaluate/export request, so none of this is seeded over
 * the API.
 */
async function buildAndExportStep(
  page: Page,
  assemblyName: string,
  partIds: readonly string[],
): Promise<string> {
  await page.goto("/assemblies");
  await page.getByTestId("create-assembly-name").fill(assemblyName);
  await page.getByTestId("create-assembly-name").press("Enter");
  const row = page
    .getByTestId("assembly-row")
    .filter({ hasText: assemblyName });
  await expect(row).toBeVisible();
  await row.getByTestId("assembly-open").click();
  await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);

  await page.getByTestId("add-instance").click();
  for (const [index, partId] of partIds.entries()) {
    await page.getByTestId(`add-instance-part-${partId}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(index + 1, {
      timeout: 30_000,
    });
  }
  await page.getByTestId("add-instance-done").click();

  const step = page.getByTestId("assembly-export-band-step");
  await expect(step).toBeEnabled({ timeout: 30_000 });
  return (await download(page, "assembly-export-band-step")).toString("utf-8");
}

/** Every name in the file that is a bare UUID — the S-22 symptom itself. */
function uuidNames(text: string): string[] {
  return [...productNames(text), ...occurrenceNames(text)].filter((name) =>
    UUID_RE.test(name),
  );
}

test.describe("Assemblies — the exported STEP names its components", () => {
  test("two instances of an accented part export as named occurrences and one shared PRODUCT", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, PART_NAME);
    await seedCube(page, account.token, part.id);

    // Two instances of ONE part: the case where the instance/part naming split
    // is observable at all (they must share a single PRODUCT and differ at the
    // occurrence).
    const text = await buildAndExportStep(page, "Flange stack", [
      part.id,
      part.id,
    ]);

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
    expect(uuidNames(text)).toEqual([]);
  });

  test("the audit's two-part assembly names both components by part name, in the bytes and read back through XCAF", async ({
    page,
  }) => {
    // `AUDIT-PRODUCT` S-22's exact shape: TWO DIFFERENT parts, one instance
    // each, under "Chassis subassembly". It differs from the case above in the
    // one way the writer cares about — two PRODUCTs, not one shared — and it is
    // the file the audit actually opened. The parts get different geometry on
    // purpose: import dedups parts by body hash, so two identical cubes would
    // read back as ONE part and the read-back could not tell the names apart.
    test.setTimeout(120_000);
    const account = await seedSession(page);
    const bracket = await createPartViaApi(
      page,
      account.token,
      "Chassis bracket",
    );
    await seedCube(page, account.token, bracket.id);
    const plate = await createPartViaApi(page, account.token, "Mounting plate");
    await seedDenseHolePlate(page, account.token, plate.id);

    const text = await buildAndExportStep(page, "Chassis subassembly", [
      bracket.id,
      plate.id,
    ]);

    // The bytes. Instance numbering is workspace-global (`AssemblyPage` mints
    // `${part.name} <${instances.length + 1}>`), hence `<2>` on the plate.
    expect(occurrenceNames(text)).toEqual([
      "Chassis bracket <1>",
      "Mounting plate <2>",
    ]);
    const products = productNames(text);
    expect(products.filter((name) => name === "Chassis bracket")).toHaveLength(
      1,
    );
    expect(products.filter((name) => name === "Mounting plate")).toHaveLength(
      1,
    );
    expect(products).toContain("Chassis subassembly");
    expect(uuidNames(text)).toEqual([]);

    // Read back the way the audit did: OCCT's XCAF reader, which is what the
    // app's own assembly import runs (`_step_assembly_parse_worker` takes each
    // component's name from its NAUO label, falling back to its PRODUCT). The
    // audit's reading was `comp: c7ebc346-…`; a regression anywhere between
    // the request and the reader shows up here as a UUID instance name.
    const imported = await page.request.post(
      "/api/v1/assemblies/import?name=Chassis%20subassembly%20readback",
      {
        data: Buffer.from(text, "utf-8"),
        headers: {
          Authorization: `Bearer ${account.token}`,
          "Content-Type": "application/octet-stream",
        },
      },
    );
    expect(imported.status(), await imported.text()).toBe(201);
    // The generated wire type (via the app's own import client), not a
    // hand-written shape — narrowed on `kind` exactly as the register does.
    const result = (await imported.json()) as StepImportResult;
    if (result.kind !== "assembly") {
      throw new Error(
        `read-back imported as a ${result.kind}, not an assembly`,
      );
    }
    expect(result.part_ids).toHaveLength(2);
    expect(result.assembly.instances.map((i) => i.name).sort()).toEqual([
      "Chassis bracket <1>",
      "Mounting plate <2>",
    ]);
  });
});
