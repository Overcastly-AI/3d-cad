/**
 * AssemblyClashPanel — does the interference report tell the truth?
 *
 * Two defects lived here, both invisible to the pure formatter tests: the panel
 * printed `mm³` regardless of the document unit (the last mm-only readout on an
 * inch page, after the assembly inspector was converted), and it drew a pair the
 * kernel could NOT measure (`unresolved: true`) exactly like a measured overlap
 * — so a user could not tell "no interference" from "we could not determine
 * this pair". Both are rendering questions, so they are pinned at this tier.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  ClashPair,
  InstanceResponse,
  InterferenceResult,
} from "../api/assemblies";
import { DocumentUnitProvider } from "../units/documentUnit";
import { AssemblyClashPanel } from "./AssemblyClashPanel";
import type { LengthUnit } from "@loft/design";

const IDS = ["i-a", "i-b", "i-c"] as const;

function instances(): InstanceResponse[] {
  return IDS.map((id, index) => ({
    id,
    assembly_id: "asm",
    ref_document_id: `p-${index}`,
    ref_document_kind: "part",
    ref_pinned_version: null,
    name: `Plate ${index + 1}`,
    order_index: index,
    grounded: index === 0,
    placement: {
      position: { x: 0, y: 0, z: 0 },
      orientation: { w: 1, x: 0, y: 0, z: 0 },
    },
    created_at: "2026-07-25T00:00:00Z",
    updated_at: "2026-07-25T00:00:00Z",
  }));
}

function pair(
  a: string,
  b: string,
  mm3: number,
  unresolved = false,
): ClashPair {
  return {
    instance_a: a,
    instance_b: b,
    overlap_volume_mm3: mm3,
    unresolved,
  };
}

function result(clashes: ClashPair[]): InterferenceResult {
  return {
    assembly_id: "asm",
    version: 1,
    status: "well_constrained",
    clashes,
  };
}

function renderPanel(
  clashes: ClashPair[] | null,
  unit: LengthUnit = "mm",
): void {
  render(
    <DocumentUnitProvider unit={unit}>
      <AssemblyClashPanel
        instances={instances()}
        result={clashes === null ? null : result(clashes)}
        busy={false}
        error={null}
      />
    </DocumentUnitProvider>,
  );
}

describe("AssemblyClashPanel — document unit", () => {
  it("reads a measured overlap in mm³ in a millimetre assembly", () => {
    renderPanel([pair("i-a", "i-b", 31391.38)]);
    const row = screen.getByTestId("clash-row");
    expect(within(row).getByTestId("clash-volume")).toHaveTextContent(
      "31,391.38",
    );
    expect(row).toHaveTextContent("mm³ overlap");
  });

  it("converts the overlap to in³ in an inch assembly", () => {
    renderPanel([pair("i-a", "i-b", 31391.38)], "in");
    const row = screen.getByTestId("clash-row");
    // The defect that shipped: 31,391.38 mm³ printed verbatim under `in`.
    expect(within(row).getByTestId("clash-volume")).toHaveTextContent("1.9156");
    expect(row).toHaveTextContent("in³ overlap");
    expect(row).not.toHaveTextContent("mm");
  });

  it("keeps a tiny genuine overlap off zero in an inch assembly", () => {
    renderPanel([pair("i-a", "i-b", 0.02)], "in");
    expect(screen.getByTestId("clash-volume")).toHaveTextContent("1.2e-6");
  });
});

describe("AssemblyClashPanel — unverified pairs", () => {
  it("marks an unmeasurable pair unverified with an upper-bound figure", () => {
    renderPanel([pair("i-a", "i-c", 5210.4, true)], "in");
    const row = screen.getByTestId("clash-row");
    expect(row).toHaveAttribute("data-unresolved", "true");
    expect(within(row).getByTestId("clash-unverified-badge")).toHaveTextContent(
      "Unverified",
    );
    // A bound, not a reading: parenthesised (reference figure) and captioned.
    // 5,210.4 mm³ / 25.4³ = 0.318 in³.
    expect(within(row).getByTestId("clash-volume")).toHaveTextContent(
      "(0.318)",
    );
    expect(row).toHaveTextContent("in³ at most");
  });

  it("explains in plain language what unverified means and what to do", () => {
    renderPanel([pair("i-a", "i-c", 5210.4, true)]);
    const note = screen.getByTestId("clash-unverified-note");
    expect(note).toHaveTextContent(/could not be computed/);
    expect(note).toHaveTextContent(/instead of calling it clear/);
    expect(note).toHaveTextContent(/upper bound, not a measurement/);
    expect(note).toHaveTextContent(/Inspect the pair in the viewport/);
  });

  it("never reports an unverified-only report as no interference", () => {
    renderPanel([pair("i-a", "i-c", 5210.4, true)]);
    expect(screen.queryByTestId("clash-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("clash-row")).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Interference · 1 unverified" }),
    ).toBeInTheDocument();
  });

  it("keeps a measured clash unstamped, first, and counted apart", () => {
    renderPanel([
      pair("i-a", "i-c", 5210.4, true),
      pair("i-a", "i-b", 31391.38),
    ]);
    const rows = screen.getAllByTestId("clash-row");
    expect(rows).toHaveLength(2);
    // Measured outranks unverified regardless of the kernel's report order.
    expect(rows[0]).toHaveAttribute("data-unresolved", "false");
    expect(rows[1]).toHaveAttribute("data-unresolved", "true");
    expect(
      within(rows[0] as HTMLElement).queryByTestId("clash-unverified-badge"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Interference · 1 · 1 unverified" }),
    ).toBeInTheDocument();
  });

  it("shows no unverified note when every pair was measured", () => {
    renderPanel([pair("i-a", "i-b", 31391.38)]);
    expect(
      screen.queryByTestId("clash-unverified-note"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("clash-unverified-badge"),
    ).not.toBeInTheDocument();
  });

  it("still says clear when the kernel measured everything and found nothing", () => {
    renderPanel([]);
    expect(screen.getByTestId("clash-empty")).toHaveTextContent(
      "No interferences found",
    );
  });

  it("invites the first run before any check", () => {
    renderPanel(null);
    expect(screen.getByTestId("clash-idle")).toHaveTextContent(
      "Run Check interference",
    );
  });
});
