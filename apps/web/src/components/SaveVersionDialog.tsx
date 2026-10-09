import { Button, Kbd, TextField } from "@loft/design";
import { useCallback, useEffect, useRef, useState } from "react";

import { useModalLayer } from "../lib/modalGate";
import { containFocus, isSaveChord } from "./dialogKeys";

/** The wire's limits (loft_wire.versions): name 1..120, message ..2000. */
export const VERSION_NAME_MAX = 120;
export const VERSION_MESSAGE_MAX = 2000;

export interface SaveVersionDialogProps {
  /** The part being versioned, named in the header. */
  partName: string;
  /** Seeded into the name field, selected, so Enter alone saves it ("V3"). */
  defaultName: string;
  /** A save is in flight: the fields hold, the action says so. */
  pending: boolean;
  /** Why the last save was refused, in a sentence; null when it was not. */
  error: string | null;
  onSave: (input: { name: string; message: string }) => void;
  onCancel: () => void;
}

/**
 * SAVE VERSION: name the tree as it is now (Onshape "Create version", Fusion
 * "Save version with description"). A name, an optional description, and the
 * fact that matters: saving is not an edit, so undo is untouched.
 *
 * Modal through `lib/modalGate`, so Enter and Escape reach this dialog and
 * nothing behind it. Enter in either field submits (the form's own implicit
 * submission); Escape cancels.
 */
export function SaveVersionDialog({
  partName,
  defaultName,
  pending,
  error,
  onSave,
  onCancel,
}: SaveVersionDialogProps) {
  const panelRef = useRef<HTMLFormElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const returnFocusTo = useRef<Element | null>(null);
  const [name, setName] = useState(defaultName);
  const [message, setMessage] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  /** Typed in: a late-arriving default (the list loading) must not clobber it. */
  const touched = useRef(false);

  useEffect(() => {
    if (touched.current) return;
    setName(defaultName);
    requestAnimationFrame(() => {
      if (!touched.current && document.activeElement === nameRef.current) {
        nameRef.current?.select();
      }
    });
  }, [defaultName]);

  useEffect(() => {
    returnFocusTo.current = document.activeElement;
    nameRef.current?.focus();
    nameRef.current?.select();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement && target.isConnected) target.focus();
    };
  }, []);

  const onKeyDown = useCallback(
    (event: KeyboardEvent, insidePanel: boolean) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      // Ctrl+S again saves what is typed (and never opens "Save page").
      if (isSaveChord(event)) {
        event.preventDefault();
        panelRef.current?.requestSubmit();
        return;
      }
      containFocus(panelRef.current, event, insidePanel);
    },
    [onCancel],
  );
  useModalLayer("save version", panelRef, onKeyDown);

  const submit = () => {
    if (pending) return;
    const trimmed = name.trim();
    if (trimmed === "") {
      setNameError("Name the version.");
      nameRef.current?.focus();
      return;
    }
    setNameError(null);
    onSave({ name: trimmed, message: message.trim() });
  };

  return (
    <div
      data-testid="save-version-backdrop"
      onClick={onCancel}
      className="fixed inset-0 z-menu flex items-center justify-center bg-carbide/85 p-4"
    >
      <form
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="save-version-title"
        aria-describedby="save-version-note"
        tabIndex={-1}
        noValidate
        data-testid="save-version-dialog"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        className="w-full max-w-md border border-etch bg-anvil text-mist shadow-float outline-none"
      >
        <header className="flex items-baseline gap-x-4 border-b border-hairline bg-carbide px-4 py-2.5">
          <h2
            id="save-version-title"
            className="font-display text-2xs uppercase tracking-[0.2em] text-gauge"
          >
            Save version
          </h2>
          <span className="grow" />
          <span className="min-w-0 truncate font-data text-xs text-brass">
            {partName}
          </span>
        </header>
        <div className="flex flex-col gap-3 px-4 pt-3">
          <TextField
            ref={nameRef}
            label="Name"
            value={name}
            maxLength={VERSION_NAME_MAX}
            autoComplete="off"
            disabled={pending}
            error={nameError}
            data-testid="save-version-name"
            onChange={(event) => {
              touched.current = true;
              setName(event.target.value);
              if (nameError !== null) setNameError(null);
            }}
          />
          <TextField
            label="Description (optional)"
            value={message}
            maxLength={VERSION_MESSAGE_MAX}
            autoComplete="off"
            placeholder="What changed, and why"
            disabled={pending}
            data-testid="save-version-message"
            onChange={(event) => setMessage(event.target.value)}
          />
          <p id="save-version-note" className="font-body text-xs text-gauge">
            Keeps the feature tree as it is now. Saving is not an edit; your
            undo history is untouched.
          </p>
          {error !== null ? (
            <p
              role="alert"
              data-testid="save-version-error"
              className="border border-flag px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
        </div>
        <footer className="mt-4 flex items-center justify-end gap-2 border-t border-hairline px-4 py-2.5">
          <Button
            onClick={onCancel}
            data-testid="save-version-cancel"
            className="gap-2"
          >
            Cancel
            <Kbd aria-hidden="true">Esc</Kbd>
          </Button>
          <Button
            type="submit"
            variant="solid"
            disabled={pending}
            aria-busy={pending}
            data-testid="save-version-submit"
          >
            {pending ? "Saving…" : "Save version"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
