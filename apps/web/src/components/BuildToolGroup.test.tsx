// @vitest-environment jsdom
/**
 * The Build group's row and its BUILD ▾ menu: the building generators sit on
 * the row in Build-menu order (Wall, then Deck), every other plugin behind
 * the eyebrow. The width it saves is measured by
 * `apps/web/e2e/toolbar-overflow.spec.ts`.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PluginManifest } from "../api/plugins";
import { TWISTED_PRISM } from "../test/pluginFixture";
import { BuildToolGroup } from "./BuildToolGroup";

afterEach(cleanup);

function plugin(id: string, title: string): PluginManifest {
  return { ...TWISTED_PRISM, id, title, description: `A ${title}.` };
}

const DECK = plugin("loft.deck", "Deck");
const WALL = plugin("loft.wall", "Wall");

describe("BuildToolGroup", () => {
  it("puts Wall then Deck on the row and the rest in BUILD ▾", () => {
    const onOpen = vi.fn();
    render(
      <BuildToolGroup
        catalog={[DECK, TWISTED_PRISM, WALL]}
        treeReady
        activeCommand={null}
        onOpen={onOpen}
      />,
    );
    const group = screen.getByTestId("build-tools");
    const row = Array.from(
      group.querySelectorAll("[data-testid^='plugin-tool-']"),
    ).map((el) => el.getAttribute("data-testid"));
    expect(row).toEqual(["plugin-tool-loft.wall", "plugin-tool-loft.deck"]);

    fireEvent.click(screen.getByTestId("build-more"));
    const prism = screen.getByTestId("plugin-tool-loft.twisted_prism");
    fireEvent.click(prism);
    expect(onOpen).toHaveBeenCalledWith(TWISTED_PRISM);
  });

  it("shows every plugin on the row when no building generator is installed", () => {
    render(
      <BuildToolGroup
        catalog={[TWISTED_PRISM]}
        treeReady
        activeCommand={null}
        onOpen={vi.fn()}
      />,
    );
    expect(
      screen.getByTestId("plugin-tool-loft.twisted_prism"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("build-more")).toBeNull();
  });
});
