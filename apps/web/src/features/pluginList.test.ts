/**
 * The list input in the generated form (CASEWORK): rows seed from the
 * manifest's default and from stored rows, round-trip exactly, add a copy of
 * the last row, remove one, are checked per field with the row named, and
 * write their values in each field's own unit.
 */
import { describe, expect, it } from "vitest";

import type { PluginManifest } from "../api/plugins";
import { TWISTED_PRISM } from "../test/pluginFixture";
import {
  defaultPluginForm,
  firstPluginBlocker,
  formFromCustomParams,
  pluginInputsFromForm,
  validatePluginForm,
} from "./pluginForm";
import {
  addRow,
  type ListInput,
  listRows,
  removeRow,
  setRowField,
} from "./pluginList";

const IN = 25.4;

const BOXES: ListInput = {
  kind: "list",
  name: "boxes",
  label: "Boxes",
  item_label: "Box",
  min_items: 1,
  max_items: 32,
  fields: [
    {
      kind: "choice",
      name: "type",
      label: "Type",
      options: [
        { value: "base", label: "Base" },
        { value: "wall", label: "Wall" },
      ],
      default: "base",
    },
    {
      kind: "length",
      name: "width_mm",
      label: "Width",
      default: 24 * IN,
      minimum: 0.5 * IN,
      maximum: 48 * IN,
      exclusive_minimum: false,
      unit: "mm",
    },
    {
      kind: "count",
      name: "shelves",
      label: "Shelves",
      default: 1,
      minimum: 0,
      maximum: 8,
    },
  ],
  default: [{ type: "base", width_mm: 24 * IN }],
};

const CABINETS: PluginManifest = {
  ...TWISTED_PRISM,
  id: "loft.cabinets",
  inputs: [BOXES],
};

describe("a list input", () => {
  it("seeds a new feature's rows from its default, each field filled", () => {
    const form = defaultPluginForm(CABINETS, "in", []);
    expect(listRows(form.values.boxes ?? "")).toEqual([
      { type: "base", width_mm: "24", shelves: "1" },
    ]);
    expect(pluginInputsFromForm(CABINETS, form, "in", [], null)).toEqual({
      boxes: [{ type: "base", width_mm: 24 * IN, shelves: 1 }],
    });
  });

  it("adds a copy of the last row and removes one", () => {
    const one = defaultPluginForm(CABINETS, "in", []).values.boxes ?? "";
    const wide = setRowField(one, 0, "width_mm", "36");
    const two = addRow(BOXES, wide, "in");
    expect(listRows(two).map((r) => r.width_mm)).toEqual(["36", "36"]);
    const walled = setRowField(two, 1, "type", "wall");
    expect(listRows(removeRow(walled, 0))).toEqual([
      { type: "wall", width_mm: "36", shelves: "1" },
    ]);
  });

  it("round-trips stored rows exactly", () => {
    const stored = {
      plugin_id: "loft.cabinets",
      plugin_version: "1.0.0",
      inputs: {
        boxes: [
          { type: "base", width_mm: 609.6000000000001, shelves: 0 },
          { type: "wall", width_mm: 27 * IN, shelves: 2 },
        ],
      },
    };
    const form = formFromCustomParams(CABINETS, stored, "in");
    expect(pluginInputsFromForm(CABINETS, form, "in", [], null)).toEqual(
      stored.inputs,
    );
  });

  it("checks each field and names the row", () => {
    const base = defaultPluginForm(CABINETS, "in", []);
    const text = setRowField(
      addRow(BOXES, base.values.boxes ?? "", "in"),
      1,
      "width_mm",
      "60",
    );
    const form = { values: { boxes: text }, stored: null };
    const errors = validatePluginForm(CABINETS, form, "in", [], null);
    expect(errors["boxes/1/width_mm"]).toBe("Too large.");
    expect(firstPluginBlocker(CABINETS, errors)).toBe(
      "Boxes: Box 2, Width: Too large.",
    );
    expect(pluginInputsFromForm(CABINETS, form, "in", [], null)).toBeNull();
    const empty = { values: { boxes: "[]" }, stored: null };
    expect(
      firstPluginBlocker(
        CABINETS,
        validatePluginForm(CABINETS, empty, "in", [], null),
      ),
    ).toBe("Boxes: Add at least 1.");
  });
});
