/**
 * PluginFeatureEditor (PLUGIN-UI): the dialog is generated from the manifest,
 * its fields are ValueFields that take formulas, a bound is refused on the
 * field and gates Create with the reason, a plugin refusal reads with its
 * heading, and a feature whose plugin is missing opens read-only.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { FeatureResponse } from "../api/parts";
import type { CustomFeatureWrite, CustomParams } from "../api/plugins";
import { TWISTED_PRISM } from "../test/pluginFixture";
import { PluginFeatureEditor } from "./PluginFeatureEditor";

const SKETCH = {
  id: "s1",
  part_id: "p",
  order_index: 0,
  name: "Sketch1",
  feature: { type: "sketch", version: 1, params: {} },
  rolled_back: false,
  created_at: "",
  updated_at: "",
} as unknown as FeatureResponse;

function wrap(node: ReactNode) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}

function renderEditor(
  overrides: {
    stored?: CustomParams;
    catalog?: (typeof TWISTED_PRISM)[] | undefined;
    error?: string | null;
  } = {},
) {
  const onSubmit = vi.fn<(write: CustomFeatureWrite) => void>();
  wrap(
    <PluginFeatureEditor
      mode={overrides.stored === undefined ? "create" : "edit"}
      pluginId="loft.twisted_prism"
      pluginVersion="1.0.0"
      featureId={overrides.stored === undefined ? undefined : "c1"}
      stored={overrides.stored}
      catalog={"catalog" in overrides ? overrides.catalog : [TWISTED_PRISM]}
      features={[SKETCH]}
      onSubmit={onSubmit}
      onCancel={vi.fn()}
      saving={false}
      error={overrides.error ?? null}
    />,
  );
  return { onSubmit };
}

describe("PluginFeatureEditor — the generated form", () => {
  it("renders one field per manifest input, at its defaults", () => {
    renderEditor();
    expect(screen.getByText("New Twisted prism")).toBeInTheDocument();
    expect(screen.getByTestId("plugin-version")).toHaveTextContent("v1.0.0");
    expect(screen.getByTestId("plugin-input-profile")).toHaveValue("s1");
    expect(screen.getByTestId("plugin-input-distance_mm")).toHaveValue("10");
    expect(screen.getByTestId("plugin-input-twist_angle_deg")).toHaveValue(
      "30",
    );
    // Two short options: a segmented control.
    expect(
      screen.getByTestId("plugin-input-operation-cut"),
    ).toBeInTheDocument();
  });

  it("creates with the typed inputs, pinned to the manifest's version", () => {
    const { onSubmit } = renderEditor();
    fireEvent.change(screen.getByTestId("plugin-input-twist_angle_deg"), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByTestId("plugin-input-operation-cut"));
    fireEvent.click(screen.getByTestId("plugin-submit"));
    expect(onSubmit).toHaveBeenCalledWith({
      pluginId: "loft.twisted_prism",
      pluginVersion: "1.0.0",
      inputs: {
        profile: { kind: "feature", feature_id: "s1" },
        distance_mm: 10,
        twist_angle_deg: 45,
        operation: "cut",
      },
    });
  });

  it("refuses a value past a bound on the field, and says why Create is shut", () => {
    const { onSubmit } = renderEditor();
    fireEvent.change(screen.getByTestId("plugin-input-distance_mm"), {
      target: { value: "0" },
    });
    expect(screen.getByText("Must be more than 0 mm.")).toBeInTheDocument();
    const submit = screen.getByTestId("plugin-submit");
    expect(submit).toHaveAttribute("aria-disabled", "true");
    expect(
      screen.getByText("Distance: Must be more than 0 mm."),
    ).toBeInTheDocument();
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("marks a formula and keeps it out of the number check", () => {
    renderEditor();
    const twist = screen.getByTestId("plugin-input-twist_angle_deg");
    fireEvent.change(twist, { target: { value: "twist*2" } });
    expect(twist).toHaveAttribute("data-formula");
  });

  it("heads a plugin's typed refusal", () => {
    renderEditor({
      error:
        "[plugin_expansion_too_large] the part would send more than 1000 features to geometry.",
    });
    expect(screen.getByTestId("plugin-error")).toHaveTextContent(
      "Too many members: the part would send more than 1000 features",
    );
  });

  it("seeds an edit from the stored inputs", () => {
    renderEditor({
      stored: {
        plugin_id: "loft.twisted_prism",
        plugin_version: "1.0.0",
        inputs: {
          profile: { kind: "feature", feature_id: "s1" },
          distance_mm: 25,
          twist_angle_deg: 90,
          operation: "add",
        },
      },
    });
    expect(screen.getByText("Edit Twisted prism")).toBeInTheDocument();
    expect(screen.getByTestId("plugin-input-distance_mm")).toHaveValue("25");
    expect(screen.getByTestId("plugin-input-twist_angle_deg")).toHaveValue(
      "90",
    );
    expect(screen.getByTestId("plugin-submit")).toHaveTextContent("Save");
  });
});

describe("PluginFeatureEditor — a missing plugin", () => {
  it("opens read-only, naming the pinned version, with no Save", () => {
    renderEditor({
      catalog: [{ ...TWISTED_PRISM, version: "2.0.0" }],
      stored: {
        plugin_id: "loft.twisted_prism",
        plugin_version: "1.0.0",
        inputs: {
          profile: { kind: "feature", feature_id: "s1" },
          distance_mm: 25,
        },
      },
    });
    expect(screen.getByTestId("plugin-read-only")).toBeInTheDocument();
    expect(screen.getByTestId("plugin-missing")).toHaveTextContent(
      "loft.twisted_prism v1.0.0 is not installed on this server",
    );
    // What it was built from, by name.
    expect(screen.getByText("Sketch1")).toBeInTheDocument();
    expect(screen.queryByTestId("plugin-submit")).toBeNull();
  });
});

describe("PluginFeatureEditor — a release that builds wrong geometry", () => {
  const STORED: CustomParams = {
    plugin_id: "loft.twisted_prism",
    plugin_version: "1.0.0",
    inputs: {
      profile: { kind: "feature", feature_id: "s1" },
      distance_mm: 25,
      twist_angle_deg: 90,
      operation: "add",
    },
  };

  function renderWarned(updateTo: string | null) {
    const custom = {
      ...SKETCH,
      id: "c1",
      order_index: 1,
      name: "Roof",
      feature: { type: "custom", version: 1, params: STORED },
      plugin_warnings: [
        {
          code: "roof_through_sheathing",
          message: "This roof's rafter tails pass through the wall sheathing.",
          overlap_in3: 33.2551,
          pairs: 30,
          update_to: updateTo,
        },
      ],
    } as unknown as FeatureResponse;
    const onSubmit = vi.fn<(write: CustomFeatureWrite) => void>();
    wrap(
      <PluginFeatureEditor
        mode="edit"
        pluginId="loft.twisted_prism"
        pluginVersion="1.0.0"
        featureId="c1"
        stored={STORED}
        catalog={[TWISTED_PRISM]}
        features={[SKETCH, custom]}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        saving={false}
        error={null}
      />,
    );
    return { onSubmit };
  }

  it("shows the warning, and Update re-pins with the same inputs", () => {
    const { onSubmit } = renderWarned("1.5.0");
    expect(screen.getByTestId("plugin-warning")).toHaveTextContent(
      "pass through the wall sheathing",
    );
    const update = screen.getByTestId("plugin-update");
    expect(update).toHaveTextContent("Update to 1.5.0");
    // Nothing is re-pinned until the user asks.
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(update);
    expect(onSubmit).toHaveBeenCalledWith({
      pluginId: "loft.twisted_prism",
      pluginVersion: "1.5.0",
      inputs: STORED.inputs,
    });
  });

  it("warns with no Update when no release fixes it", () => {
    renderWarned(null);
    expect(screen.getByTestId("plugin-warning")).toBeInTheDocument();
    expect(screen.queryByTestId("plugin-update")).toBeNull();
  });

  it("heads a crawl-space warning by its code, not the roof's", () => {
    const custom = {
      ...SKETCH,
      id: "c1",
      order_index: 1,
      name: "Foundation",
      feature: { type: "custom", version: 1, params: STORED },
      plugin_warnings: [
        {
          code: "crawl_height_low",
          message:
            "The crawl height is 17.5 in, under the 18 in of IRC R317.1.",
          overlap_in3: 0,
          pairs: 0,
          update_to: null,
        },
      ],
    } as unknown as FeatureResponse;
    wrap(
      <PluginFeatureEditor
        mode="edit"
        pluginId="loft.twisted_prism"
        pluginVersion="1.0.0"
        featureId="c1"
        stored={STORED}
        catalog={[TWISTED_PRISM]}
        features={[SKETCH, custom]}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        saving={false}
        error={null}
      />,
    );
    const warning = screen.getByTestId("plugin-warning");
    expect(warning).toHaveTextContent("Crawl height");
    expect(warning).not.toHaveTextContent("Through sheathing");
    expect(warning).toHaveTextContent("R317.1");
    expect(screen.queryByTestId("plugin-update")).toBeNull();
  });
});

describe("PluginFeatureEditor — an out-of-date release (OPENING-UPDATE)", () => {
  const STORED: CustomParams = {
    plugin_id: "loft.twisted_prism",
    plugin_version: "1.0.0",
    inputs: {
      profile: { kind: "feature", feature_id: "s1" },
      distance_mm: 25,
      twist_angle_deg: 90,
      operation: "add",
    },
  };
  const UPDATE = {
    to_version: "1.5.0",
    summary:
      "Adds 2 header spacers and 1 header ply. Draws the header's 1/2 in plywood spacers.",
    adds: ["2 header spacers", "1 header ply"],
    quiet: false,
    separate: false,
  };

  function renderOutOfDate(withWarning: boolean, onUpdate?: () => void) {
    const custom = {
      ...SKETCH,
      id: "c1",
      order_index: 1,
      name: "Window 1",
      feature: { type: "custom", version: 1, params: STORED },
      plugin_update: UPDATE,
      ...(withWarning
        ? {
            plugin_warnings: [
              {
                code: "roof_through_sheathing",
                message: "Tails pass through the sheathing.",
                overlap_in3: 1,
                pairs: 1,
                update_to: "1.5.0",
              },
            ],
          }
        : {}),
    } as unknown as FeatureResponse;
    const onSubmit = vi.fn<(write: CustomFeatureWrite) => void>();
    wrap(
      <PluginFeatureEditor
        mode="edit"
        pluginId="loft.twisted_prism"
        pluginVersion="1.0.0"
        featureId="c1"
        stored={STORED}
        catalog={[TWISTED_PRISM]}
        features={[SKETCH, custom]}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        saving={false}
        error={null}
        onUpdate={onUpdate}
      />,
    );
    return { onSubmit };
  }

  it("says what the update changes and updates through the server", () => {
    const onUpdate = vi.fn();
    const { onSubmit } = renderOutOfDate(false, onUpdate);
    const notice = screen.getByTestId("plugin-update-notice");
    expect(notice).toHaveTextContent("Update available");
    expect(notice).toHaveTextContent("1/2 in plywood spacers");
    expect(notice).toHaveTextContent("Undo restores this release");
    const update = screen.getByTestId("plugin-update");
    expect(update).toHaveTextContent("Update to 1.5.0");
    expect(onUpdate).not.toHaveBeenCalled();
    fireEvent.click(update);
    // The server maps the inputs: the form is not re-saved under 1.5.0.
    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("offers one Update when a warning names the same release", () => {
    const onUpdate = vi.fn();
    renderOutOfDate(true, onUpdate);
    expect(screen.getByTestId("plugin-warning")).toBeInTheDocument();
    expect(screen.getAllByTestId("plugin-update")).toHaveLength(1);
    fireEvent.click(screen.getByTestId("plugin-update"));
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });

  it("states the update but offers no action without a write path", () => {
    renderOutOfDate(false);
    expect(screen.getByTestId("plugin-update-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("plugin-update")).toBeNull();
  });

  it("names what the update adds", () => {
    renderOutOfDate(false, vi.fn());
    expect(screen.getByTestId("plugin-update-notice")).toHaveTextContent(
      "1.5.0: Adds 2 header spacers and 1 header ply.",
    );
  });

  it("asks before an update drops unsaved edits, and keeps them on dismiss", () => {
    const onUpdate = vi.fn();
    renderOutOfDate(false, onUpdate);
    fireEvent.change(screen.getByTestId("plugin-input-twist_angle_deg"), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByTestId("plugin-update"));
    expect(onUpdate).not.toHaveBeenCalled();
    const ask = screen.getByTestId("plugin-update-confirm-notice");
    expect(ask).toHaveTextContent("Unsaved edits");
    expect(ask).toHaveTextContent("your unsaved edits are dropped");
    // Keep editing: the edit stays and nothing is updated.
    fireEvent.click(screen.getByTestId("plugin-update-cancel"));
    expect(screen.queryByTestId("plugin-update-confirm-notice")).toBeNull();
    expect(screen.getByTestId("plugin-input-twist_angle_deg")).toHaveValue(
      "45",
    );
    expect(onUpdate).not.toHaveBeenCalled();
    // Asked again, the user discards them and updates.
    fireEvent.click(screen.getByTestId("plugin-update"));
    fireEvent.click(screen.getByTestId("plugin-update-confirm"));
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });

  it("updates at once when the form holds no edit", () => {
    const onUpdate = vi.fn();
    renderOutOfDate(false, onUpdate);
    // An edit typed back to the stored value is no edit.
    const twist = screen.getByTestId("plugin-input-twist_angle_deg");
    const stored = (twist as HTMLInputElement).value;
    fireEvent.change(twist, { target: { value: "45" } });
    fireEvent.change(twist, { target: { value: stored } });
    fireEvent.click(screen.getByTestId("plugin-update"));
    expect(screen.queryByTestId("plugin-update-confirm-notice")).toBeNull();
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });
});
