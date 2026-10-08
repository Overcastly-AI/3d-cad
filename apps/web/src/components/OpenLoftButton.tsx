import { Button } from "@loft/design";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useRef, useState } from "react";

import { importLoftFile } from "../api/importLoft";
import { precheckLoftFile, useLoftImportNotice } from "../features/loftImport";

/**
 * OPEN .LOFT — the parts register's File > Open (docs/FILE-FORMAT.md).
 *
 * It lives in the register's top bar, not the part workspace's Create band:
 * an import makes a NEW part, which is a register verb, and the band is full
 * at the 1280x800 floor — one more button there moved the viewport's camera
 * fit and broke two gauge drags (CRAFT-10, CRAFT-12). On success the new part
 * opens and the server's warnings show on it (`LoftImportNotice`); a refusal
 * is the server's own message, beside the button.
 */
export function OpenLoftButton() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const open = async (file: File) => {
    setError(null);
    const preError = precheckLoftFile(file);
    if (preError !== null) {
      setError(preError);
      return;
    }
    setBusy(true);
    try {
      const response = await importLoftFile(await file.arrayBuffer());
      useLoftImportNotice
        .getState()
        .show(response.part.id, response.warnings ?? []);
      await queryClient.invalidateQueries({ queryKey: ["parts"] });
      await navigate({
        to: "/parts/$partId",
        params: { partId: response.part.id },
      });
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The .loft file could not be imported.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".loft"
        data-testid="import-loft-input"
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file !== undefined) void open(file);
        }}
      />
      <Button
        variant="ghost"
        data-testid="import-loft-button"
        aria-label="Open .loft — import a Loft file as a new part"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? "Opening…" : "Open .loft"}
      </Button>
      {error !== null ? (
        <span
          role="alert"
          data-testid="import-loft-error"
          className="max-w-sm truncate font-body text-xs text-flag"
          title={error}
        >
          {error}
        </span>
      ) : null}
    </>
  );
}
