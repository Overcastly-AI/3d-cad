import { describe, expect, it } from "vitest";

import { viewRowsByProjection } from "./views";

const row = (id: string, projection: "front" | "top" | "section") => ({
  id,
  projection,
});

describe("viewRowsByProjection", () => {
  it("indexes one row per projection", () => {
    const byProjection = viewRowsByProjection([
      row("v-front", "front"),
      row("v-top", "top"),
    ]);
    expect(byProjection.get("front")?.id).toBe("v-front");
    expect(byProjection.get("top")?.id).toBe("v-top");
    expect(byProjection.size).toBe(2);
  });

  // Engineering audit H3: duplicates are refused server-side now
  // (`uq_views_sheet_projection`), but a legacy row must not make a drag PATCH
  // the LAST same-projection row — the composer anchors the first one.
  it("keeps the first row when a legacy sheet holds a duplicate projection", () => {
    const byProjection = viewRowsByProjection([
      row("section-a", "section"),
      row("section-b", "section"),
    ]);
    expect(byProjection.get("section")?.id).toBe("section-a");
    expect(byProjection.size).toBe(1);
  });

  it("is empty for a sheet with no views", () => {
    expect(viewRowsByProjection([]).size).toBe(0);
  });
});
