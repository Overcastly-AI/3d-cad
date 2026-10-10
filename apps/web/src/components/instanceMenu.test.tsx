import { describe, expect, it, vi } from "vitest";

import type { InstanceResponse } from "../api/assemblies";
import { copyBlocker } from "../assembly/useCopyComponent";
import { instanceMenuSections, moveBlocker } from "./instanceMenu";

const grounded = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  name: "Hole plate <1>",
  grounded: true,
} as InstanceResponse;

function itemsOf(instance: InstanceResponse, busy = false) {
  const actions = {
    toggleVisibility: vi.fn(),
    isolate: vi.fn(),
    showAll: vi.fn(),
    move: vi.fn(),
    copy: vi.fn(),
    toggleGrounded: vi.fn(),
    remove: vi.fn(),
  };
  const sections = instanceMenuSections(
    instance,
    {
      hidden: false,
      canIsolate: true,
      hiddenCount: 0,
      moveBlocker: moveBlocker(instance),
      copyBlocker: copyBlocker(instance, busy),
      busy,
    },
    actions,
  );
  const items = new Map(
    sections.flatMap((s) => s.items).map((item) => [item.key, item]),
  );
  return { items, actions, sections };
}

describe("instanceMenuSections", () => {
  it("refuses Move on a grounded part but offers Copy, right after Move", () => {
    const { items, actions, sections } = itemsOf(grounded);
    expect(sections[0]?.label).toBe("Hole plate <1>");
    expect(items.get("move")?.disabled).toBe(true);
    expect(items.get("move")?.disabledReason).toMatch(/Grounded/);
    const edit = sections[1]?.items.map((item) => item.key);
    expect(edit).toEqual(["move", "copy", "ground", "remove"]);
    const copy = items.get("copy");
    expect(copy?.disabled).toBe(false);
    expect(copy?.shortcut).toMatch(/^(Ctrl\+D|⌘D)$/);
    expect(copy?.["data-testid"]).toBe("instance-ctx-copy");
    copy?.onSelect?.();
    expect(actions.copy).toHaveBeenCalledOnce();
    expect(items.get("ground")?.label).toBe("Unground");
  });

  it("holds Copy, Ground and Remove while a write is in flight", () => {
    const { items } = itemsOf({ ...grounded, grounded: false }, true);
    expect(items.get("move")?.disabled).toBe(false);
    for (const key of ["copy", "ground", "remove"]) {
      expect(items.get(key)?.disabled).toBe(true);
      expect(items.get(key)?.disabledReason).toMatch(/Waiting/);
    }
  });
});
