/**
 * The set-up actions that put views on an empty sheet: the standard four-view
 * layout, the lone flat pattern, and the lone section view (with its author
 * panel's state). Split out of `DrawingPage.tsx` (SPLIT-DRAWINGPAGE);
 * behaviour unchanged.
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import {
  type SectionViewParams,
  createSheet,
  createView,
  updateSheet,
} from "../../api/drawings";
import {
  HOUSE_SCALE,
  HOUSE_SET,
  HOUSE_SHEET_SIZE,
} from "../../drawing/houseSet";
import { fetchFeatureTree } from "../../api/parts";
import {
  AUTO_SCALE,
  STANDARD_VIEWS,
  type ModelExtents,
  chooseSheetSize,
  fitStandardScale,
  proposeOrientation,
  sheetDimensions,
  sheetHeaderForNewSheet,
  standardLayout,
} from "../../drawing/layout";
import { resolveDatumPlaneOptions } from "../../sketch/plane";
import { scaleFromValue, sourceExtentsQueryOptions } from "./sheetHeader";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function useLayoutActions(
  data: Pick<
    DrawingData,
    | "hasLayout"
    | "selectedSourceId"
    | "selectedSourceKind"
    | "docVersion"
    | "sheet"
    | "scaleValue"
    | "setScaleValue"
    | "sizeValue"
    | "sizeFixed"
    | "partTree"
    | "orientationOverride"
  >,
  { drawingId, queryClient, setActionError }: DrawingActionContext,
) {
  const {
    hasLayout,
    selectedSourceId,
    selectedSourceKind,
    docVersion,
    sheet,
    scaleValue,
    setScaleValue,
    sizeValue,
    sizeFixed,
    partTree,
    orientationOverride,
  } = data;

  // ---------------------------------------------------------------------
  // The auto-layout action: create the sheet (if needed) + the four views,
  // threading the optimistic-concurrency version through each write.
  // ---------------------------------------------------------------------
  const [busy, setBusy] = useState(false);

  // Section-view authoring: the panel's open state, its own create-time error,
  // and the referenced part's reusable datums (fetched lazily when the panel
  // opens). The datum options come from the SAME resolver the sketch plane
  // picker reads, so a section's plane FeatureRef means the same plane there.
  const [sectionOpen, setSectionOpen] = useState(false);
  const [sectionError, setSectionError] = useState<string | null>(null);
  const sectionPartTreeQuery = useQuery({
    queryKey: ["drawing-section-part-tree", selectedSourceId],
    enabled:
      sectionOpen && selectedSourceId !== null && selectedSourceKind === "part",
    queryFn: () => fetchFeatureTree(selectedSourceId as string),
    staleTime: 30_000,
  });
  const sectionDatumOptions = useMemo(
    () => resolveDatumPlaneOptions(sectionPartTreeQuery.data?.features ?? []),
    [sectionPartTreeQuery.data],
  );

  const handleLayout = useCallback(() => {
    if (hasLayout || selectedSourceId === null || busy) return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        let sheetId = sheet?.id ?? null;
        // Measure FIRST, through the same cache the header cell reads, so the
        // paper is chosen from the document rather than after it (REACH-3-FLOW
        // P1-1: Sheet 1 used to be born `orientation: "landscape"` as a
        // literal). `ensureQueryData` shares the one evaluation the proposal
        // already warmed — and closes the race where a user clicks "Lay out"
        // before that query lands, which reading `orientationFit` here would
        // have left as a silent fall back to landscape.
        let extents: ModelExtents | null = null;
        try {
          extents = await queryClient.ensureQueryData(
            sourceExtentsQueryOptions(
              selectedSourceId,
              selectedSourceKind,
              partTree?.tree_version,
            ),
          );
        } catch {
          // unmeasurable — keep the picked scale and the default paper
        }
        // The paper: the user's size if they fixed one; otherwise the default
        // grows within its series only when no standard scale fits it.
        const convention = sheet?.projection ?? "third_angle";
        const size =
          extents && sheet === null
            ? chooseSheetSize(
                extents,
                sizeValue,
                sizeFixed,
                scaleValue,
                convention,
              )
            : sizeValue;
        const header = sheetHeaderForNewSheet({
          name: "Sheet 1",
          size,
          layout: "standard",
          fit: extents
            ? proposeOrientation(extents, size, scaleValue, convention)
            : null,
          inherit: sheet,
          override: orientationOverride,
        });
        if (sheetId === null) {
          const created = await createSheet(drawingId, {
            name: header.name,
            size: header.size,
            orientation: header.orientation,
            projection: header.projection,
            expected_version: version,
          });
          version = created.doc_version;
          sheetId = created.sheet.id;
        }
        // Lay out against the paper THIS sheet is actually on — a sheet added
        // portrait (REACH-3) must seed its anchors and fit its scale against
        // 210x297, not the landscape default. For a sheet created a moment ago
        // that is the proposed paper; for an existing empty sheet it is the one
        // already persisted, which the user may have flipped by hand.
        const dims = sheetDimensions(
          sheet?.size ?? header.size,
          sheet?.orientation ?? header.orientation,
        );
        const anchors = standardLayout(dims);
        // Fit-scale: never lay out views that overflow their cells — measure
        // the source and reduce the scale until the four standard views fit
        // (the user's picked scale is a ceiling; see fitScale). EITHER kind of
        // source is measurable now (`fetchSourceExtents`): a part by its bbox,
        // an ASSEMBLY by its SOLVED compound's extents. Before that route
        // existed the assembly branch kept the picked scale, and a rig whose
        // instances were seeded apart laid out at 1:1 with its right view
        // straddling the title block (ASMDRAW-FIT-1b, and the founder's
        // parts-list screenshot).
        //
        // A source that cannot be measured keeps the picked scale — the layout
        // still lands, just unfitted, and the composer's own `views_overlap` /
        // `views_crowded` measurements surface in the check strip, so a sheet
        // that could not be fitted says so rather than looking fine.
        //
        // This fit runs ONCE, here, at layout time. A later re-solve that moves
        // the extents does NOT re-scale a sheet already on screen: the scale of
        // a laid-out sheet is the user's (they can re-pick it, and a dragged
        // view is pinned `auto_place:false`), and re-flowing paper under
        // someone editing mates in another tab is the "no surprises" half of
        // the flow rule. The check strip tells them; it never moves them.
        //
        // The scale is the largest standard one whose views fit inside the
        // border, clear of the title block (BIKE2-DRAWING-SCALE): Auto may
        // enlarge a small part to 2:1 or 5:1, a picked scale is a ceiling. A
        // source that cannot be measured draws Auto at 1:1.
        const fittedValue = extents
          ? fitStandardScale(extents, dims, scaleValue, header.projection)
              .option.value
          : scaleValue === AUTO_SCALE
            ? "1:1"
            : scaleValue;
        const scale = scaleFromValue(fittedValue);
        for (const projection of STANDARD_VIEWS) {
          const anchor = anchors[projection];
          const created = await createView(drawingId, sheetId, {
            projection,
            ref_document_id: selectedSourceId,
            ref_document_kind: selectedSourceKind,
            scale,
            position: { x_mm: anchor.x, y_mm: anchor.y },
            // Auto-layout lands each standard view (bounds-aware); a later drag
            // flips this view to auto_place:false with a persisted position.
            auto_place: true,
            // A NEW arrangement clears the title block (the fit above assumed
            // it); views laid out before keep composing exactly as they did.
            clear_title_block: true,
            expected_version: version,
          });
          version = created.doc_version;
        }
        // Only after every view landed: reflect the substitution in the picker
        // state (a FAILED layout must not mutate the user's pick — review
        // 2026-07-22), and post-layout the band's scale readout derives from
        // the stored views either way.
        // Auto stays Auto.
        if (scaleValue !== AUTO_SCALE && fittedValue !== scaleValue) {
          setScaleValue(fittedValue);
        }
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The views could not be laid out.",
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [
    hasLayout,
    selectedSourceId,
    selectedSourceKind,
    busy,
    docVersion,
    sheet,
    drawingId,
    scaleValue,
    sizeValue,
    sizeFixed,
    partTree,
    orientationOverride,
    queryClient,
  ]);

  // The flat-pattern action: create the sheet (if needed) + a single flat_pattern
  // view (the lone unfold blank + its bend table, sheet-metal.md §7). A part with
  // no sheet-metal bends composes an honest `flat_pattern_not_sheet_metal` failed
  // view — surfaced inline, never a crash.
  const handleFlatPattern = useCallback(() => {
    // Part-only, and the guard is not redundant with the band's disabled cell:
    // `F` reaches this handler directly from the keyboard.
    if (hasLayout || selectedSourceId === null || busy) return;
    if (selectedSourceKind !== "part") return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        let sheetId = sheet?.id ?? null;
        // A LONE-view sheet: `fit: null` on purpose, not by omission. The
        // proposal is a reading of the FOUR-quadrant fit, and a flat pattern's
        // drawn footprint is the UNFOLDED blank, which the client has not
        // measured (see the scale note below). Proposing paper from the 3D bbox
        // here would be the "promises what it will not deliver" defect
        // REACH-3-FLOW's other half is about, in a new place.
        const header = sheetHeaderForNewSheet({
          name: "Sheet 1",
          size: sizeValue,
          layout: "lone",
          fit: null,
          inherit: sheet,
        });
        if (sheetId === null) {
          const created = await createSheet(drawingId, {
            name: header.name,
            size: header.size,
            orientation: header.orientation,
            projection: header.projection,
            expected_version: version,
          });
          version = created.doc_version;
          sheetId = created.sheet.id;
        }
        // The chosen size flows to the flat-pattern sheet too, so the lone
        // unfold blank is centred on (and composed against) the picked paper.
        // NB: the lone flat view is not yet fit-scaled to the sheet the way the
        // four standard views are — a flat-pattern fit needs the UNFOLDED
        // extents (not the 3D bbox `fitScale` reads), a separate slice (BACKLOG).
        const dims = sheetDimensions(
          sheet?.size ?? header.size,
          sheet?.orientation ?? header.orientation,
        );
        const created = await createView(drawingId, sheetId, {
          projection: "flat_pattern",
          ref_document_id: selectedSourceId,
          ref_document_kind: "part",
          scale: scaleFromValue(scaleValue),
          position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
          auto_place: true,
          clear_title_block: false,
          expected_version: version,
        });
        version = created.doc_version;
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The flat pattern could not be laid out.",
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [
    hasLayout,
    selectedSourceId,
    selectedSourceKind,
    busy,
    docVersion,
    sheet,
    drawingId,
    scaleValue,
    sizeValue,
    queryClient,
  ]);

  // The section action: create the sheet (if needed) + a single centred section
  // view carrying its cutting plane + flip (drawings-section.md §1). The compose
  // wire (E1a) then resolves the datum, cuts, and hatches automatically — no
  // request body: the compose route reads the persisted `section_params`. A
  // non-principal plane is caught in the panel before this runs; the server also
  // guards it, and the sheet renders `section_plane_not_principal` readably.
  const handleAuthorSection = useCallback(
    (plane: SectionViewParams["plane"], flip: boolean) => {
      // Part-only (`S` reaches this from the keyboard too — see flat pattern).
      if (hasLayout || selectedSourceId === null || busy) return;
      if (selectedSourceKind !== "part") return;
      setBusy(true);
      setSectionError(null);
      void (async () => {
        try {
          let version = docVersion;
          let sheetId = sheet?.id ?? null;
          // A lone centred cut, like the flat pattern above: the four-quadrant
          // fit does not model it, so it takes the shop default rather than a
          // proposal it cannot honour. Convention is still inherited.
          const header = sheetHeaderForNewSheet({
            name: "Sheet 1",
            size: sizeValue,
            layout: "lone",
            fit: null,
            inherit: sheet,
          });
          if (sheetId === null) {
            const created = await createSheet(drawingId, {
              name: header.name,
              size: header.size,
              orientation: header.orientation,
              projection: header.projection,
              expected_version: version,
            });
            version = created.doc_version;
            sheetId = created.sheet.id;
          }
          const dims = sheetDimensions(
            sheet?.size ?? header.size,
            sheet?.orientation ?? header.orientation,
          );
          await createView(drawingId, sheetId, {
            projection: "section",
            ref_document_id: selectedSourceId,
            ref_document_kind: "part",
            scale: scaleFromValue(scaleValue),
            position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
            section_params: { plane, flip },
            auto_place: true,
            clear_title_block: false,
            expected_version: version,
          });
          setSectionOpen(false);
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setSectionError(
            error instanceof Error
              ? error.message
              : "The section view could not be created.",
          );
        } finally {
          setBusy(false);
        }
      })();
    },
    [
      hasLayout,
      selectedSourceId,
      selectedSourceKind,
      busy,
      docVersion,
      sheet,
      drawingId,
      scaleValue,
      sizeValue,
      queryClient,
    ],
  );

  // The house set (HOUSE-DRAWINGS): one action lays out a builder's set — the
  // plan, the four elevations and the materials list, each on its own sheet of
  // ANSI B at 1:48 — the way Chief Architect's plan, elevation and materials
  // sheets come out of one model. An empty first sheet becomes the Plan; the
  // composer places every view itself (the positions are centred seeds).
  const handleHouseSet = useCallback(() => {
    if (hasLayout || selectedSourceId === null || busy) return;
    if (selectedSourceKind !== "part") return;
    setBusy(true);
    setActionError(null);
    void (async () => {
      try {
        let version = docVersion;
        const dims = sheetDimensions(HOUSE_SHEET_SIZE, "landscape");
        for (const [index, entry] of HOUSE_SET.entries()) {
          let sheetId: string;
          if (index === 0 && sheet !== null) {
            const updated = await updateSheet(drawingId, sheet.id, {
              name: entry.name,
              size: HOUSE_SHEET_SIZE,
              orientation: "landscape",
              expected_version: version,
            });
            version = updated.doc_version;
            sheetId = sheet.id;
          } else {
            const created = await createSheet(drawingId, {
              name: entry.name,
              size: HOUSE_SHEET_SIZE,
              orientation: "landscape",
              projection: sheet?.projection ?? "third_angle",
              expected_version: version,
            });
            version = created.doc_version;
            sheetId = created.sheet.id;
          }
          for (const projection of entry.views) {
            const made = await createView(drawingId, sheetId, {
              projection,
              ref_document_id: selectedSourceId,
              ref_document_kind: "part",
              scale: HOUSE_SCALE,
              position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
              auto_place: true,
              clear_title_block: false,
              expected_version: version,
            });
            version = made.doc_version;
          }
        }
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The house set could not be laid out.",
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [
    hasLayout,
    selectedSourceId,
    selectedSourceKind,
    busy,
    docVersion,
    sheet,
    drawingId,
    queryClient,
  ]);

  const handleToggleSection = useCallback(() => {
    setSectionError(null);
    setSectionOpen((open) => !open);
  }, []);

  return {
    busy,
    sectionOpen,
    setSectionOpen,
    sectionError,
    sectionPartTreeQuery,
    sectionDatumOptions,
    handleLayout,
    handleFlatPattern,
    handleAuthorSection,
    handleToggleSection,
    handleHouseSet,
  };
}
