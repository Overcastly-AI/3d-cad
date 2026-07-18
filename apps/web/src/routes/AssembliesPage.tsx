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
  type AssemblyResponse,
  AssemblyNameTakenError,
  createAssembly,
  deleteAssembly,
  fetchAssemblies,
} from "../api/assemblies";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { WorkspaceNav } from "../components/WorkspaceNav";
import { formatDate } from "../lib/format";
import { validatePartName } from "../lib/partName";

/**
 * The assemblies register — the sibling of the parts home. Same drawing-flat-
 * file drawer: assemblies filed oldest-first, each a scribed sheet number, its
 * title, and its dates. Opening one enters the assembly workspace (instances +
 * mates + the multi-instance viewport). The register is the hero; the create
 * line scribes a new assembly sheet.
 */
export function AssembliesPage() {
  const assemblies = useQuery({
    queryKey: ["assemblies"],
    queryFn: () => fetchAssemblies(),
    staleTime: 30_000,
  });

  const list = assemblies.data ?? [];
  const empty = assemblies.isSuccess && list.length === 0;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Assemblies</Chip>
      </TopBar>
      <main className="relative min-h-0 grow overflow-y-auto bg-carbide">
        <SheetGrid />
        <div
          className="pointer-events-none absolute inset-3 border border-hairline"
          aria-hidden="true"
        />
        <div className="relative mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12">
          <WorkspaceNav active="assemblies" />
          <section
            className="mt-4 border border-hairline bg-anvil text-mist"
            data-testid="assemblies-register"
          >
            <header className="flex items-baseline gap-3 border-b border-hairline px-3 py-3">
              <h2 className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
                Assembly register
              </h2>
              <span className="grow" />
              <RegisterCount
                loading={assemblies.isLoading}
                error={assemblies.isError}
                count={list.length}
              />
            </header>

            {assemblies.isError ? (
              <p
                role="alert"
                data-testid="assemblies-error"
                className="px-3 py-6 font-body text-sm text-flag"
              >
                {assemblies.error instanceof Error
                  ? assemblies.error.message
                  : "Your assemblies could not be loaded."}
              </p>
            ) : assemblies.isLoading ? (
              <p
                role="status"
                data-testid="assemblies-loading"
                className="px-3 py-6 font-data text-xs text-gauge"
              >
                Loading assemblies…
              </p>
            ) : empty ? (
              <EmptyRegister />
            ) : (
              <>
                <CreateLine />
                <AssembliesTable assemblies={list} />
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
  const label = loading
    ? "—"
    : count === 1
      ? "1 assembly"
      : `${count} assemblies`;
  return (
    <span
      className="font-data text-xs tabular-nums text-gauge"
      data-testid="assemblies-count"
    >
      {label}
    </span>
  );
}

function AssembliesTable({ assemblies }: { assemblies: AssemblyResponse[] }) {
  return (
    <table className="w-full border-collapse" data-testid="assemblies-table">
      <caption className="sr-only">
        Your assemblies, oldest first. Open one to compose it, or delete it.
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
        {assemblies.map((assembly, index) => (
          <AssemblyRow
            key={assembly.id}
            assembly={assembly}
            index={index + 1}
          />
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

function AssemblyRow({
  assembly,
  index,
}: {
  assembly: AssemblyResponse;
  index: number;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const remove = useMutation({
    mutationFn: () => deleteAssembly(assembly.id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["assemblies"] }),
  });

  const sheetNo = String(index).padStart(3, "0");

  if (confirming) {
    return (
      <tr
        data-testid="assembly-row"
        data-assembly-id={assembly.id}
        data-confirming="true"
        className="border-b border-hairline last:border-b-0 bg-carbide"
      >
        <td className="px-3 py-2 text-right font-data text-xs tabular-nums text-gauge">
          {sheetNo}
        </td>
        <td colSpan={3} className="px-3 py-2">
          <span className="font-body text-sm text-mist">
            Delete <span className="font-data text-flag">{assembly.name}</span>?
            This cannot be undone.
          </span>
          {remove.isError ? (
            <span
              role="alert"
              className="ml-2 font-body text-xs text-flag"
              data-testid="assembly-delete-error"
            >
              {remove.error instanceof Error
                ? remove.error.message
                : "The assembly could not be deleted."}
            </span>
          ) : null}
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center justify-end gap-2">
            <Button
              onClick={() => setConfirming(false)}
              disabled={remove.isPending}
              data-testid="assembly-delete-cancel"
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              data-testid="assembly-delete-confirm"
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
      data-testid="assembly-row"
      data-assembly-id={assembly.id}
      className="group border-b border-hairline last:border-b-0 hover:bg-carbide focus-within:bg-carbide"
    >
      <td className="px-3 py-2 text-right font-data text-xs tabular-nums text-gauge">
        {sheetNo}
      </td>
      <td className="px-3 py-2">
        <Link
          to="/assemblies/$assemblyId"
          params={{ assemblyId: assembly.id }}
          data-testid="assembly-open"
          className="rounded-sm font-body text-sm text-mist underline-offset-4 outline-none hover:text-brass hover:underline focus-visible:text-brass focus-visible:underline"
        >
          {assembly.name}
        </Link>
      </td>
      <td className="hidden px-3 py-2 font-data text-xs tabular-nums text-gauge sm:table-cell">
        {formatDate(assembly.created_at)}
      </td>
      <td className="hidden px-3 py-2 font-data text-xs tabular-nums text-gauge md:table-cell">
        {formatDate(assembly.updated_at)}
      </td>
      <td className="px-3 py-2 text-right">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          data-testid="assembly-delete"
          aria-label={`Delete ${assembly.name}`}
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
      <CreateAssemblyForm inputRef={inputRef} submitLabel="New assembly" />
    </div>
  );
}

function EmptyRegister() {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);
  return (
    <div className="px-4 py-10 sm:px-8 sm:py-14" data-testid="assemblies-empty">
      <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
        Empty register
      </p>
      <h3 className="mt-2 font-body text-lg text-mist">
        No assemblies filed yet.
      </h3>
      <p className="mt-1 max-w-md font-body text-sm text-gauge">
        Name your first assembly, then add parts to it, ground one, and bolt the
        rest together with mates.
      </p>
      <div className="mt-5 max-w-md">
        <CreateAssemblyForm
          inputRef={inputRef}
          submitLabel="Create first assembly"
        />
      </div>
    </div>
  );
}

function CreateAssemblyForm({
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
    mutationFn: (value: string) => createAssembly(value),
    onSuccess: async () => {
      setName("");
      setFieldError(null);
      await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
      inputRef.current?.focus();
    },
    onError: (error) => {
      if (error instanceof AssemblyNameTakenError) {
        setFieldError(error.message);
      } else {
        setFieldError(
          error instanceof Error
            ? error.message
            : "The assembly could not be created.",
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
      data-testid="create-assembly-form"
    >
      <TextField
        ref={inputRef}
        label="Assembly name"
        value={name}
        error={fieldError}
        placeholder="e.g. Bolted plates"
        autoComplete="off"
        disabled={create.isPending}
        data-testid="create-assembly-name"
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
        data-testid="create-assembly-submit"
        className="mb-[1px] shrink-0"
      >
        {create.isPending ? "Creating…" : submitLabel}
      </Button>
    </form>
  );
}
