import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { distinctCanvasColors, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * REACH-2 — importing a STEP assembly INTO the register, driven entirely
 * through the real UI against the real stack.
 *
 * `POST /api/v1/assemblies/import` has existed and been service-tested since
 * SLICE-2b, and no user could reach it: there was no control anywhere in the
 * app that posted to it. This spec IS the reachability proof, so it seeds
 * nothing over the API that the feature under test is supposed to produce — the
 * assembly it imports is one this same browser built and exported minutes
 * earlier through the export band.
 *
 * The round trip is the point: build 2 instances of 1 part in the UI → export
 * one STEP → import that file → get 2 instances of 1 deduped part back, on
 * screen, rendering. A stub file could not prove the dedupe, and a fixture
 * could not prove the export and import agree.
 */

/** A flat, single-body STEP — the `kind: "part"` branch of the same route. */
const FLAT_STEP = fileURLToPath(
  new URL("./fixtures/box-10x20x30.step", import.meta.url),
);

/**
 * Drop a file on the register the way a browser does it.
 *
 * `setInputFiles` drives the picker; nothing but a real `DataTransfer` carrying
 * a `File` drives the DROP, which is a separate code path (and the one a
 * migrating engineer holding a supplier file actually uses). The handle is
 * built in the page so the `File` belongs to that realm.
 */
async function dropOnRegister(
  page: Page,
  filename: string,
  content: string,
): Promise<void> {
  const dataTransfer = await page.evaluateHandle(
    ([text, name]) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([text], name, { type: "application/step" }));
      return transfer;
    },
    [content, filename] as const,
  );
  const target = page.getByTestId("assemblies-drop-target");
  await target.dispatchEvent("dragenter", { dataTransfer });
  await target.dispatchEvent("dragover", { dataTransfer });
  // The page ARMS on the drag, before anything is released — that is what makes
  // the whole register a target rather than an onDrop handler nobody can see.
  await expect(target).toHaveAttribute("data-drop-armed", "true");
  await target.dispatchEvent("drop", { dataTransfer });
  await expect(target).toHaveAttribute("data-drop-armed", "false");
}

test.describe("STEP assembly import", () => {
  test("round trip: export a 2-instance assembly, import it back", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    await setupTwoInstances(page);

    // Export the assembly the user just built — one STEP with AP214 product
    // structure: one product, two occurrences.
    const bandStep = page.getByTestId("assembly-export-band-step");
    await expect(bandStep).toBeEnabled({ timeout: 30_000 });
    const downloadPromise = page.waitForEvent("download");
    await bandStep.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("bolted-plates.step");
    // `download.path()` is an extension-less artifact name, and the import
    // affordance reads the EXTENSION (as a browser file picker would), so the
    // file has to be saved under the name the server proposed before it can be
    // handed back through the UI.
    const exported = join(
      await mkdtemp(join(tmpdir(), "loft-import-")),
      download.suggestedFilename(),
    );
    await download.saveAs(exported);
    const stepText = await readFile(exported, "utf-8");
    expect(stepText.startsWith("ISO-10303-21")).toBe(true);

    // ── Back on the register, with exactly one assembly filed. ──────────────
    await page.goto("/assemblies");
    await expect(page.getByTestId("assembly-row")).toHaveCount(1);
    const slot = page.getByTestId("assembly-import-slot");
    await expect(slot).toBeVisible();
    await expect(page.getByTestId("assembly-import-button")).toBeEnabled();

    // 1) THE PICKER PATH.
    await page.getByTestId("assembly-import-input").setInputFiles(exported);
    await expect(page.getByTestId("assembly-import-busy")).toContainText(
      "bolted-plates.step",
    );

    const result = page.getByTestId("assembly-import-result");
    await expect(result).toBeVisible({ timeout: 60_000 });
    await expect(result).toHaveAttribute("data-import-kind", "assembly");
    // TWO instances from ONE part: the server deduped the repeated product,
    // which is the whole claim of an assembly import as opposed to N imports.
    await expect(result).toContainText("2 instances from 1 part");

    // The row is in the drawer with no reload — the register is live.
    await expect(page.getByTestId("assembly-row")).toHaveCount(2);
    const imported = page
      .getByTestId("assembly-row")
      .filter({ hasText: "bolted-plates" });
    await expect(imported).toHaveCount(1);

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-import-register-1280.png`,
    });

    // 2) THE DROP PATH, with the SAME file — which also proves the name
    //    collision resolves instead of dead-ending: "bolted-plates" is taken,
    //    so the second copy is filed as "bolted-plates (2)".
    await dropOnRegister(page, "bolted-plates.step", stepText);
    await expect(result).toBeVisible({ timeout: 60_000 });
    await expect(result).toContainText("bolted-plates (2)");
    await expect(page.getByTestId("assembly-row")).toHaveCount(3);

    // 3) OPEN what was imported and prove it is a real, solvable assembly.
    await page.getByTestId("assembly-import-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
    await expect(page.getByTestId("assembly-name")).toHaveText(
      "bolted-plates (2)",
    );
    await expect(page.getByTestId("instance-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    // Two lit plates at their imported placements paint many shades; a blank
    // canvas or one un-placed body cannot.
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-import-opened-1280.png`,
    });
  });

  test("a flat STEP is filed as a part, and says so", async ({ page }) => {
    await seedSession(page);
    await page.goto("/assemblies");

    // The empty register offers the import as an EQUAL to the scribe form, not
    // as a sentence pointing at a strip 422 px down the page — see
    // `assembly-import-flow.spec.ts`, which measures the geometry. This asserts
    // the structure the copy used to have to describe: the copy now names both
    // ways and points at neither, so a text match on "the slot below" is
    // exactly what must NOT come back.
    await expect(page.getByTestId("assemblies-empty-fork")).toBeVisible();
    await expect(page.getByTestId("assemblies-empty")).not.toContainText(
      "below",
    );
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(page.getByTestId("assembly-import-slot")).toHaveAttribute(
      "data-placement",
      "fork",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-import-empty-1280.png`,
    });

    await dropOnRegister(
      page,
      "box-10x20x30.step",
      await readFile(FLAT_STEP, "utf-8"),
    );

    const result = page.getByTestId("assembly-import-result");
    await expect(result).toBeVisible({ timeout: 60_000 });
    // The server's own discrimination, surfaced rather than guessed at.
    await expect(result).toHaveAttribute("data-import-kind", "part");
    await expect(result).toContainText("filed as a part");
    // No assembly was invented to hold it — the register is still empty.
    await expect(page.getByTestId("assembly-row")).toHaveCount(0);

    await page.getByTestId("assembly-import-open").click();
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
  });

  test("a file that is not a STEP is refused legibly, twice over", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/assemblies");
    const error = page.getByTestId("assembly-import-error");

    // (a) The client pre-check: the wrong extension never leaves the browser.
    await page.getByTestId("assembly-import-input").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not a step file"),
    });
    await expect(error).toContainText("not a STEP file");
    await page.getByTestId("assembly-import-dismiss").click();
    await expect(error).toHaveCount(0);

    // (b) THE SERVER'S TYPED ENVELOPE. A `.step` full of garbage passes the
    //     client guard, so this is the gateway's own `import_not_step` message
    //     arriving verbatim — the branch a pre-check alone can never prove.
    await page.getByTestId("assembly-import-input").setInputFiles({
      name: "supplier.step",
      mimeType: "application/step",
      buffer: Buffer.from("HEADER; this is not part-21 at all\n"),
    });
    await expect(error).toContainText("ISO-10303-21", { timeout: 30_000 });

    // The register is untouched and still usable: nothing was created, and the
    // scribe line still works.
    await expect(page.getByTestId("assembly-row")).toHaveCount(0);
    await page.getByTestId("create-assembly-name").fill("Bolted plates");
    await page.getByTestId("create-assembly-name").press("Enter");
    await expect(page.getByTestId("assembly-row")).toHaveCount(1);
  });
});
