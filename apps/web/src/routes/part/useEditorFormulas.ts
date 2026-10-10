/**
 * Formulas in the part workspace's numeric fields (PART-PARAMETERS step 8,
 * docs/RESEARCH.md §20): the parameter table every `<ValueField>` reads, and
 * the open feature editor's formula session.
 *
 *  - The table is read with the part, at every `tree_version`, under the
 *    Parameters panel's own query key, so the two share one cache entry and an
 *    undo re-reads it. NOT on opening an editor: that made the click on a
 *    command the first authed request, so a session revoked elsewhere ended
 *    as the editor opened, before the user had done anything
 *    (auth.spec "when renewal truly fails"). Read ahead, the editor opens on
 *    the cached table and the command's own write meets the expiry.
 *  - The session is keyed by the open editor (`extrude:<id>`, `extrude:new`)
 *    and seeded with the feature's stored `expressions`; it carries the
 *    feature's `input_error`, so a sick feature's editor opens with the reason
 *    on the field it names. It is cleared when the editor closes.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { fetchPartParameters } from "../../api/parameters";
import type { FeatureResponse } from "../../api/parts";
import {
  describeInputError,
  enterFormulaSession,
  type FormulaSession,
  INPUT_ERROR_CODES,
  inputErrorPointer,
  inputErrorSentence,
  useFormulaSessionStore,
  useParameterScopeStore,
} from "../../features/fieldFormulas";
import type { OpenEditor } from "./openEditor";
import type { PartDocument } from "./usePartDocument";

type EditorFormulasParams = Pick<
  PartDocument,
  "partId" | "treeVersion" | "evaluation"
> & {
  editor: OpenEditor | null;
  features: readonly FeatureResponse[];
};

const NO_FORMULAS: Readonly<Record<string, string>> = {};

/** `parameter 'Q' not found.` → `Parameter 'Q' not found.` */
function capitalised(sentence: string): string {
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

export function useEditorFormulas({
  partId,
  treeVersion,
  evaluation,
  editor,
  features,
}: EditorFormulasParams) {
  const query = useQuery({
    queryKey: ["part-parameters", partId, treeVersion],
    queryFn: () => fetchPartParameters(partId),
    enabled: treeVersion !== undefined,
    staleTime: Infinity,
    // A sketch saves (and moves `tree_version`) as it is edited: keep this
    // part's last table on screen while the next one loads, never another
    // part's.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === partId
        ? keepPreviousData(previous)
        : undefined,
  });
  const setParameters = useParameterScopeStore((s) => s.setParameters);
  const rows = query.data?.parameters;
  useEffect(() => {
    setParameters(
      rows === undefined
        ? null
        : rows.map((row) => ({
            name: row.name,
            value: row.value,
            unit: row.unit,
          })),
    );
  }, [rows, setParameters]);
  // Leaving the workspace leaves no table behind for the next part.
  useEffect(() => () => setParameters(null), [setParameters]);

  const featureId = editor?.featureId;
  const key = editor === null ? null : `${editor.kind}:${featureId ?? "new"}`;
  const stored =
    featureId === undefined
      ? undefined
      : features.find((feature) => feature.id === featureId);
  const seed = stored?.feature.expressions ?? NO_FORMULAS;
  const result =
    featureId === undefined
      ? undefined
      : evaluation.data?.features.find((f) => f.feature_id === featureId);
  const inputErrorMessage =
    result?.status === "error" &&
    result.error != null &&
    INPUT_ERROR_CODES.has(result.error.code)
      ? result.error.message
      : null;

  const formulaSession = useMemo<FormulaSession | null>(
    () =>
      key === null
        ? null
        : {
            key,
            seed,
            inputError:
              inputErrorMessage === null
                ? null
                : {
                    pointer: inputErrorPointer(inputErrorMessage),
                    message: capitalised(inputErrorSentence(inputErrorMessage)),
                  },
          },
    [key, seed, inputErrorMessage],
  );

  // Another editor (or none): the last one's formulas and refusals go, and
  // this one's survive whatever its fields wrote first (`enterFormulaSession`;
  // pinned by `useEditorFormulas.test.tsx`).
  useEffect(() => {
    enterFormulaSession(key);
  }, [key]);

  // The input_error the editor's footer carries when no field on screen
  // names it (a pointer the form does not show, or none at all).
  const pointer =
    inputErrorMessage === null ? null : inputErrorPointer(inputErrorMessage);
  const fieldShowsIt = useFormulaSessionStore(
    (s) => pointer !== null && (s.mounted[pointer] ?? 0) > 0,
  );
  const editorInputError =
    inputErrorMessage === null || fieldShowsIt
      ? null
      : describeInputError(inputErrorMessage);

  return { formulaSession, editorInputError };
}

export type EditorFormulas = ReturnType<typeof useEditorFormulas>;
