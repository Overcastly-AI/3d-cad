/**
 * WHICH FEATURE THE VIEWPORT TINTS — the command's scope when a command is
 * asking, the tree selection otherwise (REACH-2-FLOW-B).
 *
 * The defect this closes: the body's feature tint read `selectedFeatureId`, so
 * it answered a different question from the two surfaces beside it. On a plate
 * with two identical bores it went on tinting `Hole1` after the user flipped
 * the pattern's scope row to `This body` — chrome stating something the command
 * will not do — and it tinted nothing at all when the editor seeded itself from
 * the TIP with nothing selected. The tree stamp and the timeline chip already
 * read `scopedFeatureIds` and get both cases right; this makes the third
 * surface read the same source.
 *
 * WHY THE SCOPE NEEDS THREE STATES AND NOT TWO. `[]` used to mean both "the
 * whole body" and "no command is asking", which the tree and the timeline can
 * afford to conflate — neither has a fallback, so both readings render the same
 * absence. The viewport cannot: it must fall back to the selection when no
 * command is open, and must NOT when the open command has chosen the body. So
 * `null` is "nobody is asking" and `[]` is "asked, and the answer names no
 * feature".
 *
 * WHY `This body` PAINTS NOTHING, which is a choice and not a default. A
 * highlight is a DIFFERENCER: it is legible only against the un-highlighted
 * thing beside it. Tinting every face for a whole-body scope would flood the
 * frame with brass, hide the machined read the user is about to pattern, and
 * carry exactly as much information as tinting none — while colliding with the
 * distinct whole-body SELECT state that already means something else
 * (`ModelMesh.highlight === "selected"`). Clearing it also makes the two
 * readings tell each other apart at a glance, which is the entire job of an
 * echo, and it keeps the viewport in step with the tree and the timeline, which
 * clear in the same frame. The words `This body` are on the scope row itself,
 * pressed and named, with its note beneath — the reading is stated where it is
 * legible rather than smeared over the model.
 */

/**
 * The feature ids whose faces the viewport should tint.
 *
 * @param commandScope What the OPEN command will act on, published by its scope
 *   row (`usePublishedScope`). `null` when no command is authoring a scope;
 *   `[]` when one is and its answer is the whole body.
 * @param selectedFeatureId The tree selection, or null.
 */
export function highlightedFeatureIds(
  commandScope: readonly string[] | null,
  selectedFeatureId: string | null,
): readonly string[] {
  if (commandScope !== null) return commandScope;
  return selectedFeatureId === null ? [] : [selectedFeatureId];
}
