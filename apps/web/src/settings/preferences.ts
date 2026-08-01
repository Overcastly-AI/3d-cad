/**
 * APPLICATION PREFERENCES — the settings that belong to YOU rather than to a
 * document, and the seam every surface that honours one reads.
 *
 * Scope, stated once so no surface has to guess (Fusion's split, and the
 * founder's): a DOCUMENT setting travels with the file and is stored on it (a
 * part's `length_unit` is the shipped example — it lives on the part row and
 * every collaborator sees the same one). An APPLICATION preference is about the
 * person at the keyboard, is stored in this browser, and never touches the
 * document — so it can differ between two engineers opening the same part, which
 * is the entire point for the navigation bindings below.
 *
 * WHAT IS DELIBERATELY NOT HERE. A preference is only real if something reads
 * it. Angular unit, display precision, grid/snap step and a default material
 * have no property behind them in this build (no angular unit vocabulary; no
 * precision plumbing; the snap step is a sketch-store constant being made
 * configurable elsewhere), so they are not rendered. A settings page listing
 * switches that do nothing is the same defect class as a panel titled for a
 * number it does not have — filed in BACKLOG, not faked here.
 *
 * Persistence mirrors `auth/session.ts` exactly (localStorage, injectable for
 * tests, corrupt/partial values falling back to defaults rather than throwing):
 * a preference that survives a reload is the whole point, and a preference file
 * from a future version must never be able to break the app on boot.
 */
import { LENGTH_UNITS, type LengthUnit } from "@loft/design";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import type { SessionStorageLike } from "../auth/session";

export const PREFERENCES_STORAGE_KEY = "loft.preferences.v1";

/**
 * How hard the pointer pushes the camera. Three named steps rather than a raw
 * multiplier: the useful range is small, the difference between 1.0 and 1.15 is
 * not something anyone can aim at, and a named step is honest about the
 * precision on offer (a number field would imply more).
 */
export type NavSensitivity = "slow" | "standard" | "fast";

export const NAV_SENSITIVITIES: readonly NavSensitivity[] = [
  "slow",
  "standard",
  "fast",
];

/** The multiplier each step hands the orbit rig. `standard` is three's own default. */
export const SENSITIVITY_FACTOR: Readonly<Record<NavSensitivity, number>> = {
  slow: 0.5,
  standard: 1,
  fast: 2,
};

export interface Preferences {
  /**
   * The `length_unit` stamped on documents you CREATE. Existing documents keep
   * their own — this is a default, never a conversion.
   */
  readonly newDocumentUnit: LengthUnit;
  /**
   * Wheel/trackpad zoom runs the other way. CAD muscle memory on this is
   * violent and it differs by tool, so a fixed binding is a real adoption
   * blocker — this is the row that exists for that reason.
   */
  readonly invertZoom: boolean;
  readonly orbitSensitivity: NavSensitivity;
  readonly panSensitivity: NavSensitivity;
  readonly zoomSensitivity: NavSensitivity;
}

export const DEFAULT_PREFERENCES: Preferences = {
  newDocumentUnit: "mm",
  invertZoom: false,
  orbitSensitivity: "standard",
  panSensitivity: "standard",
  zoomSensitivity: "standard",
};

/**
 * The three numbers the orbit rig actually takes — the ONE place a preference
 * becomes a control parameter.
 *
 * The zoom sign is the whole inversion mechanism and is worth stating: the rig
 * scales the orbit radius by `0.95 ** zoomSpeed` per notch, so a NEGATIVE speed
 * makes each notch scale by the reciprocal — the same magnitude, the opposite
 * direction — and pinch-dolly (which shares the exponent) inverts with it. No
 * event interception, no second code path for inverted users.
 */
export interface NavigationControls {
  readonly rotateSpeed: number;
  readonly panSpeed: number;
  readonly zoomSpeed: number;
}

export function navigationControls(prefs: Preferences): NavigationControls {
  const zoom = SENSITIVITY_FACTOR[prefs.zoomSensitivity];
  return {
    rotateSpeed: SENSITIVITY_FACTOR[prefs.orbitSensitivity],
    panSpeed: SENSITIVITY_FACTOR[prefs.panSensitivity],
    zoomSpeed: prefs.invertZoom ? -zoom : zoom,
  };
}

export interface PreferencesState extends Preferences {
  /** Change one preference; the rest are untouched and the set is persisted. */
  set: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
  /** Back to the shipped defaults — the page's one destructive verb. */
  reset: () => void;
}

function isLengthUnit(value: unknown): value is LengthUnit {
  return LENGTH_UNITS.some((unit) => unit === value);
}

function isSensitivity(value: unknown): value is NavSensitivity {
  return NAV_SENSITIVITIES.some((step) => step === value);
}

/**
 * Read whatever is in storage into a COMPLETE preference set: every field is
 * validated on its own and falls back to its default, so a file written by an
 * older (or newer) build contributes what it can and breaks nothing.
 */
export function parsePreferences(raw: string | null): Preferences {
  if (raw === null) return DEFAULT_PREFERENCES;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return DEFAULT_PREFERENCES;
  }
  if (typeof parsed !== "object" || parsed === null) return DEFAULT_PREFERENCES;
  const o = parsed as Record<string, unknown>;
  return {
    newDocumentUnit: isLengthUnit(o.newDocumentUnit)
      ? o.newDocumentUnit
      : DEFAULT_PREFERENCES.newDocumentUnit,
    invertZoom:
      typeof o.invertZoom === "boolean"
        ? o.invertZoom
        : DEFAULT_PREFERENCES.invertZoom,
    orbitSensitivity: isSensitivity(o.orbitSensitivity)
      ? o.orbitSensitivity
      : DEFAULT_PREFERENCES.orbitSensitivity,
    panSensitivity: isSensitivity(o.panSensitivity)
      ? o.panSensitivity
      : DEFAULT_PREFERENCES.panSensitivity,
    zoomSensitivity: isSensitivity(o.zoomSensitivity)
      ? o.zoomSensitivity
      : DEFAULT_PREFERENCES.zoomSensitivity,
  };
}

/** Build a preferences store over *storage* (tests inject a fake). */
export function createPreferencesStore(storage: SessionStorageLike) {
  const write = (prefs: Preferences) => {
    try {
      storage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Quota / private mode: the session still honours the change in memory,
      // exactly as the session store behaves.
    }
  };
  let initial: Preferences;
  try {
    initial = parsePreferences(storage.getItem(PREFERENCES_STORAGE_KEY));
  } catch {
    initial = DEFAULT_PREFERENCES;
  }
  return create<PreferencesState>()((set, get) => ({
    ...initial,
    set: (key, value) => {
      set({ [key]: value } as Pick<Preferences, typeof key>);
      // Persist the VALUES only — `preferencesOf` is the one projection that
      // knows which keys those are, so the actions can never leak into storage.
      write(preferencesOf(get()));
    },
    reset: () => {
      set({ ...DEFAULT_PREFERENCES });
      write(DEFAULT_PREFERENCES);
    },
  }));
}

/** No-op storage for environments without localStorage (SSR, unit tests). */
const nullStorage: SessionStorageLike = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

function defaultStorage(): SessionStorageLike {
  try {
    return globalThis.localStorage ?? nullStorage;
  } catch {
    return nullStorage;
  }
}

/** THE app preferences store (browser localStorage-backed). */
export const usePreferencesStore = createPreferencesStore(defaultStorage());

/**
 * The stored set without the actions.
 *
 * Wrapped in `useShallow` at every call site, and that is not a style choice:
 * this projection allocates a fresh object per render, so a bare
 * `usePreferencesStore(preferencesOf)` re-renders forever (React's store
 * subscription compares by identity). Selecting the whole set is what the
 * settings sheet and the orbit rig both genuinely want, so the seam that makes
 * it safe lives here rather than being re-derived by each caller.
 */
export function preferencesOf(state: PreferencesState): Preferences {
  return {
    newDocumentUnit: state.newDocumentUnit,
    invertZoom: state.invertZoom,
    orbitSensitivity: state.orbitSensitivity,
    panSensitivity: state.panSensitivity,
    zoomSensitivity: state.zoomSensitivity,
  };
}

/** Every preference, re-rendering only when one of them actually changes. */
export function usePreferences(): Preferences {
  return usePreferencesStore(useShallow(preferencesOf));
}
