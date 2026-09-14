/**
 * THE REFERENCE CUBE DURING AUTHORING (CRAFT-6) — plane pick and sketch.
 *
 * WHY THIS EXISTS AT ALL. `Viewport` mounts the cube, the view rail and the
 * nav cue together under one `viewNav` prop, which `PartPage` sets to
 * `mode === "off"`. So entering a sketch took the cube away, and the craft
 * audit is right that this is backwards: orientation matters MORE while you
 * are drawing on a plane suspended in space than it does while you are turning
 * a finished body. The cube is an orientation READOUT before it is a control,
 * and a readout is exactly what a modeller loses track of mid-sketch.
 *
 * WHY IT IS NOT SIMPLY A BUG IN THAT PROP. Whoever built the sketch rig had a
 * real reason, recorded in `ProjectionRig`'s doc comment: the sketch rig frames
 * a plane by parking the camera at a computed DISTANCE
 * (`SketchScene.sketchCameraDistanceMm`), which a parallel camera does not
 * answer to — so the rig holds perspective for the duration, and putting the
 * PROJECTION control on screen would offer a mode it cannot honour. That half
 * is correct and is preserved: the view rail (which carries `view-projection`)
 * stays unmounted. Only the cube comes back, through the `hud` slot, which is
 * why this is a component here rather than a second prop on `Viewport`.
 *
 * IS THE CUBE INTERACTIVE HERE? YES — MEASURED, not assumed, because the
 * honest default was "display-only if steering fights the rig". It does not
 * fight it. At 1280x800, against the live stack:
 *
 *   plane pick  facet click moved the camera 41.851 deg, residual motion over
 *               the next 1.2 s: 0.0000 deg
 *   sketch      facet click moved the camera 45.000 deg, residual motion over
 *               the next 1.2 s: 0.0000 deg
 *
 * Zero residual is the load-bearing number. The failure everyone fears here is
 * the documented DEADLOCK — two rigs easing one camera toward different poses
 * never converge, and the camera oscillates forever (measured at radius ~180
 * while landing FB-7). That cannot happen, because `SketchCameraRig`'s goal is
 * set by an effect keyed on `[mode, plane]` and cleared the moment the park
 * lands: after the entry ease it is DORMANT, not holding. This is the same
 * reason mid-sketch orbit already works on the middle button and Alt+left
 * (VP-1/VP-1a) — the sketch rig does not re-park a camera the modeller moves.
 * A facet click is that same gesture issued by another instrument.
 *
 * It also cannot lose the sketch framing: `CameraRig`'s `direction` branch
 * rotates about the CURRENT target at the CURRENT radius, so the distance the
 * sketch rig computed survives the move untouched. Only the attitude changes.
 *
 * WHAT DOES HAVE TO BE HELD BACK: THE PROJECTION PREFERENCE.
 * `requestDirection` arms orthographic unconditionally — correct in the part
 * workspace, where "look along this axis" is what orthographic is for. But
 * `ProjectionRig` is pinned to perspective while the sketch rig owns the
 * camera, so during authoring that preference cannot be honoured NOW; it is
 * simply banked, and cashed at sketch exit. Measured before this guard existed:
 * enter a sketch in perspective, click one facet, leave — and the stamp reads
 *
 *   AFTER-EXIT projection stamp: orthographic
 *
 * i.e. the modeller's projection silently changed while they were doing
 * something else, applied to the CAMRESTORE-1 pose they were handed back
 * rather than to anything they asked it for. That is precisely the invariant
 * the `restore` command is documented to protect ("it puts the camera back at
 * an attitude the modeler already had ... must not silently change how they
 * were looking"), so the leak defeats a rule the code already states.
 *
 * So: while authoring, the projection preference is FROZEN. The cube may
 * orient; it may not re-mode a camera the rig is holding. That is not a
 * workaround bolted over the store — it is the accurate statement of what this
 * instrument can do in this mode, and it has no false positives, because the
 * cube is the only thing that can reach `projection` during authoring (the
 * view rail is unmounted, `useViewHotkeys` is disarmed with `viewNav`, and
 * `openViewportMenu` returns early unless `mode === "off"`).
 *
 * WHY IT GUARDS RATHER THAN RESTORING ON UNMOUNT. A snapshot put back in the
 * unmount cleanup would let the store hold the leaked value right through the
 * commit where `viewNav` flips true — so `ProjectionRig` would read
 * orthographic, swap the camera class, and swap back a render later when the
 * restore landed. Two camera swaps, each of which rebuilds OrbitControls and
 * re-carries the orbit target, on the exact frame CAMRESTORE-1 is easing the
 * remembered pose back. Holding the value steady means the wrong value never
 * exists, so there is nothing to flash.
 *
 * NO VISUAL DELTA, DELIBERATELY. The cube is the same instrument here as in
 * the part workspace — same block, same seat, same brass on hover — because it
 * behaves the same way, and because the mandate spends boldness in ONE place
 * and it is already spent on this block. A "sketch mode" badge or a dimmed
 * variant would invent a second dialect for one instrument and decorate rather
 * than inform, which mandate 3a(c) calls a defect outright. There is nothing to
 * signal: it accepts clicks, so it correctly looks like it accepts clicks.
 */
import { useEffect } from "react";

import { useViewCommandStore } from "../viewport/viewCommands";
import { ViewCube } from "../viewport/ViewCube";

export function AuthoringViewCube() {
  useEffect(() => {
    const held = useViewCommandStore.getState().projection;
    // Synchronous: zustand notifies inside `set`, so the corrective toggle
    // lands before React reads a snapshot. The nested `set` re-enters this
    // listener exactly once, finds `projection === held`, and stops.
    return useViewCommandStore.subscribe((state) => {
      if (state.projection !== held) state.toggleProjection();
    });
  }, []);

  return <ViewCube />;
}
