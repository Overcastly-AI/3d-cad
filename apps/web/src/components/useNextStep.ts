/**
 * WHEN the band may propose — the build gate in front of `nextStepFor`'s table.
 *
 * W2 review, finding 6: the proposal was passed as `nextStepFor(tree.features)`
 * with nothing else, so it was purely a property of the TREE'S SHAPE. Open a
 * part whose last live feature is an extrude — from last week, from last month
 * — and the band wore the dot and said "Round the new body's edges" about work
 * the user finished and moved on from. Dismissal keys on the feature id in
 * component state, so it re-armed on every navigation, forever. That
 * contradicted FLOW-B3's own contract ("written once per build, never
 * re-armed") and, more to the point, a proposal that reappears for the rest of
 * a part's life stops being a proposal and becomes furniture.
 *
 * THE GATE: a proposal is armed only for a feature this workspace watched
 * ARRIVE. The first tree a mount receives establishes what already existed —
 * everything in it predates the session and proposes nothing, however recent it
 * looks — and every id that shows up after that was built here, now, by this
 * user. `nextStepFor` is unchanged and still decides WHICH verb; this only
 * decides whether there is a moment to propose about at all.
 *
 * What it deliberately does NOT arm, because each would be a different claim
 * than "something just built":
 *
 *  · an EDIT of an existing feature (same id, new parameters). Arguable, and
 *    left out because the tree's tip after an edit is usually not the feature
 *    edited, so the proposal would be about something the user did not touch.
 *  · rolling the timeline forward, or unsuppressing — no id arrives, and the
 *    feature it reveals was built long ago.
 *  · an undo that restores a deleted feature: the id is one this session has
 *    already seen, so it stays quiet rather than re-arming a proposal the user
 *    has already answered.
 *
 * A set of ids rather than "the last one to arrive": an import lands several
 * features at once, and the question this has to answer is about the ONE the
 * table picked, not about arrival order.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import type { FeatureResponse } from "../api/parts";

import { nextStepFor, type NextStepProposal } from "./nextStep";

export function useNextStepAfterBuild(
  features: readonly FeatureResponse[] | undefined,
): NextStepProposal | null {
  /**
   * Ids born while this workspace has been mounted. State, not a ref: the
   * proposal is read during render, so a ref would show the dot one render
   * late — after some unrelated update happened to re-render the band.
   */
  const [born, setBorn] = useState<ReadonlySet<string>>(() => new Set());
  /** Every id seen so far, including the ones that predate the session. */
  const known = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (features === undefined) return;
    const before = known.current;
    if (before === null) {
      // THE FIRST TREE. Everything in it existed before the user arrived, so
      // nothing here is a build — this is the line that stops a page load
      // proposing about last week's extrude.
      known.current = new Set(features.map((feature) => feature.id));
      return;
    }
    const fresh = features
      .map((feature) => feature.id)
      .filter((id) => !before.has(id));
    for (const id of fresh) before.add(id);
    if (fresh.length === 0) return;
    setBorn((previous) => {
      const next = new Set(previous);
      for (const id of fresh) next.add(id);
      return next;
    });
  }, [features]);

  const proposal = useMemo(() => nextStepFor(features ?? []), [features]);
  if (proposal === null) return null;
  return born.has(proposal.featureId) ? proposal : null;
}
