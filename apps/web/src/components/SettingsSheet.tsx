/**
 * THE SETUP SHEET — where the tool is set up for the person using it.
 *
 * The product had no settings surface at all (founder item #58): the document
 * unit lived in one workspace's top bar and everything else was a constant in
 * the source. This is the application half of Fusion's two-scope split, and the
 * scope is stated on the sheet rather than assumed — an APPLICATION preference
 * is about the person at the keyboard and is stored in this browser; a DOCUMENT
 * setting travels with the file and is set where the document is open.
 *
 * FORM. No new look was invented: this is the register's drawer frame (hairline
 * rule, carbide ground, tracked-caps eyebrows) with the title block's field
 * anatomy — a ruled row per setting, the CONTROL on the left as a labeled cell
 * exactly like a feature editor's, and the CONSEQUENCE beside it in the note
 * column, because on a preferences sheet the sentence "what will this change"
 * is the content, not decoration. The remaining lines of the sheet are ruled to
 * the bottom of the frame, the way the register's unfiled lines are, so the page
 * reads as a filled-in sheet rather than a card adrift in a void.
 *
 * WHAT IS NOT ON THE SHEET is the load-bearing part. Every row here is wired to
 * a property something actually reads (the unit stamps documents you create; the
 * navigation rows are the orbit rig's own parameters). Angular unit, display
 * precision, grid/snap step and a default material are NOT rendered, because
 * nothing in this build stores or honours them — a sheet with three live
 * switches and six dead ones is a surface promising what it cannot deliver,
 * which is the defect class this whole pass is about.
 */
import {
  Button,
  LENGTH_UNITS,
  SegmentedControl,
  SelectField,
} from "@loft/design";
import type { ReactNode } from "react";

import {
  DEFAULT_PREFERENCES,
  type NavSensitivity,
  type Preferences,
  usePreferences,
  usePreferencesStore,
} from "../settings/preferences";

/** The three named steps, once — every sensitivity row offers the same set. */
const SENSITIVITY_OPTIONS: readonly {
  value: NavSensitivity;
  label: string;
}[] = [
  { value: "slow", label: "Slow" },
  { value: "standard", label: "Standard" },
  { value: "fast", label: "Fast" },
];

function sensitivityOptions(id: string) {
  return SENSITIVITY_OPTIONS.map((option) => ({
    ...option,
    "data-testid": `${id}-${option.value}`,
  }));
}

export function SettingsSheet() {
  const prefs = usePreferences();
  const set = usePreferencesStore((state) => state.set);
  const reset = usePreferencesStore((state) => state.reset);
  const changed = (
    Object.keys(DEFAULT_PREFERENCES) as (keyof Preferences)[]
  ).some((key) => prefs[key] !== DEFAULT_PREFERENCES[key]);

  return (
    <section
      className="mt-4 flex min-h-0 grow flex-col border border-hairline bg-anvil text-mist"
      data-testid="settings-sheet"
    >
      <header className="flex shrink-0 items-baseline gap-3 border-b border-hairline px-3 py-3">
        <h2 className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
          Preferences
        </h2>
        <span className="grow" />
        {/* Not a badge: it answers "who does this apply to, and where does it
            live" — the one thing a two-scope settings model has to say. */}
        <span
          className="font-display text-2xs uppercase tracking-[0.14em] text-gauge"
          data-testid="settings-scope"
        >
          Application · saved in this browser
        </span>
      </header>

      <SettingsGroup title="New documents">
        <SettingRow
          note="New parts and assemblies are created in this unit. It is display metadata — existing documents keep the unit they were created with, and nothing is converted."
          control={
            <SelectField
              label="Length unit"
              // Full control-column width, like every other row: the sheet's
              // controls share one left edge AND one right edge, so the eye
              // reads a column of instruments rather than ragged form cells.
              value={prefs.newDocumentUnit}
              data-testid="settings-new-document-unit"
              options={LENGTH_UNITS.map((unit) => ({
                value: unit,
                label: unit,
              }))}
              onChange={(event) => {
                const next = LENGTH_UNITS.find(
                  (unit) => unit === event.currentTarget.value,
                );
                if (next !== undefined) set("newDocumentUnit", next);
              }}
            />
          }
        />
      </SettingsGroup>

      <SettingsGroup title="Viewport navigation">
        <SettingRow
          note="Which way the wheel or trackpad zooms. Invert it if your hands expect the other direction — every CAD tool picks a side, and this one is yours."
          control={
            <SegmentedControl
              label="Scroll to zoom"
              value={prefs.invertZoom ? "inverted" : "standard"}
              onChange={(value) => set("invertZoom", value === "inverted")}
              options={[
                {
                  value: "standard",
                  label: "Standard",
                  "data-testid": "settings-zoom-standard",
                },
                {
                  value: "inverted",
                  label: "Inverted",
                  "data-testid": "settings-zoom-inverted",
                },
              ]}
            />
          }
        />
        <SettingRow
          note="How far the model turns for a given drag of the left button."
          control={
            <SegmentedControl
              label="Orbit sensitivity"
              value={prefs.orbitSensitivity}
              onChange={(value) => set("orbitSensitivity", value)}
              options={sensitivityOptions("settings-orbit")}
            />
          }
        />
        <SettingRow
          note="How far the model slides for a given drag of the right button (or a two-finger drag)."
          control={
            <SegmentedControl
              label="Pan sensitivity"
              value={prefs.panSensitivity}
              onChange={(value) => set("panSensitivity", value)}
              options={sensitivityOptions("settings-pan")}
            />
          }
        />
        <SettingRow
          note="How much closer each notch of the wheel takes you."
          control={
            <SegmentedControl
              label="Zoom sensitivity"
              value={prefs.zoomSensitivity}
              onChange={(value) => set("zoomSensitivity", value)}
              options={sensitivityOptions("settings-zoom-sensitivity")}
            />
          }
        />
      </SettingsGroup>

      <div className="flex shrink-0 items-center gap-3 border-b border-hairline px-3 py-3">
        <Button
          onClick={reset}
          disabled={!changed}
          data-testid="settings-reset"
          title={
            changed
              ? undefined
              : "Everything on this sheet is already at its default."
          }
        >
          Restore defaults
        </Button>
        <span className="font-body text-xs text-gauge">
          {changed
            ? "Puts every preference on this sheet back to how it shipped."
            : "Every preference is as it shipped."}
        </span>
      </div>

      <RuledRemainder />
    </section>
  );
}

/** A titled block of settings — the sheet's one structural division. */
function SettingsGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="shrink-0 border-b border-hairline">
      <h3 className="border-b border-hairline bg-carbide px-3 py-1.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
        {title}
      </h3>
      {children}
    </div>
  );
}

/**
 * One ruled line of the sheet: the control (a labeled title-block cell) and,
 * beside it, what changing it does. The note is the row's reason for existing —
 * a preference nobody can predict the effect of is a switch in the dark.
 */
function SettingRow({ control, note }: { control: ReactNode; note: string }) {
  return (
    <div className="flex flex-col gap-2 border-b border-hairline/60 px-3 py-3 last:border-b-0 sm:flex-row sm:items-start sm:gap-5">
      <div className="w-full shrink-0 sm:w-[17rem]">{control}</div>
      <p className="max-w-prose font-body text-xs text-gauge sm:pt-5">{note}</p>
    </div>
  );
}

/**
 * The sheet's unfilled lines, ruled at the row rhythm and running to the bottom
 * of the frame — the register's device, for the same reason: a sheet that stops
 * halfway down reads as a card on a web page. Ground, not a control.
 */
function RuledRemainder() {
  return (
    <div
      className="grow overflow-hidden"
      aria-hidden="true"
      data-testid="settings-ruled-remainder"
    >
      {Array.from({ length: 16 }, (_, index) => (
        <div key={index} className="h-10 border-b border-hairline/40" />
      ))}
    </div>
  );
}
