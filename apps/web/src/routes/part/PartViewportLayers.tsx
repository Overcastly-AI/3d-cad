/**
 * Everything the viewport draws over the body for the open command: the
 * gauges, the ghosts and the pick overlays.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { MeasureOverlay } from "../../viewport/MeasureOverlay";
import { BendHighlightOverlay } from "../../viewport/BendHighlightOverlay";
import { FlangeSpanOverlay } from "../../viewport/FlangeSpanOverlay";
import { EdgePickOverlay } from "../../viewport/EdgePickOverlay";
import { useEdgePickStore } from "../../features/edgePickStore";
import { ShellFaceOverlay } from "../../viewport/ShellFaceOverlay";
import { HolePointOverlay } from "../../viewport/HolePointOverlay";
import { FacePickOverlay } from "../../viewport/FacePickOverlay";
import { DraftGauge } from "../../viewport/DraftGauge";
import { ExtrudePreview } from "../../viewport/ExtrudePreview";
import { ChamferGauge } from "../../viewport/ChamferGauge";
import { FilletGauge } from "../../viewport/FilletGauge";
import { RevolveGauge } from "../../viewport/RevolveGauge";
import { DatumGauge } from "../../viewport/DatumGauge";
import { ShellGauge } from "../../viewport/ShellGauge";
import { HoleGauge } from "../../viewport/HoleGauge";
import { PatternGaugeLayer } from "../../viewport/PatternGaugeLayer";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { EditorSeat } from "./useEditorSeat";
import type { ViewportState } from "./useViewportState";
import type { PickOverlays } from "./usePickOverlays";
import type { PickSessions } from "./usePickSessions";
import type { PickState } from "./usePickState";
import type { SketchEntry } from "./useSketchEntry";
import type { DatumFacePicking } from "./useDatumFacePicking";
import type { HolePicking } from "./useHolePicking";

export function PartViewportLayers({
  partDocument,
  partBody,
  editorSeat,
  viewportState,
  pickOverlays,
  pickSessions,
  pickState,
  sketchEntry,
  datumFacePicking,
  holePicking,
}: {
  partDocument: Pick<PartDocument, "mode" | "lengthUnit">;
  partBody: Pick<PartBody, "editor">;
  editorSeat: Pick<
    EditorSeat,
    | "patternPreview"
    | "patternCountGauge"
    | "patternSpacingGauge"
    | "extrudePreview"
    | "handleExtrudeDrag"
    | "revolveGauge"
    | "handleRevolveDrag"
    | "draftGauge"
    | "handleDraftDrag"
    | "filletRadiusMm"
    | "edgeGaugeAnchors"
    | "filletRadiusGauge"
    | "chamferDistanceMm"
    | "chamferDistanceGauge"
    | "shellThicknessMm"
    | "shellThicknessGauge"
    | "datumGaugeSeed"
    | "datumOffsetGauge"
    | "holeGauge"
    | "holeDiameterGauge"
    | "holeDepthGauge"
  >;
  viewportState: Pick<
    ViewportState,
    | "patternGaugeAnchor"
    | "patternBodyGeometry"
    | "showExtrudeGhost"
    | "extrudeGhostLayer"
    | "revolveGaugeLayer"
    | "draftGaugeFace"
  >;
  pickOverlays: Pick<
    PickOverlays,
    | "edgePicking"
    | "shellPicking"
    | "pickableFaces"
    | "datumPickableFaces"
    | "holePickableFaces"
    | "holePlacementHidden"
    | "holeOverlayFaces"
    | "holeOverlayVertices"
    | "holeOverlayEdges"
  >;
  pickSessions: Pick<
    PickSessions,
    | "reliefBendHighlights"
    | "edgeFlangeSpan"
    | "edgeFlangeSpanLabel"
    | "shellGaugeAnchor"
    | "datumGaugeAnchor"
    | "holeGaugeAnchor"
  >;
  pickState: Pick<
    PickState,
    "pendingFaceIndex" | "datumFacePick" | "holePick" | "holePreview"
  >;
  sketchEntry: Pick<SketchEntry, "authorFacePlane">;
  datumFacePicking: Pick<DatumFacePicking, "pickDatumFace">;
  holePicking: Pick<HolePicking, "pickHoleFace" | "pickHolePoint">;
}) {
  const { mode, lengthUnit } = partDocument;
  const { editor } = partBody;
  const {
    patternPreview,
    patternCountGauge,
    patternSpacingGauge,
    extrudePreview,
    handleExtrudeDrag,
    revolveGauge,
    handleRevolveDrag,
    draftGauge,
    handleDraftDrag,
    filletRadiusMm,
    edgeGaugeAnchors,
    filletRadiusGauge,
    chamferDistanceMm,
    chamferDistanceGauge,
    shellThicknessMm,
    shellThicknessGauge,
    datumGaugeSeed,
    datumOffsetGauge,
    holeGauge,
    holeDiameterGauge,
    holeDepthGauge,
  } = editorSeat;
  const {
    patternGaugeAnchor,
    patternBodyGeometry,
    showExtrudeGhost,
    extrudeGhostLayer,
    revolveGaugeLayer,
    draftGaugeFace,
  } = viewportState;
  const {
    edgePicking,
    shellPicking,
    pickableFaces,
    datumPickableFaces,
    holePickableFaces,
    holePlacementHidden,
    holeOverlayFaces,
    holeOverlayVertices,
    holeOverlayEdges,
  } = pickOverlays;
  const {
    reliefBendHighlights,
    edgeFlangeSpan,
    edgeFlangeSpanLabel,
    shellGaugeAnchor,
    datumGaugeAnchor,
    holeGaugeAnchor,
  } = pickSessions;
  const { pendingFaceIndex, datumFacePick, holePick, holePreview } = pickState;
  const { authorFacePlane } = sketchEntry;
  const { pickDatumFace } = datumFacePicking;
  const { pickHoleFace, pickHolePoint } = holePicking;
  // The sketcher's Project tool picks body edges WHILE sketching
  // (SKETCH-PROJECT-EDGES); every other edge pick is a model-mode command.
  const projecting = useEdgePickStore((s) => s.purpose === "project");
  return (
    <>
      {/* ANCHOR D, pattern (CRAFT-11) — two mounts and a ghost. The
                  anchor is computed HERE and handed down, so CRAFT-12's
                  selection store re-wires this one expression rather than the
                  gauge component. */}
      {mode === "off" &&
      editor?.kind === "pattern" &&
      patternPreview !== null &&
      patternGaugeAnchor !== null ? (
        <PatternGaugeLayer
          anchor={patternGaugeAnchor}
          count={patternPreview.count}
          spacingMm={patternPreview.spacingMm}
          onCountChange={patternCountGauge.set}
          onSpacingChange={patternSpacingGauge.set}
          bodyGeometry={patternBodyGeometry}
        />
      ) : null}
      {showExtrudeGhost && extrudeGhostLayer !== null && extrudePreview ? (
        <ExtrudePreview
          layer={extrudeGhostLayer}
          distanceMm={extrudePreview.distanceMm}
          direction={extrudePreview.direction}
          extent={extrudePreview.extent}
          operation={extrudePreview.operation}
          onDepthChange={handleExtrudeDrag}
          twistDeg={extrudePreview.twistDeg}
          twistCentre={extrudePreview.twistCentre}
        />
      ) : null}
      {/* ANCHOR D (CRAFT-10) — THE ANGULAR GAUGES.
                  The revolve arc stands on its own axis, which this item draws
                  for the first time: before it, the axis was a dropdown and the
                  scene showed nothing, so an arc would have been an arc around
                  nothing. The layer is resolved from the full `solved` set (not
                  from whatever the browser is showing) for the same reason the
                  extrude ghost is: the gauge must appear whether or not a body
                  already exists. */}
      {mode === "off" &&
      editor?.kind === "revolve" &&
      revolveGauge !== null &&
      revolveGaugeLayer !== null ? (
        <RevolveGauge
          basis={revolveGaugeLayer.basis}
          entities={revolveGaugeLayer.entities}
          axis={revolveGauge.axis}
          angleDeg={revolveGauge.angleDeg}
          onAngleChange={handleRevolveDrag}
        />
      ) : null}
      {/* The taper gauge stands on the FIRST picked face — pick order is
                  preserved by the store, so "the one you picked first" is a
                  stable answer, and a draft that tapers six faces by one angle
                  needs one instrument, not six. The face is passed DOWN as a
                  prop; `DraftGauge` reads no store, so W4's selection store is a
                  change to this line rather than to that component. */}
      {mode === "off" &&
      editor?.kind === "draft" &&
      draftGauge !== null &&
      draftGaugeFace !== undefined ? (
        <DraftGauge
          face={draftGaugeFace}
          neutral={{
            base: draftGauge.base,
            offsetMm: draftGauge.offsetMm,
            flip: draftGauge.flip,
          }}
          angleDeg={draftGauge.angleDeg}
          onAngleChange={handleDraftDrag}
        />
      ) : null}
      <MeasureOverlay />
      {edgePicking && (mode === "off" || (mode === "draw" && projecting)) ? (
        <EdgePickOverlay />
      ) : null}
      {/* The fillet/chamfer gauges stand on the picked edges and draw
                  the RESULT at the live value — route (b) of direction §8.4,
                  line-work rather than a ghost: the rolling ball's tangency
                  and the bevel band, both computed from the number the arrow
                  reports, so the drag moves the model and not only the field. */}
      {mode === "off" &&
      editor?.kind === "fillet" &&
      filletRadiusMm !== null ? (
        <FilletGauge
          anchors={edgeGaugeAnchors}
          radiusMm={filletRadiusMm}
          unit={lengthUnit}
          onRadiusChange={filletRadiusGauge.set}
        />
      ) : null}
      {mode === "off" &&
      editor?.kind === "chamfer" &&
      chamferDistanceMm !== null ? (
        <ChamferGauge
          anchors={edgeGaugeAnchors}
          distanceMm={chamferDistanceMm}
          unit={lengthUnit}
          onDistanceChange={chamferDistanceGauge.set}
        />
      ) : null}
      {mode === "off" && reliefBendHighlights.length > 0 ? (
        <BendHighlightOverlay bends={reliefBendHighlights} />
      ) : null}
      {mode === "off" &&
      editor?.kind === "edgeFlange" &&
      edgeFlangeSpan !== null ? (
        <FlangeSpanOverlay span={edgeFlangeSpan} label={edgeFlangeSpanLabel} />
      ) : null}
      {mode === "off" && shellPicking ? (
        <ShellFaceOverlay
          testIdPrefix={editor?.kind === "draft" ? "draft-face" : "shell-face"}
        />
      ) : null}
      {/* THE SHELL GAUGE stands on the face you last opened — so it
                  appears with the pick rather than before it, and the editor's
                  own field is still the exact path (CRAFT-9b). */}
      {mode === "off" &&
      editor?.kind === "shell" &&
      shellGaugeAnchor !== null &&
      shellThicknessMm !== null ? (
        <ShellGauge
          anchor={shellGaugeAnchor}
          thicknessMm={shellThicknessMm}
          onChange={shellThicknessGauge.set}
        />
      ) : null}
      {mode === "off" &&
      editor?.kind === "datum" &&
      datumGaugeAnchor !== null &&
      datumGaugeSeed !== null ? (
        <DatumGauge
          anchor={datumGaugeAnchor}
          offsetMm={datumGaugeSeed.offsetMm}
          onChange={datumOffsetGauge.set}
        />
      ) : null}
      {/* Mounted for the whole plane-pick step (SKETCH-PLANE-PICK): the faces
          are pickable beside the origin sheets, which yield to the body
          (`sheetYield.ts`). `pickableFaces` is null when there is none. */}
      {mode === "plane" ? (
        <FacePickOverlay
          faces={pickableFaces}
          onPick={authorFacePlane}
          pendingIndex={pendingFaceIndex}
        />
      ) : null}
      {mode === "off" && editor?.kind === "datum" && datumFacePick !== null ? (
        <FacePickOverlay
          faces={datumPickableFaces}
          onPick={pickDatumFace}
          pendingIndex={null}
        />
      ) : null}
      {mode === "off" && editor?.kind === "hole" && holePick === "face" ? (
        <FacePickOverlay
          faces={holePickableFaces}
          onPick={pickHoleFace}
          pendingIndex={null}
        />
      ) : null}
      {/* ANCHOR D, hole (CRAFT-9c) — Ø and depth, with the bore circle
                  and the depth plane. Stood down while a PICK is armed: a pick
                  in progress is a different gesture on the same face, and a
                  hit sleeve lying across the drill point would take the very
                  click the point pick is waiting for. It comes back the moment
                  the pick lands. Withheld with the placement overlay when the
                  face's body is hidden (SEL-7), for that overlay's reason. */}
      {mode === "off" &&
      editor?.kind === "hole" &&
      holePick === null &&
      !holePlacementHidden &&
      holeGaugeAnchor !== null &&
      holeGauge !== null &&
      holeGauge.diameterMm !== null ? (
        <HoleGauge
          anchor={holeGaugeAnchor}
          diameterMm={holeGauge.diameterMm}
          depthMm={holeGauge.depthMm}
          onDiameterChange={holeDiameterGauge.set}
          onDepthChange={holeDepthGauge.set}
        />
      ) : null}
      {/* The placement overlay shows from the moment a face exists, not
                only while the point pick is armed: the datum crosshair is what
                says where the editor's X/Y cells count from, and it has to be
                on screen while they are being typed (QA3-1). */}
      {mode === "off" &&
      editor?.kind === "hole" &&
      holePreview?.signature != null ? (
        <HolePointOverlay
          signature={holePreview.signature}
          // Not `holePickableFaces`, which is gated on the FACE pick
          // being armed — the point pick needs the same list to resolve
          // its placement face's ordinal for the free-placement raycast.
          faces={holeOverlayFaces}
          vertices={holeOverlayVertices}
          edges={holeOverlayEdges}
          position={holePreview.position}
          armed={holePick === "point"}
          onPick={pickHolePoint}
        />
      ) : null}
    </>
  );
}
