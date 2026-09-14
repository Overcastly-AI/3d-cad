import { expect, test, type Page } from "./fixtures";

import { partVerbKey, type PartVerbId } from "../src/shortcuts/registry";
import { seedCube } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * FLOW-B2 — the five most-used modelling verbs answer to a letter.
 *
 * The workspace used to bind `P S L H D O I` (pattern, sweep, loft, shell,
 * draft, hole, mirror) and gave sketch, extrude, revolve, fillet and chamfer no
 * key at all — an exact inversion of what a hand reaches for. This spec is the
 * proof that the five now fire, in the real app, against the real stack.
 *
 * THE LETTERS ARE READ FROM THE REGISTRY, never typed here. A spec that spelled
 * `press("e")` would be a second source for the binding and would keep passing
 * if the registry re-keyed Extrude — it would simply be testing a letter the
 * reference no longer teaches. Reading `partVerbKey("extrude")` means a re-key
 * re-keys this spec, which is the same derivation rule the shortcut sheet is
 * built on.
 */

/** The letter a verb answers to — failing loudly rather than pressing nothing. */
function letter(id: PartVerbId): string {
  const key = partVerbKey(id);
  if (key === undefined) throw new Error(`${id} has no accelerator to press`);
  return key;
}

/** A part whose body is a 20 mm cube: a solved sketch AND a body, so all five verbs are live. */
async function seedCubePart(page: Page): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Accelerator cube");
  await seedCube(page, token, part.id);
  return part.id;
}

/** Both gates the five keys read: `hasBody` and `hasSolvedSketch` are true from here. */
async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
}

test.describe("the five most-used verbs have keys", () => {
  test("E R F C each open their editor, and K starts a sketch", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);

    // Each verb, its letter, and the surface that proves the verb started.
    for (const [id, editor] of [
      ["extrude", "extrude-editor"],
      ["revolve", "revolve-editor"],
      ["fillet", "fillet-editor"],
      ["chamfer", "chamfer-editor"],
    ] as const) {
      await expect(
        page.getByTestId(editor),
        `${editor} was already open before ${id}`,
      ).toHaveCount(0);

      await page.keyboard.press(letter(id));
      await expect(
        page.getByTestId(editor),
        `${letter(id)} did not open ${editor}`,
      ).toBeVisible();

      // Esc backs out of the command without creating a feature, which returns
      // the workspace to the state the next letter needs.
      await page.keyboard.press("Escape");
      await expect(page.getByTestId(editor)).toHaveCount(0);
    }

    // Sketch is the one that is always live — it needs neither a body nor a
    // solved profile — and its command surface is the strip, not an editor.
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await page.keyboard.press(letter("sketch"));
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  });

  test("a letter stays inert while its verb's condition is unmet", async ({
    page,
  }) => {
    // Guards the test above from passing for the wrong reason: if the openers
    // ran unconditionally, the assertions there would look identical. On an
    // EMPTY part there is no body and no solved sketch, so four of the five
    // must refuse — and the fifth, Sketch, must still work, or "inert" would
    // just mean "the page is not listening yet".
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Empty part");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-tree")).toBeVisible();
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    for (const [id, editor] of [
      ["extrude", "extrude-editor"],
      ["revolve", "revolve-editor"],
      ["fillet", "fillet-editor"],
      ["chamfer", "chamfer-editor"],
    ] as const) {
      await page.keyboard.press(letter(id));
      await expect(
        page.getByTestId(editor),
        `${letter(id)} opened ${editor} with nothing to act on`,
      ).toHaveCount(0);
    }

    // The page IS listening — same keyboard, same moment, one letter apart.
    await page.keyboard.press(letter("sketch"));
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
  });

  test("in a sketch the same letters belong to the sketch, not to the band", async ({
    page,
  }) => {
    // `E R F C K` are also sketch letters (equal, rect, offset, circle, extend)
    // and that is NOT a collision: the create handler bails unless
    // `mode === "off"`, so mode disambiguates before the key is read. The test
    // proves the key was DELIVERED and went to the other vocabulary — a bare
    // "no editor opened" assertion would pass just as well if the keystroke had
    // never arrived, which is this repo's most-repeated defect.
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XZ").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XZ");

    // SKETCH GOES FIRST, and the order is load-bearing rather than tidy. Any
    // create letter that gets through opens an editor, and the opener effect
    // bails on `editor !== null` — which UNREGISTERS its own listener. So the
    // first leaked letter silently disarms every letter after it, and a loop
    // that leads with Revolve tests the remaining three against a handler that
    // is no longer listening. Measured: with both sketch-mode defences removed
    // this test passed in that order and fails in this one.
    for (const [id, tool] of [
      ["sketch", "extend"],
      ["revolve", "rect"],
      ["chamfer", "circle"],
      ["fillet", "offset"],
    ] as const) {
      await page.keyboard.press(letter(id));
      // The POSITIVE half: the sketch vocabulary consumed the letter.
      await expect(
        page.getByTestId(`tool-${tool}`),
        `${letter(id)} did not arm the ${tool} tool in sketch mode`,
      ).toHaveAttribute("aria-pressed", "true");
      // ...and the sketch survived it. Checked EVERY iteration, not once at the
      // end, for the same reason the order matters.
      await expect(
        page.getByTestId("sketch-step"),
        `${letter(id)} dropped the sketch`,
      ).toHaveText("On XZ");
    }

    // WHAT THE MUTATIONS MEASURED, stated exactly, because "this gate catches
    // sketch-mode leaks" would be a broader claim than the evidence supports.
    // Sketch mode is defended THREE deep:
    //
    //   1. the opener effect bails unless `mode === "off"`;
    //   2. the sketch cascade `preventDefault()`s every letter it claims
    //      (`PartPage.tsx:1361`), which this item's own `defaultPrevented`
    //      guard then honours — so the guard added for the proposal note also
    //      makes the band defer to the sketch, which was not its purpose;
    //   3. the editor panel is render-gated on `mode === "off"` anyway.
    //
    // Deleting (1) ALONE reddens nothing here — measured, twice. Deleting (1)
    // and (2) together reddens the first loop iteration, because `startSketch`
    // calls `begin()` and returns to the plane pick, which is the FB-13 class
    // of misfire: destructive rather than merely wrong. That is what this test
    // is worth. It is not a gate on layer (1) by itself, and saying so is the
    // difference between a gate and a comment claiming to be one.
    //
    // ...and the modelling verbs those letters name in the band never started.
    await page.keyboard.press(letter("extrude"));
    for (const editor of [
      "extrude-editor",
      "revolve-editor",
      "fillet-editor",
      "chamfer-editor",
    ]) {
      await expect(
        page.getByTestId(editor),
        `${editor} opened from inside a sketch`,
      ).toHaveCount(0);
    }
    // The sketch itself is untouched — no letter dropped us out of the mode.
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XZ");
  });
});

/**
 * The `defaultPrevented` guard (W2 direction §3.5).
 *
 * A proposal note binds the same letters on `window` in the CAPTURE phase and
 * calls `preventDefault()`. Without the guard, pressing `E` while the extrude
 * offer is showing runs BOTH handlers and the opener's generic
 * `openCreateExtrude` wins last, replacing the offered profile with the default
 * one. The editor is open either way and looks right; only the profile is
 * wrong, so nothing fails visibly and review would pass it.
 *
 * This models the note with a real capture-phase listener rather than a
 * synthetic event, because the mechanism under test IS the phase ordering.
 */
interface CaptureProbe {
  handler: (event: KeyboardEvent) => void;
  /** How many keydowns the capture listener actually saw. */
  seen: number;
}
type ProbeWindow = Window & { __flowB2?: CaptureProbe };

test.describe("a proposal's key claim wins", () => {
  test("defaultPrevented stops the opener, and only defaultPrevented does", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    const key = letter("extrude");

    // (A) POSITIVE CONTROL — the binding is live in THIS page, right now.
    await page.keyboard.press(key);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);

    // (B) Stand in for the note: capture-phase on `window`, preventDefault, and
    // a counter so a listener that never fires cannot masquerade as a guard
    // that worked.
    await page.evaluate((pressed: string) => {
      const w = window as unknown as ProbeWindow;
      const probe: CaptureProbe = {
        seen: 0,
        handler: (event: KeyboardEvent) => {
          if (event.key.toLowerCase() !== pressed) return;
          probe.seen += 1;
          event.preventDefault();
        },
      };
      w.__flowB2 = probe;
      window.addEventListener("keydown", probe.handler, { capture: true });
    }, key);

    await page.keyboard.press(key);

    // The keystroke REACHED the window — so the silence below is the guard
    // declining, not a key that was never delivered.
    await expect
      .poll(() =>
        page.evaluate(
          () => (window as unknown as ProbeWindow).__flowB2?.seen ?? 0,
        ),
      )
      .toBe(1);
    await expect(
      page.getByTestId("extrude-editor"),
      "the opener ran despite defaultPrevented",
    ).toHaveCount(0);

    // (C) SECOND POSITIVE CONTROL — remove the flag, change nothing else. If
    // (B) had been silent for any other reason (a dead page, a lost focus, a
    // torn-down listener) this would stay closed too.
    await page.evaluate(() => {
      const w = window as unknown as ProbeWindow;
      if (w.__flowB2 !== undefined) {
        window.removeEventListener("keydown", w.__flowB2.handler, {
          capture: true,
        });
      }
    });
    await page.keyboard.press(key);
    await expect(
      page.getByTestId("extrude-editor"),
      "the opener did not come back once the key was released",
    ).toBeVisible();
  });
});
