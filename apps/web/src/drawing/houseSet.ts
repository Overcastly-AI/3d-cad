/**
 * The house set (HOUSE-DRAWINGS): what one "House set" lays out for a part —
 * a builder's permit and crew drawings. Revit cuts a floor plan 4'-0" above
 * its level and places schedules on sheets; Chief Architect dimensions the
 * exterior to the opening centres and puts its Materials List on a sheet. So:
 *
 *   1. Plan — the horizontal section 48 in above the lowest floor, with its
 *      exterior dimension strings;
 *   2. Elevations — front, back, left and right;
 *   3. Materials — the cut list as a yard order.
 *
 * All three on ANSI B (11 x 17, the half-size set a crew carries) at 1/4" =
 * 1'-0" (1:48), the scale a plan and its elevations are drawn at. The composer
 * places every view itself, so the stored positions are only centred seeds.
 */
import type { components } from "@loft/ts-client/gateway";

import type { SheetSize, ViewProjection, ViewScale } from "../api/drawings";
import type { FeatureResponse } from "../api/partTypes";

export type DrawingMember = components["schemas"]["DrawingMember"];

/** The set's paper: ANSI B landscape. */
export const HOUSE_SHEET_SIZE: SheetSize = "ANSI_B";

/** 1/4" = 1'-0". */
export const HOUSE_SCALE: ViewScale = { numerator: 1, denominator: 48 };

/** The set's sheets, in order, and the views each carries. */
export const HOUSE_SET: readonly {
  name: string;
  views: readonly ViewProjection[];
}[] = [
  { name: "Plan", views: ["plan"] },
  {
    name: "Elevations",
    views: [
      "elevation_front",
      "elevation_back",
      "elevation_left",
      "elevation_right",
    ],
  },
  { name: "Materials", views: ["materials"] },
];

/**
 * The part's plugin members — which body is a subfloor, a header, a top plate
 * — read from each custom feature's stored expansion, as documents' cut-list
 * request reads them. A drawing evaluation sends them so the plan cuts at the
 * same height, and dimensions the same openings, as the composed sheet.
 */
export function drawingMembers(
  features: readonly FeatureResponse[],
): DrawingMember[] {
  return features.flatMap((row): DrawingMember[] => {
    const feature = row.feature;
    if (feature.type !== "custom") return [];
    return (feature.params.expansion ?? []).map((member) => ({
      feature_id: member.id,
      plugin_id: feature.params.plugin_id,
      role: member.role,
    }));
  });
}

/** True when the sheet carries a materials list (its CSV can be downloaded). */
export function hasMaterialsView(
  views: readonly { projection: ViewProjection }[],
): boolean {
  return views.some((view) => view.projection === "materials");
}
