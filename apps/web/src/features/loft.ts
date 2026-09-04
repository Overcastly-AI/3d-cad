/**
 * Loft-feature view logic — pure functions the LoftEditor and the PartPage
 * share, kept out of the component so they can be unit-tested without a DOM
 * (the sweep module's twin). Param shapes come from the generated client
 * (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * Loft is the second feature (after sweep) to reference more than one earlier
 * sketch — but unlike sweep's fixed two slots (profile + path), a loft carries
 * an ORDERED LIST of ≥2 section sketches, blended in list ORDER. So the picker
 * is an ordered stack of ruled selects over the tree's sketch features (the
 * sweep select idiom, promoted from two slots to a reorderable list):
 * keyboard-first, deterministically testable, no viewport selection layer.
 * Order is meaning here (the skin threads the sections top-to-bottom), so the
 * list supports add / remove / reorder and every op returns a fresh form.
 */
import type { FeatureResponse, LoftParams } from "../api/parts";
import { profileOptions, type ProfileOption } from "./extrude";

export { profileOptions };
export type { ProfileOption };

export type LoftOperation = LoftParams["operation"];

/** A loft needs at least this many sections (matches the schema's `min 2`). */
export const MIN_LOFT_SECTIONS = 2;

/** The editable loft form: an ordered list of section refs + the add/cut sense. */
export interface LoftForm {
  /** Earlier sketch feature ids, in blend order; "" is an unchosen slot. */
  sections: string[];
  operation: LoftOperation;
  /** "Merge result" (multi-body §MB-1) — see `ExtrudeForm.merge`. */
  merge: boolean;
}

/** The default new-loft form: add, through the given ordered section sketches. */
export function defaultLoftForm(sections: readonly string[]): LoftForm {
  return { sections: [...sections], operation: "add", merge: true };
}

/** Seed the form from an existing loft feature for editing (order preserved). */
export function formFromLoftParams(params: LoftParams): LoftForm {
  return {
    sections: params.profiles.map((p) => p.feature_id),
    operation: params.operation,
    merge: params.merge,
  };
}

/**
 * The default ordered sections for a NEW loft: the first two sketch features in
 * build order (the tool is gated on ≥2 existing, so both are present). The user
 * then retargets, reorders, or adds more sections.
 */
export function defaultLoftSections(
  features: readonly FeatureResponse[],
): string[] {
  return profileOptions(features)
    .slice(0, MIN_LOFT_SECTIONS)
    .map((s) => s.id);
}

/** How many sketch features exist — the loft tool needs ≥2 sections. */
export function loftEligibleSketchCount(
  features: readonly FeatureResponse[],
): number {
  return profileOptions(features).length;
}

/** Append an empty section slot (the user then picks its sketch). */
export function addSection(form: LoftForm): LoftForm {
  return { ...form, sections: [...form.sections, ""] };
}

/** Remove the section at `index` (the component gates removal at MIN). */
export function removeSectionAt(form: LoftForm, index: number): LoftForm {
  return { ...form, sections: form.sections.filter((_, i) => i !== index) };
}

/** Set the sketch id of the section at `index`. */
export function setSectionAt(
  form: LoftForm,
  index: number,
  sketchId: string,
): LoftForm {
  return {
    ...form,
    sections: form.sections.map((id, i) => (i === index ? sketchId : id)),
  };
}

/**
 * Move the section at `index` one place toward `dir` (-1 up, +1 down), swapping
 * with its neighbour. Out-of-range moves are no-ops — order is the blend
 * sequence, so this is the only way to re-sequence sections.
 */
export function moveSection(
  form: LoftForm,
  index: number,
  dir: -1 | 1,
): LoftForm {
  const target = index + dir;
  if (target < 0 || target >= form.sections.length) return form;
  const sections = [...form.sections];
  const a = sections[index] as string;
  const b = sections[target] as string;
  sections[index] = b;
  sections[target] = a;
  return { ...form, sections };
}

/**
 * True when the form can be submitted: at least MIN sections, and every slot
 * has a chosen sketch. Distinctness is NOT enforced here — the schema allows a
 * repeated ref and the kernel reports a truly degenerate skin as `loft_failed`.
 */
export function canSubmitLoft(form: LoftForm): boolean {
  return loftSubmitBlocker(form) === null;
}

/**
 * WHY the loft cannot be created yet, or null when it can (REASON-GATE-1 — see
 * `submitBlocker.ts` for the rule and the 48-character budget).
 *
 * An empty slot is named by its ORDINAL, the same two-digit numeral the section
 * row carries ("Section 03"), because a stack of identical selects is exactly
 * the form where "choose a sketch" leaves the user hunting for which one.
 */
export function loftSubmitBlocker(form: LoftForm): string | null {
  if (form.sections.length < MIN_LOFT_SECTIONS) {
    return `A loft needs at least ${MIN_LOFT_SECTIONS} sections.`;
  }
  const empty = form.sections.findIndex((id) => id === "");
  if (empty !== -1) {
    return `Choose a sketch for section ${String(empty + 1).padStart(2, "0")}.`;
  }
  return null;
}

/** Build the persisted params from valid form state, or null when incomplete. */
export function buildLoftParams(form: LoftForm): LoftParams | null {
  if (!canSubmitLoft(form)) return null;
  return {
    profiles: form.sections.map((id) => ({
      kind: "feature" as const,
      feature_id: id,
    })),
    operation: form.operation,
    // Merge is an ADD choice only (see ExtrudeEditor); a cut sends `true`.
    merge: form.operation === "add" ? form.merge : true,
  };
}
