import { expect } from "vitest";

/**
 * Assert a control is GATED the way this product gates controls: `aria-disabled`
 * rather than the native `disabled` attribute, so the control stays in the
 * accessibility tree and keeps hover + focus and can therefore explain itself
 * (`ToolButton`'s treatment, extended to `PanelActionCell` / `PickButton` /
 * `ContextMenu` rows after UI-REVIEW 2026-07-30 P2 found them to be disabled
 * traps).
 *
 * The negative half is the load-bearing one: `not.toBeDisabled()` fails the
 * moment someone "simplifies" a gate back to the native attribute, which is
 * exactly the regression that would silently re-close the a11y hole. (jest-dom's
 * `toBeDisabled` deliberately ignores `aria-disabled`; Playwright's honours it,
 * which is why the e2e gate assertions were unaffected by the change.)
 */
export function expectGated(el: HTMLElement): void {
  expect(el).toHaveAttribute("aria-disabled", "true");
  expect(el).not.toBeDisabled();
}

/** The other side: an actionable control carries no gate of either kind. */
export function expectNotGated(el: HTMLElement): void {
  expect(el).not.toHaveAttribute("aria-disabled", "true");
  expect(el).not.toBeDisabled();
}
