/**
 * ONE HOST FOR EVERY PICK MARK — the behaviour, and the cost that motivated it
 * (board item #70).
 *
 * ## Why there is a benchmark in a unit suite
 *
 * The defect was not a wrong answer, it was a hang: drei `Html` builds one
 * `ReactDOM` root PER MARK, measured at ~3.3 ms each in the real app, and the
 * buggy 10 665-face golden arms **452** of them — ~13 s of main-thread script
 * before anything can be clicked. Nothing about that is visible to a
 * correctness assertion, so the only gate that can see it is a timed one.
 *
 * ## Why the defective mechanism is SHIPPED here as a control leg
 *
 * Two reasons, and the second is the one that matters.
 *
 * (a) A per-mark budget in absolute milliseconds is a flake generator: four
 * agents run in parallel on this box and CI runners are slower again. Measuring
 * BOTH mechanisms back to back in the same process and asserting the RATIO
 * cancels whatever the machine is doing, which is the only form of this
 * assertion that is honest under contention.
 *
 * (b) An assertion nobody has watched fail is not yet a gate. `LegacyPickMark`
 * below is the exact code this change removed, so the budget has a live
 * negative control: point the measured leg at it and the expectation reads
 * 1.0x and fails. Without it, a future refactor that quietly reintroduced a
 * root per mark would leave a green suite.
 *
 * ## What is NOT measured here, stated so the number is not over-read
 *
 * jsdom is not a browser and this harness is not the app: there is no
 * stylesheet, no layout and no compositor, and the scene holds nothing but the
 * marks. The absolute numbers therefore belong to this harness only. The same
 * two mechanisms measured in headless Chromium at N=452 came out at
 * **1.055 ms/mark (drei roots)** vs **0.298 ms/mark (portal host)**, and the
 * per-mark cost of the OLD path grows with N (1.082 / 1.055 / 1.318 ms at
 * 113 / 452 / 904) while the new one stays flat (0.326 / 0.298 / 0.324) —
 * which is the real finding: the old mechanism was super-linear.
 *
 * Reachability cannot be measured here either, for the same reason (jsdom has
 * no layout, so every `getBoundingClientRect` is zero and `elementFromPoint`
 * answers nothing). It was measured in Chromium instead: each mark's box is
 * **24.0 x 24.0**, `document.elementFromPoint` at its centre resolves to the
 * mark itself at 6 of 6 samples, and a real `page.mouse.click` at the centre of
 * `bench-2` reached `bench-2`. What this file CAN pin is the DOM contract that
 * reachability rests on — the slot inert, the mark opted back in — so it does.
 */
import { PickNode } from "@loft/design";
import { Html } from "@react-three/drei";
import { advance, createRoot, extend, useThree } from "@react-three/fiber";
import type { RootState } from "@react-three/fiber";
import { act, type ReactNode } from "react";
import * as THREE from "three";
import type { WebGLRenderer } from "three";
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useRegisterArmedPick } from "./armedPicks";
import { PickMark } from "./PickMark";
import { pickMarkLayerCount } from "./pickMarkLayer";

// r3f's catalogue is populated by `<Canvas>`, which needs a GPU. Booting the
// root by hand is what lets the real component tree run in jsdom.
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- `extend` takes r3f's Catalogue; the THREE namespace satisfies it structurally but is not typed as one.
extend(THREE as any);

// React only honours `act` when the environment declares itself a test one.
// Without this the layer's own microtask flush escapes every `act` boundary and
// the assertions below read a half-committed host.
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- a React global with no published type.
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

/** The same global, typed, so the benchmark can switch it off for its window. */
const reactActFlag = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };

/** The mark count the board item measured on the buggy golden. */
const N = 452;

/**
 * The implementation this change replaced, kept verbatim as the benchmark's
 * control leg. Do not "clean this up" — it is a fixture, and its job is to be
 * the slow thing.
 */
const INERT_WRAPPER = { pointerEvents: "none" } as const;
function LegacyPickMark({
  position,
  zIndexRange,
  children,
}: {
  position: [number, number, number];
  zIndexRange: [number, number];
  children: ReactNode;
}) {
  useRegisterArmedPick();
  return (
    <Html
      position={position}
      center
      zIndexRange={zIndexRange}
      style={INERT_WRAPPER}
    >
      {children}
    </Html>
  );
}

/**
 * A renderer that draws nothing. Everything under test is projection and DOM,
 * so the only thing the layer needs from `gl` is a canvas with a parent.
 */
function nullRenderer(canvas: HTMLCanvasElement): WebGLRenderer {
  return {
    domElement: canvas,
    render: () => {},
    setSize: () => {},
    setPixelRatio: () => {},
    setClearAlpha: () => {},
    getPixelRatio: () => 1,
    xr: { enabled: false, isPresenting: false, addEventListener: () => {} },
    shadowMap: { enabled: false },
    outputColorSpace: "",
    toneMapping: 0,
  } as unknown as WebGLRenderer;
}

interface Harness {
  host: HTMLDivElement;
  root: ReturnType<typeof createRoot>;
  /** The r3f state, captured from INSIDE the tree — a public seam. */
  state: () => RootState;
}

const live: Harness[] = [];

/** Publishes the root state the component tree actually sees. */
function StateProbe({ onState }: { onState: (state: RootState) => void }) {
  const state = useThree();
  onState(state);
  return null;
}

function boot(): Harness {
  const host = document.createElement("div");
  host.style.position = "relative";
  document.body.appendChild(host);
  const canvas = document.createElement("canvas");
  host.appendChild(canvas);
  const root = createRoot(canvas);
  root.configure({
    frameloop: "never",
    size: { width: 1280, height: 800, top: 0, left: 0 },
    gl: () => nullRenderer(canvas),
    camera: { position: [0, 0, 10], fov: 40 },
  });
  let captured: RootState | null = null;
  const harness: Harness = {
    host,
    root,
    state: () => {
      if (captured === null) throw new Error("render the tree before reading");
      return captured;
    },
  };
  captureInto(harness, (state) => {
    captured = state;
  });
  live.push(harness);
  return harness;
}

/** Wires the probe into whatever the harness renders next. */
const probes = new WeakMap<Harness, (state: RootState) => void>();
function captureInto(harness: Harness, sink: (state: RootState) => void): void {
  probes.set(harness, sink);
}

async function teardown(harness: Harness): Promise<void> {
  const at = live.indexOf(harness);
  if (at >= 0) live.splice(at, 1);
  await act(async () => {
    harness.root.unmount();
  });
  await act(async () => {
    await Promise.resolve();
  });
  harness.host.remove();
}

afterEach(async () => {
  for (const harness of live.slice()) await teardown(harness);
  expect(
    pickMarkLayerCount(),
    "a layer outliving its root would leak a host into the next case",
  ).toBe(0);
});

type MarkComponent = typeof PickMark;

function Marks({
  Mark,
  n,
  pitch = 1.5,
}: {
  Mark: MarkComponent;
  n: number;
  pitch?: number;
}) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <Mark
          key={i}
          position={[(i - n / 2) * pitch, 0, 0]}
          zIndexRange={[30, 10]}
        >
          <PickNode
            shape="face"
            data-testid={`face-${i}`}
            aria-label={`Face ${i}`}
          />
        </Mark>
      ))}
    </>
  );
}

/** Render into the harness and let the host root's microtask flush land. */
async function render(harness: Harness, node: ReactNode): Promise<void> {
  const sink = probes.get(harness);
  await act(async () => {
    harness.root.render(
      <>
        {sink === undefined ? null : <StateProbe onState={sink} />}
        {node}
      </>,
    );
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

/** Render `n` marks. */
const mount = (
  harness: Harness,
  Mark: MarkComponent,
  n: number,
  pitch?: number,
): Promise<void> => render(harness, <Marks Mark={Mark} n={n} pitch={pitch} />);

const layerHosts = () =>
  document.querySelectorAll("[data-testid='pick-mark-layer']");

/** Marks inside ONE harness — several are live at once during the benchmark. */
const marksIn = (harness: Harness) =>
  harness.host.querySelectorAll("[data-testid^='face-']");

describe("the shared pick mark host", () => {
  it("gives sixty marks ONE host, not sixty roots", async () => {
    const harness = boot();
    await mount(harness, PickMark, 60);
    expect(layerHosts()).toHaveLength(1);
    expect(pickMarkLayerCount()).toBe(1);
    expect(document.querySelectorAll("[data-testid^='face-']")).toHaveLength(
      60,
    );
  });

  it("keeps every test hook QA drives the marks by", async () => {
    // The e2e suite picks marks by `data-testid`, by role and by accessible
    // name. A performance rewrite that renamed any of them is a cross-territory
    // break, so all three are asserted on the assembled DOM rather than trusted.
    const harness = boot();
    await mount(harness, PickMark, 4);
    const mark = document.querySelector("[data-testid='face-2']");
    expect(mark).not.toBeNull();
    // By ROLE and ACCESSIBLE NAME, resolved the way Playwright resolves them,
    // rather than by reading the attributes back — the name is what a screen
    // reader announces and what `getByRole(..., { name })` matches on.
    expect(screen.getByRole("button", { name: "Face 2" })).toBe(mark);
  });

  it("hands the mark an inert slot and lets the mark opt back in", async () => {
    // MEASURE-PROXY-1: the wrapper takes the mark's square BOX while the mark
    // is a circle, so an inert wrapper is what stops a neighbour's dead corner
    // sitting on this mark's centre. Measured in Chromium after this change:
    // slot `pointer-events: none`, mark `pointer-events: auto`, box 24x24,
    // `elementFromPoint` at the centre resolving to the mark at 6 of 6.
    const harness = boot();
    await mount(harness, PickMark, 3);
    const mark = document.querySelector("[data-testid='face-1']");
    const slot = mark?.parentElement ?? null;
    expect(slot).not.toBeNull();
    expect(slot?.style.pointerEvents).toBe("none");
    expect(mark?.className).toContain("pointer-events-auto");
    // The host itself spans nothing and stacks nothing — a z-index or a
    // transform on it would trap every mark's depth index in a new stacking
    // context and restack the whole overlay against the HUD.
    const host = layerHosts()[0] as HTMLElement;
    expect(host.style.pointerEvents).toBe("none");
    expect(host.style.zIndex).toBe("");
    expect(host.style.transform).toBe("");
  });

  it("places each mark before the first frame, centred on its anchor", async () => {
    const harness = boot();
    await mount(harness, PickMark, 3, 0);
    // All three sit on the camera axis, so all three land on the frame centre.
    for (const id of ["face-0", "face-1", "face-2"]) {
      const slot = document.querySelector(
        `[data-testid='${id}']`,
      )?.parentElement;
      expect(slot?.style.transform).toBe(
        "translate3d(640px,400px,0) translate3d(-50%,-50%,0)",
      );
      expect(Number(slot?.style.zIndex)).toBeGreaterThanOrEqual(10);
      expect(Number(slot?.style.zIndex)).toBeLessThanOrEqual(30);
    }
  });

  it("follows a TRANSFORMED parent, not just the position prop", async () => {
    // The assembly mate overlay mounts its marks under
    // `<group position quaternion>` for the instance's pose. Reading the prop
    // instead of the world matrix would park every mate mark at the origin.
    const harness = boot();
    await render(
      harness,
      <>
        <group position={[3, 0, 0]}>
          <PickMark position={[0, 0, 0]} zIndexRange={[30, 10]}>
            <PickNode shape="face" data-testid="posed" aria-label="Posed" />
          </PickMark>
        </group>
        <PickMark position={[3, 0, 0]} zIndexRange={[30, 10]}>
          <PickNode shape="face" data-testid="direct" aria-label="Direct" />
        </PickMark>
        <PickMark position={[0, 0, 0]} zIndexRange={[30, 10]}>
          <PickNode shape="face" data-testid="origin" aria-label="Origin" />
        </PickMark>
      </>,
    );
    const slotOf = (id: string) =>
      document.querySelector(`[data-testid='${id}']`)?.parentElement?.style
        .transform;
    // The invariant, with no hand-computed pixel to go stale: a mark posed by
    // its parent and a mark placed at the same WORLD point land identically.
    expect(slotOf("posed")).toBe(slotOf("direct"));
    // And the negative control, so the case cannot pass by both being unset:
    // the same mark at the origin lands somewhere else, dead centre.
    expect(slotOf("origin")).toBe(
      "translate3d(640px,400px,0) translate3d(-50%,-50%,0)",
    );
    expect(slotOf("posed")).not.toBe(slotOf("origin"));
  });

  it("repositions every mark from ONE frame pass when the camera moves", async () => {
    const harness = boot();
    await mount(harness, PickMark, 3, 0);
    const slot = () =>
      document.querySelector("[data-testid='face-0']")?.parentElement;
    const before = slot()?.style.transform;
    const state = harness.state();
    state.camera.position.set(4, 0, 10);
    state.camera.updateMatrixWorld();
    act(() => {
      advance(performance.now(), false, state);
    });
    expect(slot()?.style.transform).not.toBe(before);
  });

  it("takes the host away when the last mark leaves", async () => {
    const harness = boot();
    await mount(harness, PickMark, 5);
    expect(layerHosts()).toHaveLength(1);
    await render(harness, null);
    expect(pickMarkLayerCount()).toBe(0);
    expect(layerHosts()).toHaveLength(0);
  });
});

/**
 * Main-thread script time for a mount of `n` marks, in ms per mark.
 *
 * Each leg gets a FRESH document and tears its own harness down before
 * returning. That is not tidiness: a leg left mounted puts hundreds of live
 * marks — and, for the control, hundreds of live React roots — in the same
 * document, and the next leg pays for walking them. Measured: legs run back to
 * back without teardown read 2.5x where isolated legs read 4.2x, in the
 * direction that FLATTERS the control. A benchmark whose legs can see each
 * other is measuring the order you ran them in.
 */
async function perMarkScriptTime(
  Mark: MarkComponent,
  n: number,
): Promise<number> {
  const harness = boot();
  // React's `act` queue is switched OFF for the measured window. It is test
  // bookkeeping, it is not in the app, and it does not fall on the two legs
  // equally — measured, it roughly doubles the portal leg (0.43 -> 0.81 ms per
  // mark) while barely moving the control, which turned a 4.2x result into
  // 2.4x. A benchmark that includes its own harness is measuring the harness.
  reactActFlag.IS_REACT_ACT_ENVIRONMENT = false;
  // CPU time, not wall clock: four agents share this box, and a wall-clock
  // budget would measure their load rather than this code.
  const cpu0 = process.cpuUsage();
  try {
    harness.root.render(<Marks Mark={Mark} n={n} />);
    // Yield until every mark is in the document. Both reconcilers here are
    // concurrent — r3f's for the anchors and the host's for the slots — so
    // "mounted" is a state to wait FOR, not a line to fall past. Waiting costs
    // no CPU time, which is exactly why the budget is denominated in CPU time
    // and not in wall clock.
    // The DOM is counted every 32nd tick rather than every tick: the count is
    // a `querySelectorAll` over a document that is growing to thousands of
    // nodes, and charging it to the measured window would tax the SLOWER leg
    // hardest — an instrument that punishes whatever it is measuring.
    for (let tick = 0; tick < 8000; tick += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
      if (tick % 32 === 31 && marksIn(harness).length >= n) break;
    }
  } finally {
    reactActFlag.IS_REACT_ACT_ENVIRONMENT = true;
  }
  const cpu = process.cpuUsage(cpu0);
  expect(
    marksIn(harness).length,
    "the leg must actually have mounted its marks, or the number below is a measurement of nothing",
  ).toBe(n);
  await teardown(harness);
  return (cpu.user + cpu.system) / 1000 / n;
}

describe("mount cost", () => {
  it("costs a fraction per mark of what a root per mark costs", async () => {
    // Warm both paths at a small N so neither leg pays for first-call JIT.
    await perMarkScriptTime(LegacyPickMark, 40);
    await perMarkScriptTime(PickMark, 40);

    const before = await perMarkScriptTime(LegacyPickMark, N);
    const after = await perMarkScriptTime(PickMark, N);
    const verdict =
      `pick mark mount, N=${N}: control (a React root per mark) ` +
      `${before.toFixed(3)} ms/mark, portal host ${after.toFixed(3)} ms/mark, ` +
      `${(before / after).toFixed(1)}x`;
    console.log(verdict);

    // THE BUDGET, AND WHERE IT COMES FROM. It is `before / 2` — derived from
    // the control leg measured moments earlier IN THIS SAME PROCESS, because
    // that is the only form that survives a contended box: four agents share
    // this machine and CI runners are slower again, so an absolute ms/mark
    // ceiling would be a flake generator rather than a gate.
    //
    // The divisor is the WORST observation minus a margin, not a round number.
    // Five consecutive runs of this exact gate measured 3.1x / 2.8x / 2.6x /
    // 2.5x / 2.7x (control 2.09-2.42 ms/mark, portal 0.74-0.98), so 2 leaves
    // ~25% headroom under the lowest. A regression to a React root per mark
    // reads ~1.0x and misses by a factor of two.
    //
    // This gate's ratio is DELIBERATELY smaller than the headline one. jsdom
    // charges the portal leg for CSS parsing the real browser does far more
    // cheaply, and the same two mechanisms in headless Chromium measured
    // 1.055 -> 0.298 ms/mark at this N. Quoting 2x here rather than the real
    // 3.5x is the conservative direction: the gate under-claims and cannot
    // flake, and the browser numbers are recorded in the docblock above where
    // they cannot be mistaken for something this process measured.
    const budget = before / 2;
    expect(
      after,
      `${verdict} — budget was ${budget.toFixed(3)} ms/mark`,
    ).toBeLessThan(budget);
  }, 120_000);
});
