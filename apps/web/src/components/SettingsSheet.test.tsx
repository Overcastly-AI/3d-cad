/**
 * The settings sheet (#58).
 *
 * What can regress here is not the layout: it is whether a switch on the sheet
 * still REACHES the thing it claims to change, and whether the sheet only shows
 * switches that reach something. So these drive the real store the app uses and
 * assert the stored value, plus the one structural rule — no row for a setting
 * nothing honours.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_PREFERENCES,
  usePreferencesStore,
} from "../settings/preferences";
import { SettingsSheet } from "./SettingsSheet";

describe("SettingsSheet", () => {
  beforeEach(() => {
    usePreferencesStore.getState().reset();
  });

  it("stores the unit that new documents will be created in", () => {
    render(<SettingsSheet />);
    fireEvent.change(screen.getByTestId("settings-new-document-unit"), {
      target: { value: "in" },
    });
    expect(usePreferencesStore.getState().newDocumentUnit).toBe("in");
  });

  it("flips the scroll direction — the row CAD muscle memory needs", () => {
    render(<SettingsSheet />);
    expect(usePreferencesStore.getState().invertZoom).toBe(false);
    fireEvent.click(screen.getByTestId("settings-zoom-inverted"));
    expect(usePreferencesStore.getState().invertZoom).toBe(true);
    expect(screen.getByTestId("settings-zoom-inverted")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByTestId("settings-zoom-standard"));
    expect(usePreferencesStore.getState().invertZoom).toBe(false);
  });

  it("sets each navigation sensitivity on its own axis", () => {
    render(<SettingsSheet />);
    fireEvent.click(screen.getByTestId("settings-orbit-slow"));
    fireEvent.click(screen.getByTestId("settings-pan-fast"));
    const state = usePreferencesStore.getState();
    expect(state.orbitSensitivity).toBe("slow");
    expect(state.panSensitivity).toBe("fast");
    // ...and does not smear across the others.
    expect(state.zoomSensitivity).toBe("standard");
  });

  it("offers RESTORE DEFAULTS only when something is off default", () => {
    render(<SettingsSheet />);
    const reset = screen.getByTestId("settings-reset");
    expect(reset).toBeDisabled();
    fireEvent.click(screen.getByTestId("settings-orbit-fast"));
    expect(reset).toBeEnabled();
    fireEvent.click(reset);
    expect(usePreferencesStore.getState().orbitSensitivity).toBe(
      DEFAULT_PREFERENCES.orbitSensitivity,
    );
    expect(screen.getByTestId("settings-reset")).toBeDisabled();
  });

  it("says whose settings these are and where they live", () => {
    render(<SettingsSheet />);
    expect(screen.getByTestId("settings-scope")).toHaveTextContent(
      /Application · saved in this browser/,
    );
  });

  it("shows no row for a setting nothing in this build honours", () => {
    // The defect class this sheet must not join: a preferences page whose rows
    // are decorations. If one of these ships, it ships with the property behind
    // it — and this assertion is what makes that deliberate.
    const { container } = render(<SettingsSheet />);
    const text = container.textContent ?? "";
    for (const absent of [
      "Angular unit",
      "Display precision",
      "Grid snap",
      "Default material",
    ]) {
      expect(text).not.toContain(absent);
    }
  });
});
