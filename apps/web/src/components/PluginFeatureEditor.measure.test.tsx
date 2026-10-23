/**
 * OPENING-MEASURE-SWITCH in the generated form: changing Measured from
 * converts the distance so the opening stays put, the distance from both
 * wall ends reads under the field, and a click on either end makes it the
 * reference.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FeatureResponse } from "../api/parts";
import type { CustomFeatureWrite, PluginManifest } from "../api/plugins";
import { DocumentUnitProvider } from "../units/documentUnit";
import { PluginFeatureEditor } from "./PluginFeatureEditor";

const IN = 25.4;

/** A 240 in wall from the origin out along +X (its top plate's section). */
const WALL = {
  id: "w1",
  part_id: "p",
  order_index: 0,
  name: "Wall 1",
  rolled_back: false,
  created_at: "",
  updated_at: "",
  feature: {
    type: "custom",
    version: 1,
    params: {
      plugin_id: "loft.wall",
      plugin_version: "1.2.0",
      inputs: {},
      expansion: [
        {
          id: "s",
          role: "section",
          index: 0,
          name: "top_plate/course/1",
          feature: {
            type: "sketch",
            version: 1,
            params: {
              plane: { kind: "datum_plane", plane: "XY" },
              constraints: [],
              entities: [
                {
                  id: "e1",
                  kind: "line",
                  start: { x: 0, y: 0 },
                  end: { x: 240 * IN, y: 0 },
                },
              ],
            },
          },
        },
        {
          id: "t",
          role: "top_plate",
          index: 0,
          name: "course/1",
          feature: { type: "extrude", version: 1, params: {} },
        },
      ],
    },
  },
} as unknown as FeatureResponse;

const WINDOW = {
  description: "",
  group: "build",
  latest: true,
  members: [],
  id: "loft.window",
  version: "1.2.0",
  title: "Window",
  inputs: [
    {
      kind: "feature",
      name: "host_wall",
      label: "Host wall",
      feature_types: ["custom"],
      plugin_ids: ["loft.wall"],
      optional: false,
      host: true,
    },
    {
      kind: "segments",
      name: "wall_segment",
      label: "Wall",
      outline_input: "host_wall",
      min_items: 0,
      max_items: 1,
    },
    {
      kind: "choice",
      name: "measure_from",
      label: "Measured from",
      options: [
        { value: "nearer", label: "Nearer the origin" },
        { value: "start", label: "Wall start" },
        { value: "end", label: "Wall end" },
        { value: "centre", label: "Wall centre" },
      ],
      default: "nearer",
    },
    {
      kind: "length",
      name: "offset_mm",
      label: "Distance",
      unit: "mm",
      default: 72 * IN,
      minimum: -960 * IN,
      maximum: 960 * IN,
      exclusive_minimum: false,
    },
  ],
} as unknown as PluginManifest;

function renderEditor() {
  const onSubmit = vi.fn<(write: CustomFeatureWrite) => void>();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DocumentUnitProvider unit="in">
        <PluginFeatureEditor
          mode="edit"
          featureId="o1"
          stored={{
            plugin_id: "loft.window",
            plugin_version: "1.2.0",
            inputs: {
              host_wall: { kind: "feature", feature_id: "w1" },
              measure_from: "start",
              offset_mm: 48 * IN,
            },
          }}
          pluginId="loft.window"
          pluginVersion="1.2.0"
          catalog={[WINDOW]}
          features={[WALL]}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          saving={false}
          error={null}
        />
      </DocumentUnitProvider>
    </QueryClientProvider>,
  );
  return { onSubmit };
}

describe("Measured from keeps the opening put", () => {
  it("converts the distance when the reference changes", () => {
    const { onSubmit } = renderEditor();
    const distance = screen.getByTestId("plugin-input-offset_mm");
    const from = screen.getByTestId("plugin-input-measure_from");
    expect(distance).toHaveValue("48");
    expect(screen.getByTestId("opening-ends")).toHaveTextContent(
      "48 in from start · 192 in from end",
    );
    fireEvent.change(from, { target: { value: "end" } });
    expect(distance).toHaveValue("192");
    fireEvent.change(from, { target: { value: "centre" } });
    expect(distance).toHaveValue("-72");
    // Nearer the origin is this wall's start.
    fireEvent.change(from, { target: { value: "nearer" } });
    expect(distance).toHaveValue("48");
    expect(screen.getByTestId("opening-ends")).toHaveTextContent(
      "48 in from start · 192 in from end",
    );
    fireEvent.change(from, { target: { value: "start" } });
    fireEvent.click(screen.getByTestId("plugin-submit"));
    // Back where it started: the stored value, exactly.
    expect(onSubmit.mock.calls[0]?.[0].inputs.offset_mm).toBe(48 * IN);
  });

  it("makes the clicked end the reference, caret in the distance", () => {
    const { onSubmit } = renderEditor();
    const end = screen.getByTestId("opening-ends-end");
    expect(screen.getByTestId("opening-ends-start")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(end);
    const distance = screen.getByTestId("plugin-input-offset_mm");
    expect(screen.getByTestId("plugin-input-measure_from")).toHaveValue("end");
    expect(distance).toHaveValue("192");
    expect(distance).toHaveFocus();
    expect(end).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(distance, { target: { value: "180" } });
    expect(screen.getByTestId("opening-ends")).toHaveTextContent(
      "60 in from start · 180 in from end",
    );
    fireEvent.click(screen.getByTestId("plugin-submit"));
    const inputs = onSubmit.mock.calls[0]?.[0].inputs;
    expect(inputs?.measure_from).toBe("end");
    expect(inputs?.offset_mm).toBeCloseTo(180 * IN, 9);
  });
});
