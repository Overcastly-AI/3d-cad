import { Button, Chip, TextField } from "@loft/design";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  createPart,
  deletePart,
  type PartResponse,
  PartNameTakenError,
  fetchParts,
} from "../api/parts";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { formatDate } from "../lib/format";
import { validatePartName } from "../lib/partName";

/**
 * The parts home — the landing surface after sign-in (frontend-design pass,
 * 2026-07-11). Not a card grid of thumbnails we cannot render yet: a DRAWING
 * REGISTER. Parts are filed oldest-first, each a scribed sheet number, its
 * title, and its dates — a machinist's flat-file drawer, honest about having
 * no previews. The register is the hero; the create line scribes a new sheet.
 * The bench (SheetGrid) carries over from the un-issued sign-in sheet.
 */
export function PartsPage() {
  const parts = useQuery({
    queryKey: ["parts"],
    queryFn: () => fetchParts(),
    staleTime: 30_000,
  });

  const list = parts.data ?? [];
  const empty = parts.isSuccess && list.length === 0;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Parts</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        {/* Sheet border, matching the sign-in un-issued sheet. */}
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12">
          <section
            className="border border-hairline bg-anvil text-mist"
            data-testid="parts-register"
          >
            <header className="flex items-baseline gap-3 border-b border-hairline px-3 py-3">
              <h2 className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
                Parts register
              </h2>
              <span className="grow" />
              <RegisterCount
                loading={parts.isLoading}
                error={parts.isError}
                count={list.length}
              />
            </header>

            {parts.isError ? (
              <p
                role="alert"
                data-testid="parts-error"
                className="px-3 py-6 font-body text-sm text-flag"
              >
                {parts.error instanceof Error
                  ? parts.error.message
                  : "Your parts could not be loaded."}
              </p>
            ) : parts.isLoading ? (
              <p
                role="status"
                data-testid="parts-loading"
                className="px-3 py-6 font-data text-xs text-gauge"
              >
                Loading parts…
              </p>
            ) : empty ? (
              <EmptyRegister />
            ) : (
              <>
                <CreateLine />
                <PartsTable parts={list} />
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function RegisterCount({
  loading,
  error,
  count,
}: {
  loading: boolean;
  error: boolean;
  count: number;
}) {
  if (error) return null;
  const label = loading ? "—" : count === 1 ? "1 part" : `${count} parts`;
  return (
    <span
      className="font-data text-xs tabular-nums text-gauge"
      data-testid="parts-count"
    >
      {label}
    </span>
  );
}

/** The register's rows — a real table so the columns carry meaning for AT. */
function PartsTable({ parts }: { parts: PartResponse[] }) {
  return (
    <table className="w-full border-collapse" data-testid="parts-table">
      <caption className="sr-only">
        Your parts, oldest first. Open a part to model it, or delete it.
      </caption>
      <thead>
        <tr className="border-b border-hairline">
          <Th className="w-12 text-right">№</Th>
          <Th>Name</Th>
          <Th className="hidden sm:table-cell">Created</Th>
          <Th className="hidden md:table-cell">Updated</Th>
          <th className="w-10">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {parts.map((part, index) => (
          <PartRow key={part.id} part={part} index={index + 1} />
        ))}
      </tbody>
    </table>
  );
}

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-3 py-2 text-left font-display text-2xs uppercase tracking-[0.16em] text-gauge ${
        className ?? ""
      }`}
    >
      {children}
    </th>
  );
}

/** One filed sheet: scribe number, title (opens the workspace), dates, delete. */
function PartRow({ part, index }: { part: PartResponse; index: number }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const remove = useMutation({
    mutationFn: () => deletePart(part.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["parts"] }),
  });

  const sheetNo = String(index).padStart(3, "0");

  if (confirming) {
    return (
      <tr
        data-testid="part-row"
        data-part-id={part.id}
        data-confirming="true"
        className="border-b border-hairline last:border-b-0 bg-carbide"
      >
        <td className="px-3 py-2 text-right font-data text-xs tabular-nums text-gauge">
          {sheetNo}
        </td>
        <td colSpan={3} className="px-3 py-2">
          <span className="font-body text-sm text-mist">
            Delete <span className="font-data text-flag">{part.name}</span>?
            This cannot be undone.
          </span>
          {remove.isError ? (
            <span
              role="alert"
              className="ml-2 font-body text-xs text-flag"
              data-testid="part-delete-error"
            >
              {remove.error instanceof Error
                ? remove.error.message
                : "The part could not be deleted."}
            </span>
          ) : null}
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center justify-end gap-2">
            <Button
              onClick={() => setConfirming(false)}
              disabled={remove.isPending}
              data-testid="part-delete-cancel"
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              data-testid="part-delete-confirm"
            >
              {remove.isPending ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr
      data-testid="part-row"
      data-part-id={part.id}
      className="group border-b border-hairline last:border-b-0 hover:bg-carbide focus-within:bg-carbide"
    >
      <td className="px-3 py-2 text-right font-data text-xs tabular-nums text-gauge">
        {sheetNo}
      </td>
      <td className="px-3 py-2">
        <Link
          to="/parts/$partId"
          params={{ partId: part.id }}
          data-testid="part-open"
          className="rounded-sm font-body text-sm text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline"
        >
          {part.name}
        </Link>
      </td>
      <td className="hidden px-3 py-2 font-data text-xs tabular-nums text-gauge sm:table-cell">
        {formatDate(part.created_at)}
      </td>
      <td className="hidden px-3 py-2 font-data text-xs tabular-nums text-gauge md:table-cell">
        {formatDate(part.updated_at)}
      </td>
      <td className="px-3 py-2 text-right">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          data-testid="part-delete"
          aria-label={`Delete ${part.name}`}
          className="rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-flag focus-visible:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

/**
 * The scribe line: a blank register entry waiting for a name. Keyboard-first —
 * pressing "n" anywhere on the page focuses it; Enter files the part. A
 * duplicate name (409) pins its message to the field.
 */
function CreateLine() {
  const inputRef = useRef<HTMLInputElement>(null);
  const focus = useCallback(() => inputRef.current?.focus(), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [focus]);

  return (
    <div className="border-b border-hairline px-3 py-3">
      <CreatePartForm inputRef={inputRef} submitLabel="New part" />
    </div>
  );
}

/** First-run: an invitation, not a blank drawer. */
function EmptyRegister() {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);
  return (
    <div className="px-4 py-10 sm:px-8 sm:py-14" data-testid="parts-empty">
      <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
        Empty register
      </p>
      <h3 className="mt-2 font-body text-lg text-mist">
        Nothing filed here yet.
      </h3>
      <p className="mt-1 max-w-md font-body text-sm text-gauge">
        Name your first part to open a fresh sheet — sketch it, extrude it, and
        it will be filed here for next time.
      </p>
      <div className="mt-5 max-w-md">
        <CreatePartForm inputRef={inputRef} submitLabel="Create first part" />
      </div>
    </div>
  );
}

/** The shared create control — a name cell + the one brass action. */
function CreatePartForm({
  inputRef,
  submitLabel,
}: {
  inputRef: React.RefObject<HTMLInputElement | null>;
  submitLabel: string;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (value: string) => createPart(value),
    onSuccess: async () => {
      setName("");
      setFieldError(null);
      await queryClient.invalidateQueries({ queryKey: ["parts"] });
      inputRef.current?.focus();
    },
    onError: (error) => {
      if (error instanceof PartNameTakenError) {
        setFieldError(error.message);
      } else {
        setFieldError(
          error instanceof Error
            ? error.message
            : "The part could not be created.",
        );
      }
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const invalid = validatePartName(name);
    if (invalid !== null) {
      setFieldError(invalid);
      return;
    }
    create.mutate(name.trim());
  };

  return (
    <form
      className="flex items-end gap-3"
      onSubmit={submit}
      noValidate
      data-testid="create-part-form"
    >
      <TextField
        ref={inputRef}
        label="Part name"
        value={name}
        error={fieldError}
        placeholder="e.g. Bracket plate"
        autoComplete="off"
        disabled={create.isPending}
        data-testid="create-part-name"
        className="grow"
        onChange={(event) => {
          setName(event.currentTarget.value);
          if (fieldError !== null) setFieldError(null);
        }}
      />
      <Button
        type="submit"
        variant="solid"
        disabled={create.isPending}
        data-testid="create-part-submit"
        className="mb-[1px] shrink-0"
      >
        {create.isPending ? "Creating…" : submitLabel}
      </Button>
    </form>
  );
}
