/**
 * `usePrefetchIntent` — when the app speculates, and when it stops.
 *
 * Prefetch is invisible when it works, which makes it exactly the kind of code
 * that rots silently: a hook that stopped firing would show up as "the app got
 * slower again", months later, with nothing failing. So the wiring is pinned
 * here — including the half that costs a core rather than saving one, the
 * CANCEL.
 */
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PrefetchRequest } from "../api/prefetch";
import {
  prefetchTicket,
  usePrefetchIntent,
  type PrefetchIntent,
} from "./prefetch";

const { warmSpy, cancelSpy } = vi.hoisted(() => ({
  warmSpy: vi.fn(),
  cancelSpy: vi.fn(),
}));

vi.mock("../api/prefetch", () => ({
  prefetchPrefix: warmSpy,
  cancelPrefetch: cancelSpy,
}));

const PART = "00000000-0000-0000-0000-0000000000fa";
const FEATURE = "00000000-0000-0000-0000-0000000000a9";
const OTHER = "00000000-0000-0000-0000-0000000000b7";

const EDIT: PrefetchIntent = {
  partId: PART,
  featureId: FEATURE,
  kind: "feature_edit",
};

function Harness({
  intent,
  enabled = true,
}: {
  intent: PrefetchIntent | null;
  enabled?: boolean;
}) {
  usePrefetchIntent(intent, { delayMs: 5, enabled });
  return null;
}

function warmed(): PrefetchRequest[] {
  return warmSpy.mock.calls.map((call) => call[0] as PrefetchRequest);
}

function cancelled(): string[] {
  return cancelSpy.mock.calls.map((call) => call[0] as string);
}

/** A little longer than the harness's settle, so "never fired" is provable. */
function afterSettle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 25));
}

beforeEach(() => {
  warmSpy.mockReset().mockResolvedValue(true);
  cancelSpy.mockReset().mockResolvedValue(true);
});

describe("usePrefetchIntent", () => {
  it("warms the declared intent once it has settled", async () => {
    render(<Harness intent={EDIT} />);
    await waitFor(() => expect(warmed()).toHaveLength(1));
    expect(warmed()[0]).toEqual({
      ticket: prefetchTicket(EDIT),
      part_id: PART,
      feature_id: FEATURE,
      kind: "feature_edit",
    });
  });

  it("cancels when the intent goes away — the editor closing stops the work", async () => {
    const view = render(<Harness intent={EDIT} />);
    await waitFor(() => expect(warmed()).toHaveLength(1));
    view.rerender(<Harness intent={null} />);
    await waitFor(() => expect(cancelled()).toEqual([prefetchTicket(EDIT)]));
  });

  it("cancels on unmount, so navigating away does not leave a warm running", async () => {
    const view = render(<Harness intent={EDIT} />);
    await waitFor(() => expect(warmed()).toHaveLength(1));
    view.unmount();
    await waitFor(() => expect(cancelled()).toEqual([prefetchTicket(EDIT)]));
  });

  it("does not fire for an intent the user moved off before it settled", async () => {
    // A drag crossing twenty stops must not spend a core on the nineteen it
    // passed through: only the one it rests on is a declaration of intent.
    const view = render(<Harness intent={EDIT} />);
    view.rerender(<Harness intent={{ ...EDIT, featureId: OTHER }} />);
    await waitFor(() => expect(warmed()).toHaveLength(1));
    expect(warmed()[0]?.feature_id).toBe(OTHER);
    // Nothing to cancel for the abandoned one — it was never submitted.
    expect(cancelled()).toEqual([]);
  });

  it("re-declaring the SAME intent keeps one ticket, so the worker no-ops it", async () => {
    const view = render(<Harness intent={EDIT} />);
    await waitFor(() => expect(warmed()).toHaveLength(1));
    view.rerender(<Harness intent={{ ...EDIT }} />);
    await afterSettle();
    expect(warmed().map((request) => request.ticket)).toEqual([
      prefetchTicket(EDIT),
    ]);
    expect(cancelled()).toEqual([]);
  });

  it("moving to another feature supersedes the previous ticket", async () => {
    const view = render(<Harness intent={EDIT} />);
    await waitFor(() => expect(warmed()).toHaveLength(1));
    view.rerender(<Harness intent={{ ...EDIT, featureId: OTHER }} />);
    await waitFor(() => expect(warmed()).toHaveLength(2));
    expect(cancelled()).toEqual([prefetchTicket(EDIT)]);
    expect(warmed()[1]?.ticket).toBe(
      prefetchTicket({ ...EDIT, featureId: OTHER }),
    );
  });

  it("declares nothing while disabled", async () => {
    render(<Harness intent={EDIT} enabled={false} />);
    await afterSettle();
    expect(warmed()).toEqual([]);
  });

  it("gives each kind its own ticket, so the two triggers cannot collide", () => {
    expect(prefetchTicket(EDIT)).not.toBe(
      prefetchTicket({ ...EDIT, kind: "travel_stop" }),
    );
  });
});
