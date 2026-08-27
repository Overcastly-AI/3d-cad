import { expect, test, type Page } from "./fixtures";

import {
  balloonPose,
  pickDispatch,
  setupTwoInstances,
  waitForSolved,
} from "./assemblyFlow";

/**
 * MATE-OBS — the assembly page may not display a previous solve while reporting
 * it as the current one.
 *
 * WHAT WAS MEASURED, and why it matters more than a cosmetic beat. A kernel
 * investigation drove this exact fixture through the real API on an isolated
 * stack: a coincident mate between the two plates returns
 * `status: under_constrained, remaining_dof: 3, mate_errors: []` and seats the
 * free plate. The SAME fixture with `mates=[]` returns `remaining_dof: 6` and
 * the unseated pose — and that is bit-for-bit what the UI reported. Documents
 * persisted the mate, the graph read returned it, the gateway forwarded it,
 * geometry acted on it. Every service was correct; the OBSERVER was reading the
 * pre-mate evaluation, and nothing on the page said so. For a human it is a
 * beat before the parts snap. For a reader it is indistinguishable from a mate
 * that did nothing, which is precisely the conclusion it produced.
 *
 * THE ASSERTION IS ON THE POSE, NEVER THE STATUS. Geometry's
 * `test_status_alone_cannot_distinguish_the_two` proves a seating solve and a
 * constraint-free solve BOTH report `under_constrained`, so a status-keyed gate
 * passes in a world where mates do nothing. Every claim here is paired with the
 * balloon's solved pose — the number that actually differs.
 *
 * The retained evaluation itself is DELIBERATE and stays: `AssemblyPage`'s
 * evaluate query carries `placeholderData: keepPreviousData` so the camera does
 * not teleport mid-refetch. What this gate holds is that the retention is never
 * silent.
 */

/** One 25 ms sample of every claim the workspace makes about the solve. */
interface SolveTrace {
  /** ms from the write at which a SETTLED status stood over the pre-mate pose. */
  statusLies: number[];
  /** ms at which FREE DOF spent the previous solve's count over that pose. */
  dofLies: number[];
  /** ms at which the provenance stamp said "current" over that pose. */
  stampLies: number[];
  /**
   * ms at which the OLD barrier's predicate (any status that is not "Solving…"
   * or "—") was satisfied while the pose was still pre-mate.
   *
   * This is the mutation evidence for `waitForSolved`, recorded in the same
   * trace as everything else: a non-empty list here with an EMPTY `stampLies`
   * is the fixed barrier and the broken one measured side by side on one write.
   */
  oldBarrierEarly: number[];
  /** One line per CHANGE of any readout — the order and timing, for a human. */
  timeline: string[];
  /** ms from the sampler's start at which the write was observed to go out. */
  armed: number;
  /** Which tell armed it — named so a silent instrument cannot pass as silence. */
  armTell: string;
  /** ms from the write at which the MATED pose first reached the screen. */
  settledAt: number;
}

declare global {
  interface Window {
    __mateProvenance?: SolveTrace;
  }
}

const EMPTY: SolveTrace = {
  statusLies: [],
  dofLies: [],
  stampLies: [],
  oldBarrierEarly: [],
  timeline: [],
  armed: -1,
  armTell: "(never)",
  settledAt: -1,
};

function readTrace(page: Page): Promise<SolveTrace> {
  return page.evaluate(
    (empty) => window.__mateProvenance ?? empty,
    EMPTY,
  ) as Promise<SolveTrace>;
}

/**
 * Install the sampler. It runs in the page at 25 ms — the same granularity
 * QA-R4's gate used, because the window it has to see is ~600 ms wide and a
 * per-second poll reports a clean page.
 *
 * `preY` is the free instance's scene-space y BEFORE the mate, which is the
 * solved OCCT **z** (`assembly/placement` maps `(x, y, z)` → `(x, z, -y)`) —
 * the seating axis a coincident mate moves.
 */
async function installSampler(
  page: Page,
  instanceId: string,
  preY: number,
): Promise<void> {
  await page.evaluate(
    ([id, before]) => {
      const trace: SolveTrace = {
        statusLies: [],
        dofLies: [],
        stampLies: [],
        oldBarrierEarly: [],
        timeline: [],
        armed: -1,
        armTell: "(never)",
        settledAt: -1,
      };
      window.__mateProvenance = trace;
      const started = Date.now();
      let last = "";

      const text = (selector: string): string =>
        (
          document.querySelector(selector) as HTMLElement | null
        )?.innerText.trim() ?? "";

      const sample = () => {
        const elapsed = Date.now() - started;
        const status = text('[data-testid="assembly-solve-status"]');
        // PanelRow renders <label><value>[<unit>]; the value is the second child.
        const dofRow = document.querySelector('[data-testid="assembly-dof"]');
        const dof =
          (dofRow?.children[1] as HTMLElement | null)?.textContent?.trim() ??
          "";
        const workspace = document.querySelector(
          '[data-testid="assembly-workspace"]',
        );
        const stamp = workspace?.getAttribute("data-eval-stale") ?? "(absent)";
        const balloon = document.querySelector(
          `[data-testid="assembly-balloon-${id}"]`,
        ) as HTMLElement | null;
        const y = balloon === null ? NaN : Number(balloon.dataset.solvedY);

        // ARMED — the write is out. The mate HUD switches to "Solving the
        // assembly…" the instant `submitting` flips, which is t+0 of the POST;
        // the mate row appearing in the tree is the later, guaranteed fallback so
        // a missed 25 ms tick cannot silently disarm the whole gate.
        if (trace.armed < 0) {
          const hud = text('[data-testid="mate-hud"]');
          const rows = document.querySelectorAll(
            '[data-testid="mate-row"]',
          ).length;
          if (hud.includes("Solving the assembly")) {
            trace.armed = elapsed;
            trace.armTell = "mate HUD reported the submit";
          } else if (rows > 0) {
            trace.armed = elapsed;
            trace.armTell = "the mate row landed in the tree";
          }
        }

        const line =
          `status=${status} dof=${dof} eval-stale=${stamp} ` +
          `solved-y=${Number.isNaN(y) ? "(no balloon)" : y}`;
        if (line !== last) {
          last = line;
          trace.timeline.push(
            `t+${trace.armed < 0 ? `${elapsed}(pre-write)` : elapsed - trace.armed} ${line}`,
          );
        }

        if (trace.armed >= 0) {
          const at = elapsed - trace.armed;
          // THE POSE IS THE SUBJECT. A claim only counts as a lie while the
          // balloon still carries the PRE-mate seat; once the mated pose is up,
          // every one of these readouts is entitled to say whatever it likes.
          const preMatePose = !Number.isNaN(y) && Math.abs(y - before) < 0.05;
          // CASE-INSENSITIVE, and that is not pedantry — it is the second half
          // of the defect. The cell is `uppercase` in CSS and `innerText`
          // returns RENDERED text, so the string here is "SOLVING…". The old
          // barrier's `/Solving|^—$/` therefore never matched the transient word
          // at all: it released even on a page that was honestly saying it was
          // still solving.
          const settledStatus = status !== "" && !/solving|^—$/i.test(status);
          if (preMatePose) {
            if (settledStatus) trace.statusLies.push(at);
            if (dof !== "" && dof !== "—") trace.dofLies.push(at);
            if (stamp === "false") trace.stampLies.push(at);
            // The OLD `waitForSolved` predicate, verbatim.
            if (settledStatus) trace.oldBarrierEarly.push(at);
          } else if (trace.settledAt < 0 && !Number.isNaN(y)) {
            trace.settledAt = at;
          }
        }

        // Keep sampling a beat past the settle so a claim made AFTER the new pose
        // lands is still caught, then stop. The budget is a CEILING, not a wait.
        const done =
          trace.settledAt >= 0 &&
          elapsed - trace.armed - trace.settledAt > 1000;
        if (!done && elapsed < 40_000) window.setTimeout(sample, 25);
      };
      sample();
    },
    [instanceId, preY] as const,
  );
}

test.describe("MATE-OBS — a mate in flight is never reported as the solve", () => {
  test("no readout claims a settled solve over the pre-mate pose", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);

    const before = await balloonPose(page, idB);
    expect(before, "the free instance's balloon is on screen").not.toBeNull();
    expect(
      before?.stale,
      "the fixture must start from a SETTLED solve, else the sampler's " +
        "pre-mate baseline is itself a previous solve",
    ).toBe(false);
    const preY = before?.y ?? Number.NaN;
    expect(Number.isNaN(preY)).toBe(false);

    // Arm the coincident tool and collect the first face; the SECOND pick is
    // the write (the value-free mates auto-commit on a complete pair).
    await page.getByTestId("mate-coincident").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await pickDispatch(
      page,
      `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
    );

    await installSampler(page, idB, preY);
    await pickDispatch(
      page,
      `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
    );

    await expect
      .poll(async () => (await readTrace(page)).settledAt, {
        timeout: 45_000,
        message:
          "the free instance never left its pre-mate seat, so the sampler " +
          "watched nothing happen and its silence proves nothing about the app",
      })
      .toBeGreaterThanOrEqual(0);
    // The sampler runs one beat past the settle — let it finish.
    await page.waitForTimeout(1300);
    const trace = await readTrace(page);

    console.log(
      `MATE-OBS timeline (ms from the write, armed by ${trace.armTell}):\n  ` +
        trace.timeline.join("\n  "),
    );

    // THE INSTRUMENT'S OWN GUARDS, first and non-negotiable. Every assertion
    // below is a `toBe(0)`, which a sampler that measured NOTHING satisfies
    // trivially — so the gate must first prove it watched the write go out,
    // recorded readouts, and saw the mated pose arrive.
    expect(
      trace.armed,
      "the sampler never saw the mate write go out (neither the HUD's submit " +
        "state nor the mate row), so it measured the wrong window",
    ).toBeGreaterThanOrEqual(0);
    expect(
      trace.timeline.length,
      "the sampler armed but recorded no readouts at all",
    ).toBeGreaterThan(0);
    expect(
      trace.settledAt,
      "the sampler never saw the mated pose reach the screen",
    ).toBeGreaterThanOrEqual(0);

    const span = (moments: number[]) =>
      moments.length === 0
        ? 0
        : (moments[moments.length - 1] as number) - (moments[0] as number);
    const tail = `Timeline:\n  ${trace.timeline.join("\n  ")}`;

    expect(
      trace.statusLies.length,
      `SOLVE STATUS reported a settled verdict for ${span(trace.statusLies)} ms ` +
        `(${trace.statusLies.length} samples from t+${trace.statusLies[0]}) while ` +
        `the free instance was still at its PRE-mate seat y=${preY}. That reading ` +
        `is indistinguishable from a mate that did nothing. ${tail}`,
    ).toBe(0);
    expect(
      trace.dofLies.length,
      `FREE DOF spent the previous solve's count for ${span(trace.dofLies)} ms ` +
        `(${trace.dofLies.length} samples) over the pre-mate pose — the exact ` +
        `6-instead-of-3 the kernel investigation was handed. ${tail}`,
    ).toBe(0);
    expect(
      trace.stampLies.length,
      `data-eval-stale said "false" over the pre-mate pose for ` +
        `${span(trace.stampLies)} ms. The provenance stamp is the one thing ` +
        `every pose reader trusts; it may not be wrong. ${tail}`,
    ).toBe(0);

    // MUTATION EVIDENCE, measured on the same write: the OLD barrier's
    // predicate (any status that is not "Solving…"/"—") was satisfiable inside
    // the window before the fix — that is why `waitForSolved` returned on its
    // first tick and every pose read after it got the previous solve. It is
    // logged rather than asserted in either direction: asserting it stayed > 0
    // would pin the defect open, and asserting it is 0 duplicates the status
    // gate above. What matters is that the stamp gate is 0 regardless.
    console.log(
      `MATE-OBS: the OLD waitForSolved predicate was satisfied over the ` +
        `pre-mate pose in ${trace.oldBarrierEarly.length} samples ` +
        `(t+${trace.oldBarrierEarly[0] ?? "-"}..${
          trace.oldBarrierEarly[trace.oldBarrierEarly.length - 1] ?? "-"
        } ms); the provenance barrier in ${trace.stampLies.length}. ` +
        `The mated pose reached the screen at t+${trace.settledAt} ms.`,
    );
  });

  test("waitForSolved returns only once the mated pose is on screen", async ({
    page,
  }) => {
    // The barrier's contract, asserted the only way that means anything: read
    // the pose the INSTANT it returns, with no poll to wait out a window it was
    // supposed to have waited out. The old barrier fails this by ~600 ms.
    const { idA, idB, seedX } = await setupTwoInstances(page);

    await page.getByTestId("mate-concentric").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await pickDispatch(page, `[data-testid^="mate-axis-${idA}-"]`);
    await pickDispatch(page, `[data-testid^="mate-axis-${idB}-"]`);
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });

    const status = await waitForSolved(page);
    const pose = await balloonPose(page, idB);
    expect(pose, "the free instance's balloon is on screen").not.toBeNull();
    expect(
      pose?.stale,
      "waitForSolved returned while the workspace still reported a superseded " +
        "solve — the barrier released inside the window it exists to close",
    ).toBe(false);
    expect(
      pose?.x ?? Number.NaN,
      `waitForSolved returned "${status}" and the free instance was still at ` +
        `its authored seed x=${seedX}. The concentric mate pulls its hole axis ` +
        `onto the grounded plate's, so a pose still at the seed means the ` +
        `barrier handed back the PREVIOUS solve — the defect, not a slow solve.`,
    ).toBeLessThan(seedX - 20);
  });
});
