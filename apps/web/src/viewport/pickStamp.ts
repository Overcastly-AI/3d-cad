/**
 * THE QA STAMP for an armed pick — "what is the pointer addressing right now",
 * published on the viewport container as a `data-*` attribute.
 *
 * It exists because the thing under test is a RAYCAST handler, and
 * `document.elementFromPoint` can only ever answer "the canvas" for one of
 * those. Without a stamp, an overlay's affordance can only be measured by
 * CLICKING, which mutates the document once per sample point — so the
 * reachability census that scored SEL-1 A2 (9.9 % -> 84.6 %) would not have
 * been affordable, let alone repeatable. The same posture `data-hovered-face`
 * and `data-body-highlight` already take.
 *
 * Extracted on the second use and now serving six overlays (SEL-4). The
 * CLEANUP is load-bearing, not hygiene: a stamp left set after the overlay
 * unmounts scores 100 % on a body that is not on screen, which is the exact
 * "gate measuring the wrong input" failure this repo keeps relearning. Every
 * spec that reads one of these pairs it with a negative control (park the
 * pointer off the body, assert the attribute clears).
 */
import { useThree } from "@react-three/fiber";
import { useEffect } from "react";

/**
 * Stamp `value` on `[data-testid="viewport"]` under `datasetKey` (a camelCase
 * `dataset` key, so `edgePickHover` renders as `data-edge-pick-hover`), and
 * remove it when the value is null or the overlay unmounts.
 */
export function useViewportPickStamp(
  datasetKey: string,
  value: number | string | null,
): void {
  const canvas = useThree((state) => state.gl.domElement);
  useEffect(() => {
    const node = canvas.closest<HTMLElement>('[data-testid="viewport"]');
    if (node === null) return;
    if (value === null) delete node.dataset[datasetKey];
    else node.dataset[datasetKey] = String(value);
    return () => {
      delete node.dataset[datasetKey];
    };
  }, [datasetKey, value, canvas]);
}
