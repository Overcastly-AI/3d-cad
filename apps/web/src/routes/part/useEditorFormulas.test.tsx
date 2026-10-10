/**
 * The formula session's lifetime across an editor switch (PART-PARAMETERS
 * step 8). React runs a child's effects BEFORE its parent's, so the fields of
 * a newly opened editor write the session (a formula typed, a gauge dropping
 * one) before the workspace's `useEditorFormulas` effect sees the new key.
 * That effect must keep what the new editor's fields wrote and drop only the
 * previous editor's, whatever order a refactor gives the two effects.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { type ReactNode, useEffect } from "react";
import { afterEach, describe, expect, it } from "vitest";

import {
  clearFormulaSession,
  sessionFormulas,
  setSessionFormula,
  useFormulaSessionStore,
} from "../../features/fieldFormulas";
import type { OpenEditor } from "./openEditor";
import { useEditorFormulas } from "./useEditorFormulas";
import type { PartDocument } from "./usePartDocument";

afterEach(() => {
  cleanup();
  clearFormulaSession();
});

const NO_EVALUATION = {
  data: undefined,
} as unknown as PartDocument["evaluation"];

function editor(kind: "extrude" | "revolve", featureId?: string): OpenEditor {
  return {
    kind,
    mode: featureId === undefined ? "create" : "edit",
    initial: {},
    ...(featureId === undefined ? {} : { featureId }),
  } as unknown as OpenEditor;
}

/** A field of the open editor that writes its formula as it mounts. */
function FieldWritingOnMount({
  sessionKey,
  pointer,
  formula,
}: {
  sessionKey: string;
  pointer: string;
  formula: string;
}) {
  useEffect(() => {
    setSessionFormula({ key: sessionKey, seed: {} }, pointer, formula);
  }, [sessionKey, pointer, formula]);
  return null;
}

/** The workspace: the hook in the PARENT, the editor's fields below it. */
function Workspace({
  open,
  children,
}: {
  open: OpenEditor | null;
  children?: ReactNode;
}) {
  useEditorFormulas({
    partId: "p-1",
    treeVersion: undefined,
    evaluation: NO_EVALUATION,
    editor: open,
    features: [],
  });
  return <>{children}</>;
}

function formulasOf(key: string): Readonly<Record<string, string>> {
  return sessionFormulas(useFormulaSessionStore.getState(), key, {});
}

describe("useEditorFormulas: the session across an editor switch", () => {
  it("keeps what the new editor's fields wrote before the hook's effect ran", () => {
    const client = new QueryClient();
    const view = render(
      <QueryClientProvider client={client}>
        <Workspace open={editor("extrude")}>
          <FieldWritingOnMount
            sessionKey="extrude:new"
            pointer="/distance_mm"
            formula="H/2"
          />
        </Workspace>
      </QueryClientProvider>,
    );
    expect(formulasOf("extrude:new")).toEqual({ "/distance_mm": "H/2" });

    // Straight to another editor, whose field writes as it mounts.
    act(() =>
      view.rerender(
        <QueryClientProvider client={client}>
          <Workspace open={editor("revolve", "f-2")}>
            <FieldWritingOnMount
              sessionKey="revolve:f-2"
              pointer="/angle_deg"
              formula="A*2"
            />
          </Workspace>
        </QueryClientProvider>,
      ),
    );
    expect(formulasOf("revolve:f-2")).toEqual({ "/angle_deg": "A*2" });
    // ...and the extrude's edit did not follow it.
    expect(formulasOf("extrude:new")).toEqual({});
  });

  it("drops the editor's formulas when it closes", () => {
    const client = new QueryClient();
    const view = render(
      <QueryClientProvider client={client}>
        <Workspace open={editor("extrude")}>
          <FieldWritingOnMount
            sessionKey="extrude:new"
            pointer="/distance_mm"
            formula="H/2"
          />
        </Workspace>
      </QueryClientProvider>,
    );
    act(() =>
      view.rerender(
        <QueryClientProvider client={client}>
          <Workspace open={null} />
        </QueryClientProvider>,
      ),
    );
    expect(useFormulaSessionStore.getState().key).toBeNull();
    expect(formulasOf("extrude:new")).toEqual({});
  });
});
