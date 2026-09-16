/**
 * HOW A PICK MARK IS PLANTED IN THE SCENE — an anchor in the scene graph, and
 * a SLOT in the one shared DOM host (`pickMarkLayer.tsx`).
 *
 * ## What changed, and why (board item #70)
 *
 * This used to render a drei `<Html>` per mark, which is `ReactDOM.createRoot`
 * per mark. Measured at **~3.3 ms each**, and the buggy 10 665-face golden
 * arms **452** of them — ~13 s of main-thread script, i.e. a hang. The marks
 * now share ONE React root and ONE per-frame projection pass; everything about
 * how a mark LOOKS and BEHAVES is unchanged, and `pickMarkProjection.ts` holds
 * drei's own arithmetic under unit test so that claim is checkable rather than
 * asserted. The full reasoning lives in `pickMarkLayer.tsx`.
 *
 * The props are deliberately identical, so the six overlays that mount marks
 * (face, edge, shell face, hole point, measure, instance mate) needed no edit
 * at all — this repo's standing rule about fixing the primitive rather than
 * the instance, applied to a performance defect.
 *
 * ## The INERT WRAPPER survives the rewrite (MEASURE-PROXY-1, T-14)
 *
 * A wrapper around a mark takes the mark's BOX, while a `PickNode` is
 * `rounded-full` — so a Ø24 circle inside a 24x24 box leaves four corners that
 * are a pointer target doing nothing at all, and a NEIGHBOUR's corner lands
 * squarely on other marks. Measured on the audit's motor-mount plate,
 * `measure-edge-4`, `-5` and `-6` each had another mark's wrapper corner on
 * their own centre and a real `page.mouse.click` there registered NOTHING.
 * With the wrapper inert those pixels fall through to the canvas, where the
 * band answers. The slot the layer gives each mark therefore carries
 * `pointer-events: none`, and `PickNode` opts ITSELF back in — because a
 * control that cannot be pointed at is not a control, and that is the
 * primitive's business rather than each caller's.
 *
 * ## It is also the census of "a pick is armed"
 *
 * Being the one host every pick affordance passes through makes this the only
 * honest place to COUNT them, so `armedPicks.ts` registers here. That is what
 * lets ambient chrome (the reference cube) yield its pointer for the duration
 * of a pick without anybody plumbing a boolean per mode.
 */
import { useStore } from "@react-three/fiber";
import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import type { Group } from "three";

import { useRegisterArmedPick } from "./armedPicks";
import {
  acquirePickMarkLayer,
  createPickMarkSlot,
  type PickMarkLayer,
  releasePickMarkLayer,
} from "./pickMarkLayer";

export interface PickMarkProps {
  /** Scene-space anchor for the mark. */
  position: [number, number, number];
  /**
   * The depth→z-index band for this class of mark. Overlays use it to keep a
   * vertex above an edge mark and both below the HUD — the HUD's own chrome
   * stops COMPETING for the pointer while a pick is armed (`armedPicks.ts`)
   * rather than being out-stacked, so this band stays a statement about marks.
   */
  zIndexRange: [number, number];
  /** The mark itself — a `PickNode`, which opts back into pointer events. */
  children: ReactNode;
}

export function PickMark({ position, zIndexRange, children }: PickMarkProps) {
  // Every armed pick counts itself here, which is what lets the reference cube
  // give up its pointer while the tool is asking for a pick — see
  // `armedPicks.ts`. It lives in the primitive because a hand-maintained list
  // of pick modes is exactly the thing that goes stale.
  useRegisterArmedPick();

  const store = useStore();
  const group = useRef<Group>(null);
  const layer = useRef<PickMarkLayer | null>(null);
  // One slot per mark, for the mark's whole life. Its id is the host's React
  // key, so a stable identity here is what stops a re-render remounting every
  // mark's DOM.
  const [slot] = useState(() => createPickMarkSlot(zIndexRange, children));

  // A real `Object3D` anchor rather than a bare position, because a mark may
  // sit under a transformed group (an assembly instance's pose) and only the
  // world matrix knows that.
  useLayoutEffect(() => {
    const held = acquirePickMarkLayer(store);
    layer.current = held;
    slot.object = group.current;
    held.add(slot);
    return () => {
      held.remove(slot);
      layer.current = null;
      releasePickMarkLayer(store);
    };
  }, [store, slot]);

  // Deliberately NO dependency array: `children` is a fresh element every
  // render and comparing it costs more than assigning it. The layer folds
  // every mark's request into ONE `root.render` on the microtask queue — and
  // ONE `invalidate`, which is what draws the frame a moved anchor needs under
  // `frameloop="demand"`. That is the whole difference between this and 452
  // roots: everything per-mark that could be said once is said once.
  useLayoutEffect(() => {
    slot.node = children;
    slot.zIndexRange = zIndexRange;
    layer.current?.scheduleRender();
  });

  return <group ref={group} position={position} />;
}
