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
  type DrawingResponse,
  DrawingNameTakenError,
  createDrawing,
  deleteDrawing,
  fetchDrawings,
} from "../api/drawings";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { WorkspaceNav } from "../components/WorkspaceNav";
import { formatDate } from "../lib/format";
import { validatePartName } from "../lib/partName";

/**
 * The drawings register — the third sibling of the parts / assemblies homes.
 * Same drawing-flat-file drawer: drawings filed oldest-first by sheet number,
 * each a title and its dates. Opening one enters the drawing editor (an
 * engineering sheet + the standard views). The register is the hero; the
 * create line scribes a new drawing.
 */
export function DrawingsPage() {
  const drawings = useQuery({
    queryKey: ["drawings"],
    queryFn: () => fetchDrawings(),
    staleTime: 30_000,
  });

  const list = drawings.data ?? [];
  const empty = drawings.isSuccess && list.length === 0;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Drawings</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12">
          <WorkspaceNav active="drawings" />
          <section
            className="mt-4 border border-hairline bg-anvil text-mist"
            data-testid="drawings-register"
          >
            <header className="flex items-baseline gap-3 border-b border-hairline px-3 py-3">
              <h2 className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
                Drawing register
              </h2>
              <span className="grow" />
              <RegisterCount
                loading={drawings.isLoading}
                error={drawings.isError}
                count={list.length}
              />
            </header>

            {drawings.isError ? (
              <p
                role="alert"
                data-testid="drawings-error"
                className="px-3 py-6 font-body text-sm text-flag"
              >
                {drawings.error instanceof Error
                  ? drawings.error.message
                  : "Your drawings could not be loaded."}
              </p>
            ) : drawings.isLoading ? (
              <p
                role="status"
                data-testid="drawings-loading"
                className="px-3 py-6 font-data text-xs text-gauge"
              >
                Loading drawings…
              </p>
            ) : empty ? (
              <EmptyRegister />
            ) : (
              <>
                <CreateLine />
                <DrawingsTable drawings={list} />
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
  const label = loading ? "—" : count === 1 ? "1 drawing" : `${count} drawings`;
  return (
    <span
      className="font-data text-xs tabular-nums text-gauge"
      data-testid="drawings-count"
    >
      {label}
    </span>
  );
}

function DrawingsTable({ drawings }: { drawings: DrawingResponse[] }) {
  return (
    <table className="w-full border-collapse" data-testid="drawings-table">
      <caption className="sr-only">
        Your drawings, oldest first. Open one to lay out its views, or delete
        it.
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
        {drawings.map((drawing, index) => (
          <DrawingRow key={drawing.id} drawing={drawing} index={index + 1} />
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

function DrawingRow({
  drawing,
  index,
}: {
  drawing: DrawingResponse;
  index: number;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const remove = useMutation({
    mutationFn: () => deleteDrawing(drawing.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["drawings"] }),
  });

  const sheetNo = String(index).padStart(3, "0");

  if (confirming) {
    return (
      <tr
        data-testid="drawing-row"
        data-drawing-id={drawing.id}
        data-confirming="true"
        className="border-b border-hairline last:border-b-0 bg-carbide"
      >
        <td className="px-3 py-2 text-right font-data text-xs tabular-nums text-gauge">
          {sheetNo}
        </td>
        <td colSpan={3} className="px-3 py-2">
          <span className="font-body text-sm text-mist">
            Delete <span className="font-data text-flag">{drawing.name}</span>?
            This cannot be undone.
          </span>
          {remove.isError ? (
            <span
              role="alert"
              className="ml-2 font-body text-xs text-flag"
              data-testid="drawing-delete-error"
            >
              {remove.error instanceof Error
                ? remove.error.message
                : "The drawing could not be deleted."}
            </span>
          ) : null}
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center justify-end gap-2">
            <Button
              onClick={() => setConfirming(false)}
              disabled={remove.isPending}
              data-testid="drawing-delete-cancel"
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              data-testid="drawing-delete-confirm"
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
      data-testid="drawing-row"
      data-drawing-id={drawing.id}
      className="group border-b border-hairline last:border-b-0 hover:bg-carbide focus-within:bg-carbide"
    >
      <td className="px-3 py-2 text-right font-data text-xs tabular-nums text-gauge">
        {sheetNo}
      </td>
      <td className="px-3 py-2">
        <Link
          to="/drawings/$drawingId"
          params={{ drawingId: drawing.id }}
          data-testid="drawing-open"
          className="rounded-sm font-body text-sm text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline"
        >
          {drawing.name}
        </Link>
      </td>
      <td className="hidden px-3 py-2 font-data text-xs tabular-nums text-gauge sm:table-cell">
        {formatDate(drawing.created_at)}
      </td>
      <td className="hidden px-3 py-2 font-data text-xs tabular-nums text-gauge md:table-cell">
        {formatDate(drawing.updated_at)}
      </td>
      <td className="px-3 py-2 text-right">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          data-testid="drawing-delete"
          aria-label={`Delete ${drawing.name}`}
          className="rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-flag focus-visible:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

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
      <CreateDrawingForm inputRef={inputRef} submitLabel="New drawing" />
    </div>
  );
}

function EmptyRegister() {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);
  return (
    <div className="px-4 py-10 sm:px-8 sm:py-14" data-testid="drawings-empty">
      <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
        Empty register
      </p>
      <h3 className="mt-2 font-body text-lg text-mist">
        No drawings filed yet.
      </h3>
      <p className="mt-1 max-w-md font-body text-sm text-gauge">
        Name your first drawing, then open it to reference a part and lay out
        the standard views on a sheet.
      </p>
      <div className="mt-5 max-w-md">
        <CreateDrawingForm
          inputRef={inputRef}
          submitLabel="Create first drawing"
        />
      </div>
    </div>
  );
}

function CreateDrawingForm({
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
    mutationFn: (value: string) => createDrawing(value),
    onSuccess: async () => {
      setName("");
      setFieldError(null);
      await queryClient.invalidateQueries({ queryKey: ["drawings"] });
      inputRef.current?.focus();
    },
    onError: (error) => {
      if (error instanceof DrawingNameTakenError) {
        setFieldError(error.message);
      } else {
        setFieldError(
          error instanceof Error
            ? error.message
            : "The drawing could not be created.",
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
      data-testid="create-drawing-form"
    >
      <TextField
        ref={inputRef}
        label="Drawing name"
        value={name}
        error={fieldError}
        placeholder="e.g. Bracket — sheet 1"
        autoComplete="off"
        disabled={create.isPending}
        data-testid="create-drawing-name"
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
        data-testid="create-drawing-submit"
        className="mb-[1px] shrink-0"
      >
        {create.isPending ? "Creating…" : submitLabel}
      </Button>
    </form>
  );
}
