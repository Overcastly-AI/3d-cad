/**
 * BUILDING-OUTLINE in the generated form: a side pick lists the outline's
 * walls by the way they face and never shows an id; a pick that replaces
 * typed fields hides them; the viewport gets the live field's lines; and a
 * browser row click fills the field that takes it.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FeatureResponse } from "../api/parts";
import type { CustomFeatureWrite, PluginManifest } from "../api/plugins";
import { useOutlinePickStore } from "../features/outlinePickStore";
import { withPluginValue } from "../features/pluginForm";
import { sceneOriginBasis } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";
import type { SolvedSketchLayer } from "../viewport/solvedSketchLayer";
import { PluginFeatureEditor } from "./PluginFeatureEditor";

afterEach(() => {
  useOutlinePickStore.setState({ offer: null, hover: null, treePick: null });
});

function line(id: string, a: [number, number], b: [number, number]) {
  return {
    id,
    kind: "line",
    construction: false,
    start: { x: a[0], y: a[1] },
    end: { x: b[0], y: b[1] },
  } as SketchEntity;
}

/** B7's outline: the Rectangle tool from the origin (mm). */
const B7: SketchEntity[] = [
  line("e1", [0, 0], [7315.2, 0]),
  line("e2", [7315.2, 0], [7315.2, 4876.8]),
  line("e3", [7315.2, 4876.8], [0, 4876.8]),
  line("e4", [0, 4876.8], [0, 0]),
];

function row(id: string, name: string, feature: unknown): FeatureResponse {
  return {
    id,
    part_id: "p",
    order_index: 0,
    name,
    feature,
    rolled_back: false,
    created_at: "",
    updated_at: "",
  } as unknown as FeatureResponse;
}

const SKETCH = row("s1", "Outline", {
  type: "sketch",
  version: 1,
  params: {
    entities: B7,
    constraints: [],
    plane: { kind: "datum_plane", plane: "XY" },
  },
});
const WALL = row("w1", "Wall 1", {
  type: "custom",
  version: 1,
  params: {
    plugin_id: "loft.wall",
    plugin_version: "1.3.0",
    inputs: { outline: { kind: "feature", feature_id: "s1" } },
  },
});
const LAYERS: SolvedSketchLayer[] = [
  { featureId: "s1", basis: sceneOriginBasis("XY"), entities: B7 },
];

const BASE = {
  description: "",
  group: "build",
  latest: true,
  members: [],
};

const WINDOW = {
  ...BASE,
  id: "loft.window",
  version: "1.1.0",
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
  ],
} as unknown as PluginManifest;

const WALL_MANIFEST = {
  ...BASE,
  id: "loft.wall",
  version: "1.3.0",
  title: "Wall",
  inputs: [
    {
      kind: "feature",
      name: "outline",
      label: "Outline",
      feature_types: ["sketch"],
      optional: true,
      host: false,
    },
    {
      kind: "length",
      name: "length_mm",
      label: "Length",
      unit: "mm",
      default: 3657.6,
      minimum: 0,
      exclusive_minimum: true,
      superseded_by: "outline",
    },
  ],
} as unknown as PluginManifest;

function renderEditor(manifest: PluginManifest, features: FeatureResponse[]) {
  const onSubmit = vi.fn<(write: CustomFeatureWrite) => void>();
  const client = new QueryClient();
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={client}>{node}</QueryClientProvider>
  );
  const { unmount } = render(
    wrap(
      <PluginFeatureEditor
        mode="create"
        pluginId={manifest.id}
        pluginVersion={manifest.version}
        catalog={[manifest]}
        features={features}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        saving={false}
        error={null}
        sketchLayers={LAYERS}
      />,
    ),
  );
  return { onSubmit, unmount };
}

describe("a side pick (an opening's Wall)", () => {
  it("lists the outline wall's sides by facing and stores the line", () => {
    const { onSubmit } = renderEditor(WINDOW, [SKETCH, WALL]);
    const field = screen.getByTestId("plugin-input-wall_segment");
    expect(field).toHaveAttribute("data-armed", "true");
    for (const name of ["Front", "Left", "Back", "Right"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(field).not.toHaveTextContent(/e\d/);
    fireEvent.click(screen.getByRole("button", { name: "Front" }));
    expect(
      screen.getByRole("button", { name: "Wall: Front" }),
    ).toBeInTheDocument();
    // One wall at most: a second side replaces the first.
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(
      screen.getByRole("button", { name: "Wall: Back" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("plugin-submit"));
    expect(onSubmit.mock.calls[0]?.[0].inputs.wall_segment).toEqual(["e3"]);
  });

  it("offers the viewport the sides, and a click there toggles one", () => {
    renderEditor(WINDOW, [SKETCH, WALL]);
    const offer = useOutlinePickStore.getState().offer;
    expect(offer?.kind).toBe("segments");
    expect(offer?.lines.map((l) => l.label)).toEqual([
      "Front",
      "Left",
      "Back",
      "Right",
    ]);
    // The front line, walked clockwise, runs back to the origin (scene mm).
    expect(offer?.lines[0]?.end).toEqual([0, 0, 0]);
    act(() => offer?.onPick("e2"));
    expect(
      screen.getByRole("button", { name: "Wall: Right" }),
    ).toBeInTheDocument();
    expect(useOutlinePickStore.getState().offer?.selected).toEqual(["e2"]);
  });
});

describe("a new outline drops the side picks made on the old one", () => {
  // A second house on its own rectangle: its lines are e1..e4 too.
  const SKETCH_2 = row("s2", "Garage", {
    type: "sketch",
    version: 1,
    params: {
      entities: B7,
      constraints: [],
      plane: { kind: "datum_plane", plane: "XY" },
    },
  });
  const WALL_2 = row("w2", "Wall 2", {
    type: "custom",
    version: 1,
    params: {
      plugin_id: "loft.wall",
      plugin_version: "1.3.0",
      inputs: { outline: { kind: "feature", feature_id: "s2" } },
    },
  });
  const TREE = [SKETCH, WALL, SKETCH_2, WALL_2];
  const SEGMENT = WINDOW.inputs[1] as Extract<
    PluginManifest["inputs"][number],
    { kind: "segments" }
  >;

  it("clears e2 when the host moves to another outline, keeps it otherwise", () => {
    const values = { host_wall: "w1", wall_segment: "e2" };
    expect(
      withPluginValue(WINDOW, values, "host_wall", "w2", TREE).wall_segment,
    ).toBe("");
    // The same outline (the host re-picked): the pick still means its wall.
    expect(
      withPluginValue(WINDOW, values, "host_wall", "w1", TREE).wall_segment,
    ).toBe("e2");
    // Other fields never touch it.
    expect(
      withPluginValue(WINDOW, values, "offset_mm", "60", TREE).wall_segment,
    ).toBe("e2");
    expect(SEGMENT.outline_input).toBe("host_wall");
  });

  it("in the dialog: Right on Wall 1, then Wall 2, reads Select again", () => {
    renderEditor(WINDOW, TREE);
    fireEvent.change(screen.getByTestId("plugin-input-host_wall"), {
      target: { value: "w1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Right" }));
    expect(
      screen.getByRole("button", { name: "Wall: Right" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("plugin-input-host_wall"), {
      target: { value: "w2" },
    });
    expect(
      screen.getByRole("button", { name: "Wall: Select" }),
    ).toBeInTheDocument();
  });
});

describe("an Outline pick (a wall)", () => {
  it("hides the typed line once an outline is picked from the browser", () => {
    renderEditor(WALL_MANIFEST, [SKETCH]);
    expect(screen.getByTestId("plugin-input-length_mm")).toBeInTheDocument();
    const offer = useOutlinePickStore.getState().offer;
    expect(offer?.kind).toBe("sketch");
    expect(offer?.lines).toHaveLength(4);
    let took = false;
    act(() => {
      took = useOutlinePickStore.getState().treePick?.(SKETCH) ?? false;
    });
    expect(took).toBe(true);
    expect(screen.getByTestId("plugin-input-outline")).toHaveValue("s1");
    expect(screen.queryByTestId("plugin-input-length_mm")).toBeNull();
  });

  it("leaves a browser row no field takes to open as before", () => {
    renderEditor(WALL_MANIFEST, [SKETCH, WALL]);
    expect(useOutlinePickStore.getState().treePick?.(WALL)).toBe(false);
  });

  it("clears the offer when the dialog closes", () => {
    const { unmount } = renderEditor(WALL_MANIFEST, [SKETCH]);
    expect(useOutlinePickStore.getState().offer).not.toBeNull();
    unmount();
    expect(useOutlinePickStore.getState().offer).toBeNull();
    expect(useOutlinePickStore.getState().treePick).toBeNull();
  });
});

describe("a call size (OPENING-UNITS)", () => {
  const UNIT_WINDOW = {
    ...BASE,
    id: "loft.window",
    version: "1.3.0",
    title: "Window",
    inputs: [
      {
        kind: "length",
        name: "width_mm",
        label: "Custom width",
        unit: "mm",
        default: 914.4,
        minimum: 0,
        exclusive_minimum: true,
        superseded_by: "size",
        superseded_unless: "custom",
      },
      {
        kind: "choice",
        name: "size",
        label: "Size",
        options: [
          { value: "window_3040", label: `3040 (3'0" x 4'0")` },
          { value: "window_2030", label: `2030 (2'0" x 3'0")` },
          { value: "custom", label: "Custom (type the size)" },
        ],
        default: "window_3040",
      },
    ],
  } as unknown as PluginManifest;

  it("hides the Custom size while a code is picked, and shows it for Custom", () => {
    const { onSubmit } = renderEditor(UNIT_WINDOW, []);
    const size = screen.getByTestId("plugin-input-size");
    expect(size).toHaveValue("window_3040");
    expect(screen.queryByTestId("plugin-input-width_mm")).toBeNull();
    fireEvent.change(size, { target: { value: "window_2030" } });
    expect(screen.queryByTestId("plugin-input-width_mm")).toBeNull();
    fireEvent.change(size, { target: { value: "custom" } });
    expect(screen.getByTestId("plugin-input-width_mm")).toBeInTheDocument();
    fireEvent.change(size, { target: { value: "window_2030" } });
    expect(screen.queryByTestId("plugin-input-width_mm")).toBeNull();
    // The typed size is kept, unread, while a code sizes the unit.
    fireEvent.click(screen.getByTestId("plugin-submit"));
    expect(onSubmit.mock.calls[0]?.[0].inputs).toMatchObject({
      size: "window_2030",
      width_mm: 914.4,
    });
  });
});
