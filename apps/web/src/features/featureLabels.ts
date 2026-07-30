/**
 * Human labels for the wire feature types — ONE source, read by every surface
 * that names a feature (the tree row's badge, the timeline chip's accessible
 * name). Extracted from `FeatureTreePanel` on the second use (the bottom
 * timeline), so a chip and a row can never disagree about what a feature is.
 */

/**
 * Friendlier type badges for the few feature types whose wire name is
 * snake_case. Everything else (extrude / fillet / …) is already a plain word,
 * so it falls through to the raw type.
 */
const FEATURE_TYPE_LABEL: Record<string, string> = {
  sheet_metal_base_flange: "base flange",
  sheet_metal_edge_flange: "edge flange",
  sheet_metal_hem: "hem",
  sheet_metal_corner_relief: "corner relief",
};

/** The label for a feature type — a friendly name, else the raw type. */
export function featureTypeLabel(type: string): string {
  return FEATURE_TYPE_LABEL[type] ?? type;
}
