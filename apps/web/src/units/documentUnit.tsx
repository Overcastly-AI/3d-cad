/**
 * The one conversion seam for document length units (docs/design/units.md §U2).
 *
 * A single React context carries the loaded document's `length_unit` down to
 * every dimension cell and readout. The document editors (part + assembly) wrap
 * their chrome in {@link DocumentUnitProvider} fed by the loaded document; every
 * length input reads {@link useDocumentLengthUnit} to (a) label its cell with the
 * unit and (b) parse/format its value at the mm boundary. Nothing below this
 * seam knows about units — the value that crosses the wire is always canonical
 * mm.
 *
 * Default is `"mm"` so a component rendered outside a provider (a test harness,
 * a legacy surface) behaves exactly as before this slice — canonical mm in, mm
 * out — which keeps the change backward compatible.
 */
import type { LengthUnit } from "@loft/design";
import { createContext, type ReactNode, useContext } from "react";

const DocumentLengthUnitContext = createContext<LengthUnit>("mm");

export interface DocumentUnitProviderProps {
  /** The loaded document's display unit; `undefined`/`null` falls back to mm. */
  unit: LengthUnit | null | undefined;
  children: ReactNode;
}

/** Provide the loaded document's length unit to every dimension cell below. */
export function DocumentUnitProvider({
  unit,
  children,
}: DocumentUnitProviderProps) {
  return (
    <DocumentLengthUnitContext.Provider value={unit ?? "mm"}>
      {children}
    </DocumentLengthUnitContext.Provider>
  );
}

/** The current document's length unit (mm outside a provider). */
export function useDocumentLengthUnit(): LengthUnit {
  return useContext(DocumentLengthUnitContext);
}
