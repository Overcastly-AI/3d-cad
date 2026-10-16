/**
 * The base features geometry is sent for a stretch of a part's tree.
 *
 * A custom feature (a plugin's, RESEARCH §23) never reaches geometry: it
 * stands for the members documents expanded it to and stored with it
 * (`params.expansion`), each under its stable member id. Every client-built
 * request (assembly, measure, drawing views) goes through here, so they all
 * send what documents' own evaluation request sends.
 */
import type { components } from "@loft/ts-client/gateway";

import type { FeatureResponse } from "./partTypes";

export type EvaluatedFeatureInput =
  components["schemas"]["EvaluatedFeatureInput"];

export function evaluatedFeatures(
  features: readonly FeatureResponse[],
): EvaluatedFeatureInput[] {
  return features.flatMap((row): EvaluatedFeatureInput[] => {
    const feature = row.feature;
    if (feature.type !== "custom") {
      return [{ id: row.id, feature }];
    }
    return (feature.params.expansion ?? []).map((member) => ({
      id: member.id,
      feature: { ...member.feature, suppressed: feature.suppressed ?? false },
    }));
  });
}
