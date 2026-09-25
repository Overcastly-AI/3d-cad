/**
 * CRAFT-7 — THE PRECISION FALLBACK: how a drag hands off to typing.
 *
 * The mandate's sentence is *"the numeric field is the precision fallback"*.
 * Before this item the field was 800 px away in the rail, `Tab` from the grip
 * went to `view-home`, and the gauge discarded every digit you typed at it —
 * so the precise path existed and led out of the command. Three routes now end
 * in the same cell, and each has a case here:
 *
 *  · COARSE — drag the instrument (covered by `extrude-grip-reach`);
 *  · STEPWISE — arrows on the focused grip (covered by `extrude-drag-handle`);
 *  · EXACT — type a digit while the gauge is live, or `Tab` into the cell.
 *
 * …plus the two exits, which are where FB-13 and FB-16 actually bite:
 * `Enter` means one thing everywhere, and `Escape` undoes the INNERMOST thing
 * and never more than one level of it.
 */
// The SUBPATH, not the package root: `@loft/design`'s index re-exports the
// Tailwind preset, whose `tailwindcss/plugin` specifier Node cannot resolve
// without the `.js` — so importing the root here fails at collection with
// "No tests found", which reads like a missing spec rather than a bad import.
// Same reason the palette specs import `@loft/design/tokens`.
import { LADDER_MIN_MAJOR_PX, LADDER_MIN_PITCH_PX } from "@loft/design/gauge";

import { expect, test, type Page } from "./fixtures";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import { createPartViaApi, seedSession, waitForFrames } from "./support";

async function openExtrude(page: Page, iso = true): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await page.keyboard.press("r");
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  if (iso) {
    await page.getByTestId("view-iso").click();
    await waitForCameraRest(page);
  }
}

async function distance(page: Page): Promise<number> {
  return Number.parseFloat(
    await page.getByTestId("extrude-distance").inputValue(),
  );
}

/** The tag's own input, once the cell is open. */
function tagCell(page: Page) {
  return page.getByTestId("extrude-depth-readout").getByRole("textbox");
}

/**
 * Leave the rail's field, which the editor AUTOFOCUSES on open.
 *
 * This is not spec plumbing, it is the contract: a digit typed with the caret
 * in a text control belongs to that control, and the gauge's window listener
 * stands down for it (`modalGate`'s typing-target bail). So the digit handoff
 * is reachable exactly when the keyboard is NOT already in a field — after a
 * drag, or from the focused grip — which is the flow it is for. The case below
 * asserts the deference directly.
 */
async function leaveTheRail(page: Page): Promise<void> {
  await page.getByRole("slider", { name: "Extrude depth" }).focus();
}

test.describe("the gauge's number is the field", () => {
  test("typing a digit at the viewport opens the tag's own cell", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Typed boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    // Start at the value we are about to type, so the comparison at the end is
    // about the READOUT BECOMING AN INPUT and not about the arrow having grown.
    await page.getByTestId("extrude-distance").fill("25");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "25",
    );
    await leaveTheRail(page);
    // The readout is TEXT until a digit arrives — the pointer owns the number.
    await expect(tagCell(page)).toHaveCount(0);
    const before = await page
      .getByTestId("extrude-depth-readout")
      .boundingBox();
    if (before === null) throw new Error("no tag box");

    await page.keyboard.press("2");
    await page.keyboard.press("5");

    // The cell is open, focused, and holds what was typed — including the FIRST
    // character, which is the half a naive "open on keydown" implementation
    // drops and the half the user notices.
    const cell = tagCell(page);
    await expect(cell).toBeFocused();
    await expect(cell).toHaveValue("25");
    // …and it reached the editor, live, without an Enter.
    await expect.poll(() => distance(page)).toBeCloseTo(25, 6);

    // THE NUMBER DID NOT MOVE. That is the single property that makes this read
    // as "the readout became typeable" rather than as a field appearing over
    // the model — and it is the reason the cell is the same component in both
    // states rather than two that look alike.
    const after = await page.getByTestId("extrude-depth-readout").boundingBox();
    if (after === null) throw new Error("no tag box after");
    expect(Math.abs(after.x - before.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1);
  });

  test("a letter is NOT the gauge's, and the band's keys keep working", async ({
    page,
  }) => {
    // The gauge must not swallow the keyboard. FLOW-A1 rejected an
    // auto-focusing field for exactly this reason: it takes every key and
    // quietly breaks the verbs the command band advertises on screen.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Letters");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    await leaveTheRail(page);
    await page.keyboard.press("x");
    await page.keyboard.press("q");
    await expect(tagCell(page)).toHaveCount(0);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
  });

  test("a digit typed INTO the rail's field still belongs to that field", async ({
    page,
  }) => {
    // The other half of contract α, and the half that is easy to break by
    // reaching for a raw `window` listener: the editor autofocuses its distance
    // field, so the very first digit anyone types lands there. A gauge that
    // grabbed it would yank the caret out of a field the user is already in —
    // and the gauge's own cell would then be the ONLY place a number could be
    // typed, which is a smaller version of the dead end this item is closing.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Deferred");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    // The editor autofocuses this field on open; the iso click in `openExtrude`
    // moves focus to the view rail, so put the caret back where a user who had
    // just opened the command would have left it.
    await page.getByTestId("extrude-distance").click();
    await expect(page.getByTestId("extrude-distance")).toBeFocused();
    await page.getByTestId("extrude-distance").press("ControlOrMeta+a");
    await page.keyboard.press("7");
    await expect(page.getByTestId("extrude-distance")).toHaveValue("7");
    await expect(tagCell(page)).toHaveCount(0);
  });

  test("Tab from the grip lands in the cell, Shift+Tab comes back", async ({
    page,
  }) => {
    // It used to go to `view-home` — 800 px away in the view rail, mid-command.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tabbed");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await grip.focus();
    await grip.press("Tab");
    await expect(tagCell(page)).toBeFocused();
    // Seeded with the value that was showing, so Tab is a way IN to the number
    // rather than a way to clear it.
    await expect(tagCell(page)).toHaveValue("10");

    await tagCell(page).press("Shift+Tab");
    await expect(grip).toBeFocused();
    await expect(tagCell(page)).toHaveCount(0);
  });

  test("Enter from the cell commits, exactly as it does from the grip", async ({
    page,
  }) => {
    // ONE MEANING, ALWAYS. FB-13 is a key that sometimes saves and sometimes
    // discards; the guard is that every surface in the wave routes Enter
    // through the same submit.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Committed");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    await leaveTheRail(page);
    await page.keyboard.press("1");
    await page.keyboard.press("8");
    await expect(tagCell(page)).toHaveValue("18");
    await tagCell(page).press("Enter");

    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-extents")).toContainText("18");
  });

  test("Escape from an open cell reverts the cell, NOT the command", async ({
    page,
  }) => {
    // CONTRACT γ, the cell half. Escape only ever discards, and never more than
    // one level at a time — so there is always a visible step back before work
    // is lost, which is what stops people hesitating at every keystroke.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Nested");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    await leaveTheRail(page);
    await page.keyboard.press("3");
    await expect(tagCell(page)).toHaveValue("3");

    await page.keyboard.press("Escape");
    // One level: the cell is closed and focus is back on the grip, and the
    // command is STILL OPEN.
    await expect(tagCell(page)).toHaveCount(0);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await expect(
      page.getByRole("slider", { name: "Extrude depth" }),
    ).toBeFocused();

    // …and the SECOND Escape cancels the command, which is what the band
    // promises in words on screen.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);
  });

  test("Escape mid-drag reverts the value and keeps the command open", async ({
    page,
  }) => {
    // CONTRACT γ, the drag half, and the broken state it replaces: the editor
    // used to unmount while the pointer was STILL CAPTURED by a node that no
    // longer existed, so the drag had no terminator and the next `pointerup`
    // went nowhere. It did not throw and it did not show in a screenshot.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Abandoned");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    const box = await grip.boundingBox();
    if (box === null) throw new Error("no grip box");
    const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(at.x, at.y);
    await page.mouse.down();
    for (let step = 1; step <= 4; step += 1) {
      await page.mouse.move(at.x, at.y + step * 14);
    }
    // Mid-gesture, button still down.
    await expect(grip).toHaveAttribute("data-grabbed", "true");
    await expect.poll(() => distance(page)).toBeLessThan(40);

    await page.keyboard.press("Escape");
    await page.mouse.up();

    // Reverted to where the grab started, capture released, command open.
    await expect(grip).toHaveAttribute("data-grabbed", "false");
    await expect.poll(() => distance(page)).toBeCloseTo(40, 6);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();

    // …and the gauge is still a working control afterwards, which is the half
    // an unterminated drag would have destroyed silently.
    await grip.focus();
    await grip.press("ArrowUp");
    await expect.poll(() => distance(page)).toBeGreaterThan(40);
  });

  test("the drawn rungs ARE the stops, and they follow the camera", async ({
    page,
  }) => {
    // §3.1: the ladder and the snap used to be two different ladders — rungs
    // from a decade series, snap from a constant — so the scale you could see
    // had nothing to do with what the drag did. `data-snap` is the ladder's own
    // pitch, and a dragged value has to land on it.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Ruled");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await grip.hover();
    // POLLED, not sampled. Arming the ladder is a React state change, and the
    // scale it is built from is read in the NEXT rendered frame, so the
    // attribute is a round trip behind the hover — a bare read races it and
    // reports the rest state, which looks exactly like "there is no ladder".
    await expect
      .poll(async () => Number(await grip.getAttribute("data-snap")), {
        message: "a hovered gauge must be ruled",
      })
      .toBeGreaterThan(0);
    const snap = Number(await grip.getAttribute("data-snap"));

    const box = await grip.boundingBox();
    if (box === null) throw new Error("no grip box");
    const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(at.x, at.y);
    await page.mouse.down();
    // A deliberately awkward travel, so the raw value is nowhere near a stop.
    await page.mouse.move(at.x + 3, at.y + 19);
    await page.mouse.move(at.x + 3, at.y + 23);
    await page.mouse.up();

    const landed = await distance(page);
    const off = Math.abs(landed / snap - Math.round(landed / snap));
    expect(
      off,
      `dragged to ${landed}, which is not a multiple of the drawn ${snap}`,
    ).toBeLessThan(1e-6);

    // …and Ctrl frees it: the same gesture, off the grid, which is one of the
    // two escapes §3.3 allows and the only one that keeps the pointer.
    //
    // RE-READ THE BOX. The first drag moved the arrow, so the grip is no longer
    // where it was — pressing at the stale point lands on the canvas, nothing
    // happens, and the value from the previous drag is still sitting on the
    // grid. That reads exactly like "Ctrl did not work", which is the wrong
    // conclusion to draw from a missed press.
    const moved = await grip.boundingBox();
    if (moved === null) throw new Error("no grip box after the first drag");
    const from = {
      x: moved.x + moved.width / 2,
      y: moved.y + moved.height / 2,
    };
    await page.keyboard.down("Control");
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(from.x + 2, from.y + 7);
    await page.mouse.move(from.x + 2, from.y + 11);
    await page.mouse.up();
    await page.keyboard.up("Control");
    const free = await distance(page);
    expect(free, "the free drag must have moved the value at all").not.toBe(
      landed,
    );
    expect(
      Math.abs(free / snap - Math.round(free / snap)),
      `a free drag landed on ${free}, exactly on the ${snap} grid it is meant to escape`,
    ).toBeGreaterThan(1e-6);
  });
});

/**
 * THE DRAWN SPINE'S LENGTH ON SCREEN, CSS pixels — read off the MESH, not off
 * the component's own arithmetic.
 *
 * This exists because CRAFT-7 shipped a biased px-per-value and then MEASURED
 * ITSELF: the numbers in its commit came from the component's internal
 * `pxPerValue`, which is the quantity that carried the bug, so they agreed with
 * each other and with nothing on screen. The reading below cannot do that. It
 * takes the spine cylinder's own `matrixWorld`, its own unit height (scaled in
 * Y by the segment's length), and the camera that actually rendered the frame,
 * and it returns pixels the user could measure with a ruler held to the glass.
 *
 * Summed over every segment, so it stays true for CRAFT-10's arc spine.
 */
async function drawnSpinePx(page: Page): Promise<number> {
  return page.evaluate((): number => {
    interface Mat {
      elements: number[];
    }
    interface Obj3D {
      name: string;
      matrixWorld: Mat;
      traverse: (fn: (child: Obj3D) => void) => void;
      updateWorldMatrix?: (parents: boolean, children: boolean) => void;
    }
    interface Cam {
      projectionMatrix: Mat;
      matrixWorldInverse: Mat;
    }
    const w = window as unknown as Record<string, unknown>;
    const scenes = (w["__loftScenes"] ?? {}) as Record<string, Obj3D>;
    const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
    const canvas = document.querySelector(
      '[data-testid="viewport"] canvas',
    ) as HTMLCanvasElement | null;
    if (canvas === null) return -1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    /** Column-major 4x4 times a point; homogeneous `w` comes back last. */
    const apply = (
      e: readonly number[],
      p: readonly [number, number, number],
    ): [number, number, number, number] => {
      const [x, y, z] = p;
      const at = (i: number): number => e[i] as number;
      return [
        at(0) * x + at(4) * y + at(8) * z + at(12),
        at(1) * x + at(5) * y + at(9) * z + at(13),
        at(2) * x + at(6) * y + at(10) * z + at(14),
        at(3) * x + at(7) * y + at(11) * z + at(15),
      ];
    };

    for (const uuid of order) {
      const scene = scenes[uuid];
      const camera = cameras[uuid];
      if (scene === undefined || camera === undefined) continue;
      const spines: Obj3D[] = [];
      scene.traverse((child) => {
        if (child.name === "gauge-extrude-depth-spine") spines.push(child);
      });
      if (spines.length === 0) continue;
      let total = 0;
      for (const spine of spines) {
        spine.updateWorldMatrix?.(true, false);
        const ends: [number, number][] = [];
        for (const localY of [-0.5, 0.5]) {
          const world = apply(spine.matrixWorld.elements, [0, localY, 0]);
          const view = apply(camera.matrixWorldInverse.elements, [
            world[0],
            world[1],
            world[2],
          ]);
          const clip = apply(camera.projectionMatrix.elements, [
            view[0],
            view[1],
            view[2],
          ]);
          const iw = 1 / clip[3];
          ends.push([
            ((clip[0] * iw + 1) / 2) * width,
            ((1 - clip[1] * iw) / 2) * height,
          ]);
        }
        const [from, to] = ends as [[number, number], [number, number]];
        total += Math.hypot(to[0] - from[0], to[1] - from[1]);
      }
      return total;
    }
    return -1;
  });
}

test.describe("the ladder's floor is a fact about the screen", () => {
  test("the DRAWN pitch clears 7 px at every zoom the wheel reaches", async ({
    page,
  }) => {
    // THE PROOF THE COMMIT THAT SHIPPED THIS DID NOT HAVE. Every number here is
    // derived from the spine MESH's projection (`drawnSpinePx`) and the DOM's
    // `data-snap`, so nothing the component believes about its own scale can
    // make this pass. Before the fix the same walk read 12.08 / 12.38 / 12.06
    // px at 1600x1000 against a floor the ladder thought was 14 — the gauge was
    // dividing a seat-to-head-BASE world length by a seat-to-TIP projection,
    // inflating px/mm by 1.18 and quietly sliding the floor to 11.9, then to
    // 9.7 on a short feature.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Ruled floor");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );
    const depth = 40;

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await grip.hover();
    await expect
      .poll(async () => Number(await grip.getAttribute("data-snap")), {
        message: "a hovered gauge must be ruled",
      })
      .toBeGreaterThan(0);

    const readPitch = async (): Promise<{
      snap: number;
      spinePx: number;
      pitchPx: number;
    }> => {
      const snap = Number(await grip.getAttribute("data-snap"));
      const spinePx = await drawnSpinePx(page);
      return { snap, spinePx, pitchPx: (snap * spinePx) / depth };
    };

    const seen: { snap: number; spinePx: number; pitchPx: number }[] = [];
    seen.push(await readPitch());

    // One notch at a time, re-reading whenever the ladder subdivides. The
    // pointer is parked ONCE — each `mouse.move` is a CDP round trip, and it is
    // already where it needs to be after the first.
    const box = await grip.boundingBox();
    if (box === null) throw new Error("no grip box");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    let last = seen[0]?.snap ?? 0;
    for (let i = 0; i < 24; i += 1) {
      await page.mouse.wheel(0, -120);
      await waitForFrames(page, 3);
      const snap = Number(await grip.getAttribute("data-snap"));
      if (snap === last || !(snap > 0)) continue;
      last = snap;
      seen.push(await readPitch());
    }

    // The ladder has to have MOVED, or this walk proved nothing about a floor
    // it never approached — the vacuous-gate failure this repo keeps paying
    // for. Zooming in subdivides, so a second, finer rung must have appeared.
    expect(
      seen.length,
      `the ladder never subdivided: ${JSON.stringify(seen)}`,
    ).toBeGreaterThanOrEqual(2);

    // PRINTED BEFORE THE ASSERTIONS, deliberately. A failure here is a claim
    // about a NUMBER, and the whole walk is the evidence for it; logging after
    // the loop means the one run that needs the evidence never prints it.
    console.log(
      `drawn pitch walk: ${seen
        .map(
          (at) =>
            `${at.snap}mm -> ${at.pitchPx.toFixed(2)}px (shaft ${at.spinePx.toFixed(1)}px)`,
        )
        .join(", ")}`,
    );

    for (const at of seen) {
      expect(at.spinePx).toBeGreaterThan(0);
      // 0.5 px of slack for the scale hysteresis: the component only rebuilds
      // the stop set once the projected scale has moved 2 %, so a reading taken
      // mid-hysteresis is that much behind the geometry it is measured against.
      // It is not slack in the floor.
      expect(
        at.pitchPx,
        `snap ${at.snap} mm drew a ${at.pitchPx.toFixed(2)} px pitch on a ${at.spinePx.toFixed(1)} px shaft`,
      ).toBeGreaterThanOrEqual(LADDER_MIN_PITCH_PX - 0.5);
      // …and the MAJORS, which are the marks a value is read off, clear 14 —
      // the number the direction actually argued for, one level up the series.
      const majorStep = Math.pow(10, Math.floor(Math.log10(at.snap)) + 1);
      expect(
        (majorStep * at.spinePx) / depth,
        `major ${majorStep} mm on a ${at.spinePx.toFixed(1)} px shaft`,
      ).toBeGreaterThanOrEqual(LADDER_MIN_MAJOR_PX - 0.5);
    }
  });
});
