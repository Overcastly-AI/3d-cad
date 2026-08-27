// @vitest-environment jsdom
/**
 * SelectField option groups — the cell has to be able to say "these two names
 * are different KINDS of thing" (a part vs an assembly on the drawing setup
 * band). Grouping is per-option and opt-in, so an ungrouped caller must emit
 * exactly the flat markup it always did: an empty `<optgroup>` wrapper would
 * change how the cell is announced for every existing picker in the app.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SelectField } from "./SelectField";

afterEach(cleanup);

describe("SelectField", () => {
  it("renders no optgroup when no option declares one", () => {
    const { container } = render(
      <SelectField
        label="Scale"
        options={[
          { value: "1:1", label: "1:1" },
          { value: "1:2", label: "1:2" },
        ]}
        value="1:1"
        onChange={() => {}}
      />,
    );
    expect(container.querySelectorAll("optgroup")).toHaveLength(0);
    expect(container.querySelectorAll("option")).toHaveLength(2);
  });

  it("files grouped options under headings, in first-seen order", () => {
    const { container } = render(
      <SelectField
        label="Source"
        options={[
          { value: "p1", label: "Bracket plate", group: "Parts" },
          { value: "a1", label: "Gearbox", group: "Assemblies" },
          { value: "p2", label: "Cover plate", group: "Parts" },
        ]}
        value="p1"
        onChange={() => {}}
      />,
    );
    const groups = Array.from(container.querySelectorAll("optgroup"));
    expect(groups.map((g) => g.label)).toEqual(["Parts", "Assemblies"]);
    expect(
      Array.from(groups[0]!.querySelectorAll("option")).map((o) => o.value),
    ).toEqual(["p1", "p2"]);
    expect(
      Array.from(groups[1]!.querySelectorAll("option")).map((o) => o.value),
    ).toEqual(["a1"]);
    // Every option is still selectable by its bare value — the group is a
    // heading, never part of the value.
    expect(screen.getByLabelText("Source")).toHaveValue("p1");
  });

  it("keeps ungrouped options above the first heading", () => {
    const { container } = render(
      <SelectField
        label="Source"
        options={[
          { value: "", label: "None" },
          { value: "p1", label: "Bracket plate", group: "Parts" },
        ]}
        value=""
        onChange={() => {}}
      />,
    );
    const select = container.querySelector("select")!;
    expect(select.children[0]!.tagName).toBe("OPTION");
    expect(select.children[1]!.tagName).toBe("OPTGROUP");
  });
});
