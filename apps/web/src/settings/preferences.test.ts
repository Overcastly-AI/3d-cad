/**
 * Preferences (#58) — a setting is only real if it survives a reload and if
 * something downstream consumes it. Both halves are asserted here: the storage
 * round-trip (including the junk cases a persisted file can arrive in) and the
 * translation into the three numbers the orbit rig takes, where the SIGN of the
 * zoom speed IS the inverted-scroll binding.
 */
import { describe, expect, it } from "vitest";

import type { SessionStorageLike } from "../auth/session";
import {
  createPreferencesStore,
  DEFAULT_PREFERENCES,
  navigationControls,
  parsePreferences,
  PREFERENCES_STORAGE_KEY,
  SENSITIVITY_FACTOR,
} from "./preferences";

function fakeStorage(seed: Record<string, string> = {}): SessionStorageLike & {
  data: Record<string, string>;
} {
  const data = { ...seed };
  return {
    data,
    getItem: (key) => data[key] ?? null,
    setItem: (key, value) => {
      data[key] = value;
    },
    removeItem: (key) => {
      delete data[key];
    },
  };
}

describe("parsePreferences", () => {
  it("falls back to the shipped defaults for nothing, junk, or the wrong shape", () => {
    expect(parsePreferences(null)).toEqual(DEFAULT_PREFERENCES);
    expect(parsePreferences("{not json")).toEqual(DEFAULT_PREFERENCES);
    expect(parsePreferences("[]")).toEqual(DEFAULT_PREFERENCES);
    expect(parsePreferences("null")).toEqual(DEFAULT_PREFERENCES);
  });

  it("takes the fields it recognises and defaults the ones it does not", () => {
    // A file written by another build: one good field, one bogus value, one
    // unknown key. It must contribute what it can and break nothing.
    const parsed = parsePreferences(
      JSON.stringify({
        newDocumentUnit: "in",
        orbitSensitivity: "ludicrous",
        futureSetting: 42,
      }),
    );
    expect(parsed.newDocumentUnit).toBe("in");
    expect(parsed.orbitSensitivity).toBe(DEFAULT_PREFERENCES.orbitSensitivity);
    expect(parsed).not.toHaveProperty("futureSetting");
  });

  it("refuses a unit that is not a unit", () => {
    expect(
      parsePreferences(JSON.stringify({ newDocumentUnit: "furlong" }))
        .newDocumentUnit,
    ).toBe("mm");
  });
});

describe("the preferences store", () => {
  it("reads what a previous session wrote", () => {
    const store = createPreferencesStore(
      fakeStorage({
        [PREFERENCES_STORAGE_KEY]: JSON.stringify({
          newDocumentUnit: "in",
          invertZoom: true,
        }),
      }),
    );
    expect(store.getState().newDocumentUnit).toBe("in");
    expect(store.getState().invertZoom).toBe(true);
  });

  it("persists one change without disturbing the others", () => {
    const storage = fakeStorage();
    const store = createPreferencesStore(storage);
    store.getState().set("invertZoom", true);
    store.getState().set("zoomSensitivity", "fast");
    const written: unknown = JSON.parse(
      storage.data[PREFERENCES_STORAGE_KEY] ?? "{}",
    );
    expect(written).toEqual({
      ...DEFAULT_PREFERENCES,
      invertZoom: true,
      zoomSensitivity: "fast",
    });
    // The actions themselves are never persisted.
    expect(written).not.toHaveProperty("set");
  });

  it("restores the defaults, in memory and on disk", () => {
    const storage = fakeStorage();
    const store = createPreferencesStore(storage);
    store.getState().set("newDocumentUnit", "ft");
    store.getState().reset();
    expect(store.getState().newDocumentUnit).toBe("mm");
    expect(JSON.parse(storage.data[PREFERENCES_STORAGE_KEY] ?? "{}")).toEqual(
      DEFAULT_PREFERENCES,
    );
  });

  it("keeps working when storage refuses to write", () => {
    const storage: SessionStorageLike = {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => undefined,
    };
    const store = createPreferencesStore(storage);
    expect(() => store.getState().set("invertZoom", true)).not.toThrow();
    expect(store.getState().invertZoom).toBe(true);
  });
});

describe("navigationControls", () => {
  it("hands the rig three ones at the shipped defaults", () => {
    expect(navigationControls(DEFAULT_PREFERENCES)).toEqual({
      rotateSpeed: 1,
      panSpeed: 1,
      zoomSpeed: 1,
    });
  });

  it("inverts the SIGN of the zoom speed and nothing else", () => {
    const inverted = navigationControls({
      ...DEFAULT_PREFERENCES,
      invertZoom: true,
    });
    expect(inverted.zoomSpeed).toBe(-1);
    expect(inverted.rotateSpeed).toBe(1);
    expect(inverted.panSpeed).toBe(1);
  });

  it("keeps the inversion at every sensitivity, magnitude intact", () => {
    for (const step of ["slow", "standard", "fast"] as const) {
      const base = { ...DEFAULT_PREFERENCES, zoomSensitivity: step };
      expect(navigationControls(base).zoomSpeed).toBe(SENSITIVITY_FACTOR[step]);
      expect(navigationControls({ ...base, invertZoom: true }).zoomSpeed).toBe(
        -SENSITIVITY_FACTOR[step],
      );
    }
  });

  it("routes each sensitivity to its own axis", () => {
    const controls = navigationControls({
      ...DEFAULT_PREFERENCES,
      orbitSensitivity: "slow",
      panSensitivity: "fast",
      zoomSensitivity: "standard",
    });
    expect(controls).toEqual({ rotateSpeed: 0.5, panSpeed: 2, zoomSpeed: 1 });
  });
});
